"""
Main application window for Quotio.

WORKFLOW OVERVIEW:
==================
This module manages the main application window and coordinates between:
- Qt GUI framework (PyQt6) - handles UI rendering and user input
- Async event loop - handles async operations (API calls, proxy management)
- View model - central state management (quotas, proxy status, auth files)

KEY ARCHITECTURE DECISION:
PyQt6 runs on the main thread, but async operations need an event loop.
We run the asyncio event loop in a separate background thread to avoid blocking
the Qt event loop. This allows the UI to remain responsive during async operations.

WORKFLOW:
1. MainWindow.__init__() creates Qt app, sets up async loop, creates view model
2. UI screens are created and registered with view model
3. View model initialization starts (loads settings, starts proxy if needed)
4. UI displays data from view model, user interactions trigger async operations
5. View model updates trigger UI callbacks to refresh displays
6. Background timers handle periodic updates (quota refresh, status updates)
"""

import asyncio
import sys
import os
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QLabel,
        QPushButton,
        QTabWidget,
        QMenu,
    )
    from PyQt6.QtCore import Qt, QTimer, QPoint
    from PyQt6.QtGui import QIcon, QAction
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    print("PyQt6 not available. Install with: pip install PyQt6")
    print("Falling back to console mode.")


# Global event loop for async operations
# These are module-level globals to share the event loop across the application
_async_loop = None  # The asyncio event loop instance
_loop_thread = None  # Thread running the event loop
_loop_running = False  # Flag indicating if loop is currently running


def setup_async_loop(exception_handler=None):
    """
    Set up asyncio event loop for Qt integration.
    
    ARCHITECTURE:
    PyQt6 runs on the main thread and has its own event loop. Async operations
    (API calls, proxy management) need an asyncio event loop. We run the asyncio
    loop in a separate background thread to avoid blocking the Qt UI.
    
    WORKFLOW:
    1. Check if loop already exists and is running (idempotent)
    2. Create new asyncio event loop
    3. Enable debug mode if requested (for troubleshooting async issues)
    4. Set exception handler if provided (for logging async exceptions)
    5. Start the loop in a daemon thread (dies when main thread exits)
    6. Loop runs forever, processing async tasks scheduled via run_async_coro()
    
    Args:
        exception_handler: Optional exception handler function for asyncio exceptions
    
    Returns:
        The asyncio event loop instance
    """
    global _async_loop, _loop_thread, _loop_running
    
    # Idempotent: if loop already exists and is running, return it
    if _async_loop is not None and _loop_running:
        return _async_loop
    
    # Create new event loop
    # This will be the event loop for all async operations
    _async_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_async_loop)
    
    # Enable debug mode if requested
    # Debug mode helps catch async/await issues and unawaited coroutines
    if os.getenv('ASYNCIO_DEBUG') == '1' or os.getenv('PYTHONASYNCIODEBUG') == '1':
        _async_loop.set_debug(True)
    
    # Set exception handler if provided
    if exception_handler:
        _async_loop.set_exception_handler(exception_handler)
    
    # Start event loop in a separate thread
    # This allows Qt UI to remain responsive while async operations run
    import threading
    def run_loop():
        """Thread function that runs the asyncio event loop."""
        global _loop_running
        _loop_running = True
        print("[AsyncLoop] Starting asyncio event loop in thread...")
        try:
            # Run forever - this processes all async tasks scheduled to this loop
            _async_loop.run_forever()
        except Exception as e:
            print(f"[AsyncLoop] Event loop error: {e}")
        finally:
            _loop_running = False
            print("[AsyncLoop] Event loop stopped")
    
    # Create daemon thread (dies when main thread exits)
    _loop_thread = threading.Thread(target=run_loop, daemon=True)
    _loop_thread.start()
    print(f"[AsyncLoop] Event loop thread started: {_loop_thread.name}")
    
    return _async_loop


def process_asyncio_tasks():
    """
    Process pending asyncio tasks. Call this periodically from Qt.
    
    NOTE: This function is now a no-op because we run the event loop in a
    separate thread. The loop thread automatically processes all tasks.
    This function is kept for compatibility but does nothing.
    """
    # This is now handled by the thread running the event loop
    pass


def run_async_coro(coro):
    """
    Run an async coroutine, creating task if loop is running.
    
    PURPOSE:
    This is the bridge between Qt (main thread) and asyncio (background thread).
    When UI code needs to run async operations, it calls this function to
    schedule the coroutine in the background event loop.
    
    WORKFLOW:
    1. Check if async loop exists and is running
    2. If not, set it up and wait briefly for it to start
    3. Use asyncio.run_coroutine_threadsafe() to schedule the coroutine
       in the background thread's event loop
    4. Returns a Future that can be used to check completion/get results
    
    THREAD SAFETY:
    Uses asyncio.run_coroutine_threadsafe() which is specifically designed
    to schedule coroutines from one thread into another thread's event loop.
    
    Args:
        coro: The async coroutine to run
        
    Returns:
        Future object representing the scheduled task, or None on error
    """
    global _async_loop
    # Ensure loop is set up before trying to schedule tasks
    if _async_loop is None or not _loop_running:
        setup_async_loop()
        # Wait a moment for loop to start
        import time
        time.sleep(0.1)
    
    try:
        # Use call_soon_threadsafe to schedule the coroutine in the loop thread
        if _async_loop is not None and _loop_running:
            # Schedule task creation in the loop thread
            # run_coroutine_threadsafe is the thread-safe way to schedule
            # a coroutine from one thread into another thread's event loop
            future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
            print(f"[run_async_coro] Scheduled coroutine in loop thread: {future}")
            return future
        else:
            # Fallback: try to create task directly (if we're already in an async context)
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(coro)
                print(f"[run_async_coro] Created task in running loop: {task}")
                return task
            except RuntimeError:
                # No running loop - can't create task directly
                # This should not happen if setup_async_loop() was called properly
                print(f"[run_async_coro] Warning: No running event loop, cannot create task")
                print(f"[run_async_coro] Attempting to setup loop and retry...")
                # Try to setup loop one more time
                setup_async_loop()
                import time
                time.sleep(0.2)  # Wait a bit longer for loop to start
                if _async_loop is not None and _loop_running:
                    future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
                    print(f"[run_async_coro] Scheduled coroutine after retry: {future}")
                    return future
                else:
                    print(f"[run_async_coro] Error: Still no event loop available after retry")
                    return None
    except Exception as e:
        print(f"[run_async_coro] Error creating task: {e}")
        import traceback
        traceback.print_exc()
        return None

from ..services.proxy_manager import CLIProxyManager
from ..viewmodels.quota_viewmodel import QuotaViewModel
from .screens.dashboard import DashboardScreen
from .screens.providers import ProvidersScreen
from .screens.settings import SettingsScreen
from .screens.agents import AgentSetupScreen
from .screens.logs import LogsScreen
from .screens.custom_providers import CustomProvidersScreen
from .screens.ide_scan import IDEScanScreen
from .screens.warmup import WarmupScreen


class MainWindow:
    """
    Main application window - coordinates UI, async operations, and state management.
    
    ARCHITECTURE:
    This class is the central coordinator that:
    - Creates and manages the Qt application window
    - Sets up the async event loop in a background thread
    - Creates the view model (QuotaViewModel) which manages all application state
    - Creates and manages all UI screens (Dashboard, Providers, Agents, etc.)
    - Handles communication between UI and async operations
    
    WORKFLOW:
    1. __init__() - Sets up Qt app, async loop, view model, UI screens
    2. _setup_ui() - Creates window, tabs, status bar, all screen widgets
    3. _initialize_viewmodel() - Starts async initialization (loads settings, starts proxy)
    4. Runtime - UI displays data, user actions trigger async operations via view model
    5. _cleanup() - Called on exit, closes connections, stops background tasks
    """
    
    def __init__(self):
        """
        Initialize the main window.
        
        WORKFLOW:
        1. Create QuotaViewModel (central state management)
        2. If PyQt6 available:
           - Create QApplication (Qt framework initialization)
           - Set up cross-thread communication utilities
           - Set up async event loop in background thread
           - Create main window widget
           - Set up UI (tabs, screens, status bar)
           - Schedule view model initialization (after Qt event loop starts)
        3. If PyQt6 not available:
           - Run in console mode (no GUI)
        """
        # Create view model - this is the central state management object
        # It manages: proxy status, quotas, auth files, settings, etc.
        self.view_model = QuotaViewModel()
        
        # Get asyncio exception handler from main module if available
        exception_handler = None
        try:
            from ..main import _asyncio_exception_handler
            exception_handler = _asyncio_exception_handler
        except (ImportError, AttributeError):
            pass
        
        if PYQT_AVAILABLE:
            # Create Qt application - required for all Qt widgets
            self.app = QApplication(sys.argv)
            
            # Initialize main thread receiver for cross-thread calls
            # This allows async operations (running in background thread) to
            # safely update Qt widgets (running on main thread)
            from ..ui.utils import initialize_main_thread_receiver
            initialize_main_thread_receiver()
            
            # Set up async event loop in background thread
            # This allows async operations without blocking the Qt UI
            # Pass exception handler if available
            setup_async_loop(exception_handler=exception_handler)
            
            # Create main window widget
            self.window = QMainWindow()
            
            # Set up UI (creates tabs, screens, status bar, etc.)
            self._setup_ui()
            
            # Initialize view model (defer until event loop is running)
            # QTimer.singleShot(0, ...) schedules the function to run after
            # the current event loop iteration, ensuring Qt is fully initialized
            QTimer.singleShot(0, self._initialize_viewmodel)
        else:
            # Console mode - no GUI available
            self.app = None
            self.window = None
            print("Running in console mode. GUI not available.")
    
    def _setup_ui(self):
        """Set up the UI."""
        if not self.window:
            return
        
        self.window.setWindowTitle("Quotio - Cross-Platform Edition")
        self.window.setGeometry(100, 100, 1200, 800)
        
        # Store reference to main window for modal dialogs
        self._main_window_ref = self.window
        
        # Create central widget with status bar
        central_widget = QWidget()
        central_layout = QVBoxLayout()
        central_widget.setLayout(central_layout)
        
        # Create tab widget
        self.tabs = QTabWidget()
        central_layout.addWidget(self.tabs)
        
        # Status bar at bottom (copyable)
        self.status_bar = QLabel("Ready")
        self.status_bar.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
                padding: 4px 8px;
                font-size: 11px;
                color: #666;
            }
        """)
        self.status_bar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Enable text selection for copying
        self.status_bar.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | 
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        # Add context menu for copy
        self.status_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_bar.customContextMenuRequested.connect(self._on_status_bar_context_menu)
        central_layout.addWidget(self.status_bar)
        
        self.window.setCentralWidget(central_widget)
        
        # Create screens
        # Get agent_viewmodel from agents screen first
        self.agents_screen = AgentSetupScreen(self.view_model)
        agent_viewmodel = getattr(self.agents_screen, 'agent_viewmodel', None)
        # Create merged dashboard screen (combines dashboard and quota)
        self.dashboard_screen = DashboardScreen(self.view_model, agent_viewmodel)
        self.providers_screen = ProvidersScreen(self.view_model)
        self.settings_screen = SettingsScreen(self.view_model, main_window=self)
        self.logs_screen = LogsScreen(self.view_model)
        self.custom_providers_screen = CustomProvidersScreen(self.view_model)
        self.ide_scan_screen = IDEScanScreen(self.view_model)
        # Warmup screen is now a modal dialog, no longer a tab
        
        # Connect view model status updates
        self._setup_status_updates()
        
        # Connect cleanup on app exit
        if self.app:
            self.app.aboutToQuit.connect(self._cleanup)
        
        # Initialize logging to file
        from .utils import _get_log_file
        _get_log_file()  # Initialize log file
        
        # Add tabs (only show tabs available in current mode)
        self.tabs.addTab(self.dashboard_screen, "Dashboard")
        self.tabs.addTab(self.providers_screen, "Providers")
        
        # Only show these tabs in local proxy mode
        if self.view_model.mode_manager.is_local_proxy_mode:
            self.tabs.addTab(self.agents_screen, "Agents")
            
            # Check tab visibility settings
            show_logs_tab = self.view_model.settings.get("showLogsTab", True)
            if show_logs_tab:
                self.tabs.addTab(self.logs_screen, "Logs")
            
            show_custom_providers_tab = self.view_model.settings.get("showCustomProvidersTab", True)
            if show_custom_providers_tab:
                self.tabs.addTab(self.custom_providers_screen, "Custom Providers")
        
        self.tabs.addTab(self.ide_scan_screen, "IDE Scan")
        self.tabs.addTab(self.settings_screen, "Settings")
        
        # Store tab indices for later reference
        self._tab_indices = {}
        for i in range(self.tabs.count()):
            tab_name = self.tabs.tabText(i)
            self._tab_indices[tab_name] = i
        
        # Connect tab change to refresh
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        # Status update timer (configurable interval, default 5 minutes)
        # This timer controls auto-refresh of quota/provider data
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self._last_auto_refresh_time = None
        # Will be initialized after view_model is ready
    
    def _setup_status_updates(self):
        """Set up status message updates from view model."""
        # Create a timer to poll status messages
        self.status_update_timer = QTimer()
        self.status_update_timer.timeout.connect(self._update_status_message)
        self.status_update_timer.start(100)  # Update every 100ms for smooth updates
    
    def _update_status_message(self):
        """Update status bar message from view model."""
        if not self.view_model:
            return
        
        try:
            # Get current status message
            status_msg = getattr(self.view_model, 'status_message', None)
            if status_msg:
                self.status_bar.setText(status_msg)
            else:
                # Default status based on state
                if self.view_model.isLoading:
                    self.status_bar.setText("Loading...")
                elif self.view_model.isLoadingQuotas:
                    self.status_bar.setText("Refreshing quotas...")
                elif self.view_model.proxy_manager.is_starting:
                    self.status_bar.setText("Starting proxy...")
                elif self.view_model.proxy_manager.is_downloading:
                    progress = int(self.view_model.proxy_manager.download_progress * 100)
                    self.status_bar.setText(f"Downloading proxy binary... {progress}%")
                elif self.view_model.proxy_manager.proxy_status.running:
                    self.status_bar.setText("Proxy running")
                else:
                    self.status_bar.setText("Ready")
        except (AttributeError, RuntimeError) as e:
            # Silently fail to avoid breaking the UI
            # These can happen if view_model is being modified during update
            pass
        except Exception as e:
            # Log unexpected errors but don't crash
            print(f"[MainWindow] Error updating status message: {e}")
            pass
    
    def _on_status_bar_context_menu(self, position: QPoint):
        """Show context menu for status bar with copy option."""
        if not self.status_bar:
            return
        
        menu = QMenu(self.status_bar)
        
        # Copy action
        copy_action = QAction("Copy", self.status_bar)
        copy_action.triggered.connect(self._copy_status_bar_text)
        menu.addAction(copy_action)
        
        # Select All action
        select_all_action = QAction("Select All", self.status_bar)
        select_all_action.triggered.connect(self._select_all_status_bar_text)
        menu.addAction(select_all_action)
        
        # Show menu at cursor position
        menu.exec(self.status_bar.mapToGlobal(position))
    
    def _copy_status_bar_text(self):
        """Copy status bar text to clipboard."""
        if not self.status_bar:
            return
        
        clipboard = QApplication.clipboard()
        text = self.status_bar.text()
        if text:
            clipboard.setText(text)
            # Show brief feedback
            original_text = self.status_bar.text()
            self.status_bar.setText(f"Copied: {text[:50]}..." if len(text) > 50 else f"Copied: {text}")
            
            # Use a proper function reference instead of lambda to avoid closure issues
            def restore_text():
                if self.status_bar:
                    self.status_bar.setText(original_text)
            
            QTimer.singleShot(2000, restore_text)
    
    def _select_all_status_bar_text(self):
        """Select all text in status bar."""
        if not self.status_bar:
            return
        
        # QLabel doesn't have selectAll(), but we can select text programmatically
        # by setting the selection through text interaction
        self.status_bar.setFocus()
        # For QLabel, we need to use text selection flags
        # The text is already selectable, user can select it manually
        # This action just focuses the label so user can use Ctrl+A
        self.status_bar.setFocus()
    
    def _initialize_viewmodel(self):
        """Initialize the view model asynchronously."""
        self.status_bar.setText("Initializing...")
        run_async_coro(self._do_initialize())
    
    async def _do_initialize(self):
        """Actually initialize the view model."""
        try:
            self.status_bar.setText("Loading settings...")
            await asyncio.sleep(0.1)  # Small delay for UI update
            
            if self.view_model._auto_start:
                self.status_bar.setText("Auto-starting proxy...")
                await asyncio.sleep(0.1)
            
            await self.view_model.initialize()
            
            # Update auto-refresh timer after initialization (schedule on main thread)
            QTimer.singleShot(0, self._update_auto_refresh_timer)
            
            # Ensure UI screens are registered for quota updates after initialization
            # This ensures callbacks are registered even if initialization triggers quota refresh
            QTimer.singleShot(100, self._register_quota_callbacks)
            
            self.status_bar.setText("Ready")
        except Exception as e:
            self.status_bar.setText(f"Error: {str(e)}")
    
    def _register_quota_callbacks(self):
        """Register quota update callbacks for all screens."""
        if hasattr(self, 'dashboard_screen') and self.dashboard_screen:
            if not hasattr(self.dashboard_screen, '_quota_callback_registered'):
                self.view_model.register_quota_update_callback(self.dashboard_screen._update_display)
                self.dashboard_screen._quota_callback_registered = True
                print(f"[MainWindow] Registered Dashboard quota update callback")
        
        if hasattr(self, 'providers_screen') and self.providers_screen:
            if not hasattr(self.providers_screen, '_quota_callback_registered'):
                self.view_model.register_quota_update_callback(self.providers_screen._update_display)
                self.providers_screen._quota_callback_registered = True
                print(f"[MainWindow] Registered Providers quota update callback")
    
    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        # Refresh the current screen
        current_widget = self.tabs.currentWidget()
        if hasattr(current_widget, 'refresh'):
            current_widget.refresh()
        # Also ensure Providers screen updates display when tab is selected
        if hasattr(self, 'providers_screen') and current_widget == self.providers_screen:
            # Force update display to show current provider_quotas data
            if hasattr(self.providers_screen, '_update_display'):
                self.providers_screen._update_display()
    
    def _cleanup(self):
        """Clean up resources when app is about to quit."""
        print("[MainWindow] Cleaning up resources...")
        if self.view_model:
            # Run cleanup asynchronously
            async def cleanup_viewmodel():
                try:
                    await self.view_model.cleanup()
                    print("[MainWindow] View model cleanup completed")
                except Exception as e:
                    print(f"[MainWindow] Error during cleanup: {e}")
            
            # Try to run cleanup, but don't block if event loop is not available
            try:
                result = run_async_coro(cleanup_viewmodel())
                if result:
                    # Wait a short time for cleanup to complete
                    import time
                    time.sleep(0.5)
            except Exception as e:
                print(f"[MainWindow] Could not run cleanup async: {e}")
        
        # Stop status timers
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
        if hasattr(self, 'status_update_timer'):
            self.status_update_timer.stop()
        
        # Close log file
        from .utils import close_log_file
        close_log_file()
    
    def _update_auto_refresh_timer(self):
        """Update the auto-refresh timer based on settings."""
        if not hasattr(self, 'view_model') or not self.view_model:
            return
        
        # Get auto-refresh settings
        auto_refresh_enabled = self.view_model.settings.get("autoRefreshEnabled", True)
        auto_refresh_interval_minutes = self.view_model.settings.get("autoRefreshIntervalMinutes", 5)
        auto_refresh_interval_ms = auto_refresh_interval_minutes * 60 * 1000
        
        # Stop the timer first
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
        
        if auto_refresh_enabled:
            # Restart with new interval
            self.status_timer.start(auto_refresh_interval_ms)
            print(f"[MainWindow] Auto-refresh enabled: {auto_refresh_interval_minutes} minutes ({auto_refresh_interval_ms}ms)")
        else:
            print(f"[MainWindow] Auto-refresh disabled")
    
    def _update_status(self):
        """Update status display - called by timer at configured interval."""
        if not self.view_model:
            return
        
        # Check if auto-refresh is enabled
        auto_refresh_enabled = self.view_model.settings.get("autoRefreshEnabled", True)
        if not auto_refresh_enabled:
            # Auto-refresh disabled - don't refresh screens
            return
        
            # Only refresh if not currently loading to avoid UI lag
            # Also skip if proxy is starting to prevent UI freeze
            if (not self.view_model.isLoading and 
                not self.view_model.isLoadingQuotas and
                not self.view_model.proxy_manager.is_starting):
                
                auto_refresh_interval_minutes = self.view_model.settings.get("autoRefreshIntervalMinutes", 5)
                print(f"[MainWindow] Auto-refresh triggered (interval: {auto_refresh_interval_minutes} minutes)")
                
                # Refresh data from proxy first (matches original: refreshData() which includes usage stats)
                # This ensures usage stats are updated before UI refresh
                if self.view_model.proxy_manager.proxy_status.running and self.view_model.api_client:
                    # Call refresh_data() to get fresh usage stats and other data
                    from ..utils import run_async_coro
                    run_async_coro(self.view_model.refresh_data())
                
                # Refresh all screens (but do it asynchronously to avoid blocking)
                # Use longer delays to reduce refresh frequency and prevent connection spam
                # Only refresh providers screen if proxy is running (to avoid connection errors)
                if self.view_model.proxy_manager.proxy_status.running:
                    QTimer.singleShot(500, lambda: self.dashboard_screen.refresh() if hasattr(self, 'dashboard_screen') else None)
                    QTimer.singleShot(700, lambda: self.providers_screen.refresh() if hasattr(self, 'providers_screen') else None)
                    QTimer.singleShot(800, lambda: self.agents_screen.refresh() if hasattr(self, 'agents_screen') else None)
                    QTimer.singleShot(900, lambda: self.settings_screen.refresh() if hasattr(self, 'settings_screen') else None)
                else:
                    # Proxy not running - only refresh non-API screens
                    QTimer.singleShot(500, lambda: self.dashboard_screen.refresh() if hasattr(self, 'dashboard_screen') else None)
                    # Skip providers screen refresh when proxy is not running
                    QTimer.singleShot(800, lambda: self.agents_screen.refresh() if hasattr(self, 'agents_screen') else None)
                    QTimer.singleShot(900, lambda: self.settings_screen.refresh() if hasattr(self, 'settings_screen') else None)
    
    def run(self):
        """Run the application."""
        if self.app:
            self.window.show()
            sys.exit(self.app.exec())
        else:
            # Console mode
            print("\nQuotio - Cross-Platform Edition - Console Mode")
            print("=" * 50)
            print(f"Binary installed: {self.view_model.proxy_manager.is_binary_installed}")
            print(f"Port: {self.view_model.proxy_manager.port}")
            print(f"Status: {'Running' if self.view_model.proxy_manager.proxy_status.running else 'Stopped'}")
            print("\nTo use the GUI, install PyQt6:")
            print("  pip install PyQt6")
            print("\nPress Ctrl+C to exit.")
