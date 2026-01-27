"""
Main entry point for Quotio Python Edition.

WORKFLOW OVERVIEW:
==================
This is the application entry point. The workflow proceeds as follows:

1. Application Initialization:
   - Checks for debug flags (--debug, -d, or QUOTIO_DEBUG env var)
   - Sets up debug logging if enabled
   - Creates the MainWindow instance which initializes the entire application

2. MainWindow Initialization (see ui/main_window.py):
   - Creates QApplication for PyQt6 GUI
   - Sets up async event loop in a separate thread (for async operations)
   - Creates QuotaViewModel (central state management)
   - Initializes all UI screens (Dashboard, Providers, Agents, Settings, etc.)
   - Starts the view model initialization (loads settings, starts proxy if auto-start enabled)

3. View Model Initialization (see viewmodels/quota_viewmodel.py):
   - Loads settings from disk
   - Determines operating mode (Local Proxy, Remote Proxy, or Monitor Mode)
   - If auto-start enabled: downloads proxy binary if needed, starts proxy server
   - Sets up API client connection to proxy management API
   - Loads auth files and fetches quota data from all providers
   - Starts background services (usage stats polling, warmup scheduler)

4. Runtime:
   - UI screens display data from view model
   - User interactions trigger async operations via view model
   - View model updates trigger UI callbacks to refresh displays
   - Background services poll for updates periodically

5. Shutdown:
   - User closes application
   - Cleanup handlers close API connections, stop background tasks
   - Proxy process is stopped if running
"""

import asyncio
import sys
import os
import logging
import traceback
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
# This allows importing quotio modules when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from quotio.ui.main_window import MainWindow


# Global log file handle for stdout/stderr redirection
_log_file_handle = None
_original_stdout = None
_original_stderr = None
_asyncio_exception_handler = None  # Global asyncio exception handler


def _get_log_file_path():
    """Get the path to the log file in the logs directory."""
    # Find the repo root by looking for quotio-python directory or .git
    current = Path(__file__).resolve()
    repo_root = None
    
    # Walk up from current file to find repo root
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
    
    # Log file name with timestamp
    log_filename = f"quotio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    return logs_dir / log_filename


class TeeOutput:
    """A class that writes to both file and original stdout/stderr."""
    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file
    
    def write(self, message):
        """Write to both original stream and log file."""
        try:
            self.original_stream.write(message)
            self.original_stream.flush()
            if self.log_file:
                self.log_file.write(message)
                self.log_file.flush()
        except Exception:
            # If writing fails, try to write to original stream only
            try:
                self.original_stream.write(message)
                self.original_stream.flush()
            except Exception:
                pass
    
    def flush(self):
        """Flush both streams."""
        try:
            self.original_stream.flush()
            if self.log_file:
                self.log_file.flush()
        except Exception:
            pass
    
    def __getattr__(self, name):
        """Delegate other attributes to original stream."""
        return getattr(self.original_stream, name)


def setup_file_logging():
    """
    Set up file logging to redirect all logs and errors to a log file.
    
    This function:
    - Creates a log file in the logs directory
    - Sets up Python logging to write to the file
    - Redirects stdout and stderr to both console and file
    - Sets up exception handlers to log uncaught exceptions
    """
    global _log_file_handle, _original_stdout, _original_stderr
    
    log_path = _get_log_file_path()
    
    try:
        # Open log file in append mode
        _log_file_handle = open(log_path, 'a', encoding='utf-8')
        
        # Write header
        _log_file_handle.write(f"\n{'='*80}\n")
        _log_file_handle.write(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        _log_file_handle.write(f"Log file: {log_path}\n")
        _log_file_handle.write(f"Python version: {sys.version}\n")
        _log_file_handle.write(f"Working directory: {os.getcwd()}\n")
        _log_file_handle.write(f"{'='*80}\n\n")
        _log_file_handle.flush()
        
        # Save original stdout and stderr
        _original_stdout = sys.stdout
        _original_stderr = sys.stderr
        
        # Redirect stdout and stderr to both console and file
        sys.stdout = TeeOutput(_original_stdout, _log_file_handle)
        sys.stderr = TeeOutput(_original_stderr, _log_file_handle)
        
        # Set up exception handler to log uncaught exceptions
        def exception_handler(exc_type, exc_value, exc_traceback):
            """Log uncaught exceptions to the log file."""
            if issubclass(exc_type, KeyboardInterrupt):
                # Don't log keyboard interrupts
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            print(f"\n{'='*80}", file=sys.stderr)
            print(f"Uncaught exception:", file=sys.stderr)
            print(error_msg, file=sys.stderr)
            print(f"{'='*80}\n", file=sys.stderr)
            sys.stderr.flush()
        
        sys.excepthook = exception_handler
        
        # Set up asyncio exception handler
        def asyncio_exception_handler(loop, context):
            """Log asyncio exceptions."""
            exception = context.get('exception')
            if exception:
                error_msg = ''.join(traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                ))
                print(f"\n{'='*80}", file=sys.stderr)
                print(f"Asyncio exception:", file=sys.stderr)
                print(f"Context: {context}", file=sys.stderr)
                print(error_msg, file=sys.stderr)
                print(f"{'='*80}\n", file=sys.stderr)
            else:
                print(f"\n{'='*80}", file=sys.stderr)
                print(f"Asyncio error: {context}", file=sys.stderr)
                print(f"{'='*80}\n", file=sys.stderr)
            sys.stderr.flush()
        
        # Store handler globally for later use when loop is created
        global _asyncio_exception_handler
        _asyncio_exception_handler = asyncio_exception_handler
        
        print(f"Logging to file: {log_path}")
        print(f"All logs and errors will be written to: {log_path}")
        
        return log_path
        
    except Exception as e:
        print(f"Warning: Could not set up file logging: {e}", file=sys.stderr)
        return None, None


def setup_debug_logging(log_file_path=None):
    """
    Set up comprehensive debug logging.
    
    This function configures detailed logging for troubleshooting:
    - Enables Python asyncio debug mode to catch async issues
    - Sets up structured logging with timestamps
    - Configures log levels for different modules (aiohttp, quotio, etc.)
    - Reduces asyncio verbosity to INFO level (DEBUG shows too much transport detail)
    
    Args:
        log_file_path: Optional path to log file for file handler
    """
    # Enable Python debug mode - this helps catch async/await issues
    os.environ['PYTHONASYNCIODEBUG'] = '1'
    
    # Create log file handler if log file path is provided
    handlers = []
    if log_file_path:
        try:
            file_handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file handler: {e}", file=sys.stderr)
    
    # Configure logging with structured format
    # Format: timestamp [level] module: message
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers if handlers else None,
        force=True  # Override any existing configuration
    )
    
    # Enable asyncio debug mode (will be set when loop is created)
    # Store flag for later use in async loop setup
    os.environ['ASYNCIO_DEBUG'] = '1'
    
    # Set log levels for specific modules
    # aiohttp is used for HTTP requests to proxy API
    logging.getLogger('aiohttp').setLevel(logging.DEBUG)
    logging.getLogger('aiohttp.client').setLevel(logging.DEBUG)
    logging.getLogger('aiohttp.connector').setLevel(logging.DEBUG)
    # Our application code
    logging.getLogger('quotio').setLevel(logging.DEBUG)
    
    # Configure asyncio logging to be less verbose
    # The "connected to None:None" in asyncio debug logs shows peer name/port
    # which is None for localhost connections - this is normal and not an error
    asyncio_logger = logging.getLogger('asyncio')
    # Keep asyncio logs but at INFO level to reduce verbosity
    # (DEBUG level shows all transport connection details which is too noisy)
    asyncio_logger.setLevel(logging.INFO)
    
    print("=" * 60)
    print("DEBUG MODE ENABLED")
    print("=" * 60)
    print("All logs will be shown in the terminal and written to log file")
    print("Python asyncio debug: ENABLED")
    print("Note: Asyncio transport logs are at INFO level to reduce verbosity")
    print("=" * 60)


def cleanup_logging():
    """Clean up logging resources."""
    global _log_file_handle, _original_stdout, _original_stderr
    
    if _log_file_handle:
        try:
            _log_file_handle.write(f"\n{'='*80}\n")
            _log_file_handle.write(f"Session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            _log_file_handle.write(f"{'='*80}\n\n")
            _log_file_handle.close()
        except Exception:
            pass
        _log_file_handle = None
    
    # Restore original stdout and stderr
    if _original_stdout:
        sys.stdout = _original_stdout
    if _original_stderr:
        sys.stderr = _original_stderr


def main():
    """
    Main entry point for the application.
    
    WORKFLOW:
    1. Set up file logging (redirects all logs and errors to log file)
    2. Check for debug flags (command line args or environment variable)
    3. Set up debug logging if requested
    4. Create MainWindow instance (this initializes the entire application)
    5. Run the application (starts Qt event loop, shows GUI)
    
    The MainWindow constructor handles:
    - Creating Qt application
    - Setting up async event loop
    - Creating view model (state management)
    - Initializing all UI screens
    - Starting background initialization tasks
    """
    # Set up file logging first (before any other output)
    log_path = setup_file_logging()
    
    # Check for debug flag from multiple sources:
    # - Command line: --debug or -d
    # - Environment variable: QUOTIO_DEBUG=1/true/yes
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv or os.getenv('QUOTIO_DEBUG', '').lower() in ('1', 'true', 'yes')
    
    if debug_mode:
        setup_debug_logging(log_path)
    
    # Cross-platform application - log the platform we're running on
    import platform
    system = platform.system()
    print(f"Quotio - Running on {system}")
    
    if debug_mode:
        print("[DEBUG] Debug mode is enabled")
        print("[DEBUG] Python version:", sys.version)
        print("[DEBUG] Working directory:", os.getcwd())
    
    try:
        # Create and run the application
        # MainWindow.__init__() sets up:
        # - Qt application
        # - Async event loop in background thread
        # - View model (QuotaViewModel)
        # - All UI screens
        # - Starts initialization process
        app = MainWindow()
        
        # Run the application - this starts the Qt event loop
        # The application will run until the user closes the window
        app.run()
    finally:
        # Clean up logging resources
        cleanup_logging()


if __name__ == "__main__":
    # Entry point when running as a script: python -m quotio.main
    main()
