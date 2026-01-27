"""Cursor quota fetcher."""

import json
import sqlite3
import platform
from pathlib import Path
from typing import Optional, Dict
import aiohttp

from .base import BaseQuotaFetcher, ProviderQuotaData, QuotaModel
from ...models.providers import AIProvider


class CursorQuotaFetcher(BaseQuotaFetcher):
    """Fetches quota data from Cursor using SQLite database and API."""

    API_BASE = "https://api2.cursor.sh"
    STATE_DB_PATH = "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"

    def __init__(self, api_client=None):
        """Initialize the fetcher."""
        super().__init__(api_client)
        # Adjust path for platform
        if platform.system() != "Darwin":
            # On non-macOS, try alternative paths
            self.state_db_path = Path.home() / ".cursor" / "state.vscdb"
        else:
            self.state_db_path = Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"

    def _read_auth_from_db(self) -> Optional[dict]:
        """Read auth data from Cursor's state.vscdb SQLite database."""
        # Try multiple possible paths
        possible_paths = [
            self.state_db_path,
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb",
            Path.home() / ".cursor" / "state.vscdb",
        ]

        db_path = None
        for path in possible_paths:
            if path.exists():
                db_path = path
                break

        if not db_path:
            print(f"[Cursor] Database not found. Checked paths: {[str(p) for p in possible_paths]}")
            return None

        try:
            # Try with immutable=1 first (read-only, no WAL)
            try:
                uri = f"file://{db_path}?mode=ro&immutable=1"
                conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            except Exception:
                # Fallback: try without immutable (may need WAL file)
                try:
                    conn = sqlite3.connect(str(db_path), timeout=5.0)
                except Exception as e:
                    print(f"[Cursor] Failed to connect to database: {e}")
                    return None

            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Query for auth data - try different table names
            queries = [
                "SELECT key, value FROM ItemTable WHERE key LIKE 'cursorAuth/%'",
                "SELECT key, value FROM ItemTable WHERE key LIKE '%cursorAuth%'",
                "SELECT key, value FROM ItemTable WHERE key LIKE '%accessToken%'",
            ]

            auth_data = {}
            for query in queries:
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    if rows:
                        for row in rows:
                            key = row["key"]
                            value = row["value"]

                            if key == "cursorAuth/accessToken":
                                auth_data["access_token"] = value
                            elif key == "cursorAuth/refreshToken":
                                auth_data["refresh_token"] = value
                            elif key == "cursorAuth/cachedEmail":
                                auth_data["email"] = value
                            elif key == "cursorAuth/stripeMembershipType":
                                auth_data["membership_type"] = value
                            elif key == "cursorAuth/stripeSubscriptionStatus":
                                auth_data["subscription_status"] = value

                        if auth_data.get("access_token"):
                            break
                except Exception as e:
                    print(f"[Cursor] Query failed: {query[:50]}... Error: {e}")
                    continue

            conn.close()

            if auth_data.get("access_token"):
                print(f"[Cursor] Found auth data for: {auth_data.get('email', 'unknown')}")
                return auth_data
            else:
                print(f"[Cursor] No access token found in database")
                return None
        except Exception as e:
            print(f"[Cursor] Error reading database: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _fetch_from_api(self, access_token: str, membership_type: Optional[str] = None, subscription_status: Optional[str] = None) -> Optional[ProviderQuotaData]:
        """Fetch quota from Cursor API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/json",
        }

        # Cursor API endpoint for usage-summary (has both plan and on-demand info)
        url = f"{self.API_BASE}/auth/usage-summary"

        proxy_url = self._proxy_url if self._proxy_url else None

        print(f"[Cursor] Fetching quota from API: {url}")
        print(f"[Cursor] Using proxy: {proxy_url if proxy_url else 'None (direct)'}")
        print(f"[Cursor] Access token length: {len(access_token) if access_token else 0}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    print(f"[Cursor] API response status: {response.status}")
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"[Cursor] API request failed: {response.status} - {error_text[:500]}")
                        return None

                    data = await response.json()
                    print(f"[Cursor] API response data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    quota = self._parse_quota_response(data, membership_type, subscription_status)
                    if quota:
                        print(f"[Cursor] Successfully fetched quota: {len(quota.models)} model(s)")
                    else:
                        print(f"[Cursor] Failed to parse quota from response data")
                    return quota
        except aiohttp.ClientError as e:
            print(f"[Cursor] HTTP client error: {e}")
            import traceback
            traceback.print_exc()
            return None
        except Exception as e:
            print(f"[Cursor] Error fetching from API: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_quota_response(self, data: dict, membership_type: Optional[str] = None, subscription_status: Optional[str] = None) -> ProviderQuotaData:
        """Parse quota response from Cursor API usage-summary endpoint."""
        models = []

        # Get membership type from API response or use provided one
        api_membership_type = data.get("membershipType") or membership_type

        # Format plan type for display (e.g., "pro_student" -> "Pro Student")
        plan_type_display = None
        if api_membership_type:
            plan_type_display = api_membership_type.replace("_", " ").title()

        # The API response has usage data nested under "individualUsage"
        individual_usage = data.get("individualUsage", {})

        # Parse plan usage
        plan_limit = None
        if "plan" in individual_usage:
            plan = individual_usage["plan"]
            if plan.get("enabled"):
                used = plan.get("used", 0)
                limit = plan.get("limit", 0)
                plan_limit = limit  # Store for subscription cap display
                remaining = plan.get("remaining", limit - used if limit > 0 else 0)
                # Calculate percentage from remaining/limit
                percentage = (remaining / limit * 100) if limit > 0 else 0

                models.append(QuotaModel(
                    name="Plan Usage",
                    percentage=max(0, min(100, percentage)),
                    used=used,
                    limit=limit,
                    remaining=remaining,
                ))

        # Parse on-demand usage
        if "onDemand" in individual_usage:
            on_demand = individual_usage["onDemand"]
            if on_demand.get("enabled"):
                used = on_demand.get("used", 0)
                limit = on_demand.get("limit")  # Can be None for unlimited
                remaining = on_demand.get("remaining")
                # Calculate percentage if limit exists
                if limit and limit > 0:
                    percentage = (remaining / limit * 100) if remaining is not None else 0
                else:
                    percentage = -1  # Unknown/unlimited

                models.append(QuotaModel(
                    name="On-Demand",
                    percentage=max(0, percentage) if percentage >= 0 else -1,
                    used=used,
                    limit=limit,
                    remaining=remaining,
                ))

        return ProviderQuotaData(
            models=models,
            plan_type=plan_type_display,
            membership_type=api_membership_type,
            subscription_status=subscription_status
        )

    async def fetch_quota(self, account_key: str) -> Optional[ProviderQuotaData]:
        """Fetch Cursor quota for an account."""
        auth_data = self._read_auth_from_db()
        if not auth_data or not auth_data.get("access_token"):
            return None

        membership_type = auth_data.get("membership_type")
        subscription_status = auth_data.get("subscription_status")
        return await self._fetch_from_api(auth_data["access_token"], membership_type, subscription_status)

    async def fetch_all_quotas(self) -> Dict[str, ProviderQuotaData]:
        """Fetch all Cursor quotas."""
        results = {}

        print("[Cursor] Starting quota fetch...")
        auth_data = self._read_auth_from_db()
        if not auth_data:
            print("[Cursor] No auth data found in database")
            return results

        email = auth_data.get("email", "cursor-user")
        access_token = auth_data.get("access_token")
        membership_type = auth_data.get("membership_type")  # e.g., "pro", "pro_student", "free"
        subscription_status = auth_data.get("subscription_status")

        if access_token:
            print(f"[Cursor] Found access token for {email}, fetching quota...")
            quota = await self._fetch_from_api(access_token, membership_type, subscription_status)
            if quota and quota.models:
                results[email] = quota
                print(f"[Cursor] Successfully fetched quota for {email}: {len(quota.models)} model(s), plan: {quota.plan_type}")
            else:
                if quota:
                    print(f"[Cursor] API returned empty quota (no models found in response)")
                else:
                    print(f"[Cursor] Failed to fetch quota from API (returned None)")
        else:
            print("[Cursor] No access token found in auth data")

        return results
