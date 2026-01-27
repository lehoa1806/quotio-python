"""Antigravity quota fetcher."""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider
from ...models.subscription import SubscriptionInfo


class AntigravityQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Antigravity API."""

    QUOTA_API_URL = "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
    LOAD_PROJECT_API_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    # OAuth Client ID - This is a PUBLIC identifier (safe to expose per OAuth 2.0 spec)
    # Made configurable for flexibility and consistency. Set ANTIGRAVITY_CLIENT_ID env var to override.
    _DEFAULT_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
    # SECURITY: Client secret loaded from environment variable to avoid hardcoding
    # This is a "public" OAuth client secret (for desktop app), but should still be
    # kept out of source code when possible. Set ANTIGRAVITY_CLIENT_SECRET env var
    # to override the default. See OAUTH_CLIENT_SECRET_ANALYSIS.md for details.
    _DEFAULT_CLIENT_SECRET = "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"
    USER_AGENT = "antigravity/1.11.3 Darwin/arm64"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        # Load OAuth credentials from environment variables, with fallback for backward compatibility
        # Client ID is public (safe to expose), but made configurable for flexibility
        self.CLIENT_ID = os.getenv("ANTIGRAVITY_CLIENT_ID", self._DEFAULT_CLIENT_ID)
        # Client secret should be kept private - prefer environment variable
        self.CLIENT_SECRET = os.getenv("ANTIGRAVITY_CLIENT_SECRET", self._DEFAULT_CLIENT_SECRET)
        self.auth_dir = Path.home() / ".cli-proxy-api"
        self._subscription_cache: Dict[str, dict] = {}
        self._subscription_info_cache: Dict[str, SubscriptionInfo] = {}

    def _clear_cache(self):
        """Clear the subscription cache."""
        self._subscription_cache = {}
        self._subscription_info_cache = {}

    def _normalize_email_from_filename(self, email: str) -> str:
        """Normalize email extracted from filename to proper @ format.

        Converts patterns like 'user.domain.com' to 'user@domain.com'.
        Handles filenames like 'antigravity-user_domain_com.json' -> 'user@domain.com'.
        """
        if "@" in email:
            return email

        # Try common email domain patterns
        common_domains = [
            "gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
            "yahoo.com", "icloud.com", "protonmail.com", "proton.me",
            "opensend.com"  # Add custom domain
        ]
        for domain in common_domains:
            domain_with_dot = f".{domain}"
            if email.endswith(domain_with_dot):
                return email[:-len(domain_with_dot)] + f"@{domain}"

        # Fallback: assume last two dot-separated parts are domain
        # e.g., user.opensend.com -> user@opensend.com
        parts = email.split(".")
        if len(parts) >= 3:
            user = ".".join(parts[:-2])
            domain = ".".join(parts[-2:])
            return f"{user}@{domain}"

        return email

    async def _refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Refresh access token using refresh token."""
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        proxy_url = self._proxy_url if self._proxy_url else None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.TOKEN_URL,
                    headers=headers,
                    data=data,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        return None

                    result = await response.json()
                    return result.get("access_token")
        except Exception:
            return None

    async def _fetch_subscription_info(self, access_token: str) -> Optional[dict]:
        """Fetch subscription info to get project ID and subscription details."""
        # Check cache first
        if access_token in self._subscription_cache:
            return self._subscription_cache[access_token]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": self.USER_AGENT,
            "Content-Type": "application/json",
        }

        payload = {
            "metadata": {
                "ideType": "ANTIGRAVITY"
            }
        }

        proxy_url = self._proxy_url if self._proxy_url else None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.LOAD_PROJECT_API_URL,
                    headers=headers,
                    json=payload,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        return None

                    result = await response.json()
                    # Cache the result
                    self._subscription_cache[access_token] = result
                    return result
        except Exception:
            return None

    def _parse_subscription_info(self, subscription_data: dict) -> Optional[SubscriptionInfo]:
        """Parse subscription info from API response."""
        try:
            return SubscriptionInfo.from_dict(subscription_data)
        except Exception:
            return None

    async def _fetch_project_id(self, access_token: str) -> Optional[str]:
        """Fetch project ID from subscription info (with caching)."""
        # Check cache first
        if access_token in self._subscription_cache:
            cached = self._subscription_cache[access_token]
            return cached.get("cloudaicompanionProject")

        # Fetch subscription info
        subscription_info = await self._fetch_subscription_info(access_token)
        if subscription_info:
            self._subscription_cache[access_token] = subscription_info
            return subscription_info.get("cloudaicompanionProject")

        return None

    async def _fetch_quota(self, access_token: str) -> Optional[ProviderQuotaData]:
        """Fetch quota from Antigravity API."""
        # Get project ID
        project_id = await self._fetch_project_id(access_token)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": self.USER_AGENT,
            "Content-Type": "application/json",
        }

        payload = {}
        if project_id:
            payload["project"] = project_id

        proxy_url = self._proxy_url if self._proxy_url else None

        # Retry up to 3 times
        last_error = None
        for attempt in range(1, 4):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.QUOTA_API_URL,
                        headers=headers,
                        json=payload,
                        proxy=proxy_url,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as response:
                        if response.status == 403:
                            # Forbidden - return empty data
                            return ProviderQuotaData(models=[])

                        if response.status != 200:
                            if attempt < 3:
                                await asyncio.sleep(1)
                                continue
                            return None

                        data = await response.json()
                        return self._parse_quota_response(data)
            except Exception as e:
                last_error = e
                if attempt < 3:
                    await asyncio.sleep(1)
                    continue

        return None

    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from Antigravity API.

        Note: The Antigravity API only provides percentage-based quota information
        (remainingFraction) and reset time. It does NOT provide absolute values like
        limit, used, or remaining credits. Therefore, these fields will be None.
        """
        models = []

        quota_models = data.get("models", {})

        for model_name, model_info in quota_models.items():
            # Only include gemini or claude models
            if "gemini" not in model_name.lower() and "claude" not in model_name.lower():
                continue

            quota_info = model_info.get("quotaInfo")
            if quota_info:
                remaining_fraction = quota_info.get("remainingFraction", 0)
                percentage = remaining_fraction * 100
                reset_time = quota_info.get("resetTime", "")

                # Antigravity API only provides remainingFraction (percentage) and resetTime.
                # It does NOT provide absolute quota values (limit, used, remaining).
                # These fields will be None, and the UI will only display the percentage.
                limit = None
                used = None
                remaining = None

                models.append(QuotaModel(
                    name=model_name,
                    percentage=max(0, percentage),
                    used=used,
                    limit=limit,
                    remaining=remaining,
                    reset_time=reset_time if reset_time else None,
                ))

        return ProviderQuotaData(models=models)

    def _read_auth_file(self, file_path: Path) -> Optional[dict]:
        """Read Antigravity auth file."""
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _is_token_expired(self, auth_data: dict) -> bool:
        """Check if access token is expired."""
        expires_at = auth_data.get("expiresAt")
        if not expires_at:
            return True

        try:
            # Handle both timestamp formats
            if isinstance(expires_at, (int, float)):
                expiry = datetime.fromtimestamp(expires_at)
            else:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))

            return datetime.now() > expiry
        except Exception:
            return True

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Antigravity quota for an account."""
        # Find auth file
        auth_file = self._find_auth_file(account_key)
        if not auth_file:
            return None

        auth_data = self._read_auth_file(auth_file)
        if not auth_data:
            return None

        # Get access token
        access_token = auth_data.get("accessToken") or auth_data.get("access_token")

        # Refresh if expired
        if not access_token or self._is_token_expired(auth_data):
            refresh_token = auth_data.get("refreshToken") or auth_data.get("refresh_token")
            if refresh_token:
                access_token = await self._refresh_access_token(refresh_token)
                if access_token:
                    # Update auth file
                    auth_data["accessToken"] = access_token
                    auth_data["access_token"] = access_token
                    try:
                        with open(auth_file, "w") as f:
                            json.dump(auth_data, f, indent=2)
                    except Exception:
                        pass

        if not access_token:
            return None

        return await self._fetch_quota(access_token)

    def _find_auth_file(self, account_key: str) -> Optional[Path]:
        """Find Antigravity auth file for account."""
        if not self.auth_dir.exists():
            return None

        # Look for antigravity auth files
        for file_path in self.auth_dir.glob("antigravity-*.json"):
            try:
                # Extract email from filename
                # Pattern: antigravity-user_domain_com.json -> user@domain.com
                filename = file_path.stem
                email = filename.replace("antigravity-", "")

                # Convert underscores to dots first
                email = email.replace("_", ".")

                # Convert to proper email format with @
                email = self._normalize_email_from_filename(email)

                if email == account_key or account_key in filename:
                    return file_path
            except Exception:
                continue

        return None

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Antigravity quotas."""
        results = {}

        # Clear cache at start of refresh
        self._clear_cache()

        if not self.auth_dir.exists():
            return results

        # Find all antigravity auth files
        for file_path in self.auth_dir.glob("antigravity-*.json"):
            try:
                # Extract email from filename
                # Pattern: antigravity-user_domain_com.json -> user@domain.com
                filename = file_path.stem
                email = filename.replace("antigravity-", "")

                # Convert underscores to dots first
                email = email.replace("_", ".")

                # Convert to proper email format with @
                email = self._normalize_email_from_filename(email)

                auth_data = self._read_auth_file(file_path)
                if not auth_data:
                    continue

                # Get access token
                access_token = auth_data.get("accessToken") or auth_data.get("access_token")

                # Refresh if expired
                if not access_token or self._is_token_expired(auth_data):
                    refresh_token = auth_data.get("refreshToken") or auth_data.get("refresh_token")
                    if refresh_token:
                        access_token = await self._refresh_access_token(refresh_token)
                        if access_token:
                            # Update auth file
                            auth_data["accessToken"] = access_token
                            auth_data["access_token"] = access_token
                            try:
                                with open(file_path, "w") as f:
                                    json.dump(auth_data, f, indent=2)
                            except Exception:
                                pass

                if access_token:
                    quota = await self._fetch_quota(access_token)
                    if quota:
                        results[email] = quota
            except Exception:
                continue

        return results

    async def fetch_all_antigravity_data(self) -> tuple[Dict[str, ProviderQuotaData], Dict[str, SubscriptionInfo]]:
        """Fetch all Antigravity quotas and subscription info.

        Returns:
            Tuple of (quotas_dict, subscriptions_dict) where:
            - quotas_dict: email -> ProviderQuotaData
            - subscriptions_dict: email -> SubscriptionInfo
        """
        quotas = {}
        subscriptions = {}

        # Clear cache at start of refresh
        self._clear_cache()

        if not self.auth_dir.exists():
            return quotas, subscriptions

        # Find all antigravity auth files
        for file_path in self.auth_dir.glob("antigravity-*.json"):
            try:
                # Extract email from filename
                # Pattern: antigravity-user_domain_com.json -> user@domain.com
                filename = file_path.stem
                email = filename.replace("antigravity-", "")

                # Convert underscores to dots first
                email = email.replace("_", ".")

                # Convert to proper email format with @
                email = self._normalize_email_from_filename(email)

                auth_data = self._read_auth_file(file_path)
                if not auth_data:
                    continue

                # Get access token
                access_token = auth_data.get("accessToken") or auth_data.get("access_token")

                # Refresh if expired
                if not access_token or self._is_token_expired(auth_data):
                    refresh_token = auth_data.get("refreshToken") or auth_data.get("refresh_token")
                    if refresh_token:
                        access_token = await self._refresh_access_token(refresh_token)
                        if access_token:
                            # Update auth file
                            auth_data["accessToken"] = access_token
                            auth_data["access_token"] = access_token
                            try:
                                with open(file_path, "w") as f:
                                    json.dump(auth_data, f, indent=2)
                            except Exception:
                                pass

                if access_token:
                    # Fetch quota
                    quota = await self._fetch_quota(access_token)
                    if quota:
                        quotas[email] = quota
                        # Set account email if not set
                        if not quota.account_email:
                            quota.account_email = email

                    # Fetch subscription info
                    subscription_data = await self._fetch_subscription_info(access_token)
                    if subscription_data:
                        subscription_info = self._parse_subscription_info(subscription_data)
                        if subscription_info:
                            subscriptions[email] = subscription_info
                            print(f"[Antigravity] Fetched subscription info for {email}: tier={subscription_info.tier_display_name}")
            except Exception as e:
                print(f"[Antigravity] Error processing {file_path}: {e}")
                import traceback
                traceback.print_exc()
                continue

        return quotas, subscriptions
