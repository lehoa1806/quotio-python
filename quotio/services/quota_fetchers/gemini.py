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
            print(f"[GeminiCLIQuotaFetcher] OAuth file does not exist: {self.oauth_file}")
            return None

        try:
            with open(self.oauth_file, "r") as f:
                data = json.load(f)
                print(f"[GeminiCLIQuotaFetcher] Successfully read OAuth file: {self.oauth_file}")
                return data
        except Exception as e:
            print(f"[GeminiCLIQuotaFetcher] Error reading OAuth file: {e}")
            return None

    def _read_accounts_file(self) -> Optional[dict]:
        """Read Gemini CLI accounts file."""
        if not self.accounts_file.exists():
            print(f"[GeminiCLIQuotaFetcher] Accounts file does not exist: {self.accounts_file}")
            return None

        try:
            with open(self.accounts_file, "r") as f:
                data = json.load(f)
                print(f"[GeminiCLIQuotaFetcher] Successfully read accounts file: {self.accounts_file}")
                return data
        except Exception as e:
            print(f"[GeminiCLIQuotaFetcher] Error reading accounts file: {e}")
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

        print(f"[GeminiCLIQuotaFetcher] fetch_all_quotas() called")

        # Check if Gemini CLI is installed (matches Original: guard await isInstalled())
        # Note: We can't easily check installation here, so we'll just check for auth files
        # If auth files exist, assume CLI is installed/configured

        print(f"[GeminiCLIQuotaFetcher] Checking for auth files...")
        print(f"[GeminiCLIQuotaFetcher] OAuth file path: {self.oauth_file}")
        print(f"[GeminiCLIQuotaFetcher] OAuth file exists: {self.oauth_file.exists()}")
        print(f"[GeminiCLIQuotaFetcher] Accounts file path: {self.accounts_file}")
        print(f"[GeminiCLIQuotaFetcher] Accounts file exists: {self.accounts_file.exists()}")

        # Get account info from local filesystem first (matches original behavior)
        account_info = self._get_account_info()

        # If local files don't exist, check proxy auth files (Python-specific enhancement)
        # This allows Gemini CLI to show up even if local files aren't present but proxy detected it
        if not account_info and self.api_client:
            print(f"[GeminiCLIQuotaFetcher] Local auth files not found, checking proxy auth files...")
            try:
                # Check if session is closed before making request
                if hasattr(self.api_client, 'session') and self.api_client.session.closed:
                    print(f"[GeminiCLIQuotaFetcher] API client session is closed, skipping proxy auth files check")
                else:
                    auth_files = await self.api_client.fetch_auth_files()
                    print(f"[GeminiCLIQuotaFetcher] Got {len(auth_files)} auth files from API client")

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
                            print(f"[GeminiCLIQuotaFetcher] Found Gemini CLI auth file from proxy: {auth_file.name}")
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

                            print(f"[GeminiCLIQuotaFetcher] Using email from proxy auth file: {email}")
                            account_info = {
                                "email": email,
                                "name": auth_file.label or auth_file.account,
                                "is_active": True,
                                "expiry_date": None,
                            }
                            break
            except Exception as e:
                print(f"[GeminiCLIQuotaFetcher] Error checking proxy auth files: {e}")
                import traceback
                traceback.print_exc()

        if not account_info:
            print(f"[GeminiCLIQuotaFetcher] No account info found - auth files may not exist or be invalid")
            return results

        email = account_info["email"]
        name = account_info.get("name")
        print(f"[GeminiCLIQuotaFetcher] Found account: {email} (name: {name})")

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

        print(f"[GeminiCLIQuotaFetcher] Returning {len(results)} account(s) with placeholder quota data")
        print(f"[GeminiCLIQuotaFetcher]   - {email}: 1 model (gemini-quota, percentage=-1)")
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

        print(f"[GeminiCLIQuotaFetcher] Fetching subscription info from: {self.LOAD_PROJECT_API_URL}")
        print(f"[GeminiCLIQuotaFetcher] Request payload: {json.dumps(payload, indent=2)}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.LOAD_PROJECT_API_URL,
                    headers=headers,
                    json=payload,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    print(f"[GeminiCLIQuotaFetcher] Subscription API response status: {response.status}")
                    
                    if response.status != 200:
                        # Try to read error response
                        try:
                            error_text = await response.text()
                            print(f"[GeminiCLIQuotaFetcher] Error response body: {error_text}")
                        except Exception:
                            pass
                        return None

                    result = await response.json()
                    # Print raw response for debugging
                    print(f"[GeminiCLIQuotaFetcher] Raw subscription API response:")
                    print(json.dumps(result, indent=2))
                    
                    # Cache the result
                    self._subscription_cache[access_token] = result
                    return result
        except Exception as e:
            print(f"[GeminiCLIQuotaFetcher] Error fetching subscription info: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_subscription_info(self, subscription_data: dict) -> Optional[SubscriptionInfo]:
        """Parse subscription info from API response."""
        print(f"[GeminiCLIQuotaFetcher] Parsing subscription data...")
        print(f"[GeminiCLIQuotaFetcher] Subscription data keys: {list(subscription_data.keys())}")
        try:
            subscription_info = SubscriptionInfo.from_dict(subscription_data)
            if subscription_info:
                print(f"[GeminiCLIQuotaFetcher] Successfully parsed subscription info:")
                print(f"  - Tier display name: {subscription_info.tier_display_name}")
                print(f"  - Tier ID: {subscription_info.tier_id}")
                print(f"  - Is paid tier: {subscription_info.is_paid_tier}")
                if subscription_info.effective_tier:
                    print(f"  - Effective tier name: {subscription_info.effective_tier.name}")
                    print(f"  - Effective tier ID: {subscription_info.effective_tier.id}")
            return subscription_info
        except Exception as e:
            print(f"[GeminiCLIQuotaFetcher] Error parsing subscription info: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Refresh access token using refresh token."""
        # Gemini CLI uses Google OAuth, but we don't have client credentials
        # For now, return None - token refresh would require OAuth client ID/secret
        # This is a limitation - users may need to re-authenticate if token expires
        print(f"[GeminiCLIQuotaFetcher] Token refresh not implemented (requires OAuth client credentials)")
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
            print(f"[GeminiCLIQuotaFetcher] Access token expired, attempting refresh...")
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
                    except Exception as e:
                        print(f"[GeminiCLIQuotaFetcher] Failed to update auth file: {e}")
                else:
                    print(f"[GeminiCLIQuotaFetcher] Token refresh failed - subscription info may not be available")
            else:
                print(f"[GeminiCLIQuotaFetcher] No refresh token available - subscription info may not be available")
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

        print(f"[GeminiCLIQuotaFetcher] fetch_all_gemini_data() called")

        # Get account info from local filesystem first
        account_info = self._get_account_info()

        # If local files don't exist, check proxy auth files
        if not account_info and self.api_client:
            print(f"[GeminiCLIQuotaFetcher] Local auth files not found, checking proxy auth files...")
            try:
                if hasattr(self.api_client, 'session') and self.api_client.session.closed:
                    print(f"[GeminiCLIQuotaFetcher] API client session is closed, skipping proxy auth files check")
                else:
                    auth_files = await self.api_client.fetch_auth_files()
                    print(f"[GeminiCLIQuotaFetcher] Got {len(auth_files)} auth files from API client")

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
                            print(f"[GeminiCLIQuotaFetcher] Found Gemini CLI auth file from proxy: {auth_file.name}")
                            email = auth_file.quota_lookup_key
                            if not email:
                                email = auth_file.name
                                if email.endswith(('.json', '.toml')):
                                    email = email.rsplit('.', 1)[0]
                                for prefix in ['gemini-cli-', 'gemini-']:
                                    if email.startswith(prefix):
                                        email = email[len(prefix):]

                            print(f"[GeminiCLIQuotaFetcher] Using email from proxy auth file: {email}")
                            account_info = {
                                "email": email,
                                "name": auth_file.label or auth_file.account,
                                "is_active": True,
                                "expiry_date": None,
                            }
                            break
            except Exception as e:
                print(f"[GeminiCLIQuotaFetcher] Error checking proxy auth files: {e}")
                import traceback
                traceback.print_exc()

        if not account_info:
            print(f"[GeminiCLIQuotaFetcher] No account info found")
            return quotas, subscriptions

        email = account_info["email"]
        name = account_info.get("name")
        print(f"[GeminiCLIQuotaFetcher] Processing account: {email} (name: {name})")

        # Get access token (async method)
        print(f"[GeminiCLIQuotaFetcher] Getting access token for {email}...")
        access_token = await self._get_access_token_from_auth_file()
        
        if access_token:
            print(f"[GeminiCLIQuotaFetcher] Access token found (length: {len(access_token)})")
        else:
            print(f"[GeminiCLIQuotaFetcher] No access token available from local files")
            # If no access token from local file, try to get from proxy
            if self.api_client:
                # For proxy mode, we'd need to get the token from the proxy's auth file
                # This is a limitation - we can't easily get the access token from proxy auth files
                # without additional API support
                print(f"[GeminiCLIQuotaFetcher] Cannot get access token from proxy auth files (limitation)")

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
            print(f"[GeminiCLIQuotaFetcher] Attempting to fetch subscription info for {email}...")
            try:
                subscription_data = await self._fetch_subscription_info(access_token)
                if subscription_data:
                    print(f"[GeminiCLIQuotaFetcher] Received subscription data for {email}")
                    subscription_info = self._parse_subscription_info(subscription_data)
                    if subscription_info:
                        subscriptions[email] = subscription_info
                        print(f"[GeminiCLIQuotaFetcher] ✓ Successfully fetched subscription info for {email}: tier={subscription_info.tier_display_name}")
                    else:
                        print(f"[GeminiCLIQuotaFetcher] ✗ Failed to parse subscription info for {email}")
                else:
                    print(f"[GeminiCLIQuotaFetcher] ✗ No subscription data returned for {email}")
            except Exception as e:
                print(f"[GeminiCLIQuotaFetcher] ✗ Error fetching subscription info for {email}: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[GeminiCLIQuotaFetcher] ✗ No access token available to fetch subscription info for {email}")

        print(f"[GeminiCLIQuotaFetcher] Returning {len(quotas)} quota(s) and {len(subscriptions)} subscription(s)")
        return quotas, subscriptions
