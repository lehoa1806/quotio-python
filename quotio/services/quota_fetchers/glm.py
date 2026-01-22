"""GLM (BigModel) quota fetcher."""

from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class GLMQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from GLM (BigModel) API using API keys."""
    
    QUOTA_API_URL = "https://bigmodel.cn/api/monitor/usage/quota/limit"
    
    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        # In real implementation, get API keys from CustomProviderService
        # For now, we'll accept them as parameters
    
    async def fetch_quota(self, account_key: str, api_key: Optional[str] = None) -> Optional[ProviderQuotaData]:
        """Fetch GLM quota for an account using API key."""
        if not api_key:
            return None
        
        return await self._fetch_from_api(api_key)
    
    async def _fetch_from_api(self, api_key: str) -> Optional[ProviderQuotaData]:
        """Fetch quota from GLM API."""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        proxy_url = self._proxy_url if self._proxy_url else None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.QUOTA_API_URL,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status == 401 or response.status == 403:
                        # Forbidden - return empty data with flag
                        return ProviderQuotaData(models=[])
                    
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    return self._parse_quota_response(data)
        except Exception:
            return None
    
    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from GLM API."""
        models = []
        
        if not data.get("success") or data.get("code") != 200:
            return ProviderQuotaData(models=models)
        
        quota_data = data.get("data", {})
        limits = quota_data.get("limits", [])
        
        for limit in limits:
            limit_type = limit.get("type", "Usage")
            used = limit.get("usage", 0)
            remaining = limit.get("remaining", 0)
            total = used + remaining if remaining >= 0 else used
            percentage = limit.get("percentage", 0)
            
            # If percentage not provided, calculate it
            if percentage == 0 and total > 0:
                percentage = (remaining / total * 100) if remaining >= 0 else 0
            
            models.append(QuotaModel(
                name=limit_type,
                percentage=max(0, percentage),
                used=used,
                limit=total if total > 0 else None,
                remaining=remaining if remaining >= 0 else None,
            ))
        
        return ProviderQuotaData(models=models)
    
    async def fetch_all_quotas(self, api_keys: Dict[str, str]) -> Dict[str, ProviderQuotaData]:
        """Fetch all GLM quotas for provided API keys.
        
        Args:
            api_keys: Dictionary mapping account name -> API key
            
        Returns:
            Dictionary mapping account name -> ProviderQuotaData
        """
        results = {}
        
        for account_name, api_key in api_keys.items():
            quota = await self._fetch_from_api(api_key)
            if quota:
                results[account_name] = quota
        
        return results
