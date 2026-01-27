"""Gemini CLI quota fetcher."""

import json
import base64
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider
from ...models.subscription import SubscriptionInfo


class GeminiCLIQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Gemini CLI auth files."""

    # Google API endpoints for subscription info
    LOAD_PROJECT_API_URL = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_AGENT = "gemini-cli/1.0"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_dir = Path.home() / ".gemini"
        self.oauth_file = self.auth_dir / "oauth_creds.json"
        self.accounts_file = self.auth_dir / "google_accounts.json"
        self._subscription_cache: Dict[str, dict] = {}  # Cache for subscription info

    def _read_oauth_creds(self) -> Optional[dict]:
        """Read Gemini CLI OAuth credentials."""
        if not self.oauth_file.exists():
            return None

        try:
            with open(self.oauth_file, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _read_accounts_file(self) -> Optional[dict]:
        """Read Gemini CLI accounts file."""
        if not self.accounts_file.exists():
            return None

        try:
            with open(self.accounts_file, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _decode_jwt(self, token: str) -> Optional[dict]:
        """Decode JWT token to extract claims."""
        try:
            parts = token.split(".")
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

    def _get_account_info(self) -> Optional[dict]:
        """Get account info from auth files."""
        auth_data = self._read_oauth_creds()
        if not auth_data:
            return None

        # Try to get email from accounts file first
        accounts_data = self._read_accounts_file()
        email = None
        name = None

        if accounts_data:
            email = accounts_data.get("active")

        # Fall back to JWT if accounts file doesn't have email
        if not email:
            id_token = auth_data.get("idToken") or auth_data.get("id_token")
            if id_token:
                claims = self._decode_jwt(id_token)
                if claims:
                    email = claims.get("email")
                    name = claims.get("name")

        if not email:
            return None

        # Get expiry date
        expiry_date = None
        expiry = auth_data.get("expiryDate") or auth_data.get("expiry_date")
        if expiry:
            try:
                # Handle both seconds and milliseconds
                if isinstance(expiry, (int, float)):
                    if expiry > 1e10:  # Milliseconds
                        expiry_date = datetime.fromtimestamp(expiry / 1000)
                    else:  # Seconds
                        expiry_date = datetime.fromtimestamp(expiry)
            except Exception:
                pass

        return {
            "email": email,
            "name": name,
            "is_active": True,
            "expiry_date": expiry_date,
        }

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Gemini quota for an account."""
        account_info = self._get_account_info()
        if not account_info:
            return None

        # Check if account matches
        if account_info["email"] != account_key:
            return None

        # Gemini CLI doesn't have a public quota API
        # Return placeholder data showing account is connected
        return ProviderQuotaData(
            models=[
                QuotaModel(
                    name="gemini-quota",
                    percentage=-1,  # -1 indicates unknown/unavailable
                    used=None,
                    limit=None,
                    remaining=None,
                )
            ]
        )

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Gemini CLI quotas (matches fetchAsProviderQuota).

        Returns placeholder data showing account is connected, since Gemini CLI
        doesn't have a public quota API.

        Matches Original: checks isInstalled() first, then getAccountInfo(), then
        returns placeholder data with planType: "Google Account".

        Also checks proxy auth files if local files don't exist (Python-specific enhancement).
        """
        results = {}

        # Get account info from local filesystem first (matches original behavior)
        account_info = self._get_account_info()

        # If local files don't exist, check proxy auth files (Python-specific enhancement)
        # This allows Gemini CLI to show up even if local files aren't present but proxy detected it
        if not account_info and self.api_client:
            try:
                # Check if session is closed before making request
                if not (hasattr(self.api_client, 'session') and self.api_client.session.closed):
                    auth_files = await self.api_client.fetch_auth_files()

                    # Look for Gemini CLI auth files
                    for auth_file in auth_files:
                        provider = auth_file.provider.lower() if auth_file.provider else ""
                        provider_type = auth_file.provider_type

                        # Check if this is a Gemini CLI auth file
                        is_gemini_cli = (
                            provider == "gemini-cli" or
                            provider == "gemini" or
                            (provider_type and provider_type == AIProvider.GEMINI) or
                            (auth_file.name and "gemini" in auth_file.name.lower() and "cli" in auth_file.name.lower())
                        )

                        if is_gemini_cli:
                            # Use quota_lookup_key which handles email/account extraction properly
                            email = auth_file.quota_lookup_key
                            if not email:
                                # Fallback: extract from filename
                                email = auth_file.name
                                # Remove file extension if present
                                if email.endswith(('.json', '.toml')):
                                    email = email.rsplit('.', 1)[0]
                                # Remove common prefixes
                                for prefix in ['gemini-cli-', 'gemini-']:
                                    if email.startswith(prefix):
                                        email = email[len(prefix):]

                            account_info = {
                                "email": email,
                                "name": auth_file.label or auth_file.account,
                                "is_active": True,
                                "expiry_date": None,
                            }
                            break
            except Exception:
                pass

        if not account_info:
            return results

        email = account_info["email"]
        name = account_info.get("name")

        # Gemini CLI doesn't have a public quota API
        # Return placeholder data showing account is connected (matches original implementation)
        results[email] = ProviderQuotaData(
            models=[
                QuotaModel(
                    name="gemini-quota",
                    percentage=-1,  # -1 indicates unknown/unavailable
                    used=None,
                    limit=None,
                    remaining=None,
                )
            ],
            plan_type="Google Account",  # Match Original: planType: "Google Account"
            account_email=email,
            account_name=name,
            last_updated=None,
        )

        return results

    async def _fetch_subscription_info(self, access_token: str) -> Optional[dict]:
        """Fetch subscription info to get Google AI Pro subscription details."""
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
                "ideType": "GEMINI"  # Use GEMINI for Gemini CLI
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

    async def _refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Refresh access token using refresh token."""
        # Gemini CLI uses Google OAuth, but we don't have client credentials
        # For now, return None - token refresh would require OAuth client ID/secret
        # This is a limitation - users may need to re-authenticate if token expires
        return None

    def _is_token_expired(self, auth_data: dict) -> bool:
        """Check if access token is expired."""
        expiry = auth_data.get("expiryDate") or auth_data.get("expiry_date")
        if not expiry:
            return True  # Assume expired if no expiry date

        try:
            if isinstance(expiry, (int, float)):
                if expiry > 1e10:  # Milliseconds
                    expiry_date = datetime.fromtimestamp(expiry / 1000)
                else:  # Seconds
                    expiry_date = datetime.fromtimestamp(expiry)
            else:
                expiry_date = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))

            return datetime.now() > expiry_date
        except Exception:
            return True  # Assume expired on error

    async def _get_access_token_from_auth_file(self) -> Optional[str]:
        """Get access token from OAuth credentials file, refreshing if needed."""
        auth_data = self._read_oauth_creds()
        if not auth_data:
            return None

        # Try to get access token
        access_token = auth_data.get("accessToken") or auth_data.get("access_token")

        # Check if token is expired and try to refresh
        if access_token and self._is_token_expired(auth_data):
            refresh_token = auth_data.get("refreshToken") or auth_data.get("refresh_token")
            if refresh_token:
                access_token = await self._refresh_access_token(refresh_token)
                if access_token:
                    # Update auth file (if we successfully refreshed)
                    auth_data["accessToken"] = access_token
                    auth_data["access_token"] = access_token
                    try:
                        with open(self.oauth_file, "w") as f:
                            json.dump(auth_data, f, indent=2)
                    except Exception:
                        pass
                else:
                    access_token = None  # Clear expired token
            else:
                access_token = None  # Clear expired token

        return access_token

    async def fetch_all_gemini_data(self) -> tuple[Dict[str, ProviderQuotaData], Dict[str, SubscriptionInfo]]:
        """Fetch all Gemini CLI quotas and subscription info.

        Returns:
            Tuple of (quotas_dict, subscriptions_dict) where:
            - quotas_dict: email -> ProviderQuotaData
            - subscriptions_dict: email -> SubscriptionInfo
        """
        quotas = {}
        subscriptions = {}

        # Clear cache at start of refresh
        self._subscription_cache.clear()

        # Get account info from local filesystem first
        account_info = self._get_account_info()

        # If local files don't exist, check proxy auth files
        if not account_info and self.api_client:
            try:
                if not (hasattr(self.api_client, 'session') and self.api_client.session.closed):
                    auth_files = await self.api_client.fetch_auth_files()

                    # Look for Gemini CLI auth files
                    for auth_file in auth_files:
                        provider = auth_file.provider.lower() if auth_file.provider else ""
                        provider_type = auth_file.provider_type

                        is_gemini_cli = (
                            provider == "gemini-cli" or
                            provider == "gemini" or
                            (provider_type and provider_type == AIProvider.GEMINI) or
                            (auth_file.name and "gemini" in auth_file.name.lower() and "cli" in auth_file.name.lower())
                        )

                        if is_gemini_cli:
                            email = auth_file.quota_lookup_key
                            if not email:
                                email = auth_file.name
                                if email.endswith(('.json', '.toml')):
                                    email = email.rsplit('.', 1)[0]
                                for prefix in ['gemini-cli-', 'gemini-']:
                                    if email.startswith(prefix):
                                        email = email[len(prefix):]

                            account_info = {
                                "email": email,
                                "name": auth_file.label or auth_file.account,
                                "is_active": True,
                                "expiry_date": None,
                            }
                            break
            except Exception:
                pass

        if not account_info:
            return quotas, subscriptions

        email = account_info["email"]
        name = account_info.get("name")

        # Get access token (async method)
        access_token = await self._get_access_token_from_auth_file()

        # Fetch quota (placeholder data)
        quotas[email] = ProviderQuotaData(
            models=[
                QuotaModel(
                    name="gemini-quota",
                    percentage=-1,
                    used=None,
                    limit=None,
                    remaining=None,
                )
            ],
            plan_type="Google Account",
            account_email=email,
            account_name=name,
            last_updated=None,
        )

        # Fetch subscription info if we have an access token
        if access_token:
            try:
                subscription_data = await self._fetch_subscription_info(access_token)
                if subscription_data:
                    subscription_info = self._parse_subscription_info(subscription_data)
                    if subscription_info:
                        subscriptions[email] = subscription_info
            except Exception:
                pass

        return quotas, subscriptions
