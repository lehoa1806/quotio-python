"""Kiro (AWS CodeWhisperer) quota fetcher."""

import json
import time
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class KiroQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Kiro (AWS CodeWhisperer) API."""

    USAGE_ENDPOINT = "https://codewhisperer.us-east-1.amazonaws.com/getUsageLimits"
    SOCIAL_TOKEN_ENDPOINT = "https://prod.us-east-1.auth.desktop.kiro.dev/refreshToken"
    IDC_TOKEN_ENDPOINT = "https://oidc.us-east-1.amazonaws.com/token"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        self.auth_dir = Path.home() / ".cli-proxy-api"
        self._refresh_buffer_seconds = 5 * 60  # 5 minutes

    def _read_auth_token(self, file_path: Path) -> Optional[dict]:
        """Read auth token from Kiro auth file."""
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            return {
                "access_token": data.get("accessToken") or data.get("access_token"),
                "refresh_token": data.get("refreshToken") or data.get("refresh_token"),
                "expires_at": data.get("expiresAt") or data.get("expires_at"),
                "token_type": data.get("tokenType") or data.get("token_type", "Bearer"),
            }
        except Exception:
            return None

    def _should_refresh_token(self, token_data: dict) -> bool:
        """Check if token needs refresh."""
        expires_at = token_data.get("expires_at")
        if not expires_at:
            return False

        try:
            # Parse ISO8601 date
            if isinstance(expires_at, str):
                expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            else:
                expires = datetime.fromtimestamp(expires_at)

            now = datetime.now(expires.tzinfo) if expires.tzinfo else datetime.now()
            time_until_expiry = (expires - now).total_seconds()

            return time_until_expiry < self._refresh_buffer_seconds
        except Exception:
            return False

    async def _refresh_token(self, token_data: dict, file_path: Path) -> Optional[dict]:
        """Refresh access token."""
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            return None

        # Try social token endpoint first (Google OAuth)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.SOCIAL_TOKEN_ENDPOINT,
                    json={"refreshToken": refresh_token},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Update token in file
                        token_data.update({
                            "access_token": data.get("accessToken"),
                            "refresh_token": data.get("refreshToken", refresh_token),
                            "expires_at": self._calculate_expiry(data.get("expiresIn", 3600)),
                        })
                        # Save updated token
                        with open(file_path, "w") as f:
                            json.dump(token_data, f, indent=2)
                        return token_data
        except Exception:
            pass

        return None

    def _calculate_expiry(self, expires_in: int) -> str:
        """Calculate expiry timestamp."""
        expires = datetime.now().timestamp() + expires_in
        return datetime.fromtimestamp(expires).isoformat()

    async def _fetch_from_api(self, access_token: str) -> Optional[ProviderQuotaData]:
        """Fetch quota from Kiro API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        proxy_url = self._proxy_url if self._proxy_url else None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.USAGE_ENDPOINT,
                    headers=headers,
                    json={},  # Empty body
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()
                    return self._parse_quota_response(data)
        except Exception:
            return None

    def _parse_quota_response(self, data: dict) -> ProviderQuotaData:
        """Parse quota response from Kiro API."""
        models = []

        # Parse usage breakdown
        usage_breakdown = data.get("usageBreakdownList", [])
        for breakdown in usage_breakdown:
            display_name = breakdown.get("displayName", "Usage")
            used = breakdown.get("currentUsage", 0)
            limit = breakdown.get("usageLimit", 0)
            remaining = limit - used if limit > 0 else 0
            percentage = (remaining / limit * 100) if limit > 0 else 0

            models.append(QuotaModel(
                name=display_name,
                percentage=max(0, percentage),
                used=int(used),
                limit=int(limit) if limit else None,
                remaining=int(remaining) if remaining else None,
            ))

        return ProviderQuotaData(models=models)

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Kiro quota for an account."""
        # Find auth file
        auth_file = self._find_auth_file(account_key)
        if not auth_file:
            return None

        token_data = self._read_auth_token(auth_file)
        if not token_data or not token_data.get("access_token"):
            return None

        # Refresh token if needed
        if self._should_refresh_token(token_data):
            token_data = await self._refresh_token(token_data, auth_file)

        if not token_data or not token_data.get("access_token"):
            return None

        return await self._fetch_from_api(token_data["access_token"])

    def _find_auth_file(self, account_key: str) -> Optional[Path]:
        """Find Kiro auth file for account."""
        if not self.auth_dir.exists():
            return None

        # Look for kiro auth files
        for file_path in self.auth_dir.glob("*kiro*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    # Check if this matches the account
                    filename = file_path.stem
                    if filename == account_key or account_key in filename:
                        return file_path
            except Exception:
                continue

        return None

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Kiro quotas."""
        results = {}

        if not self.auth_dir.exists():
            return results

        # Find all kiro auth files
        for file_path in self.auth_dir.glob("*kiro*.json"):
            try:
                token_data = self._read_auth_token(file_path)
                if not token_data:
                    continue

                # Refresh if needed
                if self._should_refresh_token(token_data):
                    token_data = await self._refresh_token(token_data, file_path)

                if not token_data or not token_data.get("access_token"):
                    continue

                # Use filename as key (without .json)
                key = file_path.stem
                quota = await self._fetch_from_api(token_data["access_token"])
                if quota:
                    results[key] = quota
            except Exception:
                continue

        return results

    async def refresh_all_tokens_if_needed(self) -> int:
        """Refresh all tokens that need refreshing."""
        if not self.auth_dir.exists():
            return 0

        refreshed_count = 0

        for file_path in self.auth_dir.glob("*kiro*.json"):
            try:
                token_data = self._read_auth_token(file_path)
                if not token_data:
                    continue

                if self._should_refresh_token(token_data):
                    if await self._refresh_token(token_data, file_path):
                        refreshed_count += 1
            except Exception:
                continue

        return refreshed_count
