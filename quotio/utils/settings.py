"""Settings persistence manager.

All config keys used across the app. Each key is persisted on set() and loaded
from settings.json at startup (when SettingsManager is first created).
"""
import json
import os
import platform
from pathlib import Path
from typing import Any, Optional

# Registry of all persisted config keys (for documentation and validation)
CONFIG_KEYS = {
    # Proxy
    "proxyPort",
    "autoStartProxy",
    "autoRestartProxy",
    # Operating mode
    "operatingMode",
    "hasCompletedOnboarding",
    "remoteConnectionConfig",
    # UI
    "showLogsTab",
    "showCustomProvidersTab",
    "autoRefreshEnabled",
    "autoRefreshIntervalMinutes",
    # Dashboard
    "quotaFavorites",
    "ignoredModels",
    "quotaProviderFilter",
    "quotaAccountFilter",
    "quotaModelFilter",
    # Warmup
    "warmupEnabledAccounts",
    "warmupCadence",
    "warmupCadenceByAccount",
    "warmupScheduleMode",
    "warmupScheduleModeByAccount",
    "warmupDailyMinutes",
    "warmupDailyMinutesByAccount",
    "warmupSelectedModels",
    "warmupExcludedAccounts",
    # IDE scan
    "ideScanOptions",
    "ideAutoScanAtStartup",
    "ideScanAutoScanMode",
    "ideScanAutoScan",
    "ideScanResult",
    # Custom providers
    "customProviders",
}


class SettingsManager:
    """Manages application settings persistence."""

    def __init__(self, app_name: str = "Quotio"):
        """Initialize settings manager."""
        system = platform.system()
        if system == "Darwin":  # macOS
            config_dir = Path.home() / "Library" / "Preferences"
        elif system == "Windows":
            config_dir = Path.home() / "AppData" / "Local" / app_name
        else:  # Linux
            config_dir = Path.home() / ".config" / app_name

        config_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = config_dir / "settings.json"
        self._settings: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load settings from file."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r") as f:
                    self._settings = json.load(f)
            except Exception:
                self._settings = {}
        else:
            self._settings = {}

    def _save(self):
        """Save settings to file."""
        try:
            # Set restrictive permissions
            old_umask = os.umask(0o077)
            try:
                with open(self.settings_file, "w") as f:
                    json.dump(self._settings, f, indent=2)
                os.chmod(self.settings_file, 0o600)
            finally:
                os.umask(old_umask)
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        """Set a setting value."""
        self._settings[key] = value
        self._save()

    def delete(self, key: str):
        """Delete a setting."""
        if key in self._settings:
            del self._settings[key]
            self._save()

    def remove(self, key: str):
        """Remove a setting (alias for delete)."""
        self.delete(key)

    def clear(self):
        """Clear all settings."""
        self._settings = {}
        self._save()
