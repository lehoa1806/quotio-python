"""IDE scan service for detecting IDEs and CLI tools.

This service provides explicit, user-consent-based scanning for IDE quota tracking.
Cursor and Trae quotas are NOT auto-refreshed - they require explicit user scan
to address privacy concerns (issue #29).
"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import platform

from ..models.operating_mode import OperatingModeManager


@dataclass
class IDEScanOptions:
    """Options for IDE scanning."""
    scan_cursor: bool = False
    scan_trae: bool = False
    scan_cli_tools: bool = True

    @property
    def has_ide_scan_enabled(self) -> bool:
        """Check if any IDE scan option is enabled."""
        return self.scan_cursor or self.scan_trae

    @property
    def has_any_scan_enabled(self) -> bool:
        """Check if any scan option is enabled."""
        return self.scan_cursor or self.scan_trae or self.scan_cli_tools


@dataclass
class IDEScanResult:
    """Result of an IDE scan operation."""
    cursor_found: bool = False
    cursor_email: Optional[str] = None
    trae_found: bool = False
    trae_email: Optional[str] = None
    cli_tools_found: List[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        """Initialize default values."""
        if self.cli_tools_found is None:
            self.cli_tools_found = []
        if self.timestamp is None:
            self.timestamp = datetime.now()


class IDEScanService:
    """Service for scanning IDEs and CLI tools."""

    def __init__(self):
        """Initialize the service."""
        self.system = platform.system()

    async def scan(self, options: IDEScanOptions) -> IDEScanResult:
        """Perform IDE scan with given options."""
        result = IDEScanResult()

        # Scan Cursor if enabled
        if options.scan_cursor:
            cursor_result = await self._scan_cursor()
            result.cursor_found = cursor_result["found"]
            result.cursor_email = cursor_result.get("email")

        # Scan Trae if enabled
        if options.scan_trae:
            trae_result = await self._scan_trae()
            result.trae_found = trae_result["found"]
            result.trae_email = trae_result.get("email")

        # Scan CLI tools if enabled
        if options.scan_cli_tools:
            result.cli_tools_found = await self._scan_cli_tools()

        return result

    async def _scan_cursor(self) -> dict:
        """Scan for Cursor IDE."""
        if self.system != "Darwin":  # macOS only
            return {"found": False}

        # Check for Cursor database
        cursor_db_paths = [
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb",
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.db",
        ]

        for db_path in cursor_db_paths:
            if db_path.exists():
                # Try to read email from database
                email = await self._read_cursor_email(db_path)
                return {"found": True, "email": email}

        return {"found": False}

    async def _scan_trae(self) -> dict:
        """Scan for Trae IDE."""
        if self.system != "Darwin":  # macOS only
            return {"found": False}

        # Check for Trae storage
        trae_storage_path = Path.home() / "Library" / "Application Support" / "Trae" / "User" / "globalStorage" / "storage.json"

        if trae_storage_path.exists():
            # Try to read email from storage
            email = await self._read_trae_email(trae_storage_path)
            return {"found": True, "email": email}

        return {"found": False}

    async def _scan_cli_tools(self) -> List[str]:
        """Scan for installed CLI tools."""
        import shutil

        cli_names = ["claude", "codex", "gemini", "gh", "copilot"]
        found_tools = []

        for name in cli_names:
            if shutil.which(name):
                found_tools.append(name)

        return found_tools

    async def _read_cursor_email(self, db_path: Path) -> Optional[str]:
        """Read email from Cursor database."""
        try:
            import sqlite3
            import asyncio
            import json

            # Run in executor to avoid blocking
            def read_db():
                try:
                    # Try with immutable=1 first (read-only, no WAL)
                    try:
                        uri = f"file://{db_path}?mode=ro&immutable=1"
                        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
                    except Exception:
                        # Fallback: try without immutable (may need WAL file)
                        try:
                            conn = sqlite3.connect(str(db_path), timeout=5.0)
                        except Exception as e:
                            print(f"[IDEScan] Failed to connect to Cursor DB: {e}")
                            return None

                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    # Query for auth data - try different key patterns
                    queries = [
                        "SELECT key, value FROM ItemTable WHERE key LIKE 'cursorAuth/%'",
                        "SELECT key, value FROM ItemTable WHERE key LIKE '%cursorAuth%'",
                        "SELECT key, value FROM ItemTable WHERE key LIKE '%email%'",
                    ]

                    for query in queries:
                        try:
                            cursor.execute(query)
                            rows = cursor.fetchall()
                            if rows:
                                for row in rows:
                                    key = row["key"]
                                    value = row["value"]

                                    # Check for cached email
                                    if key == "cursorAuth/cachedEmail":
                                        if value:
                                            return value

                                    # Try to extract email from JSON values
                                    if isinstance(value, str):
                                        try:
                                            data = json.loads(value)
                                            if isinstance(data, dict):
                                                email = data.get("email") or data.get("account") or data.get("cachedEmail")
                                                if email and "@" in email:
                                                    return email
                                        except:
                                            pass
                        except Exception as e:
                            print(f"[IDEScan] Query failed: {query[:50]}... Error: {e}")
                            continue

                    conn.close()
                except Exception as e:
                    print(f"[IDEScan] Error reading Cursor DB: {e}")
                    return None
                return None

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, read_db)
        except Exception as e:
            print(f"[IDEScan] Error reading Cursor email: {e}")
            return None

    async def _read_trae_email(self, storage_path: Path) -> Optional[str]:
        """Read email from Trae storage."""
        try:
            import json
            import asyncio

            def read_file():
                try:
                    with open(storage_path, "r") as f:
                        storage = json.load(f)

                        # Trae stores auth info under a specific key
                        auth_key = "iCubeAuthInfo://icube.cloudide"
                        auth_info_string = storage.get(auth_key)

                        if auth_info_string:
                            # Parse the auth info JSON string
                            auth_info = json.loads(auth_info_string)
                            if isinstance(auth_info, dict):
                                account = auth_info.get("account")
                                if isinstance(account, dict):
                                    email = account.get("email")
                                    if email:
                                        return email
                                # Fallback: try direct email field
                                email = auth_info.get("email")
                                if email:
                                    return email

                        # Fallback: try to find email anywhere in storage
                        if isinstance(storage, dict):
                            return storage.get("email") or storage.get("account")
                except Exception as e:
                    print(f"[IDEScan] Error reading Trae storage: {e}")
                    return None
                return None

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, read_file)
        except Exception as e:
            print(f"[IDEScan] Error reading Trae email: {e}")
            return None
