"""GitHub Copilot quota fetcher."""

import json
from pathlib import Path
from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class CopilotQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from GitHub Copilot API."""

    USAGE_URL = "https://api.github.com/copilot/usage"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_dir = Path.home() / ".cli-proxy-api"

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Copilot quota for an account."""
        auth_file = self._find_auth_file(account_key)
        if not auth_file:
            return None

        token = auth_file.get("access_token") or auth_file.get("token")
        if not token:
            return None

        try:
            return await self._fetch_from_api(token)
        except Exception:
            return None

    def _find_auth_file(self, account_key: str) -> Optional[dict]:
        """Find auth file for account."""
        if not self.auth_dir.exists():
            return None

        for file_path in self.auth_dir.glob("*copilot*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    email = data.get("email") or file_path.stem
                    if email == account_key or file_path.stem == account_key:
                        return data
            except Exception:
                continue

        return None

    async def _fetch_from_api(self, token: str) -> Optional[ProviderQuotaData]:
        """Fetch quota from GitHub Copilot API."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        proxy_url = self._proxy_url if self._proxy_url else None

        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.USAGE_URL,
                headers=headers,
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                return self._parse_quota_response(data)

    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from API."""
        models = []

        # Parse Copilot usage data
        if "usage" in data:
            usage = data["usage"]
            # Copilot typically has daily limits
            if "daily_limit" in usage and "daily_used" in usage:
                limit = usage["daily_limit"]
                used = usage["daily_used"]
                percentage = max(0, 100 - (used / limit * 100)) if limit > 0 else 100

                models.append(QuotaModel(
                    name="Daily",
                    percentage=percentage,
                    used=used,
                    limit=limit,
                    remaining=limit - used,
                ))

        return ProviderQuotaData(models=models)

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Copilot quotas."""
        results = {}

        if not self.auth_dir.exists():
            return results

        for file_path in self.auth_dir.glob("*copilot*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    email = data.get("email") or file_path.stem
                    token = data.get("access_token") or data.get("token")

                    if token:
                        quota = await self._fetch_from_api(token)
                        if quota:
                            results[email] = quota
            except Exception:
                continue

        return results
