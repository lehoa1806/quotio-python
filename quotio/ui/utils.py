"""UI utility functions."""

import os
import sys
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from PyQt6.QtWidgets import QMessageBox, QWidget, QApplication, QMenu
from PyQt6.QtCore import Qt, QTimer, QThread, QMetaObject, QPoint
from PyQt6.QtGui import QAction
try:
    from PyQt6.QtCore import pyqtSlot
except ImportError:
    # pyqtSlot might not be available, we'll use a different approach
    pyqtSlot = None


def get_main_window(widget: QWidget) -> Optional[QWidget]:
    """Get the main window from any widget."""
    parent = widget.parent()
    while parent:
        if hasattr(parent, 'window') and hasattr(parent.window, 'setWindowTitle'):
            return parent.window()
        parent = parent.parent()
    # Fallback: try to get from widget's window
    if hasattr(widget, 'window'):
        return widget.window()
    return None


def show_message_box(
    widget: QWidget,
    title: str,
    message: str,
    icon: QMessageBox.Icon = QMessageBox.Icon.Information,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    parent: Optional[QWidget] = None
) -> QMessageBox.StandardButton:
    """Show a message box modal to the main window."""
    # Get main window as parent
    main_window = parent or get_main_window(widget)
    if not main_window:
        main_window = widget
    
    msg_box = QMessageBox(main_window)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setIcon(icon)
    msg_box.setStandardButtons(buttons)
    msg_box.setWindowModality(Qt.WindowModality.WindowModal)  # Modal to parent window
    msg_box.setModal(True)
    
    # Ensure it's not a separate window
    msg_box.setWindowFlags(
        Qt.WindowType.Dialog | 
        Qt.WindowType.WindowTitleHint | 
        Qt.WindowType.WindowCloseButtonHint |
        Qt.WindowType.MSWindowsFixedSizeDialogHint
    )
    
    # Center on parent window
    if main_window:
        main_rect = main_window.geometry()
        # Calculate center position
        msg_box.adjustSize()  # Ensure size is calculated
        x = main_rect.x() + (main_rect.width() - msg_box.width()) // 2
        y = main_rect.y() + (main_rect.height() - msg_box.height()) // 2
        msg_box.move(max(0, x), max(0, y))
    
    return msg_box.exec()


def show_question_box(
    widget: QWidget,
    title: str,
    message: str,
    parent: Optional[QWidget] = None
) -> QMessageBox.StandardButton:
    """Show a question dialog modal to the main window."""
    return show_message_box(
        widget,
        title,
        message,
        QMessageBox.Icon.Question,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        parent
    )


# Global receiver object for cross-thread calls
class _MainThreadReceiver(QWidget):
    """Helper class to receive method invocations on the main thread."""
    def __init__(self):
        super().__init__()
        self._pending_calls = []
        self._timer = QTimer()
        self._timer.timeout.connect(self._process_pending)
        self._timer.start(10)  # Check every 10ms for pending calls
        self.setObjectName("_MainThreadReceiver")
    
    def _process_pending(self):
        """Process all pending function calls. Called by QTimer."""
        if not self._pending_calls:
            return
        
        # Process all pending calls
        calls_to_process = self._pending_calls[:]  # Copy list
        self._pending_calls.clear()  # Clear original list
        
        for func, args, kwargs in calls_to_process:
            try:
                func_name = func.__name__ if hasattr(func, '__name__') else str(func)
                log_with_timestamp(f"Executing pending function: {func_name}", "[call_on_main_thread]")
                func(*args, **kwargs)
                log_with_timestamp(f"Pending function {func_name} completed", "[call_on_main_thread]")
                
                # Force event processing after each function to ensure UI updates are visible
                # This is especially important for updates coming from background threads
                QApplication.processEvents()
            except Exception as e:
                log_with_timestamp(f"Error executing function: {e}", "[call_on_main_thread]")
                import traceback
                traceback.print_exc()
    
    def execute_pending(self):
        """Execute all pending function calls. This is called via QMetaObject.invokeMethod."""
        self._process_pending()

# Singleton receiver instance
_receiver = None

def _get_receiver():
    """Get or create the main thread receiver. Must be called from main thread."""
    global _receiver
    if _receiver is None:
        app = QApplication.instance()
        if app is not None:
            # Ensure we're on the main thread when creating the receiver
            current_thread = QThread.currentThread()
            app_thread = app.thread()
            if current_thread == app_thread:
                _receiver = _MainThreadReceiver()
                log_with_timestamp("Created _MainThreadReceiver on main thread", "[call_on_main_thread]")
            else:
                # Can't create from non-main thread, will use QTimer fallback
                log_with_timestamp(f"Cannot create receiver from background thread (current: {current_thread}, app: {app_thread})", "[call_on_main_thread]")
                return None
    return _receiver

def initialize_main_thread_receiver():
    """Initialize the main thread receiver. Call this early in app startup."""
    receiver = _get_receiver()
    if receiver:
        log_with_timestamp("Main thread receiver initialized successfully", "[call_on_main_thread]")
    else:
        log_with_timestamp("Warning: Could not initialize main thread receiver", "[call_on_main_thread]")

def call_on_main_thread(func: Callable, *args, **kwargs):
    """
    Schedule a function to be called on the Qt main thread.
    This is safe to call from any thread, including asyncio event loop threads.
    
    Uses QMetaObject.invokeMethod which is more reliable than QTimer for cross-thread calls.
    
    Args:
        func: The function to call
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
    """
    app = QApplication.instance()
    if app is None:
        # No QApplication yet, can't schedule
        log_with_timestamp("Warning: No QApplication instance, cannot schedule function", "[call_on_main_thread]")
        return
    
    func_name = func.__name__ if hasattr(func, '__name__') else str(func)
    log_with_timestamp(f"Scheduling function: {func_name}", "[call_on_main_thread]")
    
    # Check if we're already on the main thread
    current_thread = QThread.currentThread()
    app_thread = app.thread()
    if current_thread == app_thread:
        # Already on main thread - execute directly
        log_with_timestamp(f"Already on main thread, executing {func_name} directly", "[call_on_main_thread]")
        try:
            func(*args, **kwargs)
            log_with_timestamp(f"Function {func_name} completed", "[call_on_main_thread]")
        except Exception as e:
            log_with_timestamp(f"Error calling function {func_name}: {e}", "[call_on_main_thread]")
            import traceback
            traceback.print_exc()
        return
    
    # Not on main thread - use the polling timer receiver
    receiver = _get_receiver()
    if receiver is not None:
        # Add to pending calls - the polling timer will pick it up automatically
        receiver._pending_calls.append((func, args, kwargs))
        log_with_timestamp(f"Added {func_name} to pending calls (will be processed by polling timer)", "[call_on_main_thread]")
        return
    
    # Fallback to QTimer - but we need to ensure it's called from main thread
    # Since we're not on main thread, we need to use a different approach
    # Create a custom event or use QApplication.postEvent
    log_with_timestamp(f"Using QTimer fallback for {func_name} (from background thread)", "[call_on_main_thread]")
    
    # Create a timer on the main thread by posting an event
    # We'll use a lambda that captures the function and args
    def create_timer_on_main():
        """This will be called on main thread to create the timer."""
        def wrapper():
            try:
                log_with_timestamp(f"Executing {func_name} in QTimer wrapper", "[call_on_main_thread]")
                func(*args, **kwargs)
                log_with_timestamp(f"Function {func_name} completed in QTimer wrapper", "[call_on_main_thread]")
            except Exception as e:
                log_with_timestamp(f"Error calling function {func_name}: {e}", "[call_on_main_thread]")
                import traceback
                traceback.print_exc()
        
        # Now we're on main thread, so QTimer will work
        QTimer.singleShot(0, wrapper)
        log_with_timestamp(f"QTimer.singleShot(0) created on main thread for {func_name}", "[call_on_main_thread]")
    
    # Schedule the timer creation on main thread using QMetaObject
    # This ensures the timer is created from the main thread
    receiver = _get_receiver()
    if receiver is not None:
        receiver._pending_calls.append((create_timer_on_main, (), {}))
        QMetaObject.invokeMethod(
            receiver,
            "execute_pending",
            Qt.ConnectionType.QueuedConnection
        )
    else:
        # Last resort: try QTimer directly (might not work from background thread)
        def wrapper():
            try:
                func(*args, **kwargs)
            except Exception as e:
                log_with_timestamp(f"Error calling function {func_name}: {e}", "[call_on_main_thread]")
                import traceback
                traceback.print_exc()
        QTimer.singleShot(0, wrapper)
        log_with_timestamp(f"QTimer.singleShot(0) scheduled directly (may not work from background thread)", "[call_on_main_thread]")


# ============================================================================
# Status Color Utilities (for visual indicators - green/yellow/red)
# ============================================================================

from PyQt6.QtGui import QColor
from enum import Enum


class QuotaDisplayMode(str, Enum):
    """Display mode for quota percentages."""
    REMAINING = "remaining"  # Show remaining percentage
    USED = "used"  # Show used percentage


def get_quota_status_color(usage_percent: float) -> QColor:
    """
    Get color for quota status based on usage percentage.
    
    Logic based on usage percentage:
    - Dark green: usage > 60%
    - Orange: usage >= 20% and <= 60%
    - Red: usage < 20%
    
    Args:
        usage_percent: Usage quota percentage (0-100)
        
    Returns:
        QColor for the status
    """
    # Clamp to valid range
    usage_percent = max(0.0, min(100.0, usage_percent))
    
    # Apply thresholds based on usage
    if usage_percent > 60:
        return QColor(16, 185, 129)  # Dark green (teal-600: #10B981)
    elif usage_percent >= 20 and usage_percent <= 60:
        return QColor(251, 146, 60)  # Orange (#FB923C)
    else:  # usage_percent < 20
        return QColor(239, 68, 68)  # Red (#EF4444)


def get_http_status_color(status_code: int) -> QColor:
    """
    Get color for HTTP status code.
    
    Logic matches original implementation:
    - Green: 200-299 (success)
    - Orange: 400-499 (client error)
    - Red: 500-599 (server error)
    - Gray: other codes
    
    Args:
        status_code: HTTP status code
        
    Returns:
        QColor for the status code
    """
    if 200 <= status_code < 300:
        return QColor(34, 197, 94)  # Green
    elif 400 <= status_code < 500:
        return QColor(251, 146, 60)  # Orange
    elif 500 <= status_code < 600:
        return QColor(239, 68, 68)  # Red
    else:
        return QColor(128, 128, 128)  # Gray


def get_proxy_status_color(is_running: bool) -> QColor:
    """
    Get color for proxy status.
    
    Args:
        is_running: Whether proxy is running
        
    Returns:
        QColor for the status
    """
    if is_running:
        return QColor(34, 197, 94)  # Green
    else:
        return QColor(128, 128, 128)  # Gray


def get_agent_status_color(is_configured: bool) -> QColor:
    """
    Get color for agent configuration status.
    
    Args:
        is_configured: Whether agent is configured
        
    Returns:
        QColor for the status
    """
    if is_configured:
        return QColor(34, 197, 94)  # Green
    else:
        return QColor(239, 68, 68)  # Red


# ============================================================================
# Logging Utilities
# ============================================================================

# Global log file handle
_log_file = None
_log_file_path = None

def _get_log_file_path():
    """Get the path to the log file in the repo root."""
    global _log_file_path
    if _log_file_path is None:
        # Find the repo root by looking for quotio-python directory or .git
        current = Path(__file__).resolve()
        repo_root = None
        
        # Walk up from current file to find repo root
        # Look for quotio-python directory (where this code lives) or parent with .git
        for parent in current.parents:
            # If we're in quotio-python, use its parent (the repo root)
            if parent.name == "quotio-python":
                repo_root = parent.parent
                break
            # Or if we find .git, that's the repo root
            if (parent / ".git").exists():
                repo_root = parent
                break
        
        # Fallback: use quotio-python directory if we can't find repo root
        if repo_root is None:
            # Try to find quotio-python directory
            for parent in current.parents:
                if parent.name == "quotio-python":
                    repo_root = parent
                    break
            # Last resort: use current directory
            if repo_root is None:
                repo_root = Path.cwd()
        
        # Create logs directory if it doesn't exist
        logs_dir = repo_root / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        # Log file name with date
        log_filename = f"quotio_{datetime.now().strftime('%Y%m%d')}.log"
        _log_file_path = logs_dir / log_filename
    
    return _log_file_path

def _get_log_file():
    """Get or create the log file handle."""
    global _log_file
    if _log_file is None or _log_file.closed:
        log_path = _get_log_file_path()
        try:
            _log_file = open(log_path, 'a', encoding='utf-8')
            # Write a separator when opening a new session
            _log_file.write(f"\n{'='*80}\n")
            _log_file.write(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            _log_file.write(f"Log file: {log_path}\n")
            _log_file.write(f"{'='*80}\n")
            _log_file.flush()
            # Also print to terminal
            print(f"Logging to: {log_path}")
        except Exception as e:
            print(f"Warning: Could not open log file {log_path}: {e}", file=sys.stderr)
            _log_file = None
    return _log_file

def close_log_file():
    """Close the log file handle."""
    global _log_file
    if _log_file and not _log_file.closed:
        try:
            _log_file.write(f"\n{'='*80}\n")
            _log_file.write(f"Session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            _log_file.write(f"{'='*80}\n\n")
            _log_file.close()
        except Exception:
            pass
        _log_file = None

def log_with_timestamp(message: str, prefix: str = ""):
    """
    Print a log message with timestamp to both terminal and log file.
    
    Args:
        message: The log message
        prefix: Optional prefix (e.g., "[IDEScan]", "[QuotaViewModel]")
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds
    
    # Format the log message
    if prefix:
        log_message = f"{timestamp} {prefix} {message}"
    else:
        log_message = f"{timestamp} {message}"
    
    # Print to terminal (stdout)
    print(log_message)
    sys.stdout.flush()
    
    # Write to log file
    log_file = _get_log_file()
    if log_file:
        try:
            log_file.write(log_message + "\n")
            log_file.flush()
        except Exception as e:
            # If writing fails, just print to stderr
            print(f"Warning: Could not write to log file: {e}", file=sys.stderr)


# Global storage for original texts (thread-safe since accessed only from main thread)
_label_original_texts = {}

def make_label_copyable(label: QWidget):
    """
    Make a QLabel copyable by enabling text selection and adding context menu.
    
    This function must be called from the main Qt thread to ensure thread safety.
    
    Args:
        label: The QLabel widget to make copyable
    """
    from PyQt6.QtWidgets import QLabel
    
    if not isinstance(label, QLabel):
        return
    
    # Ensure we're on the main thread - if not, schedule this function to run on main thread
    app = QApplication.instance()
    if app is None:
        return
    
    current_thread = QThread.currentThread()
    app_thread = app.thread()
    if current_thread != app_thread:
        # Not on main thread - schedule to run on main thread
        call_on_main_thread(make_label_copyable, label)
        return
    
    # Enable text selection
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | 
        Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    
    # Add context menu for copy
    label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    
    # Create closure-safe functions that capture the label
    def _on_context_menu(position: QPoint):
        """Show context menu with copy option. Called from Qt signal (main thread)."""
        # Ensure we're on main thread (should be, but double-check)
        if QThread.currentThread() != app.thread():
            return
        
        try:
            menu = QMenu(label)
            
            # Copy action - use functools.partial or direct function reference
            copy_action = QAction("Copy", label)
            # Create a bound method that captures the label safely
            def copy_handler():
                _copy_label_text(label)
            copy_action.triggered.connect(copy_handler)
            menu.addAction(copy_action)
            
            # Select All action
            select_all_action = QAction("Select All", label)
            def select_all_handler():
                _select_all_text(label)
            select_all_action.triggered.connect(select_all_handler)
            menu.addAction(select_all_action)
            
            # Show menu at cursor position
            menu.exec(label.mapToGlobal(position))
        except Exception as e:
            # Log error but don't crash
            print(f"[make_label_copyable] Error showing context menu: {e}")
            import traceback
            traceback.print_exc()
    
    label.customContextMenuRequested.connect(_on_context_menu)

def _copy_label_text(widget: QLabel):
    """Copy label text to clipboard. Must be called from main thread."""
    app = QApplication.instance()
    if app is None:
        return
    
    # Ensure we're on main thread
    if QThread.currentThread() != app.thread():
        call_on_main_thread(_copy_label_text, widget)
        return
    
    try:
        clipboard = QApplication.clipboard()
        text = widget.text()
        if text:
            clipboard.setText(text)
            # Show brief feedback
            original_text = widget.text()
            widget_id = id(widget)
            _label_original_texts[widget_id] = original_text
            widget.setText(f"Copied: {text[:50]}..." if len(text) > 50 else f"Copied: {text}")
            
            # Use QTimer safely on main thread
            def restore_text():
                if widget_id in _label_original_texts:
                    widget.setText(_label_original_texts[widget_id])
                    del _label_original_texts[widget_id]
            
            QTimer.singleShot(2000, restore_text)
    except Exception as e:
        print(f"[_copy_label_text] Error copying text: {e}")
        import traceback
        traceback.print_exc()

def _select_all_text(widget: QLabel):
    """Focus the label for text selection. Must be called from main thread."""
    app = QApplication.instance()
    if app is None:
        return
    
    # Ensure we're on main thread
    if QThread.currentThread() != app.thread():
        call_on_main_thread(_select_all_text, widget)
        return
    
    try:
        widget.setFocus()
    except Exception as e:
        print(f"[_select_all_text] Error focusing widget: {e}")
        import traceback
        traceback.print_exc()
