"""Warmup service for Antigravity accounts (Auto Wake-up feature)."""

import asyncio
import json
import uuid
from typing import Optional, List, Dict, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

from ..models.providers import AIProvider
from ..services.api_client import ManagementAPIClient
from ..utils.settings import SettingsManager


class WarmupCadence(str, Enum):
    """Warmup cadence options (interval mode)."""
    FIFTEEN_MINUTES = "15min"
    THIRTY_MINUTES = "30min"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    THREE_HOURS = "3h"
    FOUR_HOURS = "4h"
    
    @property
    def interval_seconds(self) -> float:
        """Get interval in seconds."""
        mapping = {
            "15min": 900,
            "30min": 1800,
            "1h": 3600,
            "2h": 7200,
            "3h": 10800,
            "4h": 14400,
        }
        return mapping.get(self.value, 3600)
    
    @property
    def display_name(self) -> str:
        """Get display name."""
        return self.value


class WarmupScheduleMode(str, Enum):
    """Warmup schedule mode."""
    INTERVAL = "interval"  # Run at regular intervals
    DAILY = "daily"  # Run once per day at a specific time


@dataclass
class WarmupStatus:
    """Status of warmup operation."""
    is_running: bool = False
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    progress_total: int = 0
    progress_completed: int = 0
    current_model: Optional[str] = None
    model_states: Dict[str, str] = field(default_factory=dict)  # pending, running, succeeded, failed
    last_error: Optional[str] = None


@dataclass
class WarmupAccountKey:
    """Key for identifying a warmup account."""
    provider: AIProvider
    account_key: str
    
    def to_id(self) -> str:
        """Convert to account ID string."""
        return f"{self.provider.value}::{self.account_key}"
    
    @classmethod
    def from_id(cls, account_id: str) -> Optional['WarmupAccountKey']:
        """Parse from account ID string."""
        if "::" not in account_id:
            return None
        parts = account_id.split("::", 1)
        if len(parts) != 2:
            return None
        provider_str, account_key = parts
        try:
            provider = AIProvider(provider_str)
            return cls(provider=provider, account_key=account_key)
        except ValueError:
            return None


@dataclass
class WarmupSettings:
    """Warmup settings manager (matches WarmupSettingsManager)."""
    
    settings: SettingsManager = field(default_factory=SettingsManager)
    
    # Callbacks for settings changes
    on_enabled_accounts_changed: Optional[Callable[[set], None]] = None
    on_warmup_cadence_changed: Optional[Callable[[WarmupCadence], None]] = None
    on_warmup_schedule_changed: Optional[Callable[[], None]] = None
    
    @property
    def enabled_account_ids(self) -> set:
        """Get enabled account IDs."""
        accounts = self.settings.get("warmupEnabledAccounts", [])
        if isinstance(accounts, list):
            return set(accounts)
        return set()
    
    @enabled_account_ids.setter
    def enabled_account_ids(self, value: set):
        """Set enabled account IDs."""
        self.settings.set("warmupEnabledAccounts", sorted(list(value)))
        if self.on_enabled_accounts_changed:
            self.on_enabled_accounts_changed(value)
    
    def is_enabled(self, provider: AIProvider, account_key: str) -> bool:
        """Check if warmup is enabled for an account."""
        if provider != AIProvider.ANTIGRAVITY:
            return False
        account_id = WarmupAccountKey(provider, account_key).to_id()
        return account_id in self.enabled_account_ids
    
    def toggle(self, provider: AIProvider, account_key: str):
        """Toggle warmup for an account."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        account_id = WarmupAccountKey(provider, account_key).to_id()
        accounts = self.enabled_account_ids.copy()
        if account_id in accounts:
            accounts.remove(account_id)
        else:
            accounts.add(account_id)
        self.enabled_account_ids = accounts
    
    def set_enabled(self, enabled: bool, provider: AIProvider, account_key: str):
        """Set warmup enabled state."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        account_id = WarmupAccountKey(provider, account_key).to_id()
        accounts = self.enabled_account_ids.copy()
        if enabled:
            accounts.add(account_id)
        else:
            accounts.discard(account_id)
        self.enabled_account_ids = accounts
    
    def warmup_cadence(self, provider: AIProvider, account_key: str) -> WarmupCadence:
        """Get warmup cadence for an account (per-account or default)."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        cadence_by_account = self.settings.get("warmupCadenceByAccount", {})
        if isinstance(cadence_by_account, dict) and account_id in cadence_by_account:
            try:
                return WarmupCadence(cadence_by_account[account_id])
            except ValueError:
                pass
        # Default cadence
        cadence_str = self.settings.get("warmupCadence", WarmupCadence.ONE_HOUR.value)
        try:
            return WarmupCadence(cadence_str)
        except ValueError:
            return WarmupCadence.ONE_HOUR
    
    def set_warmup_cadence(self, cadence: WarmupCadence, provider: AIProvider, account_key: str):
        """Set warmup cadence for an account."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        cadence_by_account = self.settings.get("warmupCadenceByAccount", {})
        if not isinstance(cadence_by_account, dict):
            cadence_by_account = {}
        cadence_by_account[account_id] = cadence.value
        self.settings.set("warmupCadenceByAccount", cadence_by_account)
        if self.on_warmup_cadence_changed:
            self.on_warmup_cadence_changed(cadence)
    
    def warmup_schedule_mode(self, provider: AIProvider, account_key: str) -> WarmupScheduleMode:
        """Get warmup schedule mode for an account."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        mode_by_account = self.settings.get("warmupScheduleModeByAccount", {})
        if isinstance(mode_by_account, dict) and account_id in mode_by_account:
            try:
                return WarmupScheduleMode(mode_by_account[account_id])
            except ValueError:
                pass
        # Default mode
        mode_str = self.settings.get("warmupScheduleMode", WarmupScheduleMode.INTERVAL.value)
        try:
            return WarmupScheduleMode(mode_str)
        except ValueError:
            return WarmupScheduleMode.INTERVAL
    
    def set_warmup_schedule_mode(self, mode: WarmupScheduleMode, provider: AIProvider, account_key: str):
        """Set warmup schedule mode for an account."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        mode_by_account = self.settings.get("warmupScheduleModeByAccount", {})
        if not isinstance(mode_by_account, dict):
            mode_by_account = {}
        mode_by_account[account_id] = mode.value
        self.settings.set("warmupScheduleModeByAccount", mode_by_account)
        if self.on_warmup_schedule_changed:
            self.on_warmup_schedule_changed()
    
    def warmup_daily_minutes(self, provider: AIProvider, account_key: str) -> int:
        """Get daily warmup time in minutes (0-1439)."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        minutes_by_account = self.settings.get("warmupDailyMinutesByAccount", {})
        if isinstance(minutes_by_account, dict) and account_id in minutes_by_account:
            return min(max(minutes_by_account[account_id], 0), 1439)
        # Default: 540 minutes = 9:00 AM
        return self.settings.get("warmupDailyMinutes", 540)
    
    def set_warmup_daily_minutes(self, minutes: int, provider: AIProvider, account_key: str):
        """Set daily warmup time in minutes (0-1439)."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        minutes_by_account = self.settings.get("warmupDailyMinutesByAccount", {})
        if not isinstance(minutes_by_account, dict):
            minutes_by_account = {}
        minutes_by_account[account_id] = min(max(minutes, 0), 1439)
        self.settings.set("warmupDailyMinutesByAccount", minutes_by_account)
        if self.on_warmup_schedule_changed:
            self.on_warmup_schedule_changed()
    
    def warmup_daily_time(self, provider: AIProvider, account_key: str) -> datetime:
        """Get daily warmup time as datetime (today with specified time)."""
        minutes = self.warmup_daily_minutes(provider, account_key)
        now = datetime.now()
        hour = minutes // 60
        minute = minutes % 60
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    def set_warmup_daily_time(self, time: datetime, provider: AIProvider, account_key: str):
        """Set daily warmup time from datetime."""
        minutes = time.hour * 60 + time.minute
        self.set_warmup_daily_minutes(minutes, provider, account_key)
    
    def selected_models(self, provider: AIProvider, account_key: str) -> List[str]:
        """Get selected models for an account."""
        if provider != AIProvider.ANTIGRAVITY:
            return []
        account_id = WarmupAccountKey(provider, account_key).to_id()
        models_by_account = self.settings.get("warmupSelectedModels", {})
        if isinstance(models_by_account, dict):
            return models_by_account.get(account_id, [])
        return []
    
    def has_stored_selection(self, provider: AIProvider, account_key: str) -> bool:
        """Check if there's a stored model selection for an account."""
        account_id = WarmupAccountKey(provider, account_key).to_id()
        models_by_account = self.settings.get("warmupSelectedModels", {})
        return isinstance(models_by_account, dict) and account_id in models_by_account
    
    def set_selected_models(self, models: List[str], provider: AIProvider, account_key: str):
        """Set selected models for an account."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        account_id = WarmupAccountKey(provider, account_key).to_id()
        models_by_account = self.settings.get("warmupSelectedModels", {})
        if not isinstance(models_by_account, dict):
            models_by_account = {}
        models_by_account[account_id] = models
        self.settings.set("warmupSelectedModels", models_by_account)
    
    def excluded_account_ids(self) -> set:
        """Get excluded account IDs (accounts removed from warmup list)."""
        accounts = self.settings.get("warmupExcludedAccounts", [])
        if isinstance(accounts, list):
            return set(accounts)
        return set()
    
    def set_excluded_account_ids(self, value: set):
        """Set excluded account IDs."""
        self.settings.set("warmupExcludedAccounts", sorted(list(value)))
    
    def exclude_account(self, provider: AIProvider, account_key: str):
        """Exclude an account from the warmup list."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        account_id = WarmupAccountKey(provider, account_key).to_id()
        excluded = self.excluded_account_ids()
        excluded.add(account_id)
        self.set_excluded_account_ids(excluded)
    
    def include_account(self, provider: AIProvider, account_key: str):
        """Include an account back in the warmup list."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        account_id = WarmupAccountKey(provider, account_key).to_id()
        excluded = self.excluded_account_ids()
        excluded.discard(account_id)
        self.set_excluded_account_ids(excluded)
    
    def is_excluded(self, provider: AIProvider, account_key: str) -> bool:
        """Check if an account is excluded from the warmup list."""
        if provider != AIProvider.ANTIGRAVITY:
            return False
        account_id = WarmupAccountKey(provider, account_key).to_id()
        return account_id in self.excluded_account_ids()


class WarmupService:
    """Service for executing warmup operations (Auto Wake-up for Antigravity)."""
    
    # Antigravity base URLs to try
    ANTIGRAVITY_BASE_URLS = [
        "https://daily-cloudcode-pa.googleapis.com",
        "https://daily-cloudcode-pa.sandbox.googleapis.com",
        "https://cloudcode-pa.googleapis.com"
    ]
    
    def __init__(self, api_client: Optional[ManagementAPIClient] = None):
        """Initialize warmup service."""
        self.api_client = api_client
    
    def _map_antigravity_model_alias(self, model: str) -> str:
        """Map Antigravity model alias to actual model name."""
        mapping = {
            "gemini-3-pro-preview": "gemini-3-pro-high",
            "gemini-3-flash-preview": "gemini-3-flash",
            "gemini-2.5-flash-preview": "gemini-2.5-flash",
            "gemini-2.5-flash-lite-preview": "gemini-2.5-flash-lite",
            "gemini-2.5-pro-preview": "gemini-2.5-pro",
            "gemini-claude-sonnet-4-5": "claude-sonnet-4-5",
            "gemini-claude-sonnet-4-5-thinking": "claude-sonnet-4-5-thinking",
            "gemini-claude-opus-4-5-thinking": "claude-opus-4-5-thinking",
            "gemini-2.5-computer-use-preview-10-2025": "rev19-uic3-1p",
            "gemini-3-pro-image-preview": "gemini-3-pro-image",
        }
        return mapping.get(model.lower(), model)
    
    async def warmup(
        self,
        management_client: ManagementAPIClient,
        auth_index: str,
        model: str
    ) -> None:
        """Execute warmup for a specific model (matches original implementation).
        
        Args:
            management_client: ManagementAPIClient instance
            auth_index: Auth file index
            model: Model name to warmup
            
        Raises:
            Exception if warmup fails
        """
        upstream_model = self._map_antigravity_model_alias(model)
        
        # Create warmup payload
        project_id = "warmup-" + str(uuid.uuid4())[:5].lower()
        request_id = "agent-" + str(uuid.uuid4()).lower()
        session_id = "-" + str(uuid.uuid4())[:12]
        
        payload = {
            "project": project_id,
            "requestId": request_id,
            "userAgent": "antigravity",
            "model": upstream_model,
            "request": {
                "sessionId": session_id,
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": "."}]
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": 1
                }
            }
        }
        
        body = json.dumps(payload)
        
        # Try each base URL
        last_error = None
        for base_url in self.ANTIGRAVITY_BASE_URLS:
            try:
                url = base_url + "/v1internal:generateContent"
                headers = {
                    "Authorization": "Bearer $TOKEN$",
                    "Content-Type": "application/json",
                    "User-Agent": "antigravity/1.104.0"
                }
                
                response = await management_client.api_call(
                    auth_index=auth_index,
                    method="POST",
                    url=url,
                    headers=headers,
                    data=body
                )
                
                status_code = response.get("status_code", 0)
                if 200 <= status_code < 300:
                    return  # Success
                
                last_error = f"HTTP {status_code}: {response.get('body', '')}"
            except Exception as e:
                last_error = str(e)
                continue
        
        # All URLs failed
        if last_error:
            raise Exception(f"Warmup failed: {last_error}")
        raise Exception("Warmup failed: Invalid response")
    
    async def fetch_models(
        self,
        management_client: ManagementAPIClient,
        auth_file_name: str
    ) -> List[dict]:
        """Fetch available models for an auth file.
        
        Args:
            management_client: ManagementAPIClient instance
            auth_file_name: Auth file name
            
        Returns:
            List of model info dicts with 'id', 'owned_by', 'type' keys
        """
        models = await management_client.fetch_auth_file_models(auth_file_name)
        return [
            {
                "id": m.get("id", ""),
                "owned_by": m.get("owned_by"),
                "type": m.get("type")
            }
            for m in models
        ]
    
    async def warmup_account(
        self,
        management_client: ManagementAPIClient,
        provider: AIProvider,
        account_key: str,
        auth_index: str,
        models: List[str],
        status_callback: Optional[Callable[[WarmupStatus], None]] = None
    ) -> WarmupStatus:
        """Execute warmup for an account with multiple models (matches original implementation).
        
        Args:
            management_client: ManagementAPIClient instance
            provider: AI Provider (must be ANTIGRAVITY)
            account_key: Account identifier
            auth_index: Auth file index
            models: List of model IDs to warmup
            status_callback: Optional callback for status updates
            
        Returns:
            WarmupStatus with results
        """
        if provider != AIProvider.ANTIGRAVITY:
            return WarmupStatus()
        
        status = WarmupStatus()
        status.is_running = True
        status.progress_total = len(models)
        status.progress_completed = 0
        status.last_error = None
        
        # Initialize model states
        for model in models:
            status.model_states[model] = "pending"
        
        if status_callback:
            status_callback(status)
        
        for model in models:
            status.current_model = model
            status.model_states[model] = "running"
            
            if status_callback:
                status_callback(status)
            
            try:
                await self.warmup(management_client, auth_index, model)
                status.progress_completed += 1
                status.model_states[model] = "succeeded"
            except Exception as e:
                status.progress_completed += 1
                status.model_states[model] = "failed"
                status.last_error = str(e)
            
            if status_callback:
                status_callback(status)
        
        status.is_running = False
        status.current_model = None
        status.last_run = datetime.now()
        
        return status
