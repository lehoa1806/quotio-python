"""Operating mode models for Quotio."""

from enum import Enum
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


class OperatingMode(str, Enum):
    """Unified operating mode for Quotio."""

    MONITOR = "monitor"  # Quota tracking only (no proxy)
    LOCAL_PROXY = "local"  # Run local proxy server
    REMOTE_PROXY = "remote"  # Connect to remote CLIProxyAPI

    @property
    def display_name(self) -> str:
        """Display name for the mode."""
        return {
            self.MONITOR: "Monitor Mode",
            self.LOCAL_PROXY: "Local Proxy",
            self.REMOTE_PROXY: "Remote Proxy",
        }[self]

    @property
    def description(self) -> str:
        """Description of the mode."""
        return {
            self.MONITOR: "Track quotas without running a proxy server",
            self.LOCAL_PROXY: "Run local proxy server on this machine",
            self.REMOTE_PROXY: "Connect to a remote CLIProxyAPI instance",
        }[self]

    @property
    def supports_proxy(self) -> bool:
        """Whether proxy server functionality is available."""
        return self != self.MONITOR

    @property
    def supports_proxy_control(self) -> bool:
        """Whether local proxy controls (start/stop) should be shown."""
        return self == self.LOCAL_PROXY

    @property
    def supports_binary_upgrade(self) -> bool:
        """Whether binary upgrade UI should be shown."""
        return self == self.LOCAL_PROXY

    @property
    def supports_port_config(self) -> bool:
        """Whether port configuration should be shown."""
        return self == self.LOCAL_PROXY

    @property
    def supports_agent_config(self) -> bool:
        """Whether CLI agent configuration is available."""
        return self == self.LOCAL_PROXY


@dataclass
class RemoteConnectionConfig:
    """Configuration for remote proxy connection."""
    endpoint_url: str
    display_name: str
    verify_ssl: bool = True
    timeout_seconds: int = 30
    last_connected: Optional[datetime] = None
    id: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if config is valid."""
        return bool(self.endpoint_url and self.display_name)


@dataclass
class ConnectionStatus:
    """Connection status for remote proxy."""
    status: str  # "disconnected", "connecting", "connected", "error"
    message: Optional[str] = None
    last_error: Optional[str] = None


class OperatingModeManager:
    """Manager for operating mode state."""

    def __init__(self):
        """Initialize the mode manager."""
        from ..utils.settings import SettingsManager
        self.settings = SettingsManager()

        # Load current mode
        mode_str = self.settings.get("operatingMode", "monitor")
        try:
            self.current_mode = OperatingMode(mode_str)
        except ValueError:
            self.current_mode = OperatingMode.MONITOR

        # Load onboarding status
        self.has_completed_onboarding = self.settings.get("hasCompletedOnboarding", False)

        # Remote config
        self.remote_config: Optional[RemoteConnectionConfig] = None
        self.connection_status = ConnectionStatus("disconnected")
        self._load_remote_config()

    @property
    def is_monitor_mode(self) -> bool:
        """Check if in monitor mode."""
        return self.current_mode == OperatingMode.MONITOR

    @property
    def is_local_proxy_mode(self) -> bool:
        """Check if in local proxy mode."""
        return self.current_mode == OperatingMode.LOCAL_PROXY

    @property
    def is_remote_proxy_mode(self) -> bool:
        """Check if in remote proxy mode."""
        return self.current_mode == OperatingMode.REMOTE_PROXY

    @property
    def is_proxy_mode(self) -> bool:
        """Check if any proxy mode is active."""
        return self.current_mode != OperatingMode.MONITOR

    def set_mode(self, mode: OperatingMode):
        """Set current mode and persist."""
        self.current_mode = mode
        self.settings.set("operatingMode", mode.value)

        # Reset connection status when switching modes
        if mode != OperatingMode.REMOTE_PROXY:
            self.connection_status = ConnectionStatus("disconnected")

    def complete_onboarding(self, mode: OperatingMode):
        """Complete onboarding with selected mode."""
        self.set_mode(mode)
        self.has_completed_onboarding = True
        self.settings.set("hasCompletedOnboarding", True)

    def switch_mode(self, mode: OperatingMode, stop_proxy_if_needed=None):
        """Switch mode with cleanup actions."""
        if self.current_mode == OperatingMode.LOCAL_PROXY and mode != OperatingMode.LOCAL_PROXY:
            if stop_proxy_if_needed:
                stop_proxy_if_needed()
        self.set_mode(mode)

    def switch_to_remote(self, config: RemoteConnectionConfig, management_key: str, from_onboarding: bool = False):
        """Switch to remote mode with config."""
        self.save_remote_config(config, management_key)
        self.set_mode(OperatingMode.REMOTE_PROXY)

        if from_onboarding:
            self.has_completed_onboarding = True
            self.settings.set("hasCompletedOnboarding", True)

    def save_remote_config(self, config: RemoteConnectionConfig, management_key: str):
        """Save remote config."""
        self.remote_config = config
        import json
        config_dict = {
            "endpoint_url": config.endpoint_url,
            "display_name": config.display_name,
            "verify_ssl": config.verify_ssl,
            "timeout_seconds": config.timeout_seconds,
            "last_connected": config.last_connected.isoformat() if config.last_connected else None,
            "id": config.id,
        }
        self.settings.set("remoteConnectionConfig", config_dict)

        # Save management key securely
        try:
            import keyring
            keyring.set_password("quotio", f"remote_key_{config.id or 'default'}", management_key)
        except Exception:
            pass  # Keyring may not be available

    def _load_remote_config(self):
        """Load remote config from storage."""
        config_dict = self.settings.get("remoteConnectionConfig")
        if config_dict:
            try:
                self.remote_config = RemoteConnectionConfig(
                    endpoint_url=config_dict.get("endpoint_url", ""),
                    display_name=config_dict.get("display_name", ""),
                    verify_ssl=config_dict.get("verify_ssl", True),
                    timeout_seconds=config_dict.get("timeout_seconds", 30),
                    last_connected=datetime.fromisoformat(config_dict["last_connected"]) if config_dict.get("last_connected") else None,
                    id=config_dict.get("id"),
                )
            except Exception:
                self.remote_config = None

    def clear_remote_config(self):
        """Clear remote config."""
        if self.remote_config and self.remote_config.id:
            try:
                import keyring
                keyring.delete_password("quotio", f"remote_key_{self.remote_config.id}")
            except Exception:
                pass

        self.remote_config = None
        self.settings.remove("remoteConnectionConfig")

        if self.is_remote_proxy_mode:
            self.set_mode(OperatingMode.MONITOR)

    def set_connection_status(self, status: str, message: Optional[str] = None, error: Optional[str] = None):
        """Update connection status."""
        self.connection_status = ConnectionStatus(status, message, error)
        if status == "connected":
            # Update last connected timestamp
            if self.remote_config:
                self.remote_config.last_connected = datetime.now()
                self.save_remote_config(self.remote_config, self.get_remote_management_key() or "")

    def get_remote_management_key(self) -> Optional[str]:
        """Get management key for remote config."""
        if not self.remote_config:
            return None

        try:
            import keyring
            return keyring.get_password("quotio", f"remote_key_{self.remote_config.id or 'default'}")
        except Exception:
            return None
