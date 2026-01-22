"""Warp quota fetcher."""

from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class WarpQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Warp API using connection tokens."""
    
    # Warp API endpoint (placeholder - actual endpoint may differ)
    QUOTA_API_URL = "https://api.warp.dev/v1/usage"
    
    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
    
    async def fetch_quota(self, account_key: str, token: Optional[str] = None) -> Optional[ProviderQuotaData]:
        """Fetch Warp quota for an account using connection token."""
        if not token:
            return None
        
        return await self._fetch_from_api(token)
    
    async def _fetch_from_api(self, token: str) -> Optional[ProviderQuotaData]:
        """Fetch quota from Warp API."""
        headers = {
            "Authorization": f"Bearer {token}",
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
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    return self._parse_quota_response(data)
        except Exception:
            return None
    
    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from Warp API."""
        models = []
        
        # Parse usage data (structure depends on actual API)
        if "usage" in data:
            usage = data["usage"]
            used = usage.get("used", 0)
            limit = usage.get("limit", 0)
            remaining = limit - used if limit > 0 else 0
            percentage = (remaining / limit * 100) if limit > 0 else 0
            
            models.append(QuotaModel(
                name="Usage",
                percentage=max(0, percentage),
                used=used,
                limit=limit if limit > 0 else None,
                remaining=remaining,
            ))
        
        return ProviderQuotaData(models=models)
    
    async def fetch_all_quotas(self, tokens: Dict[str, str]) -> Dict[str, ProviderQuotaData]:
        """Fetch all Warp quotas for provided tokens.
        
        Args:
            tokens: Dictionary mapping account name -> connection token
            
        Returns:
            Dictionary mapping account name -> ProviderQuotaData
        """
        results = {}
        
        for account_name, token in tokens.items():
            quota = await self._fetch_from_api(token)
            if quota:
                results[account_name] = quota
        
        return results
