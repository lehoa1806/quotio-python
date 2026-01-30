"""
QuotaViewModel - Central state management for quotas and proxy.

WORKFLOW OVERVIEW:
==================
This is the central state management class (MVVM pattern). It coordinates:
- Proxy lifecycle (start/stop)
- Quota fetching from all providers
- OAuth authentication flows
- Settings management
- Background services (warmup, usage stats polling)

ARCHITECTURE:
The view model acts as the single source of truth for application state.
UI screens observe the view model and update when data changes. User actions
in the UI trigger async operations in the view model.

KEY WORKFLOWS:
1. Initialization:
   - Loads settings from disk
   - Determines operating mode (Local Proxy, Remote Proxy, Monitor Mode)
   - If auto-start enabled: downloads binary, starts proxy
   - Sets up API client connection
   - Loads auth files and fetches quotas

2. Quota Refresh:
   - Fetches quotas from all providers in parallel
   - Updates provider_quotas dictionary
   - Notifies UI screens via callbacks
   - Handles errors gracefully (continues with other providers)

3. OAuth Flow:
   - Gets OAuth URL from proxy API
   - Opens browser for user authentication
   - Polls for completion
   - Refreshes data after successful auth

4. Proxy Management:
   - Starts proxy: downloads binary if needed, starts process, connects API client
   - Stops proxy: stops process, closes API client, stops background services
   - Monitors proxy health and handles crashes

5. Background Services:
   - Usage stats polling: fetches request/token stats every 10 seconds
   - Warmup scheduler: runs warmup cycles for Antigravity accounts
   - Request tracker: tracks request history
"""

import asyncio
import platform
from typing import Optional, Dict, List, Callable, Tuple, Union
from concurrent.futures import Future as ConcurrentFuture
import concurrent.futures
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..models.providers import AIProvider
from ..models.auth import AuthFile, OAuthState, OAuthStatus
from ..models.proxy import ProxyStatus
from ..models.operating_mode import OperatingMode, OperatingModeManager
from ..models.subscription import SubscriptionInfo
from ..models.usage_stats import UsageStats
from ..services.proxy_manager import CLIProxyManager
from ..services.api_client import ManagementAPIClient, APIError
from ..services.quota_fetchers.base import ProviderQuotaData
from ..services.notification_manager import NotificationManager, NotificationType
from ..services.warmup_service import WarmupService, WarmupSettings, WarmupStatus, WarmupAccountKey, WarmupCadence, WarmupScheduleMode
from ..services.request_tracker import RequestTracker
from ..services.custom_provider_service import CustomProviderService
from ..services.ide_scan_service import IDEScanService, IDEScanOptions, IDEScanResult
from ..services.antigravity_switcher import AntigravityAccountSwitcher
from ..services.direct_auth_file_service import DirectAuthFileService, DirectAuthFile
from ..utils.browser import open_browser
from ..utils.settings import SettingsManager
from ..ui.utils import log_with_timestamp


@dataclass
class QuotaViewModel:
    """
    View model for quota management and proxy control.

    This is the central state management class following the MVVM pattern.
    It holds all application state and provides methods for UI screens to
    interact with the proxy and fetch quota data.

    STATE MANAGEMENT:
    - provider_quotas: Dict[AIProvider, Dict[account_key, ProviderQuotaData]]
      Stores quota data for all providers and accounts
    - auth_files: List of auth files managed by the proxy
    - proxy_status: Current proxy running state
    - usage_stats: Request and token usage statistics
    - subscription_infos: Subscription information per provider/account

    UI INTEGRATION:
    UI screens register callbacks via register_quota_update_callback().
    When quotas are updated, all registered callbacks are notified to refresh
    their displays. This ensures UI stays in sync with data.
    """

    # Proxy management
    proxy_manager: CLIProxyManager = field(default_factory=CLIProxyManager)
    api_client: Optional[ManagementAPIClient] = None

    # UI update callbacks (for notifying screens when data changes)
    _quota_update_callbacks: List[Callable] = field(default_factory=list, init=False, repr=False)
    _pending_notification: bool = field(default=False, init=False, repr=False)

    def register_quota_update_callback(self, callback: Callable):
        """Register a callback to be called when quotas are updated."""
        if callback not in self._quota_update_callbacks:
            self._quota_update_callbacks.append(callback)
            print(f"[QuotaViewModel] Registered quota update callback: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    def unregister_quota_update_callback(self, callback: Callable):
        """Unregister a quota update callback."""
        if callback in self._quota_update_callbacks:
            self._quota_update_callbacks.remove(callback)
            print(f"[QuotaViewModel] Unregistered quota update callback: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    def _notify_quota_updated(self):
        """Notify all registered callbacks that quotas have been updated.

        This method is safe to call from any thread - it will schedule the work
        on the main Qt thread using call_on_main_thread.
        """
        from ..ui.utils import call_on_main_thread
        from PyQt6.QtCore import QTimer, QThread
        from PyQt6.QtWidgets import QApplication

        if not self._quota_update_callbacks:
            log_with_timestamp("No quota update callbacks registered", "[QuotaViewModel]")
            return

        log_with_timestamp(f"Notifying {len(self._quota_update_callbacks)} callback(s) of quota update", "[QuotaViewModel]")

        # Check if we're on the main thread
        app = QApplication.instance()
        on_main_thread = False
        if app is not None:
            current_thread = QThread.currentThread()
            app_thread = app.thread()
            on_main_thread = (current_thread == app_thread)
            log_with_timestamp(f"Current thread: {current_thread}, App thread: {app_thread}, On main: {on_main_thread}", "[QuotaViewModel]")

        # Schedule the notification work on the main thread
        # This ensures QTimer.singleShot is called from the correct thread
        def schedule_notifications():
            log_with_timestamp("schedule_notifications() called on main thread", "[QuotaViewModel]")
            # Schedule each callback separately with a small delay to prevent blocking
            # This allows the UI to remain responsive
            for i, callback in enumerate(self._quota_update_callbacks):
                def make_callback(cb, idx):
                    def scheduled_callback():
                        try:
                            log_with_timestamp(f"Calling callback {idx}: {cb.__name__ if hasattr(cb, '__name__') else cb}", "[QuotaViewModel]")
                            cb()
                            log_with_timestamp(f"Callback {idx} completed", "[QuotaViewModel]")
                        except Exception as e:
                            log_with_timestamp(f"Error calling quota update callback {idx}: {e}", "[QuotaViewModel]")
                            import traceback
                            traceback.print_exc()
                    return scheduled_callback

                # Stagger callbacks with small delays to prevent blocking
                delay = i * 50  # 50ms between each callback
                log_with_timestamp(f"Scheduling callback {i} with delay {delay}ms", "[QuotaViewModel]")
                QTimer.singleShot(delay, make_callback(callback, i))

            # After scheduling all callbacks, force event processing to ensure UI updates immediately
            # This is critical for ensuring quotas are visible without user interaction
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

        if on_main_thread:
            # Already on main thread - schedule directly with QTimer
            log_with_timestamp("Already on main thread, scheduling notifications directly", "[QuotaViewModel]")
            schedule_notifications()
        else:
            # Not on main thread - use call_on_main_thread to schedule on main thread
            # Then schedule_notifications will use QTimer to stagger the callbacks
            log_with_timestamp("Not on main thread, using call_on_main_thread to schedule", "[QuotaViewModel]")
            # Use call_on_main_thread to ensure schedule_notifications runs on main thread
            # where QTimer.singleShot will work correctly
            call_on_main_thread(schedule_notifications)

    # State
    current_page: str = "dashboard"
    auth_files: List[AuthFile] = field(default_factory=list)
    provider_quotas: Dict[AIProvider, Dict[str, ProviderQuotaData]] = field(default_factory=dict)
    api_keys: List[str] = field(default_factory=list)
    usage_stats: Optional[UsageStats] = None
    # Direct auth files for quota-only mode
    direct_auth_files: List[DirectAuthFile] = field(default_factory=list)
    # Subscription info per provider per account (provider -> email -> SubscriptionInfo)
    subscription_infos: Dict[AIProvider, Dict[str, SubscriptionInfo]] = field(default_factory=dict)

    # Loading states
    isLoading: bool = False
    isLoadingQuotas: bool = False
    error_message: Optional[str] = None

    # OAuth state
    oauth_state: Optional[OAuthState] = None

    # Last refresh time
    last_quota_refresh_time: Optional[datetime] = None

    # Task tracking for cancellation
    _start_proxy_task: Optional[asyncio.Task] = None

    # Status message for UI
    status_message: Optional[str] = None

    # Advanced features
    notification_manager: NotificationManager = field(default_factory=NotificationManager)
    warmup_service: Optional[WarmupService] = None
    warmup_settings: WarmupSettings = field(default_factory=WarmupSettings)
    warmup_statuses: Dict[str, WarmupStatus] = field(default_factory=dict)

    # Warmup scheduling
    # Can be either asyncio.Task (when created in async context) or concurrent.futures.Future (when scheduled via run_async_coro)
    _warmup_task: Optional[Union[asyncio.Task, concurrent.futures.Future]] = None
    _warmup_next_run: Dict[str, datetime] = field(default_factory=dict)
    _is_warmup_running: bool = False
    _warmup_running_accounts: set = field(default_factory=set)
    _warmup_model_cache: Dict[str, Tuple[List[dict], datetime]] = field(default_factory=dict)
    _warmup_model_cache_ttl: float = 28800  # 8 hours

    # Operating mode
    mode_manager: OperatingModeManager = field(default_factory=OperatingModeManager)

    # Request tracking
    request_tracker: RequestTracker = field(default_factory=RequestTracker)

    # Custom providers
    custom_provider_service: CustomProviderService = field(default_factory=CustomProviderService)

    # IDE scan
    ide_scan_service: IDEScanService = field(default_factory=IDEScanService)
    ide_scan_result: Optional[IDEScanResult] = None

    # Antigravity account switching
    antigravity_switcher: AntigravityAccountSwitcher = field(default_factory=AntigravityAccountSwitcher)

    # Direct auth file service
    direct_auth_service: DirectAuthFileService = field(default_factory=DirectAuthFileService)

    # Usage stats polling
    _usage_stats_task: Optional[asyncio.Task] = None
    _usage_stats_polling_active: bool = False
    _last_proxy_restart_attempt: Optional[float] = None  # Timestamp of last restart attempt

    def __post_init__(self):
        """Initialize after creation."""
        # Setup settings manager
        self.settings = SettingsManager()
        # Load auto-start setting
        self._auto_start = self.settings.get("autoStartProxy", False)
        # Initialize warmup service
        self.warmup_service = WarmupService()

        # Setup warmup callbacks
        self._setup_warmup_callbacks()

    async def initialize(self):
        """
        Initialize the view model.

        WORKFLOW:
        This is called when the application starts. It:
        1. Loads direct auth files (for quota-only mode)
        2. Determines operating mode and initializes accordingly:
           - Monitor Mode: Load quotas directly (no proxy needed)
           - Remote Proxy Mode: Connect to remote proxy server
           - Local Proxy Mode: Load quotas, optionally auto-start proxy
        3. If auto-start enabled: Downloads binary if needed, starts proxy
        4. Sets up API client connection
        5. Loads auth files and fetches quotas from all providers

        This method is async because it performs network operations and
        file I/O that should not block the UI thread.
        """
        self.isLoading = True
        self.status_message = "Initializing..."
        try:
            # Load direct auth files immediately (fast filesystem scan)
            # These are auth files stored directly on disk (for quota-only mode)
            await self.load_direct_auth_files()

            # Initialize based on operating mode
            # If auto-start is enabled but mode is monitor, switch to local (user had proxy running)
            if self.mode_manager.is_monitor_mode and self._auto_start:
                print("[QuotaViewModel] Auto-start enabled but mode is monitor - switching to Local Proxy")
                self.mode_manager.set_mode(OperatingMode.LOCAL_PROXY)

            if self.mode_manager.is_monitor_mode:
                # Monitor mode - load quotas directly without proxy
                # This mode is for quota monitoring only, no proxy routing
                self.status_message = "Loading quota data (monitor mode)..."
                await self.refresh_quotas_unified()
            elif self.mode_manager.is_remote_proxy_mode:
                # Remote proxy mode - connect to remote proxy server
                # The proxy is running on a remote machine, we just connect to it
                self.status_message = "Connecting to remote proxy..."
                await self._initialize_remote_mode()
            else:
                # Local proxy mode - standard initialization
                # This is the default mode where we run the proxy locally
                self.status_message = "Loading quota data..."
                await self.refresh_quotas_unified()

                # Check if proxy should auto-start
                # Auto-start is a user setting that starts the proxy automatically on launch
                if self._auto_start:
                    if not self.proxy_manager.is_binary_installed:
                        self.status_message = "Downloading proxy binary..."
                        print("[QuotaViewModel] Auto-start enabled but binary not installed, downloading...")
                        try:
                            await self.proxy_manager.download_and_install_binary()
                            print("[QuotaViewModel] Binary download completed")
                        except Exception as e:
                            error_msg = f"Failed to download proxy binary: {str(e)}"
                            print(f"[QuotaViewModel] {error_msg}")
                            self.error_message = error_msg
                            self.status_message = f"Error: {error_msg}"
                            return

                    if self.proxy_manager.is_binary_installed:
                        self.status_message = "Auto-starting proxy..."
                        print("[QuotaViewModel] Auto-starting proxy...")
                        try:
                            await self.start_proxy()
                            if self.proxy_manager.proxy_status.running:
                                print("[QuotaViewModel] Proxy auto-started successfully")
                            else:
                                error_msg = self.proxy_manager.last_error or "Proxy failed to start"
                                print(f"[QuotaViewModel] Auto-start failed: {error_msg}")
                                self.error_message = f"Auto-start failed: {error_msg}"
                                self.status_message = f"Auto-start failed: {error_msg}"
                        except Exception as e:
                            error_msg = f"Auto-start error: {str(e)}"
                            print(f"[QuotaViewModel] {error_msg}")
                            import traceback
                            traceback.print_exc()
                            self.error_message = error_msg
                            self.status_message = f"Error: {error_msg}"
                    else:
                        error_msg = "Proxy binary not available after download attempt"
                        print(f"[QuotaViewModel] {error_msg}")
                        self.error_message = error_msg
                        self.status_message = f"Error: {error_msg}"
                else:
                    print("[QuotaViewModel] Auto-start disabled, proxy not started")
                    self.status_message = "Ready (proxy not started)"

            # Clear status after a moment if no error
            if not self.error_message:
                self.status_message = None
        except Exception as e:
            error_msg = f"Initialization error: {str(e)}"
            print(f"[QuotaViewModel] {error_msg}")
            import traceback
            traceback.print_exc()
            self.error_message = error_msg
            self.status_message = f"Error: {error_msg}"
        finally:
            self.isLoading = False

    async def start_proxy(self):
        """
        Start the proxy server.

        WORKFLOW:
        This method orchestrates the proxy startup process:
        1. Checks if proxy is already starting (prevents duplicate starts)
        2. Waits for any download to complete if in progress
        3. Calls proxy_manager.start() which:
           - Downloads binary if not installed
           - Starts the proxy process
           - Waits for proxy to be ready
        4. Sets up API client connection to proxy management API
        5. Refreshes data (auth files, quotas, usage stats)
        6. Starts background services (request tracker, usage stats polling, warmup)
        7. Sends notification that proxy started

        ERROR HANDLING:
        If any step fails, the error is captured and stored in error_message
        and status_message for display in the UI. The proxy startup is
        cancelled if an error occurs.
        """
        print(f"[QuotaViewModel] start_proxy() called")
        print(f"[QuotaViewModel] Proxy manager: {self.proxy_manager}")
        print(f"[QuotaViewModel] Is downloading: {self.proxy_manager.is_downloading}")
        print(f"[QuotaViewModel] Binary installed: {self.proxy_manager.is_binary_installed}")
        print(f"[QuotaViewModel] Already running: {self.proxy_manager.proxy_status.running}")

        # Cancel any existing start task
        if self._start_proxy_task and not self._start_proxy_task.done():
            print("[QuotaViewModel] Cancelling existing start_proxy task...")
            self._start_proxy_task.cancel()
            try:
                await self._start_proxy_task
            except asyncio.CancelledError:
                pass

        # Create new task
        self._start_proxy_task = asyncio.create_task(self._do_start_proxy())
        try:
            await self._start_proxy_task
        except asyncio.CancelledError:
            print("[QuotaViewModel] start_proxy task was cancelled")
            raise
        finally:
            self._start_proxy_task = None

    async def _do_start_proxy(self):
        """Internal method to actually start the proxy."""
        try:
            if self.proxy_manager.is_downloading:
                self.status_message = "Downloading proxy binary..."
                print(f"[QuotaViewModel] Waiting for download to complete...")
            else:
                self.status_message = "Starting proxy..."

            print(f"[QuotaViewModel] Calling proxy_manager.start()...")
            await self.proxy_manager.start()
            print(f"[QuotaViewModel] proxy_manager.start() returned")
            print(f"[QuotaViewModel] Proxy running status: {self.proxy_manager.proxy_status.running}")
            print(f"[QuotaViewModel] Proxy manager last_error: {self.proxy_manager.last_error}")
            print(f"[QuotaViewModel] Proxy manager is_starting: {self.proxy_manager.is_starting}")

            if not self.proxy_manager.proxy_status.running:
                error_msg = self.proxy_manager.last_error or "Proxy failed to start"
                print(f"[QuotaViewModel] Proxy not running after start(): {error_msg}")
                raise Exception(error_msg)

            self.status_message = "Connecting to proxy..."
            print(f"[QuotaViewModel] Setting up API client...")
            await self._setup_api_client()
            print(f"[QuotaViewModel] API client set up: {self.api_client}")

            if not self.api_client:
                error_msg = "Failed to create API client"
                print(f"[QuotaViewModel] {error_msg}")
                raise Exception(error_msg)

            # Refresh data after proxy starts (matches original implementation behavior: await refreshData())
            # This is critical - without this, quotas won't be loaded after proxy starts
            self.status_message = "Loading auth files..."
            print(f"[QuotaViewModel] Refreshing data after proxy start...")
            try:
                await self.refresh_data()
                print(f"[QuotaViewModel] Data refreshed successfully")
            except Exception as e:
                # Log error but don't fail proxy startup - quotas can be refreshed manually
                print(f"[QuotaViewModel] Warning: Error refreshing data after proxy start: {e}")
                import traceback
                traceback.print_exc()

            # Start request tracker
            self.request_tracker.start()
            # Start periodic usage stats polling
            try:
                await self._start_usage_stats_polling()
            except Exception as e:
                print(f"[QuotaViewModel] Error starting usage stats polling: {e}")

            # Notify proxy started
            self.notification_manager.notify_proxy_started()

            # Start warmup scheduler after proxy is running
            self.restart_warmup_scheduler()

            # Persist operating mode and auto-start so proxy starts on next launch
            # (user had proxy running - ensure mode and auto-start are saved)
            if self.mode_manager.is_local_proxy_mode:
                self.settings.set("operatingMode", OperatingMode.LOCAL_PROXY.value)
                self.settings.set("autoStartProxy", True)
                self._auto_start = True

            self.status_message = None
            self.error_message = None
            print(f"[QuotaViewModel] Proxy started successfully")
        except Exception as e:
            error_str = str(e)
            self.error_message = error_str
            self.status_message = f"Error: {error_str}"
            print(f"[QuotaViewModel] Error starting proxy: {error_str}")
            import traceback
            traceback.print_exc()
            # Notify proxy crash if it was running before
            if self.proxy_manager.proxy_status.running:
                self.notification_manager.notify_proxy_crashed()
            # Re-raise to let caller handle it
            raise

    def cancel_proxy_startup(self):
        """Cancel the proxy startup process."""
        print("[QuotaViewModel] cancel_proxy_startup() called")

        # Cancel the async task if it exists
        if self._start_proxy_task and not self._start_proxy_task.done():
            print("[QuotaViewModel] Cancelling start_proxy task...")
            self._start_proxy_task.cancel()

        # Cancel the proxy manager startup/download
        self.proxy_manager.cancel_startup()

        # Close API client if it was created during startup
        if self.api_client:
            async def close_client():
                try:
                    if not self.api_client.session.closed:
                        await self.api_client.close()
                        print("[QuotaViewModel] Closed API client after cancellation")
                except Exception as e:
                    print(f"[QuotaViewModel] Error closing API client after cancellation: {e}")
                finally:
                    self.api_client = None

            # Try to close asynchronously
            try:
                from ..ui.main_window import run_async_coro
                run_async_coro(close_client())
            except Exception as e:
                print(f"[QuotaViewModel] Could not close API client async: {e}")

    def _setup_warmup_callbacks(self):
        """Setup warmup settings change callbacks."""
        def on_enabled_changed(accounts: set):
            self.restart_warmup_scheduler()

        def on_cadence_changed(cadence: WarmupCadence):
            self.restart_warmup_scheduler()

        def on_schedule_changed():
            self.restart_warmup_scheduler()

        self.warmup_settings.on_enabled_accounts_changed = on_enabled_changed
        self.warmup_settings.on_warmup_cadence_changed = on_cadence_changed
        self.warmup_settings.on_warmup_schedule_changed = on_schedule_changed

    def stop_proxy(self):
        """Stop the proxy server."""
        self.status_message = "Stopping proxy..."
        self.proxy_manager.stop()

        # Stop request tracker
        self.request_tracker.stop()
        # Stop usage stats polling (non-blocking)
        try:
            from ..ui.main_window import run_async_coro
            run_async_coro(self._stop_usage_stats_polling())
        except Exception:
            pass  # Ignore errors when stopping

        # Stop warmup scheduler when proxy stops
        # Cancel warmup task
        if self._warmup_task:
            if isinstance(self._warmup_task, concurrent.futures.Future):
                # Thread-safe cancellation for Future from run_async_coro
                # concurrent.futures.Future.cancel() is thread-safe
                if not self._warmup_task.done():
                    try:
                        self._warmup_task.cancel()
                    except Exception as e:
                        print(f"[QuotaViewModel] Error cancelling warmup Future: {e}")
            elif isinstance(self._warmup_task, asyncio.Task):
                # For asyncio.Task, cancel it through the event loop to avoid thread issues
                if not self._warmup_task.done():
                    # Schedule cancellation in the async loop
                    from ..ui.main_window import run_async_coro
                    async def cancel_task():
                        task = self._warmup_task
                        if task and not task.done():
                            task.cancel()
                    run_async_coro(cancel_task())

        # Notify proxy stopped
        self.notification_manager.notify_proxy_stopped()
        if self.api_client:
            # Close API client asynchronously
            async def close_client():
                try:
                    await self.api_client.close()
                except Exception:
                    pass  # Ignore errors during close

            # Use run_async_coro helper if available, otherwise just set to None
            try:
                from ..ui.main_window import run_async_coro
                result = run_async_coro(close_client())
                if result is None:
                    # Could not schedule the task, API client will be cleaned up by GC
                    print("[QuotaViewModel] Warning: Could not schedule API client close")
            except (ImportError, RuntimeError, AttributeError) as e:
                # If we can't run async, just set to None
                print(f"[QuotaViewModel] Could not close API client async: {e}")
                pass
        self.api_client = None
        self.status_message = None

    async def cleanup(self):
        """Clean up resources (close API client, stop polling, stop proxy, etc.)."""
        # Stop the proxy if it's running
        if self.proxy_manager and self.proxy_manager.proxy_status.running:
            print("[QuotaViewModel] Stopping proxy during cleanup...")
            try:
                self.stop_proxy()
                print("[QuotaViewModel] Proxy stopped successfully")
            except Exception as e:
                print(f"[QuotaViewModel] Error stopping proxy: {e}")

        # Stop usage stats polling
        try:
            await self._stop_usage_stats_polling()
        except Exception:
            pass

        # Close API client
        if self.api_client:
            try:
                await self.api_client.close()
                print("[QuotaViewModel] API client closed successfully")
            except Exception as e:
                print(f"[QuotaViewModel] Error closing API client: {e}")
            finally:
                self.api_client = None

        # Stop request tracker
        try:
            self.request_tracker.stop()
        except Exception:
            pass

    def __del__(self):
        """Destructor - ensure cleanup happens even if async cleanup wasn't called."""
        # Note: This is a fallback. Ideally cleanup() should be called explicitly.
        # We can't do async operations here, but we can at least mark the session
        # for closure. The session will be closed when the event loop processes it.
        if hasattr(self, 'api_client') and self.api_client:
            try:
                # Try to schedule close in event loop if available
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running() and not self.api_client.session.closed:
                        # Schedule close task
                        loop.create_task(self.api_client.close())
                except (RuntimeError, AttributeError):
                    # No event loop available - session will be closed by aiohttp's finalizer
                    # This is not ideal but prevents crashes
                    pass
            except Exception:
                # Ignore all errors in destructor
                pass

    async def toggle_proxy(self):
        """Toggle proxy on/off."""
        if self.proxy_manager.proxy_status.running:
            self.stop_proxy()
        else:
            await self.start_proxy()

    async def _setup_api_client(self):
        """Setup API client for management API."""
        new_client = None
        try:
            # Close existing client if any (to prevent session leaks)
            if self.api_client:
                try:
                    if not self.api_client.session.closed:
                        await self.api_client.close()
                        print("[QuotaViewModel] Closed old API client before creating new one")
                except Exception as e:
                    print(f"[QuotaViewModel] Error closing old API client: {e}")
                finally:
                    self.api_client = None

            if self.proxy_manager.proxy_status.running:
                new_client = ManagementAPIClient(
                    base_url=self.proxy_manager.management_url,
                    auth_key=self.proxy_manager.management_key,
                )
                self.api_client = new_client
        except Exception as e:
            # If something goes wrong, ensure we clean up any partially created client
            if new_client:
                try:
                    if not new_client.session.closed:
                        await new_client.close()
                        print("[QuotaViewModel] Closed partially created API client due to error")
                except Exception as close_error:
                    print(f"[QuotaViewModel] Error closing partially created API client: {close_error}")
            raise

    async def refresh_data(self):
        """Refresh all data from proxy (matches original implementation refreshData())."""
        if not self.api_client:
            print("[QuotaViewModel] refresh_data() called but API client is None, skipping")
            return

        try:
            print(f"[QuotaViewModel] refresh_data() starting...")
            # Always refresh auth files first to get current list
            self.auth_files = await self.api_client.fetch_auth_files()
            print(f"[QuotaViewModel] Refreshed {len(self.auth_files)} auth files from proxy")

            self.api_keys = await self.api_client.fetch_api_keys()
            print(f"[QuotaViewModel] Refreshed {len(self.api_keys)} API keys")

            # Fetch usage stats (matches original implementation: self.usageStats = try await client.fetchUsageStats())
            try:
                # Use shorter timeout for usage stats in refresh cycle too (15s max)
                usage_stats = await self.api_client.fetch_usage_stats(timeout=15.0)
                if usage_stats:
                    self.usage_stats = usage_stats
                    log_with_timestamp(
                        f"Refreshed usage stats: {usage_stats.usage.total_requests if usage_stats.usage else 0} requests, "
                        f"{usage_stats.usage.total_tokens if usage_stats.usage else 0} tokens",
                        "[QuotaViewModel]"
                    )
                else:
                    log_with_timestamp("Usage stats fetch returned None", "[QuotaViewModel]")
            except Exception as e:
                # Log error but don't fail - usage stats are optional
                error_msg = str(e)
                # Only log timeout errors if they're persistent (not just occasional network hiccups)
                if "timeout" in error_msg.lower() or "TimeoutError" in type(e).__name__:
                    log_with_timestamp(f"Usage stats fetch timed out (optional, will retry): {error_msg}", "[QuotaViewModel]")
                else:
                    log_with_timestamp(f"Usage stats fetch failed (optional): {error_msg}", "[QuotaViewModel]")
                # Keep existing usage_stats if fetch fails (don't clear it)

            # Refresh quotas (this is the critical part)
            print(f"[QuotaViewModel] Calling refresh_all_quotas() from refresh_data()...")
            await self.refresh_all_quotas()
            print(f"[QuotaViewModel] refresh_all_quotas() completed in refresh_data()")

            self.error_message = None
        except Exception as e:
            print(f"[QuotaViewModel] Error refreshing data: {e}")
            import traceback
            traceback.print_exc()
            self.error_message = str(e)

    async def refresh_all_quotas(self):
        """
        Refresh quotas for all providers.

        WORKFLOW:
        This is the core quota fetching method. It:
        1. Creates quota fetchers for each provider
        2. Fetches quotas in parallel (for performance)
        3. Updates provider_quotas dictionary with results
        4. Checks for low quota alerts and sends notifications
        5. Notifies UI screens via callbacks after each provider completes
        6. Handles errors gracefully (continues with other providers)

        PRIVACY NOTE:
        Cursor and Trae are NOT auto-refreshed (privacy concern - issue #29).
        These require scanning the user's IDE installations, which is a privacy-sensitive
        operation. User must explicitly scan for IDEs to detect these quotas.

        PARALLEL FETCHING:
        All providers are fetched in parallel using asyncio.gather() for better
        performance. Each provider's fetcher runs independently and updates
        provider_quotas as results arrive.
        """
        if self.isLoadingQuotas:
            print("[QuotaViewModel] Already loading quotas, skipping...")
            return

        # Check if API client is available (required for quota fetching)
        if not self.api_client:
            print("[QuotaViewModel] ⚠ API client not available, cannot fetch quotas")
            print("[QuotaViewModel]   - Proxy running:", self.proxy_manager.proxy_status.running if hasattr(self.proxy_manager, 'proxy_status') else "unknown")
            print("[QuotaViewModel]   - Mode:", self.mode_manager.current_mode if hasattr(self.mode_manager, 'current_mode') else "unknown")
            self.isLoadingQuotas = False
            return

        print(f"[QuotaViewModel] Starting quota refresh for all providers (API client: {self.api_client})")
        self.isLoadingQuotas = True
        self.status_message = "Refreshing quotas..."
        self.last_quota_refresh_time = datetime.now()

        try:
            # Import fetchers
            from ..services.quota_fetchers.claude import ClaudeCodeQuotaFetcher
            from ..services.quota_fetchers.openai import OpenAIQuotaFetcher
            from ..services.quota_fetchers.antigravity import AntigravityQuotaFetcher
            from ..services.quota_fetchers.copilot import CopilotQuotaFetcher
            # Note: Cursor and Trae removed from auto-refresh (privacy - issue #29)
            # User must explicitly scan for IDEs to detect these
            from ..services.quota_fetchers.kiro import KiroQuotaFetcher
            from ..services.quota_fetchers.codex_cli import CodexCLIQuotaFetcher
            from ..services.quota_fetchers.gemini import GeminiCLIQuotaFetcher

            # Create fetchers (excluding Cursor and Trae - require explicit scan)
            # ClaudeCode always runs (not just in Monitor Mode)
            # CodexCLI and GeminiCLI only run in Monitor Mode (quota-only mode)
            fetchers = {
                AIProvider.CLAUDE: ClaudeCodeQuotaFetcher(self.api_client),
                AIProvider.CODEX: OpenAIQuotaFetcher(self.api_client),
                AIProvider.ANTIGRAVITY: AntigravityQuotaFetcher(self.api_client),
                AIProvider.COPILOT: CopilotQuotaFetcher(self.api_client),
                AIProvider.KIRO: KiroQuotaFetcher(self.api_client),
            }

            # Add CLI fetchers based on mode and availability
            # CodexCLI: only in Monitor Mode (OpenAIQuotaFetcher handles it in Full Mode via proxy)
            # GeminiCLI: always fetch when available (it only shows connection status, no quota API)
            #   This is different implementation - we fetch it in all modes since it's just connection info
            if self.mode_manager.is_monitor_mode:
                # In Monitor Mode, add both CodexCLI and GeminiCLI
                fetchers[AIProvider.GEMINI] = GeminiCLIQuotaFetcher(self.api_client)
            else:
                # In LOCAL_PROXY mode, still fetch GeminiCLI if available
                # (CodexCLI is handled by OpenAIQuotaFetcher via proxy auth files)
                # Check if Gemini CLI is installed by trying to fetch quotas
                # If it returns data, add it to fetchers
                gemini_cli_fetcher = GeminiCLIQuotaFetcher(self.api_client)
                # We'll fetch it separately after main fetchers complete
                # This allows us to show Gemini CLI connection status even in LOCAL_PROXY mode

            # Update proxy config
            proxy_url = self.proxy_manager.proxy_url if hasattr(self.proxy_manager, 'proxy_url') else None
            print(f"[QuotaViewModel] Proxy URL: {proxy_url}")
            for fetcher in fetchers.values():
                if hasattr(fetcher, 'update_proxy_configuration'):
                    fetcher.update_proxy_configuration(proxy_url)

            print(f"[QuotaViewModel] Created {len(fetchers)} fetchers for providers: {[p.display_name for p in fetchers.keys()]}")
            print(f"[QuotaViewModel] Starting parallel quota fetch...")

            # Fetch quotas in parallel
            async def fetch_provider(provider, fetcher):
                try:
                    print(f"[QuotaViewModel] Fetching quotas for {provider.display_name}...")
                    # Special handling for Antigravity to get both quotas and subscriptions
                    if provider == AIProvider.ANTIGRAVITY and hasattr(fetcher, 'fetch_all_antigravity_data'):
                        quotas, subscriptions = await fetcher.fetch_all_antigravity_data()
                        if quotas:
                            self.provider_quotas[provider] = quotas
                            # Check for low quota notifications
                            self._check_quota_alerts(provider, quotas)
                            print(f"[QuotaViewModel] ✓ Fetched {len(quotas)} quota(s) for {provider.display_name}")
                            # Notify UI immediately after each provider's quotas are fetched
                            # This ensures UI updates progressively as data arrives
                            self._notify_quota_updated()
                        else:
                            print(f"[QuotaViewModel] ⚠ No quotas returned for {provider.display_name}")

                        # Store subscription info
                        if subscriptions:
                            if provider not in self.subscription_infos:
                                self.subscription_infos[provider] = {}
                            self.subscription_infos[provider].update(subscriptions)
                            print(f"[QuotaViewModel] ✓ Fetched {len(subscriptions)} subscription(s) for {provider.display_name}")
                    # Special handling for Gemini to get both quotas and subscriptions
                    elif provider == AIProvider.GEMINI and hasattr(fetcher, 'fetch_all_gemini_data'):
                        quotas, subscriptions = await fetcher.fetch_all_gemini_data()
                        if quotas:
                            self.provider_quotas[provider] = quotas
                            # Check for low quota notifications
                            self._check_quota_alerts(provider, quotas)
                            print(f"[QuotaViewModel] ✓ Fetched {len(quotas)} quota(s) for {provider.display_name}")
                            # Notify UI immediately after each provider's quotas are fetched
                            # This ensures UI updates progressively as data arrives
                            self._notify_quota_updated()
                        else:
                            print(f"[QuotaViewModel] ⚠ No quotas returned for {provider.display_name}")

                        # Store subscription info
                        if subscriptions:
                            if provider not in self.subscription_infos:
                                self.subscription_infos[provider] = {}
                            self.subscription_infos[provider].update(subscriptions)
                            print(f"[QuotaViewModel] ✓ Fetched {len(subscriptions)} subscription(s) for {provider.display_name}")
                    else:
                        quotas = await fetcher.fetch_all_quotas()
                        if quotas:
                            self.provider_quotas[provider] = quotas
                            # Check for low quota notifications
                            self._check_quota_alerts(provider, quotas)
                            print(f"[QuotaViewModel] ✓ Fetched {len(quotas)} quota(s) for {provider.display_name}")
                            # Notify UI immediately after each provider's quotas are fetched
                            # This ensures UI updates progressively as data arrives
                            self._notify_quota_updated()
                        else:
                            print(f"[QuotaViewModel] ⚠ No quotas returned for {provider.display_name}")
                except Exception as e:
                    # Log errors instead of silently failing
                    print(f"[QuotaViewModel] ✗ Error fetching quota for {provider.display_name}: {e}")
                    import traceback
                    traceback.print_exc()

            # Run all fetchers in parallel
            tasks = [fetch_provider(provider, fetcher) for provider, fetcher in fetchers.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any exceptions that occurred
            for i, (provider, result) in enumerate(zip(fetchers.keys(), results)):
                if isinstance(result, Exception):
                    print(f"[QuotaViewModel] ✗ Exception in task for {provider.display_name}: {result}")
                    import traceback
                    traceback.print_exc()

            print(f"[QuotaViewModel] Completed quota fetch. Current provider_quotas keys: {list(self.provider_quotas.keys())}")

            # Notify UI that quotas have been updated
            self._notify_quota_updated()

            print(f"[QuotaViewModel] About to fetch CLI-based quotas (CodexCLI and GeminiCLI)...")

            # Fetch Codex CLI only in Monitor Mode (quota-only mode)
            # This matches original implementation: refreshCodexCLIQuotasInternal only runs when modeManager.isMonitorMode
            # The OpenAIQuotaFetcher handles Codex via proxy auth files in Full Mode
            if self.mode_manager.is_monitor_mode:
                codex_cli_fetcher = CodexCLIQuotaFetcher(self.api_client)
                if proxy_url and hasattr(codex_cli_fetcher, 'update_proxy_configuration'):
                    codex_cli_fetcher.update_proxy_configuration(proxy_url)
                try:
                    quotas = await codex_cli_fetcher.fetch_all_quotas()
                    if quotas:
                        print(f"[QuotaViewModel] Fetched {len(quotas)} Codex CLI quota(s) (Monitor Mode)")
                        # Merge with CODEX provider (don't overwrite proxy data)
                        if AIProvider.CODEX not in self.provider_quotas:
                            self.provider_quotas[AIProvider.CODEX] = {}
                        # Merge instead of replace to preserve proxy data if any
                        self.provider_quotas[AIProvider.CODEX].update(quotas)
                        print(f"[QuotaViewModel] Codex provider now has {len(self.provider_quotas[AIProvider.CODEX])} account(s)")
                        # Notify UI of update
                        self._notify_quota_updated()
                except Exception as e:
                    print(f"[QuotaViewModel] Error fetching Codex CLI quotas: {e}")
                    import traceback
                    traceback.print_exc()

            # Always fetch Gemini CLI when available (shows connection status, no quota API)
            # This is different implementation - we fetch it in all modes since it's just connection info
            # and helps users see that Gemini CLI is connected even in LOCAL_PROXY mode
            print(f"[QuotaViewModel] Attempting to fetch Gemini CLI quotas (all modes)...")
            gemini_cli_fetcher = GeminiCLIQuotaFetcher(self.api_client)
            if proxy_url and hasattr(gemini_cli_fetcher, 'update_proxy_configuration'):
                gemini_cli_fetcher.update_proxy_configuration(proxy_url)
            try:
                # Try to fetch both quotas and subscriptions
                if hasattr(gemini_cli_fetcher, 'fetch_all_gemini_data'):
                    quotas, subscriptions = await gemini_cli_fetcher.fetch_all_gemini_data()
                    print(f"[QuotaViewModel] Gemini CLI fetch_all_gemini_data() returned: {len(quotas)} quota(s), {len(subscriptions)} subscription(s)")
                else:
                    # Fallback to old method if fetch_all_gemini_data doesn't exist
                    quotas = await gemini_cli_fetcher.fetch_all_quotas()
                    subscriptions = {}
                    print(f"[QuotaViewModel] Gemini CLI fetch_all_quotas() returned: {len(quotas)} account(s)")

                if quotas:
                    print(f"[QuotaViewModel] Fetched {len(quotas)} Gemini CLI account(s) (connection status)")
                    for email, quota_data in quotas.items():
                        print(f"[QuotaViewModel]   - {email}: {len(quota_data.models)} model(s)")
                    # Merge with GEMINI provider (don't overwrite proxy data if any)
                    if AIProvider.GEMINI not in self.provider_quotas:
                        self.provider_quotas[AIProvider.GEMINI] = {}
                    # Merge instead of replace to preserve proxy data if any
                    self.provider_quotas[AIProvider.GEMINI].update(quotas)
                    print(f"[QuotaViewModel] Gemini provider now has {len(self.provider_quotas[AIProvider.GEMINI])} account(s)")
                    # Notify UI of update
                    self._notify_quota_updated()

                # Store subscription info
                if subscriptions:
                    if AIProvider.GEMINI not in self.subscription_infos:
                        self.subscription_infos[AIProvider.GEMINI] = {}
                    self.subscription_infos[AIProvider.GEMINI].update(subscriptions)
                    print(f"[QuotaViewModel] ✓ Fetched {len(subscriptions)} Gemini subscription(s)")
                else:
                    print(f"[QuotaViewModel] No Gemini CLI quotas returned (auth file may not exist or no account info)")
            except Exception as e:
                print(f"[QuotaViewModel] Error fetching Gemini CLI quotas: {e}")
                import traceback
                traceback.print_exc()
                import traceback
                traceback.print_exc()
        finally:
            self.isLoadingQuotas = False
            # Final notification after all quotas are loaded
            self._notify_quota_updated()

    def _check_quota_alerts(self, provider: AIProvider, quotas: Dict[str, ProviderQuotaData]):
        """Check for low quota alerts and send notifications if needed.

        Args:
            provider: The AI provider
            quotas: Dictionary mapping account_key -> ProviderQuotaData
        """
        if not quotas:
            return

        for account_key, quota_data in quotas.items():
            if not quota_data or not quota_data.models:
                continue

            # Check each model for low quota
            for model in quota_data.models:
                # Only check if percentage is available (not -1)
                if model.percentage >= 0:
                    # Get account identifier for notification
                    account_id = quota_data.account_email or quota_data.account_name or account_key

                    # Notify if quota is low (notification manager handles threshold check)
                    self.notification_manager.notify_quota_low(
                        provider=provider.display_name,
                        account=account_id,
                        percentage=model.percentage
                    )

    async def load_direct_auth_files(self):
        """Load direct auth files from filesystem (for quota-only mode)."""
        self.direct_auth_files = await self.direct_auth_service.scan_all_auth_files()
        print(f"[QuotaViewModel] Loaded {len(self.direct_auth_files)} direct auth files")

    async def refresh_quotas_unified(self):
        """Unified quota refresh - works with or without proxy."""
        print(f"[QuotaViewModel] refresh_quotas_unified() called")
        print(f"[QuotaViewModel]   - isLoadingQuotas: {self.isLoadingQuotas}")
        print(f"[QuotaViewModel]   - api_client: {self.api_client}")
        print(f"[QuotaViewModel]   - mode: {self.mode_manager.current_mode if hasattr(self.mode_manager, 'current_mode') else 'unknown'}")

        if self.isLoadingQuotas:
            print("[QuotaViewModel] Already loading quotas, skipping refresh_quotas_unified()")
            return

        try:
            # Reload direct auth files (they may have changed)
            await self.load_direct_auth_files()

            # If in proxy mode (local or remote), refresh auth files first
            if self.mode_manager.is_proxy_mode and self.api_client:
                print(f"[QuotaViewModel] Proxy mode detected, refreshing auth files via API...")
                try:
                    self.status_message = "Loading auth files..."
                    # Refresh auth files to get current list of connected accounts
                    self.auth_files = await self.api_client.fetch_auth_files()
                    print(f"[QuotaViewModel] Refreshed {len(self.auth_files)} auth files")
                except Exception as e:
                    print(f"[QuotaViewModel] Error refreshing auth files: {e}")
                    # Continue with quota refresh even if auth files fail

            # Refresh quotas directly (works without proxy)
            # Note: refresh_all_quotas() manages isLoadingQuotas flag internally
            print(f"[QuotaViewModel] Calling refresh_all_quotas()...")
            await self.refresh_all_quotas()
            print(f"[QuotaViewModel] refresh_all_quotas() completed")

            # Also refresh auto-detected providers (Cursor, Trae) if they were previously scanned
            # This allows manual refresh to update IDE quotas without requiring a full scan
            await self.refresh_auto_detected_providers()
        finally:
            # Ensure flag is reset even if refresh_all_quotas() didn't complete properly
            if self.isLoadingQuotas:
                self.isLoadingQuotas = False
            if not self.isLoading:
                self.status_message = None

    async def refresh_auto_detected_providers(self):
        """Refresh quotas for auto-detected providers (Cursor, Trae).

        These providers are excluded from auto-refresh for privacy (issue #29),
        but should be included in manual refresh if they were previously scanned.
        """
        # Only refresh providers that don't support manual auth and have existing quota data
        auto_detected_providers = [
            AIProvider.CURSOR,
            AIProvider.TRAE,
        ]

        print(f"[QuotaViewModel] refresh_auto_detected_providers() called")
        print(f"[QuotaViewModel] Current provider_quotas keys: {list(self.provider_quotas.keys())}")

        for provider in auto_detected_providers:
            # Only refresh if provider already has quota data (was scanned before)
            # This respects privacy - we don't scan unless user explicitly did so
            if provider in self.provider_quotas:
                print(f"[QuotaViewModel] Refreshing {provider.display_name} quota (manual refresh)")
                try:
                    await self.refresh_quota_for_provider(provider)
                    # Verify the update
                    if provider in self.provider_quotas:
                        quota_count = len(self.provider_quotas[provider])
                        print(f"[QuotaViewModel] ✓ {provider.display_name} quota refreshed: {quota_count} account(s)")
                    else:
                        print(f"[QuotaViewModel] ⚠ {provider.display_name} removed from provider_quotas (no quotas found)")
                except Exception as e:
                    print(f"[QuotaViewModel] ✗ Error refreshing {provider.display_name}: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[QuotaViewModel] Skipping {provider.display_name} - not in provider_quotas (not scanned yet)")

    async def refresh_quota_for_provider(self, provider: AIProvider):
        """Refresh quota for a specific provider."""
        from ..services.quota_fetchers.claude import ClaudeCodeQuotaFetcher
        from ..services.quota_fetchers.openai import OpenAIQuotaFetcher
        from ..services.quota_fetchers.antigravity import AntigravityQuotaFetcher
        from ..services.quota_fetchers.copilot import CopilotQuotaFetcher
        from ..services.quota_fetchers.cursor import CursorQuotaFetcher
        from ..services.quota_fetchers.trae import TraeQuotaFetcher
        from ..services.quota_fetchers.kiro import KiroQuotaFetcher
        from ..services.quota_fetchers.antigravity import AntigravityQuotaFetcher
        from ..services.quota_fetchers.gemini import GeminiCLIQuotaFetcher

        proxy_url = self.proxy_manager.proxy_url if hasattr(self.proxy_manager, 'proxy_url') else None

        fetcher_map = {
            AIProvider.CLAUDE: ClaudeCodeQuotaFetcher,
            AIProvider.CODEX: OpenAIQuotaFetcher,
            AIProvider.ANTIGRAVITY: AntigravityQuotaFetcher,
            AIProvider.COPILOT: CopilotQuotaFetcher,
            AIProvider.CURSOR: CursorQuotaFetcher,
            AIProvider.TRAE: TraeQuotaFetcher,
            AIProvider.KIRO: KiroQuotaFetcher,
            AIProvider.GEMINI: GeminiCLIQuotaFetcher,
        }

        fetcher_class = fetcher_map.get(provider)
        if not fetcher_class:
            print(f"[QuotaViewModel] ✗ No fetcher class found for {provider.display_name}")
            return

        try:
            fetcher = fetcher_class(self.api_client)
            if hasattr(fetcher, 'update_proxy_configuration'):
                fetcher.update_proxy_configuration(proxy_url)
            quotas = await fetcher.fetch_all_quotas()
            if quotas:
                self.provider_quotas[provider] = quotas
                print(f"[QuotaViewModel] ✓ {provider.display_name} quota updated: {len(quotas)} account(s)")
                # Notify UI of update
                self._notify_quota_updated()
            else:
                # Remove if no quotas found
                self.provider_quotas.pop(provider, None)
                print(f"[QuotaViewModel] ⚠ {provider.display_name} removed (no quotas found)")
                # Notify UI of update
                self._notify_quota_updated()
        except Exception as e:
            print(f"[QuotaViewModel] ✗ Error fetching quota for {provider.display_name}: {e}")
            import traceback
            traceback.print_exc()
            # Don't remove existing quotas on error - keep what we have

    async def start_oauth(
        self,
        provider: AIProvider,
        project_id: Optional[str] = None,
        auth_method: Optional[str] = None,
    ):
        """Start OAuth flow for a provider."""
        self.status_message = f"Starting OAuth for {provider.display_name}..."

        # GitHub Copilot uses Device Code Flow via CLI binary
        if provider == AIProvider.COPILOT:
            await self._start_copilot_auth()
            self.status_message = None
            return

        # Kiro uses CLI-based auth
        if provider == AIProvider.KIRO:
            method = auth_method or "kiro-google-login"
            await self._start_kiro_auth(method)
            self.status_message = None
            return

        # Standard OAuth flow
        if not self.api_client:
            # Try to set up API client
            await self._setup_api_client()
            if not self.api_client:
                self.oauth_state = OAuthState(
                    provider=provider,
                    status=OAuthStatus.ERROR,
                    error="Proxy not running. Please start the proxy first."
                )
                self.status_message = "Error: Proxy not running"
                return

        self.oauth_state = OAuthState(provider=provider, status=OAuthStatus.WAITING)
        self.status_message = f"Opening browser for {provider.display_name}..."

        # Verify proxy is running before attempting OAuth
        if not self.proxy_manager.proxy_status.running:
            self.oauth_state = OAuthState(
                provider=provider,
                status=OAuthStatus.ERROR,
                error="Proxy is not running. Please start the proxy first."
            )
            self.status_message = "Error: Proxy not running"
            return

        try:
            # Add timeout wrapper for OAuth URL request
            # Use asyncio.wait_for to provide better error messages
            try:
                response = await asyncio.wait_for(
                    self.api_client.get_oauth_url(provider, project_id),
                    timeout=30.0  # 30 second timeout for OAuth URL request
                )
            except asyncio.TimeoutError:
                raise APIError("Connection timeout to proxy. The proxy may be slow to respond or not accessible.")

            if response.status != "ok" or not response.url or not response.state:
                self.oauth_state = OAuthState(
                    provider=provider,
                    status=OAuthStatus.ERROR,
                    error=response.error or "Failed to get OAuth URL"
                )
                return

            # Open browser
            print(f"[OAuth] Opening browser with URL: {response.url}")  # Debug
            try:
                browser_opened = open_browser(response.url)
                if browser_opened:
                    print("[OAuth] Browser opened successfully")  # Debug
                else:
                    print(f"[OAuth] Browser open returned False. URL: {response.url}")  # Debug
            except Exception as e:
                print(f"[OAuth] Exception opening browser: {e}")  # Debug
                browser_opened = False

            # Set polling state regardless of browser opening
            self.oauth_state = OAuthState(
                provider=provider,
                status=OAuthStatus.POLLING,
                state=response.state
            )

            # If browser didn't open, store URL in error field for user reference
            if not browser_opened:
                self.oauth_state.error = f"Browser did not open automatically. Please visit: {response.url}"
                print(f"[OAuth] Browser failed to open. User should visit: {response.url}")  # Debug

            self.oauth_state = OAuthState(
                provider=provider,
                status=OAuthStatus.POLLING,
                state=response.state
            )

            # Poll for completion
            self.status_message = f"Waiting for {provider.display_name} authentication..."
            await self._poll_oauth_status(response.state, provider)
            self.status_message = None

        except APIError as e:
            # APIError already has a formatted message
            error_msg = str(e)
            # Check if it's a timeout/connection error
            if "timeout" in error_msg.lower() or "TimeoutError" in error_msg:
                # Provide more helpful error message for timeout
                if not self.proxy_manager.proxy_status.running:
                    error_msg = "Proxy is not running. Please start the proxy first."
                else:
                    error_msg = f"Connection timeout to proxy: {error_msg}. The proxy may be slow to respond or there may be a network issue."
            self.oauth_state = OAuthState(
                provider=provider,
                status=OAuthStatus.ERROR,
                error=error_msg
            )
            self.status_message = f"Error: {error_msg}"
        except Exception as e:
            # Handle other exceptions
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "TimeoutError" in type(e).__name__:
                if not self.proxy_manager.proxy_status.running:
                    error_msg = "Proxy is not running. Please start the proxy first."
                else:
                    error_msg = f"Connection timeout: {error_msg}. Please check if the proxy is running and accessible."
            self.oauth_state = OAuthState(
                provider=provider,
                status=OAuthStatus.ERROR,
                error=error_msg
            )
            self.status_message = f"Error: {error_msg}"

    async def _start_copilot_auth(self):
        """Start GitHub Copilot authentication using Device Code Flow."""
        self.oauth_state = OAuthState(provider=AIProvider.COPILOT, status=OAuthStatus.WAITING)

        result = self.proxy_manager.run_auth_command("copilot-login")

        if result["success"]:
            self.oauth_state = OAuthState(
                provider=AIProvider.COPILOT,
                status=OAuthStatus.POLLING,
                state=result.get("device_code"),
                error=result.get("message")
            )
            await self._poll_copilot_auth_completion()
        else:
            self.oauth_state = OAuthState(
                provider=AIProvider.COPILOT,
                status=OAuthStatus.ERROR,
                error=result.get("message", "Authentication failed")
            )

    async def _start_kiro_auth(self, method: str):
        """Start Kiro authentication."""
        self.oauth_state = OAuthState(provider=AIProvider.KIRO, status=OAuthStatus.WAITING)

        result = self.proxy_manager.run_auth_command(method)

        if result["success"]:
            if method == "kiro-import":
                self.oauth_state = OAuthState(
                    provider=AIProvider.KIRO,
                    status=OAuthStatus.POLLING,
                    error="Importing quotas..."
                )
                await asyncio.sleep(1.5)
                await self.refresh_data()
                self.oauth_state = OAuthState(
                    provider=AIProvider.KIRO,
                    status=OAuthStatus.SUCCESS
                )
                return

            self.oauth_state = OAuthState(
                provider=AIProvider.KIRO,
                status=OAuthStatus.POLLING,
                state=result.get("device_code"),
                error=result.get("message")
            )
            await self._poll_kiro_auth_completion()
        else:
            self.oauth_state = OAuthState(
                provider=AIProvider.KIRO,
                status=OAuthStatus.ERROR,
                error=result.get("message", "Authentication failed")
            )

    async def _poll_oauth_status(self, state: str, provider: AIProvider):
        """Poll OAuth status until completion."""
        if not self.api_client:
            return

        for _ in range(60):  # Poll for up to 2 minutes
            await asyncio.sleep(2)

            try:
                response = await self.api_client.poll_oauth_status(state)

                if response.status == "ok":
                    self.oauth_state = OAuthState(
                        provider=provider,
                        status=OAuthStatus.SUCCESS
                    )
                    self.status_message = f"Authentication successful for {provider.display_name}..."
                    await self.refresh_data()
                    self.status_message = None
                    return
                elif response.status == "error":
                    self.oauth_state = OAuthState(
                        provider=provider,
                        status=OAuthStatus.ERROR,
                        error=response.error
                    )
                    return
            except Exception:
                continue

        # Timeout
        self.oauth_state = OAuthState(
            provider=provider,
            status=OAuthStatus.ERROR,
            error="OAuth timeout"
        )

    async def _poll_copilot_auth_completion(self):
        """Poll for Copilot auth completion by monitoring auth files."""
        start_count = len([f for f in self.auth_files if f.provider in ("github-copilot", "copilot")])

        for _ in range(90):  # Poll for up to 3 minutes
            await asyncio.sleep(2)
            await self.refresh_data()

            current_count = len([f for f in self.auth_files if f.provider in ("github-copilot", "copilot")])
            if current_count > start_count:
                self.oauth_state = OAuthState(
                    provider=AIProvider.COPILOT,
                    status=OAuthStatus.SUCCESS
                )
                return

        self.oauth_state = OAuthState(
            provider=AIProvider.COPILOT,
            status=OAuthStatus.ERROR,
            error="Authentication timeout"
        )

    async def _poll_kiro_auth_completion(self):
        """Poll for Kiro auth completion."""
        start_count = len([f for f in self.auth_files if f.provider == "kiro"])

        for _ in range(90):
            await asyncio.sleep(2)
            await self.refresh_data()

            current_count = len([f for f in self.auth_files if f.provider == "kiro"])
            if current_count > start_count:
                self.oauth_state = OAuthState(
                    provider=AIProvider.KIRO,
                    status=OAuthStatus.SUCCESS
                )
                return

        self.oauth_state = OAuthState(
            provider=AIProvider.KIRO,
            status=OAuthStatus.ERROR,
            error="Authentication timeout"
        )

    def cancel_oauth(self):
        """Cancel OAuth flow."""
        self.oauth_state = None

    async def _initialize_remote_mode(self):
        """Initialize remote proxy mode."""
        if not self.mode_manager.remote_config:
            self.error_message = "Remote config not found"
            return

        try:
            await self._setup_api_client()
            if self.api_client:
                # Test connection
                if await self.api_client.check_proxy_responding():
                    self.mode_manager.set_connection_status("connected")
                    await self.refresh_data()
                else:
                    self.mode_manager.set_connection_status("error", error="Failed to connect to remote proxy")
                    self.error_message = "Failed to connect to remote proxy"
        except Exception as e:
            self.mode_manager.set_connection_status("error", error=str(e))
            self.error_message = f"Remote connection error: {str(e)}"

    async def scan_ides(self, options: IDEScanOptions):
        """Scan for IDEs and CLI tools.

        This is the ONLY way to detect and refresh Cursor/Trae quotas (privacy - issue #29).
        They are NOT auto-refreshed in regular quota refresh cycles.
        """
        from ..ui.utils import log_with_timestamp
        log_with_timestamp(f"scan_ides() called with options: cursor={options.scan_cursor}, trae={options.scan_trae}", "[QuotaViewModel]")
        self.status_message = "Scanning for IDEs and CLI tools..."
        try:
            result = await self.ide_scan_service.scan(options)
            self.ide_scan_result = result
            log_with_timestamp(f"IDE scan service completed. Cursor found: {result.cursor_found}, Trae found: {result.trae_found}", "[QuotaViewModel]")

            # Update quotas if IDEs found (this is the explicit consent-based scan)
            if options.scan_cursor:
                log_with_timestamp("Starting Cursor quota fetch after scan...", "[QuotaViewModel]")
                try:
                    from ..services.quota_fetchers.cursor import CursorQuotaFetcher
                    fetcher = CursorQuotaFetcher(self.api_client)
                    log_with_timestamp("Created CursorQuotaFetcher, calling fetch_all_quotas()...", "[QuotaViewModel]")
                    quotas = await fetcher.fetch_all_quotas()
                    log_with_timestamp(f"fetch_all_quotas() returned: {quotas}", "[QuotaViewModel]")
                    if quotas:
                        self.provider_quotas[AIProvider.CURSOR] = quotas
                        log_with_timestamp(f"Scanned and fetched {len(quotas)} Cursor quota(s)", "[QuotaViewModel]")
                        log_with_timestamp(f"Cursor accounts: {list(quotas.keys())}", "[QuotaViewModel]")
                        # Verify it's in provider_quotas
                        if AIProvider.CURSOR in self.provider_quotas:
                            log_with_timestamp("✓ Cursor successfully added to provider_quotas", "[QuotaViewModel]")
                        else:
                            log_with_timestamp("✗ ERROR: Cursor NOT in provider_quotas after assignment!", "[QuotaViewModel]")
                        # Don't notify here - batch all notifications at the end
                    else:
                        # Clear stale data when not found
                        self.provider_quotas.pop(AIProvider.CURSOR, None)
                        log_with_timestamp("No Cursor quotas found - check if Cursor is installed and logged in", "[QuotaViewModel]")
                        # Don't notify here - batch all notifications at the end
                except Exception as e:
                    log_with_timestamp(f"✗ Error fetching Cursor quotas: {e}", "[QuotaViewModel]")
                    import traceback
                    traceback.print_exc()
                    # Don't clear existing quotas on error

            if options.scan_trae:
                log_with_timestamp("Starting Trae quota fetch after scan...", "[QuotaViewModel]")
                try:
                    from ..services.quota_fetchers.trae import TraeQuotaFetcher
                    fetcher = TraeQuotaFetcher(self.api_client)
                    log_with_timestamp("Created TraeQuotaFetcher, calling fetch_all_quotas()...", "[QuotaViewModel]")
                    quotas = await fetcher.fetch_all_quotas()
                    log_with_timestamp(f"fetch_all_quotas() returned: {quotas}", "[QuotaViewModel]")
                    if quotas:
                        self.provider_quotas[AIProvider.TRAE] = quotas
                        log_with_timestamp(f"Scanned and fetched {len(quotas)} Trae quota(s)", "[QuotaViewModel]")
                        log_with_timestamp(f"Trae accounts: {list(quotas.keys())}", "[QuotaViewModel]")
                        # Verify it's in provider_quotas
                        if AIProvider.TRAE in self.provider_quotas:
                            log_with_timestamp("✓ Trae successfully added to provider_quotas", "[QuotaViewModel]")
                        else:
                            log_with_timestamp("✗ ERROR: Trae NOT in provider_quotas after assignment!", "[QuotaViewModel]")
                        # Don't notify here - batch all notifications at the end
                    else:
                        # Clear stale data when not found
                        self.provider_quotas.pop(AIProvider.TRAE, None)
                        log_with_timestamp("No Trae quotas found - check if Trae is installed and logged in", "[QuotaViewModel]")
                        # Don't notify here - batch all notifications at the end
                except Exception as e:
                    log_with_timestamp(f"✗ Error fetching Trae quotas: {e}", "[QuotaViewModel]")
                    import traceback
                    traceback.print_exc()
                    # Don't clear existing quotas on error

            self.status_message = None
            # Final notification after all scans complete
            # No need for sleep delay - _notify_quota_updated() is thread-safe and uses QTimer
            # which naturally batches and staggers the callbacks
            self._notify_quota_updated()
        except Exception as e:
            self.status_message = f"Error: {str(e)}"
            log_with_timestamp(f"Error scanning IDEs: {e}", "[QuotaViewModel]")
            import traceback
            traceback.print_exc()

    def switch_operating_mode(self, mode: OperatingMode):
        """Switch operating mode."""
        def stop_proxy_if_needed():
            if self.proxy_manager.proxy_status.running:
                self.stop_proxy()

        self.mode_manager.switch_mode(mode, stop_proxy_if_needed)

        # Reinitialize if needed
        if mode == OperatingMode.REMOTE_PROXY:
            # Use the async coroutine runner from main_window
            try:
                from ..ui.main_window import run_async_coro
                run_async_coro(self._initialize_remote_mode())
            except (ImportError, RuntimeError, AttributeError):
                # Fallback if main_window not available or run_async_coro failed
                # Try to use run_async_coro with error handling
                try:
                    from ..ui.main_window import run_async_coro
                    # If run_async_coro returns None, it means it couldn't schedule the task
                    result = run_async_coro(self._initialize_remote_mode())
                    if result is None:
                        print("[QuotaViewModel] Warning: Could not schedule remote mode initialization")
                except Exception as e:
                    # No running loop, can't initialize async
                    print(f"[QuotaViewModel] Could not initialize remote mode: {e}")
                    pass

    async def delete_auth_file(self, file: AuthFile):
        """Delete an auth file."""
        if not self.api_client:
            return

        try:
            self.status_message = f"Deleting {file.name}..."
            await self.api_client.delete_auth_file(file.name)
            await self.refresh_data()
            self.status_message = None
        except Exception as e:
            self.error_message = str(e)
            self.status_message = f"Error deleting {file.name}"

    async def add_api_key(self, key: str):
        """Add an API key."""
        if not self.api_client:
            return

        try:
            await self.api_client.add_api_key(key)
            self.api_keys = await self.api_client.fetch_api_keys()
        except Exception as e:
            self.error_message = str(e)

    async def delete_api_key(self, key: str):
        """Delete an API key."""
        if not self.api_client:
            return

        try:
            await self.api_client.delete_api_key(key)
            self.api_keys = await self.api_client.fetch_api_keys()
        except Exception as e:
            self.error_message = str(e)

    async def _start_usage_stats_polling(self):
        """Start periodic polling of usage stats for request tracking.

        Note: This is a separate polling mechanism for real-time updates.
        Usage stats are also fetched in refresh_data() as part of the main refresh cycle.
        This polling provides more frequent updates (every 10 seconds) for better UX.
        Matches original approach but with additional polling for real-time updates.
        """
        if self._usage_stats_polling_active:
            return

        self._usage_stats_polling_active = True
        log_with_timestamp("Starting usage stats polling (10s interval)", "[QuotaViewModel]")

        async def poll_loop():
            """Poll usage stats every 10 seconds with improved error handling."""
            consecutive_errors = 0
            last_success_time = None
            first_timeout_time = None  # Track when first timeout occurred
            backoff_delay = 10  # Start with normal polling interval

            while self._usage_stats_polling_active and self.api_client:
                try:
                    # Check if proxy is running before attempting to poll
                    # This prevents timeout errors when proxy is stopped
                    if not self.proxy_manager.proxy_status.running:
                        # Proxy is not running - wait longer before checking again
                        await asyncio.sleep(30)  # Wait 30 seconds when proxy is stopped
                        consecutive_errors = 0  # Reset error count
                        first_timeout_time = None  # Reset timeout tracking
                        backoff_delay = 10  # Reset backoff delay
                        continue

                    # Fetch usage stats with extended timeout
                    # Use exponential backoff for retries within the same polling cycle
                    max_retries = 2
                    retry_delay = 1.0
                    usage_stats = None

                    for attempt in range(max_retries):
                        try:
                            usage_stats = await self.api_client.fetch_usage_stats(timeout=20.0)  # Extended from 8.0s to 20.0s
                            break  # Success, exit retry loop
                        except Exception as retry_error:
                            if attempt < max_retries - 1:
                                # Wait with exponential backoff before retry
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff: 1s, 2s
                            else:
                                # Last attempt failed, re-raise to outer handler
                                raise retry_error

                    if usage_stats:
                        # Update usage stats (this will trigger UI updates)
                        self.usage_stats = usage_stats
                        total_requests = usage_stats.usage.total_requests if usage_stats.usage else 0
                        total_tokens = usage_stats.usage.total_tokens if usage_stats.usage else 0
                        log_with_timestamp(
                            f"Usage stats updated: {total_requests} requests, {total_tokens} tokens",
                            "[QuotaViewModel]"
                        )
                        consecutive_errors = 0  # Reset error count on success
                        first_timeout_time = None  # Reset timeout tracking on success
                        backoff_delay = 10  # Reset backoff delay
                        last_success_time = asyncio.get_event_loop().time()
                    else:
                        log_with_timestamp("Usage stats fetch returned None", "[QuotaViewModel]")
                        consecutive_errors = 0  # Reset error count
                        first_timeout_time = None  # Reset timeout tracking
                        backoff_delay = 10  # Reset backoff delay

                except Exception as e:
                    consecutive_errors += 1
                    error_msg = str(e)
                    error_type = type(e).__name__

                    # Determine if this is a timeout/connection error
                    is_timeout_error = (
                        "TimeoutError" in error_type or
                        "timeout" in error_msg.lower() or
                        "Connection error" in error_msg
                    )

                    # Track when first timeout occurred
                    if is_timeout_error and first_timeout_time is None:
                        first_timeout_time = asyncio.get_event_loop().time()

                    # Suppress timeout errors when proxy is not running
                    if is_timeout_error and not self.proxy_manager.proxy_status.running:
                        # Only log once when proxy is stopped
                        if consecutive_errors == 1:
                            log_with_timestamp(
                                "Usage stats polling paused (proxy not running)",
                                "[QuotaViewModel]"
                            )
                        # Wait longer when proxy is stopped
                        await asyncio.sleep(30)
                        consecutive_errors = 0
                        first_timeout_time = None  # Reset timeout tracking
                        backoff_delay = 10
                        continue

                    # Auto-restart proxy for local proxy mode if enabled and proxy appears unresponsive
                    # Only restart if:
                    # 1. We're in local proxy mode
                    # 2. Auto-restart is enabled
                    # 3. We've had timeout errors for 5 minutes continuously
                    # 4. Proxy status says it's running but we can't connect (it may have crashed)
                    # 5. We haven't tried to restart recently (throttle to prevent loops)
                    current_time = asyncio.get_event_loop().time()
                    timeout_duration = (current_time - first_timeout_time) if first_timeout_time else 0
                    
                    if (is_timeout_error and
                        self.mode_manager.is_local_proxy_mode and
                        self.settings.get("autoRestartProxy", False) and
                        timeout_duration >= 300 and  # 5 minutes of consecutive timeouts
                        self.proxy_manager.proxy_status.running):
                        # Check if we've restarted recently (throttle: max once per 5 minutes)
                        if (self._last_proxy_restart_attempt is None or
                            (current_time - self._last_proxy_restart_attempt) >= 300):  # 5 minutes
                            log_with_timestamp(
                                f"Proxy appears unresponsive after {timeout_duration:.0f}s of consecutive timeouts. Attempting auto-restart...",
                                "[QuotaViewModel]"
                            )
                            self._last_proxy_restart_attempt = current_time
                            try:
                                # Close old API client connection first
                                if self.api_client:
                                    try:
                                        await self.api_client.close()
                                    except Exception:
                                        pass  # Ignore errors closing old client
                                    self.api_client = None
                                
                                # Stop the proxy first
                                self.proxy_manager.stop()
                                await asyncio.sleep(2)  # Brief pause before restart
                                
                                # Restart the proxy (this will also recreate the API client)
                                await self.start_proxy()
                                log_with_timestamp(
                                    "Proxy auto-restart completed. Waiting for proxy to become ready...",
                                    "[QuotaViewModel]"
                                )
                                # Wait a bit for proxy to become ready
                                await asyncio.sleep(5)
                                # Reset error count after restart attempt
                                consecutive_errors = 0
                                first_timeout_time = None  # Reset timeout tracking
                                backoff_delay = 10
                                continue
                            except Exception as restart_error:
                                log_with_timestamp(
                                    f"Failed to auto-restart proxy: {restart_error}",
                                    "[QuotaViewModel]"
                                )
                                # Continue with normal error handling

                    # Calculate adaptive backoff delay based on consecutive errors
                    # Exponential backoff: 10s, 20s, 40s, max 60s
                    if consecutive_errors <= 3:
                        backoff_delay = 10 * (2 ** (consecutive_errors - 1))  # 10s, 20s, 40s
                    else:
                        backoff_delay = 60  # Cap at 60 seconds

                    # Only log errors occasionally to reduce spam
                    # Log first error, then every 10th error (once per ~2 minutes with backoff)
                    should_log = (
                        consecutive_errors == 1 or
                        consecutive_errors % 10 == 0 or
                        (last_success_time and
                         (asyncio.get_event_loop().time() - last_success_time) > 300)  # Log if no success for 5 minutes
                    )

                    if should_log:
                        # Provide more context in error message
                        if is_timeout_error:
                            log_with_timestamp(
                                f"Usage stats polling timeout (non-fatal, attempt {consecutive_errors}, "
                                f"backoff: {backoff_delay}s): {error_msg}",
                                "[QuotaViewModel]"
                            )
                        else:
                            log_with_timestamp(
                                f"Usage stats polling error (non-fatal, attempt {consecutive_errors}): {error_msg}",
                                "[QuotaViewModel]"
                            )

                    # Apply backoff delay before next attempt
                    await asyncio.sleep(backoff_delay)
                    continue

                # Wait normal interval before next poll (only if no errors)
                await asyncio.sleep(10)

        # Start polling task
        try:
            self._usage_stats_task = asyncio.create_task(poll_loop())
            log_with_timestamp("Usage stats polling task started", "[QuotaViewModel]")
        except RuntimeError as e:
            log_with_timestamp(f"Failed to start usage stats polling task: {e}", "[QuotaViewModel]")
            # Fallback: try to schedule it via main window
            try:
                from ..ui.main_window import run_async_coro
                run_async_coro(poll_loop())
            except Exception as fallback_error:
                log_with_timestamp(f"Failed to schedule usage stats polling via fallback: {fallback_error}", "[QuotaViewModel]")

    # MARK: - Warmup Methods

    def is_warmup_enabled(self, provider: AIProvider, account_key: str) -> bool:
        """Check if warmup is enabled for an account."""
        return self.warmup_settings.is_enabled(provider, account_key)

    def warmup_status(self, provider: AIProvider, account_key: str) -> WarmupStatus:
        """Get warmup status for an account."""
        key = WarmupAccountKey(provider, account_key).to_id()
        return self.warmup_statuses.get(key, WarmupStatus())

    def warmup_next_run_date(self, provider: AIProvider, account_key: str) -> Optional[datetime]:
        """Get next warmup run date for an account."""
        key = WarmupAccountKey(provider, account_key).to_id()
        return self._warmup_next_run.get(key)

    def toggle_warmup(self, provider: AIProvider, account_key: str):
        """Toggle warmup for an account."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        self.warmup_settings.toggle(provider, account_key)

    def set_warmup_enabled(self, enabled: bool, provider: AIProvider, account_key: str):
        """Set warmup enabled state."""
        if provider != AIProvider.ANTIGRAVITY:
            return
        self.warmup_settings.set_enabled(enabled, provider, account_key)

    def _next_daily_run_date(self, minutes: int, now: datetime) -> datetime:
        """Calculate next daily run date from minutes (0-1439)."""
        hour = minutes // 60
        minute = minutes % 60
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today > now:
            return today
        return today + timedelta(days=1)

    def restart_warmup_scheduler(self):
        """Restart the warmup scheduler (matches original implementation restartWarmupScheduler)."""
        # Cancel existing task
        if self._warmup_task:
            if isinstance(self._warmup_task, concurrent.futures.Future):
                # Thread-safe cancellation for Future from run_async_coro
                # concurrent.futures.Future.cancel() is thread-safe
                if not self._warmup_task.done():
                    try:
                        self._warmup_task.cancel()
                    except Exception as e:
                        print(f"[QuotaViewModel] Error cancelling warmup Future: {e}")
            elif isinstance(self._warmup_task, asyncio.Task):
                # For asyncio.Task, cancel it through the event loop to avoid thread issues
                if not self._warmup_task.done():
                    # Schedule cancellation in the async loop
                    from ..ui.main_window import run_async_coro
                    async def cancel_task():
                        task = self._warmup_task
                        if task and not task.done():
                            task.cancel()
                    run_async_coro(cancel_task())

        if not self.warmup_settings.enabled_account_ids:
            return

        now = datetime.now()
        self._warmup_next_run = {}

        for target in self._warmup_targets():
            mode = self.warmup_settings.warmup_schedule_mode(target.provider, target.account_key)
            if mode == WarmupScheduleMode.INTERVAL:
                self._warmup_next_run[target.to_id()] = now
            elif mode == WarmupScheduleMode.DAILY:
                minutes = self.warmup_settings.warmup_daily_minutes(target.provider, target.account_key)
                self._warmup_next_run[target.to_id()] = self._next_daily_run_date(minutes, now)

            # Update status
            key = target.to_id()
            if key not in self.warmup_statuses:
                self.warmup_statuses[key] = WarmupStatus()
            self.warmup_statuses[key].next_run = self._warmup_next_run.get(key)

        if not self._warmup_next_run:
            return

        async def warmup_loop():
            while True:
                try:
                    next_runs = [dt for dt in self._warmup_next_run.values() if dt]
                    if not next_runs:
                        break
                    next_run = min(next_runs)
                    delay = max((next_run - datetime.now()).total_seconds(), 1)
                    await asyncio.sleep(delay)
                    await self._run_warmup_cycle()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[QuotaViewModel] Error in warmup loop: {e}")
                    await asyncio.sleep(60)  # Wait before retrying

        # Schedule task - always use run_async_coro to ensure thread-safe cancellation
        from ..ui.main_window import run_async_coro
        future = run_async_coro(warmup_loop())
        # Store the future so we can cancel it later
        if future:
            self._warmup_task = future
        else:
            # If run_async_coro failed, log error
            print("[QuotaViewModel] Warning: Failed to schedule warmup loop")
            self._warmup_task = None

    def _warmup_targets(self) -> List[WarmupAccountKey]:
        """Get list of warmup targets (enabled Antigravity accounts)."""
        targets = []
        for account_id in self.warmup_settings.enabled_account_ids:
            key = WarmupAccountKey.from_id(account_id)
            if key and key.provider == AIProvider.ANTIGRAVITY:
                targets.append(key)
        return sorted(targets, key=lambda k: (k.provider.display_name, k.account_key))

    async def _run_warmup_cycle(self):
        """Run a warmup cycle (matches original implementation runWarmupCycle)."""
        if self._is_warmup_running:
            return

        targets = self._warmup_targets()
        if not targets:
            return

        # Check if proxy is running
        if not self.proxy_manager.proxy_status.running:
            # Reschedule without running
            now = datetime.now()
            for target in targets:
                mode = self.warmup_settings.warmup_schedule_mode(target.provider, target.account_key)
                if mode == WarmupScheduleMode.INTERVAL:
                    cadence = self.warmup_settings.warmup_cadence(target.provider, target.account_key)
                    self._warmup_next_run[target.to_id()] = now + timedelta(seconds=cadence.interval_seconds)
                elif mode == WarmupScheduleMode.DAILY:
                    minutes = self.warmup_settings.warmup_daily_minutes(target.provider, target.account_key)
                    self._warmup_next_run[target.to_id()] = self._next_daily_run_date(minutes, now)

                key = target.to_id()
                if key not in self.warmup_statuses:
                    self.warmup_statuses[key] = WarmupStatus()
                self.warmup_statuses[key].next_run = self._warmup_next_run.get(key)
            return

        self._is_warmup_running = True
        try:
            now = datetime.now()
            due_targets = [
                target for target in targets
                if target.to_id() in self._warmup_next_run
                and self._warmup_next_run[target.to_id()] <= now
            ]

            for target in due_targets:
                await self._warmup_account(target.provider, target.account_key)

                # Reschedule
                mode = self.warmup_settings.warmup_schedule_mode(target.provider, target.account_key)
                if mode == WarmupScheduleMode.INTERVAL:
                    cadence = self.warmup_settings.warmup_cadence(target.provider, target.account_key)
                    self._warmup_next_run[target.to_id()] = datetime.now() + timedelta(seconds=cadence.interval_seconds)
                elif mode == WarmupScheduleMode.DAILY:
                    minutes = self.warmup_settings.warmup_daily_minutes(target.provider, target.account_key)
                    self._warmup_next_run[target.to_id()] = self._next_daily_run_date(minutes, datetime.now())

                key = target.to_id()
                if key not in self.warmup_statuses:
                    self.warmup_statuses[key] = WarmupStatus()
                self.warmup_statuses[key].next_run = self._warmup_next_run.get(key)
                self.warmup_statuses[key].last_error = None
        finally:
            self._is_warmup_running = False

    async def _warmup_account(self, provider: AIProvider, account_key: str):
        """Warmup a specific account (matches original implementation warmupAccount)."""
        if provider != AIProvider.ANTIGRAVITY:
            return

        account = WarmupAccountKey(provider, account_key)
        account_id = account.to_id()

        if account_id in self._warmup_running_accounts:
            return  # Already running

        self._warmup_running_accounts.add(account_id)
        try:
            if not self.proxy_manager.proxy_status.running:
                return

            if not self.api_client:
                return

            auth_info = self._warmup_auth_info(provider, account_key)
            if not auth_info:
                return

            available_models = await self._fetch_warmup_models(
                provider, account_key, auth_info["auth_file_name"]
            )
            if not available_models:
                return

            await self._warmup_account_with_models(
                provider, account_key, available_models, auth_info["auth_index"]
            )
        finally:
            self._warmup_running_accounts.discard(account_id)

    def _warmup_auth_info(self, provider: AIProvider, account_key: str) -> Optional[dict]:
        """Get auth info for warmup (auth_index and auth_file_name).

        Matches account_key against email, account, or name fields of auth files.
        Also tries to match via provider_quotas if direct match fails.
        Handles both formats: email with @ (hoa@opensend.com) and with dots (hoa.opensend.com).
        """
        if provider != AIProvider.ANTIGRAVITY:
            return None

        # Normalize account_key for matching (handle both @ and dot formats)
        def normalize_key(key: str) -> str:
            """Normalize account key for comparison."""
            if not key:
                return key
            # If it looks like an email with dots instead of @, try to convert
            # Pattern: user.domain.com -> user@domain.com
            if "@" not in key and "." in key:
                # Try to find the last dot that might be the @ separator
                # Common pattern: user.domain.com (where domain.com is the domain)
                parts = key.split(".")
                if len(parts) >= 3:
                    # Assume last two parts are domain (e.g., opensend.com)
                    # This is a heuristic - might not work for all cases
                    user = ".".join(parts[:-2])
                    domain = ".".join(parts[-2:])
                    normalized = f"{user}@{domain}"
                    return normalized
            return key

        normalized_account_key = normalize_key(account_key)

        # First, try to find matching auth file directly
        for auth_file in self.auth_files:
            if auth_file.provider_type != provider:
                continue

            # Match by email (most reliable) - try both original and normalized
            if auth_file.email:
                if auth_file.email == account_key or auth_file.email == normalized_account_key:
                    auth_index = getattr(auth_file, 'auth_index', None) or getattr(auth_file, 'id', None)
                    if auth_index:
                        name = auth_file.name.strip()
                        if name:
                            return {"auth_index": str(auth_index), "auth_file_name": name}

            # Match by account field
            if auth_file.account:
                if auth_file.account == account_key or auth_file.account == normalized_account_key:
                    auth_index = getattr(auth_file, 'auth_index', None) or getattr(auth_file, 'id', None)
                    if auth_index:
                        name = auth_file.name.strip()
                        if name:
                            return {"auth_index": str(auth_index), "auth_file_name": name}

            # Match by quota_lookup_key (handles both formats)
            lookup_key = auth_file.quota_lookup_key
            if lookup_key == account_key or lookup_key == normalized_account_key:
                auth_index = getattr(auth_file, 'auth_index', None) or getattr(auth_file, 'id', None)
                if auth_index:
                    name = auth_file.name.strip()
                    if name:
                        return {"auth_index": str(auth_index), "auth_file_name": name}

            # Match by name
            if auth_file.name and auth_file.name.strip() == account_key:
                auth_index = getattr(auth_file, 'auth_index', None) or getattr(auth_file, 'id', None)
                if auth_index:
                    name = auth_file.name.strip()
                    if name:
                        return {"auth_index": str(auth_index), "auth_file_name": name}

        # If no direct match, try to find via provider_quotas
        # The account_key might be the email from quota data
        if provider in self.provider_quotas:
            for quota_account_key, quota_data in self.provider_quotas[provider].items():
                # Check if account_key matches the quota key or the email (try both formats)
                quota_key_normalized = normalize_key(quota_account_key)
                quota_email_normalized = normalize_key(quota_data.account_email) if quota_data.account_email else None

                if (quota_account_key == account_key or quota_account_key == normalized_account_key or
                    quota_key_normalized == account_key or quota_key_normalized == normalized_account_key or
                    quota_data.account_email == account_key or quota_data.account_email == normalized_account_key or
                    (quota_email_normalized and (quota_email_normalized == account_key or quota_email_normalized == normalized_account_key))):
                    # Try to find auth file by email from quota data
                    target_email = quota_data.account_email or quota_account_key
                    target_email_normalized = normalize_key(target_email)

                    for auth_file in self.auth_files:
                        if auth_file.provider_type != provider:
                            continue
                        # Match by email (try both formats)
                        if (auth_file.email == target_email or auth_file.email == target_email_normalized or
                            auth_file.email == account_key or auth_file.email == normalized_account_key):
                            auth_index = getattr(auth_file, 'auth_index', None) or getattr(auth_file, 'id', None)
                            if auth_index:
                                name = auth_file.name.strip()
                                if name:
                                    return {"auth_index": str(auth_index), "auth_file_name": name}
                        # Also try matching by account field
                        if (auth_file.account == target_email or auth_file.account == target_email_normalized or
                            auth_file.account == account_key or auth_file.account == normalized_account_key):
                            auth_index = getattr(auth_file, 'auth_index', None) or getattr(auth_file, 'id', None)
                            if auth_index:
                                name = auth_file.name.strip()
                                if name:
                                    return {"auth_index": str(auth_index), "auth_file_name": name}

        return None

    async def _fetch_warmup_models(
        self, provider: AIProvider, account_key: str, auth_file_name: str
    ) -> List[dict]:
        """Fetch available models for warmup (with caching)."""
        key = WarmupAccountKey(provider, account_key).to_id()

        # Check cache
        if key in self._warmup_model_cache:
            models, fetched_at = self._warmup_model_cache[key]
            age = (datetime.now() - fetched_at).total_seconds()
            if age <= self._warmup_model_cache_ttl:
                return models

        # Fetch from API
        if not self.api_client:
            return []

        try:
            models = await self.warmup_service.fetch_models(self.api_client, auth_file_name)
            self._warmup_model_cache[key] = (models, datetime.now())
            return models
        except Exception as e:
            print(f"[QuotaViewModel] Error fetching warmup models: {e}")
            return []

    async def _warmup_account_with_models(
        self, provider: AIProvider, account_key: str,
        available_models: List[dict], auth_index: str
    ):
        """Warmup account with specific models (matches original implementation warmupAccount)."""
        if provider != AIProvider.ANTIGRAVITY:
            return

        account = WarmupAccountKey(provider, account_key)
        account_id = account.to_id()

        available_ids = [m.get("id", "") for m in available_models]
        selected_models = self.warmup_settings.selected_models(provider, account_key)
        models_to_warmup = [m for m in selected_models if m in available_ids]

        if not models_to_warmup:
            return

        # Update status
        if account_id not in self.warmup_statuses:
            self.warmup_statuses[account_id] = WarmupStatus()

        status = self.warmup_statuses[account_id]
        status.is_running = True
        status.last_error = None
        status.progress_total = len(models_to_warmup)
        status.progress_completed = 0
        status.current_model = None
        for model in models_to_warmup:
            status.model_states[model] = "pending"

        try:
            for model in models_to_warmup:
                status.current_model = model
                status.model_states[model] = "running"

                try:
                    await self.warmup_service.warmup(
                        self.api_client, auth_index, model
                    )
                    status.progress_completed += 1
                    status.model_states[model] = "succeeded"
                except Exception as e:
                    status.progress_completed += 1
                    status.model_states[model] = "failed"
                    status.last_error = str(e)
        finally:
            status.is_running = False
            status.current_model = None
            status.last_run = datetime.now()

    async def warmup_available_models(self, provider: AIProvider, account_key: str) -> List[str]:
        """Get available models for warmup (for UI)."""
        if provider != AIProvider.ANTIGRAVITY:
            print(f"[QuotaViewModel] warmup_available_models: Provider {provider} is not ANTIGRAVITY")
            return []
        if not self.api_client:
            print(f"[QuotaViewModel] warmup_available_models: No API client available")
            return []

        auth_info = self._warmup_auth_info(provider, account_key)
        if not auth_info:
            print(f"[QuotaViewModel] warmup_available_models: Could not find auth info for account_key={account_key}")
            print(f"[QuotaViewModel] Available auth files: {[(f.email, f.account, f.name) for f in self.auth_files if f.provider_type == provider]}")
            return []

        print(f"[QuotaViewModel] warmup_available_models: Found auth info: {auth_info}")
        models = await self._fetch_warmup_models(provider, account_key, auth_info["auth_file_name"])
        model_ids = sorted([m.get("id", "") for m in models if m.get("id")])
        print(f"[QuotaViewModel] warmup_available_models: Found {len(model_ids)} models: {model_ids[:5]}...")
        return model_ids

    async def _stop_usage_stats_polling(self):
        """Stop periodic polling of usage stats."""
        self._usage_stats_polling_active = False
        if self._usage_stats_task:
            self._usage_stats_task.cancel()
            try:
                await self._usage_stats_task
            except asyncio.CancelledError:
                pass
            self._usage_stats_task = None
