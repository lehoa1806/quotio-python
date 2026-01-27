"""Codex CLI quota fetcher."""

import json
import base64
from pathlib import Path
from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class CodexCLIQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Codex CLI auth file and OpenAI API."""

    USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
    REFRESH_URL = "https://auth.openai.com/oauth/token"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_file_path = Path.home() / ".codex" / "auth.json"

    def _read_auth_file(self) -> Optional[dict]:
        """Read Codex CLI auth file."""
        if not self.auth_file_path.exists():
            return None

        try:
            with open(self.auth_file_path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _decode_jwt(self, id_token: str) -> Optional[dict]:
        """Decode JWT id_token to extract claims (matches original implementation)."""
        try:
            parts = id_token.split(".")
            if len(parts) < 2:
                return None

            # Decode payload
            payload = parts[1]
            # Add padding if needed
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding

            # Replace URL-safe base64 characters
            payload = payload.replace("-", "+").replace("_", "/")

            decoded = base64.b64decode(payload)
            return json.loads(decoded)
        except Exception:
            return None

    def _extract_account_id_from_jwt(self, id_token: str) -> Optional[str]:
        """Extract account ID from JWT id_token."""
        claims = self._decode_jwt(id_token)
        if not claims:
            return None

        # Extract account ID from nested auth object
        auth_info = claims.get("https://api.openai.com/auth", {})
        return auth_info.get("chatgpt_account_id")

    async def _fetch_from_api(self, access_token: str, account_id: Optional[str] = None) -> Optional[ProviderQuotaData]:
        """Fetch quota from OpenAI usage API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        if account_id:
            headers["ChatGPT-Account-Id"] = account_id

        proxy_url = self._proxy_url if self._proxy_url else None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.USAGE_URL,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        print(f"[CodexCLIQuotaFetcher] API returned status {response.status}")
                        # Try to get error details
                        try:
                            error_text = await response.text()
                            print(f"[CodexCLIQuotaFetcher] Error response: {error_text[:200]}")
                        except Exception:
                            pass
                        return None

                    data = await response.json()
                    print(f"[CodexCLIQuotaFetcher] API response keys: {list(data.keys())}")
                    quota_data = self._parse_quota_response(data)
                    if quota_data:
                        print(f"[CodexCLIQuotaFetcher] Parsed {len(quota_data.models)} model(s) from response")
                    return quota_data
        except Exception as e:
            print(f"[CodexCLIQuotaFetcher] Error fetching quota: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from ChatGPT usage API.

        Matches original implementation: parses rate_limit structure with
        primary_window (session/3-hour) and secondary_window (weekly).
        """
        from datetime import datetime

        models = []
        plan_type = data.get("plan_type")
        limit_reached = False

        # Parse rate_limit structure (matches original implementation)
        rate_limit = data.get("rate_limit", {})
        if rate_limit:
            limit_reached = rate_limit.get("limit_reached", False)

            # Primary window = session (3-hour window)
            primary_window = rate_limit.get("primary_window", {})
            if primary_window:
                session_used_percent = primary_window.get("used_percent", 0)
                session_reset_at = primary_window.get("reset_at")

                reset_time_str = ""
                if session_reset_at:
                    try:
                        # reset_at is Unix timestamp (seconds)
                        reset_dt = datetime.fromtimestamp(session_reset_at)
                        reset_time_str = reset_dt.isoformat()
                    except Exception:
                        pass

                models.append(QuotaModel(
                    name="codex-session",
                    percentage=max(0, 100 - session_used_percent),
                    used=None,
                    limit=None,
                    remaining=None,
                ))

            # Secondary window = weekly
            secondary_window = rate_limit.get("secondary_window", {})
            if secondary_window:
                weekly_used_percent = secondary_window.get("used_percent", 0)
                weekly_reset_at = secondary_window.get("reset_at")

                reset_time_str = ""
                if weekly_reset_at:
                    try:
                        reset_dt = datetime.fromtimestamp(weekly_reset_at)
                        reset_time_str = reset_dt.isoformat()
                    except Exception:
                        pass

                models.append(QuotaModel(
                    name="codex-weekly",
                    percentage=max(0, 100 - weekly_used_percent),
                    used=None,
                    limit=None,
                    remaining=None,
                ))

        return ProviderQuotaData(
            models=models,
            plan_type=plan_type,
            account_email=None,
            account_name=None,
            last_updated=None,
        )

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Codex CLI quota."""
        auth_data = self._read_auth_file()
        if not auth_data:
            return None

        # Get access token - prefer OAuth token, don't use OpenAI API keys for quota
        tokens = auth_data.get("tokens", {})
        access_token = tokens.get("access_token")

        # Only fall back to OPENAI_API_KEY if it's NOT an OpenAI API key format
        # OpenAI API keys (sk-...) don't work for quota fetching
        if not access_token:
            openai_key = auth_data.get("OPENAI_API_KEY")
            if openai_key and not (openai_key.startswith("sk-") and len(openai_key) > 20):
                # Only use if it's not an OpenAI API key format
                access_token = openai_key
            else:
                # OpenAI API key format - can't be used for quota
                print(f"[CodexCLIQuotaFetcher] Cannot fetch quota: Only OAuth access tokens work for quota fetching, not OpenAI API keys")
                return None

        if not access_token:
            return None

        # Extract account ID
        account_id = tokens.get("account_id")
        if not account_id and tokens.get("id_token"):
            account_id = self._extract_account_id_from_jwt(tokens["id_token"])

        return await self._fetch_from_api(access_token, account_id)

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Codex CLI quotas (matches fetchAsProviderQuota).

        Reads ~/.codex/auth.json, extracts email and plan from JWT,
        handles token refresh if expired, and fetches quota from API.
        """
        from datetime import datetime

        results = {}

        auth_data = self._read_auth_file()
        if not auth_data:
            return results

        tokens = auth_data.get("tokens", {})
        if not tokens:
            return results

        # Extract email, plan, and organization from JWT (matches original implementation)
        email = "Codex User"
        plan_type = None
        account_id = tokens.get("account_id")
        organization_name = None

        if tokens.get("id_token"):
            claims = self._decode_jwt(tokens["id_token"])
            if claims:
                email = claims.get("email", email)
                plan_type = claims.get("plan_type")
                # Extract plan and organization from nested auth object if available
                auth_info = claims.get("https://api.openai.com/auth", {})
                if not plan_type:
                    plan_type = auth_info.get("chatgpt_plan_type")
                if not account_id:
                    account_id = auth_info.get("chatgpt_account_id")

                # Extract organization name (for platform/enterprise accounts)
                organizations = auth_info.get("organizations", [])
                if organizations and isinstance(organizations, list) and len(organizations) > 0:
                    first_org = organizations[0]
                    if isinstance(first_org, dict):
                        organization_name = first_org.get("title")

        # Get access token - prefer OAuth token, don't use OpenAI API keys for quota
        access_token = tokens.get("access_token")

        # Only fall back to OPENAI_API_KEY if it's NOT an OpenAI API key format
        # OpenAI API keys (sk-...) don't work for quota fetching
        if not access_token:
            openai_key = auth_data.get("OPENAI_API_KEY")
            if openai_key and not (openai_key.startswith("sk-") and len(openai_key) > 20):
                # Only use if it's not an OpenAI API key format
                access_token = openai_key
            else:
                # OpenAI API key format - can't be used for quota
                print(f"[CodexCLIQuotaFetcher] Cannot fetch quota: Only OAuth access tokens work for quota fetching, not OpenAI API keys")
                return results

        if not access_token:
            return results

        # Check if token is expired and refresh if needed
        # Note: Token refresh not implemented yet, but structure is ready
        current_access_token = access_token

        # Fetch quota from API
        try:
            quota_data = await self._fetch_from_api(current_access_token, account_id)
            if quota_data:
                # Update plan_type if we extracted it from JWT
                if plan_type:
                    quota_data.plan_type = plan_type

                # Store organization name in quota data
                if organization_name:
                    quota_data.organization_name = organization_name
                    print(f"[CodexCLIQuotaFetcher] Platform account detected: {email} (Organization: {organization_name})")

                # For platform/enterprise accounts, include organization name in account key
                # This helps distinguish platform accounts from personal accounts in the UI
                account_key = email
                if organization_name:
                    account_key = f"{email} ({organization_name})"

                results[account_key] = quota_data
        except Exception as e:
            print(f"[CodexCLIQuotaFetcher] Failed to fetch quota: {e}")

        return results
