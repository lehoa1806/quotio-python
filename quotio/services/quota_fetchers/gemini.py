"""Gemini CLI quota fetcher."""

import json
import base64
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class GeminiCLIQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Gemini CLI auth files."""
    
    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_dir = Path.home() / ".gemini"
        self.oauth_file = self.auth_dir / "oauth_creds.json"
        self.accounts_file = self.auth_dir / "google_accounts.json"
    
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
