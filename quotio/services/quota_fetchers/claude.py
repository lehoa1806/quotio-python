"""Claude Code quota fetcher."""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class ClaudeCodeQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Claude Code OAuth API."""
    
    USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
    
    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_dir = Path.home() / ".cli-proxy-api"
        self._cache: Dict[str, tuple] = {}  # account_key -> (data, timestamp)
        self._cache_ttl = 300  # 5 minutes
    
    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Claude quota for an account."""
        # Check cache
        if account_key in self._cache:
            data, timestamp = self._cache[account_key]
            import time
            if time.time() - timestamp < self._cache_ttl:
                return data
        
        # Find auth file
        auth_file = self._find_auth_file(account_key)
        if not auth_file:
            return None
        
        # Extract access token
        access_token = auth_file.get("access_token")
        if not access_token:
            return None
        
        # Fetch from API
        try:
            quota_data = await self._fetch_from_api(access_token)
            if quota_data:
                self._cache[account_key] = (quota_data, time.time())
            return quota_data
        except Exception:
            return None
    
    def _find_auth_file(self, account_key: str) -> Optional[dict]:
        """Find auth file for account."""
        if not self.auth_dir.exists():
            return None
        
        # Look for claude auth files
        for file_path in self.auth_dir.glob("*claude*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    # Check if this matches the account
                    email = data.get("email") or data.get("account")
                    if email == account_key or file_path.stem == account_key:
                        return data
            except Exception:
                continue
        
        return None
    
    async def _fetch_from_api(self, access_token: str) -> Optional[ProviderQuotaData]:
        """Fetch quota from Anthropic OAuth API (matches original implementation)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "anthropic-beta": "oauth-2025-04-20",  # Required header for OAuth API
        }
        
        # Use proxy if configured
        proxy_url = self._proxy_url if self._proxy_url else None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.USAGE_URL,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    # Check for authentication errors (401)
                    if response.status == 401:
                        # Token expired or invalid - needs re-authentication
                        # Return None to indicate auth error (matches original behavior)
                        return None
                    
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    
                    # Check for API error response
                    if data.get("type") == "error":
                        error_obj = data.get("error", {})
                        if error_obj.get("type") == "authentication_error":
                            # Token expired or invalid
                            return None
                        # Other API error
                        return None
                    
                    return self._parse_quota_response(data)
        except Exception as e:
            print(f"[ClaudeCodeQuotaFetcher] Network error: {e}")
            return None
    
    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from Anthropic OAuth API.
        
        Matches original implementation: parses five_hour, seven_day,
        seven_day_sonnet, seven_day_opus, and extra_usage.
        """
        models = []
        
        # Parse five_hour quota (5-hour session window)
        if "five_hour" in data:
            q = data["five_hour"]
            utilization = q.get("utilization", 0)
            # Handle both Int and Double for utilization
            if isinstance(utilization, int):
                utilization = float(utilization)
            remaining = max(0, min(100, 100 - utilization))
            resets_at = q.get("resets_at", "")
            
            models.append(QuotaModel(
                name="five-hour-session",
                percentage=remaining,
                used=None,
                limit=None,
                remaining=None,
            ))
        
        # Parse seven_day quota (7-day weekly window)
        if "seven_day" in data:
            q = data["seven_day"]
            utilization = q.get("utilization", 0)
            if isinstance(utilization, int):
                utilization = float(utilization)
            remaining = max(0, min(100, 100 - utilization))
            resets_at = q.get("resets_at", "")
            
            models.append(QuotaModel(
                name="seven-day-weekly",
                percentage=remaining,
                used=None,
                limit=None,
                remaining=None,
            ))
        
        # Parse seven_day_sonnet quota
        if "seven_day_sonnet" in data:
            q = data["seven_day_sonnet"]
            utilization = q.get("utilization", 0)
            if isinstance(utilization, int):
                utilization = float(utilization)
            remaining = max(0, min(100, 100 - utilization))
            resets_at = q.get("resets_at", "")
            
            models.append(QuotaModel(
                name="seven-day-sonnet",
                percentage=remaining,
                used=None,
                limit=None,
                remaining=None,
            ))
        
        # Parse seven_day_opus quota
        if "seven_day_opus" in data:
            q = data["seven_day_opus"]
            utilization = q.get("utilization", 0)
            if isinstance(utilization, int):
                utilization = float(utilization)
            remaining = max(0, min(100, 100 - utilization))
            resets_at = q.get("resets_at", "")
            
            models.append(QuotaModel(
                name="seven-day-opus",
                percentage=remaining,
                used=None,
                limit=None,
                remaining=None,
            ))
        
        # Parse extra_usage (only if enabled)
        if "extra_usage" in data:
            extra = data["extra_usage"]
            is_enabled = extra.get("is_enabled", False)
            if is_enabled:
                utilization = extra.get("utilization")
                if utilization is not None:
                    if isinstance(utilization, int):
                        utilization = float(utilization)
                    remaining = max(0, min(100, 100 - utilization))
                    used_credits = extra.get("used_credits")
                    monthly_limit = extra.get("monthly_limit")
                    
                    models.append(QuotaModel(
                        name="extra-usage",
                        percentage=remaining,
                        used=int(used_credits) if used_credits is not None else None,
                        limit=int(monthly_limit) if monthly_limit is not None else None,
                        remaining=None,
                    ))
        
        return ProviderQuotaData(
            models=models,
            account_email=None,
            account_name=None,
            last_updated=None,
            plan_type=None,
        )
    
    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Claude quotas."""
        results = {}
        
        if not self.auth_dir.exists():
            return results
        
        # Find all claude auth files
        for file_path in self.auth_dir.glob("*claude*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    email = data.get("email") or data.get("account") or file_path.stem
                    access_token = data.get("access_token")
                    
                    if access_token:
                        quota = await self._fetch_from_api(access_token)
                        if quota:
                            results[email] = quota
            except Exception:
                continue
        
        return results
