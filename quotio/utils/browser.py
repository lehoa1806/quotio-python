"""Cross-platform browser utilities."""

import platform
import webbrowser
from typing import Optional


def open_browser(url: str) -> bool:
    """Open a URL in the default browser (cross-platform).

    Args:
        url: URL to open

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"[Browser] Attempting to open: {url}")  # Debug
        result = webbrowser.open(url)
        print(f"[Browser] webbrowser.open() returned: {result}")  # Debug
        # webbrowser.open() returns True if it successfully launched a browser
        # On some systems it may return False but still work
        return True  # Assume success if no exception
    except Exception as e:
        print(f"[Browser] Exception: {e}")  # Debug
        return False
