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
from pathlib import Path

# Add parent directory to path for imports
# This allows importing quotio modules when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from quotio.ui.main_window import MainWindow


def setup_debug_logging():
    """
    Set up comprehensive debug logging.
    
    This function configures detailed logging for troubleshooting:
    - Enables Python asyncio debug mode to catch async issues
    - Sets up structured logging with timestamps
    - Configures log levels for different modules (aiohttp, quotio, etc.)
    - Reduces asyncio verbosity to INFO level (DEBUG shows too much transport detail)
    """
    # Enable Python debug mode - this helps catch async/await issues
    os.environ['PYTHONASYNCIODEBUG'] = '1'
    
    # Configure logging with structured format
    # Format: timestamp [level] module: message
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
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
    print("All logs will be shown in the terminal")
    print("Python asyncio debug: ENABLED")
    print("Note: Asyncio transport logs are at INFO level to reduce verbosity")
    print("=" * 60)


def main():
    """
    Main entry point for the application.
    
    WORKFLOW:
    1. Check for debug flags (command line args or environment variable)
    2. Set up debug logging if requested
    3. Create MainWindow instance (this initializes the entire application)
    4. Run the application (starts Qt event loop, shows GUI)
    
    The MainWindow constructor handles:
    - Creating Qt application
    - Setting up async event loop
    - Creating view model (state management)
    - Initializing all UI screens
    - Starting background initialization tasks
    """
    # Check for debug flag from multiple sources:
    # - Command line: --debug or -d
    # - Environment variable: QUOTIO_DEBUG=1/true/yes
    debug_mode = '--debug' in sys.argv or '-d' in sys.argv or os.getenv('QUOTIO_DEBUG', '').lower() in ('1', 'true', 'yes')
    
    if debug_mode:
        setup_debug_logging()
    
    # Cross-platform application - log the platform we're running on
    import platform
    system = platform.system()
    print(f"Quotio - Running on {system}")
    
    if debug_mode:
        print("[DEBUG] Debug mode is enabled")
        print("[DEBUG] Python version:", sys.version)
        print("[DEBUG] Working directory:", os.getcwd())
    
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


if __name__ == "__main__":
    # Entry point when running as a script: python -m quotio.main
    main()
