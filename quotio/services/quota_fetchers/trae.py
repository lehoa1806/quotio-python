"""Trae quota fetcher."""

import json
import platform
from pathlib import Path
from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class TraeQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Trae using storage.json and API."""
    
    STORAGE_JSON_PATH = "~/Library/Application Support/Trae/User/globalStorage/storage.json"
    AUTH_KEY = "iCubeAuthInfo://icube.cloudide"
    DEFAULT_API_HOST = "https://api-sg-central.trae.ai"
    
    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        # Adjust path for platform
        if platform.system() != "Darwin":
            self.storage_path = Path.home() / ".trae" / "storage.json"
        else:
            self.storage_path = Path.home() / "Library" / "Application Support" / "Trae" / "User" / "globalStorage" / "storage.json"
    
    def _read_auth_from_storage(self) -> Optional[dict]:
        """Read auth data from Trae's storage.json."""
        if not self.storage_path.exists():
            return None
        
        try:
            with open(self.storage_path, "r") as f:
                storage = json.load(f)
            
            # Get auth info string
            auth_info_string = storage.get(self.AUTH_KEY)
            if not auth_info_string:
                return None
            
            # Parse the auth info JSON string
            auth_info = json.loads(auth_info_string)
            
            return {
                "access_token": auth_info.get("token"),
                "refresh_token": auth_info.get("refreshToken"),
                "email": auth_info.get("account", {}).get("email") if isinstance(auth_info.get("account"), dict) else None,
                "username": auth_info.get("account", {}).get("username") if isinstance(auth_info.get("account"), dict) else None,
                "user_id": auth_info.get("userId"),
                "api_host": auth_info.get("host"),
            }
        except Exception:
            return None
    
    async def _fetch_from_api(self, access_token: str, api_host: Optional[str] = None) -> Optional[ProviderQuotaData]:
        """Fetch quota from Trae API."""
        host = api_host or self.DEFAULT_API_HOST
        url = f"{host}/trae/api/v1/pay/user_current_entitlement_list"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/json",
        }
        
        proxy_url = self._proxy_url if self._proxy_url else None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    return self._parse_quota_response(data)
        except Exception:
            return None
    
    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from Trae API."""
        models = []
        
        # Parse usage limits from response
        if "entitlements" in data:
            entitlements = data["entitlements"]
            for ent in entitlements:
                resource_type = ent.get("resourceType", "")
                used = ent.get("currentUsage", 0)
                limit = ent.get("usageLimit", 0)
                remaining = limit - used if limit > 0 else 0
                percentage = (remaining / limit * 100) if limit > 0 else 0
                
                # Map resource types to model names
                model_name = resource_type.replace("_", " ").title()
                if not model_name:
                    model_name = "Usage"
                
                models.append(QuotaModel(
                    name=model_name,
                    percentage=max(0, percentage),
                    used=used,
                    limit=limit,
                    remaining=remaining,
                ))
        
        return ProviderQuotaData(models=models)
    
    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Trae quota for an account."""
        auth_data = self._read_auth_from_storage()
        if not auth_data or not auth_data.get("access_token"):
            return None
        
        return await self._fetch_from_api(
            auth_data["access_token"],
            auth_data.get("api_host")
        )
    
    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Trae quotas."""
        results = {}
        
        auth_data = self._read_auth_from_storage()
        if not auth_data:
            return results
        
        email = auth_data.get("email") or auth_data.get("username") or "trae-user"
        access_token = auth_data.get("access_token")
        
        if access_token:
            quota = await self._fetch_from_api(
                access_token,
                auth_data.get("api_host")
            )
            if quota:
                results[email] = quota
        
        return results
