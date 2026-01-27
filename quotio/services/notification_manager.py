"""Notification manager for quota alerts and proxy events."""

import platform
from typing import Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from ..utils.settings import SettingsManager


class NotificationType(str, Enum):
    """Notification types."""
    QUOTA_LOW = "quotaLow"
    ACCOUNT_COOLING = "accountCooling"
    PROXY_CRASHED = "proxyCrashed"
    PROXY_STARTED = "proxyStarted"
    PROXY_STOPPED = "proxyStopped"
    UPGRADE_AVAILABLE = "upgradeAvailable"
    UPGRADE_SUCCESS = "upgradeSuccess"
    UPGRADE_FAILED = "upgradeFailed"
    ROLLBACK = "rollback"


@dataclass
class NotificationManager:
    """Manages system notifications for quota alerts and proxy events."""

    settings: SettingsManager = field(default_factory=SettingsManager)
    _sent_notifications: Set[str] = field(default_factory=set)
    _is_authorized: bool = False

    def __post_init__(self):
        """Initialize notification manager."""
        self._check_authorization()

    def _check_authorization(self):
        """Check if notifications are authorized."""
        if platform.system() == "Darwin":  # macOS
            try:
                import subprocess
                result = subprocess.run(
                    ["defaults", "read", "com.apple.ncprefs", "apps"],
                    capture_output=True,
                    text=True
                )
                # On macOS, we'll request permission when needed
                self._is_authorized = True  # Assume authorized, will request if needed
            except Exception:
                self._is_authorized = False
        else:
            # For Linux/Windows, use platform-specific notification systems
            self._is_authorized = True

    @property
    def notifications_enabled(self) -> bool:
        """Whether notifications are enabled."""
        return self.settings.get("notificationsEnabled", True)

    @notifications_enabled.setter
    def notifications_enabled(self, value: bool):
        """Set notifications enabled."""
        self.settings.set("notificationsEnabled", value)

    @property
    def quota_alert_threshold(self) -> float:
        """Quota alert threshold percentage."""
        threshold = self.settings.get("quotaAlertThreshold", 20.0)
        return float(threshold) if threshold else 20.0

    @quota_alert_threshold.setter
    def quota_alert_threshold(self, value: float):
        """Set quota alert threshold."""
        self.settings.set("quotaAlertThreshold", value)

    @property
    def notify_on_quota_low(self) -> bool:
        """Whether to notify on low quota."""
        return self.settings.get("notifyOnQuotaLow", True)

    @notify_on_quota_low.setter
    def notify_on_quota_low(self, value: bool):
        """Set notify on quota low."""
        self.settings.set("notifyOnQuotaLow", value)

    @property
    def notify_on_cooling(self) -> bool:
        """Whether to notify on account cooling."""
        return self.settings.get("notifyOnCooling", True)

    @notify_on_cooling.setter
    def notify_on_cooling(self, value: bool):
        """Set notify on cooling."""
        self.settings.set("notifyOnCooling", value)

    @property
    def notify_on_proxy_crash(self) -> bool:
        """Whether to notify on proxy crash."""
        return self.settings.get("notifyOnProxyCrash", True)

    @notify_on_proxy_crash.setter
    def notify_on_proxy_crash(self, value: bool):
        """Set notify on proxy crash."""
        self.settings.set("notifyOnProxyCrash", value)

    def request_authorization(self) -> bool:
        """Request notification authorization."""
        if platform.system() == "Darwin":
            try:
                import subprocess
                # On macOS, we can use osascript to send notifications
                # For proper authorization, user needs to grant in System Preferences
                self._is_authorized = True
                return True
            except Exception:
                return False
        else:
            self._is_authorized = True
            return True

    def send_notification(
        self,
        title: str,
        body: str,
        notification_type: Optional[NotificationType] = None
    ) -> bool:
        """Send a system notification."""
        if not self.notifications_enabled or not self._is_authorized:
            return False

        system = platform.system()

        if system == "Darwin":  # macOS
            return self._send_macos_notification(title, body)
        elif system == "Linux":
            return self._send_linux_notification(title, body)
        elif system == "Windows":
            return self._send_windows_notification(title, body)
        else:
            return False

    def _send_macos_notification(self, title: str, body: str) -> bool:
        """Send notification on macOS using osascript."""
        try:
            import subprocess
            script = f'''
            display notification "{body}" with title "{title}"
            '''
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                check=True
            )
            return True
        except Exception:
            return False

    def _send_linux_notification(self, title: str, body: str) -> bool:
        """Send notification on Linux using notify-send."""
        try:
            import subprocess
            subprocess.run(
                ["notify-send", title, body],
                capture_output=True,
                check=True
            )
            return True
        except Exception:
            return False

    def _send_windows_notification(self, title: str, body: str) -> bool:
        """Send notification on Windows using win10toast or similar."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, body, duration=5)
            return True
        except Exception:
            return False

    def notify_quota_low(
        self,
        provider: str,
        account: str,
        percentage: float
    ) -> bool:
        """Notify when quota is low."""
        if not self.notify_on_quota_low:
            return False

        # Prevent duplicate notifications
        notification_id = f"quota_low_{provider}_{account}"
        if notification_id in self._sent_notifications:
            return False

        if percentage <= self.quota_alert_threshold:
            title = f"Low Quota: {provider}"
            body = f"{account} has {percentage:.1f}% quota remaining"

            if self.send_notification(title, body, NotificationType.QUOTA_LOW):
                self._sent_notifications.add(notification_id)
                return True

        return False

    def notify_account_cooling(
        self,
        provider: str,
        account: str
    ) -> bool:
        """Notify when account is cooling."""
        if not self.notify_on_cooling:
            return False

        notification_id = f"cooling_{provider}_{account}"
        if notification_id in self._sent_notifications:
            return False

        title = f"Account Cooling: {provider}"
        body = f"{account} is in cooling period"

        if self.send_notification(title, body, NotificationType.ACCOUNT_COOLING):
            self._sent_notifications.add(notification_id)
            return True

        return False

    def notify_proxy_crashed(self) -> bool:
        """Notify when proxy crashes."""
        if not self.notify_on_proxy_crash:
            return False

        notification_id = "proxy_crashed"
        if notification_id in self._sent_notifications:
            return False

        title = "Proxy Crashed"
        body = "The proxy server has stopped unexpectedly"

        if self.send_notification(title, body, NotificationType.PROXY_CRASHED):
            self._sent_notifications.add(notification_id)
            return True

        return False

    def notify_proxy_started(self) -> bool:
        """Notify when proxy starts."""
        title = "Proxy Started"
        body = "The proxy server is now running"
        return self.send_notification(title, body, NotificationType.PROXY_STARTED)

    def notify_proxy_stopped(self) -> bool:
        """Notify when proxy stops."""
        title = "Proxy Stopped"
        body = "The proxy server has stopped"
        return self.send_notification(title, body, NotificationType.PROXY_STOPPED)

    def clear_notification_tracking(self, notification_id: Optional[str] = None):
        """Clear notification tracking."""
        if notification_id:
            self._sent_notifications.discard(notification_id)
        else:
            self._sent_notifications.clear()

    def clear_cooling_notification(self, provider: str, account: str):
        """Clear cooling notification tracking."""
        notification_id = f"cooling_{provider}_{account}"
        self._sent_notifications.discard(notification_id)

    def clear_quota_low_notification(self, provider: str, account: str):
        """Clear quota low notification tracking."""
        notification_id = f"quota_low_{provider}_{account}"
        self._sent_notifications.discard(notification_id)
