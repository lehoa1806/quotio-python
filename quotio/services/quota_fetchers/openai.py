"""OpenAI/Codex quota fetcher."""

import json
from pathlib import Path
from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class OpenAIQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from OpenAI/Codex API."""

    USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_dir = Path.home() / ".cli-proxy-api"

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch OpenAI quota for an account."""
        auth_file = self._find_auth_file(account_key)
        if not auth_file:
            return None

        access_token = auth_file.get("access_token")
        account_id = auth_file.get("account_id") or self._extract_account_id(auth_file)

        if not access_token:
            return None

        try:
            return await self._fetch_from_api(access_token, account_id)
        except Exception:
            return None

    def _find_auth_file(self, account_key: str) -> Optional[dict]:
        """Find auth file for account."""
        if not self.auth_dir.exists():
            return None

        for file_path in self.auth_dir.glob("*codex*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    email = data.get("email") or data.get("account") or file_path.stem
                    if email == account_key or file_path.stem == account_key:
                        return data
            except Exception:
                continue

        return None

    def _extract_account_id(self, auth_file: dict) -> Optional[str]:
        """Extract account ID from auth file."""
        # Try direct field
        if "account_id" in auth_file:
            return auth_file["account_id"]

        # Try from id_token JWT
        id_token = auth_file.get("id_token")
        if id_token:
            return self._decode_account_id_from_jwt(id_token)

        return None

    def _decode_account_id_from_jwt(self, token: str) -> Optional[str]:
        """Decode account ID from JWT token."""
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None

            # Decode payload
            import base64
            payload = parts[1]
            # Add padding if needed
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding

            payload = payload.replace("-", "+").replace("_", "/")
            decoded = base64.b64decode(payload)
            data = json.loads(decoded)

            # Extract account ID
            auth_info = data.get("https://api.openai.com/auth", {})
            return auth_info.get("chatgpt_account_id")
        except Exception:
            return None

    async def _fetch_from_api(self, access_token: str, account_id: Optional[str] = None) -> Optional[ProviderQuotaData]:
        """Fetch quota from ChatGPT usage API (matches original implementation)."""
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
                        print(f"[OpenAIQuotaFetcher] API returned status {response.status}")
                        # Try to get error details
                        try:
                            error_data = await response.json()
                            print(f"[OpenAIQuotaFetcher] Error response: {error_data}")
                        except Exception:
                            pass
                        return None

                    data = await response.json()
                    print(f"[OpenAIQuotaFetcher] API response keys: {list(data.keys())}")
                    quota_data = self._parse_quota_response(data)
                    if quota_data:
                        print(f"[OpenAIQuotaFetcher] Parsed {len(quota_data.models)} model(s) from response")
                    else:
                        print(f"[OpenAIQuotaFetcher] No quota data parsed from response")
                    return quota_data
        except Exception as e:
            print(f"[OpenAIQuotaFetcher] Error fetching quota: {e}")
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

        # Also check for code_review_rate_limit (if present)
        code_review_rate_limit = data.get("code_review_rate_limit", {})
        if code_review_rate_limit:
            code_review_primary = code_review_rate_limit.get("primary_window", {})
            if code_review_primary:
                used_percent = code_review_primary.get("used_percent", 0)
                models.append(QuotaModel(
                    name="codex-code-review",
                    percentage=max(0, 100 - used_percent),
                    used=None,
                    limit=None,
                    remaining=None,
                ))

        # Check for credits info (if present)
        credits = data.get("credits", {})
        if credits:
            has_credits = credits.get("has_credits", False)
            unlimited = credits.get("unlimited", False)
            balance = credits.get("balance")

            if has_credits or unlimited:
                models.append(QuotaModel(
                    name="codex-credits",
                    percentage=100 if unlimited else None,
                    used=None,
                    limit=None,
                    remaining=balance,
                ))

        return ProviderQuotaData(
            models=models,
            plan_type=plan_type,
            account_email=None,
            account_name=None,
            last_updated=None,
        )

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all OpenAI quotas."""
        results = {}
        processed_accounts = set()

        # First, try to get auth files from API client (proxy) to know which files exist
        auth_file_names = set()
        if self.api_client:
            try:
                auth_files = await self.api_client.fetch_auth_files()
                print(f"[OpenAIQuotaFetcher] Got {len(auth_files)} auth files from API client")
                # Filter for codex files
                for auth_file in auth_files:
                    provider = auth_file.provider.lower() if auth_file.provider else ""
                    if 'codex' in provider:
                        # Get the filename from the auth file
                        file_name = auth_file.name
                        if file_name:
                            auth_file_names.add(file_name)
                            print(f"[OpenAIQuotaFetcher] Found codex auth file: {file_name}")
            except Exception as e:
                print(f"[OpenAIQuotaFetcher] Error fetching auth files from API: {e}")

        # Check local filesystem for codex auth files
        local_files = []
        if self.auth_dir.exists():
            local_files = list(self.auth_dir.glob("*codex*.json"))
            print(f"[OpenAIQuotaFetcher] Found {len(local_files)} local codex auth files")

        # Process local files (they contain the actual tokens)
        for file_path in local_files:
            try:
                # If we have auth file names from API, only process matching files
                if auth_file_names and file_path.name not in auth_file_names:
                    # Still check if it's a codex file
                    if 'codex' not in file_path.name.lower():
                        continue

                with open(file_path, "r") as f:
                    data = json.load(f)
                    email = data.get("email") or data.get("account") or file_path.stem

                    if email in processed_accounts:
                        continue
                    processed_accounts.add(email)

                    access_token = data.get("access_token")
                    if not access_token:
                        print(f"[OpenAIQuotaFetcher] No access token in {file_path.name}")
                        continue

                    account_id = data.get("account_id") or self._extract_account_id(data)
                    print(f"[OpenAIQuotaFetcher] Fetching quota for {email} (from {file_path.name})...")
                    quota = await self._fetch_from_api(access_token, account_id)
                    if quota:
                        results[email] = quota
                        print(f"[OpenAIQuotaFetcher] ✓ Successfully fetched quota for {email}: {len(quota.models)} model(s)")
                    else:
                        print(f"[OpenAIQuotaFetcher] ✗ No quota data returned for {email}")
            except Exception as e:
                print(f"[OpenAIQuotaFetcher] Error processing file {file_path}: {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"[OpenAIQuotaFetcher] Total Codex quotas fetched: {len(results)}")
        if results:
            for email, quota_data in results.items():
                print(f"[OpenAIQuotaFetcher]   - {email}: {len(quota_data.models)} model(s)")
        return results
