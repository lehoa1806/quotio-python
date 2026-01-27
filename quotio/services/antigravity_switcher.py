"""Antigravity account switcher service."""

import json
import os
import sqlite3
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class SwitchState(str, Enum):
    """Account switch state."""
    IDLE = "idle"
    CONFIRMING = "confirming"
    SWITCHING = "switching"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class AntigravityActiveAccount:
    """Currently active Antigravity account."""
    email: str
    detected_at: datetime


class AntigravityAccountSwitcher:
    """Orchestrates Antigravity account switching."""

    def __init__(self):
        """Initialize the switcher."""
        self.switch_state = SwitchState.IDLE
        self.current_active_account: Optional[AntigravityActiveAccount] = None
        self._database_service = None
        self._is_docker = self._detect_docker()

    def _detect_docker(self) -> bool:
        """Detect if running inside Docker container."""
        # Check for Docker indicators
        try:
            # Check for .dockerenv file
            if Path("/.dockerenv").exists():
                return True
            # Check cgroup (common Docker indicator)
            try:
                with open("/proc/self/cgroup", "r") as f:
                    content = f.read()
                    if "docker" in content or "containerd" in content:
                        return True
            except (FileNotFoundError, IOError):
                pass
            # Check environment variable
            if os.getenv("container") == "docker":
                return True
        except Exception:
            pass
        return False

    def _get_database_path(self) -> Optional[Path]:
        """Get Antigravity database path."""
        import platform
        if platform.system() != "Darwin":
            return None

        # Try common paths
        paths = [
            Path.home() / "Library" / "Application Support" / "Antigravity" / "User" / "globalStorage" / "state.vscdb",
            Path.home() / "Library" / "Application Support" / "Antigravity" / "User" / "globalStorage" / "state.db",
        ]

        for path in paths:
            if path.exists():
                return path

        return None

    async def is_database_available(self) -> bool:
        """Check if Antigravity IDE database exists."""
        return self._get_database_path() is not None

    def is_ide_running(self) -> bool:
        """Check if Antigravity IDE is currently running."""
        import platform
        if platform.system() != "Darwin":
            return False

        # Cannot detect host processes from Docker
        if self._is_docker:
            print("[AntigravitySwitcher] Running in Docker - cannot detect if IDE is running on host")
            return False  # Assume not running to be safe

        try:
            # Check for Antigravity process
            result = subprocess.run(
                ["pgrep", "-f", "Antigravity"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    async def detect_active_account(self):
        """Detect the currently active account in Antigravity IDE."""
        db_path = self._get_database_path()
        if not db_path:
            self.current_active_account = None
            return

        try:
            email = await self._get_active_email(db_path)
            if email:
                self.current_active_account = AntigravityActiveAccount(
                    email=email,
                    detected_at=datetime.now()
                )
            else:
                self.current_active_account = None
        except Exception as e:
            print(f"[AntigravitySwitcher] Error detecting active account: {e}")
            self.current_active_account = None

    async def _get_active_email(self, db_path: Path) -> Optional[str]:
        """Get active email from database."""
        import asyncio

        def read_db():
            try:
                conn = sqlite3.connect(str(db_path), timeout=5.0)
                conn.execute("PRAGMA busy_timeout = 5000")
                cursor = conn.cursor()

                # Try to find email in antigravityAuthStatus
                cursor.execute(
                    "SELECT value FROM ItemTable WHERE key = 'antigravityAuthStatus'"
                )
                row = cursor.fetchone()

                if row:
                    value = row[0]
                    if isinstance(value, str):
                        try:
                            data = json.loads(value)
                            if isinstance(data, dict):
                                email = data.get("email") or data.get("account")
                                if email:
                                    conn.close()
                                    return email
                        except:
                            pass

                conn.close()
            except Exception as e:
                print(f"[AntigravitySwitcher] Error reading database: {e}")
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, read_db)

    def is_active_account(self, email: str) -> bool:
        """Check if a given email matches the currently active account."""
        if not self.current_active_account:
            return False
        return self.current_active_account.email.lower() == email.lower()

    def begin_switch(self, account_id: str, account_email: str):
        """Begin the account switch confirmation flow."""
        self.switch_state = SwitchState.CONFIRMING

    def cancel_switch(self):
        """Cancel the current switch operation."""
        self.switch_state = SwitchState.IDLE

    async def execute_switch(
        self,
        auth_file_path: str,
        should_restart_ide: bool = True
    ):
        """Execute the account switch."""
        self.switch_state = SwitchState.SWITCHING

        try:
            # Read auth file
            auth_path = Path(auth_file_path).expanduser()
            if not auth_path.exists():
                self.switch_state = SwitchState.FAILED
                return

            with open(auth_path, "r") as f:
                auth_data = json.load(f)

            # Try multiple token field names
            access_token = (
                auth_data.get("access_token") or
                auth_data.get("accessToken") or
                auth_data.get("token")
            )

            refresh_token = (
                auth_data.get("refresh_token") or
                auth_data.get("refreshToken")
            )

            # Check if token is expired and refresh if needed
            expired_str = auth_data.get("expired") or auth_data.get("expires_at")
            is_expired = False
            if expired_str:
                try:
                    if isinstance(expired_str, (int, float)):
                        expiry_date = datetime.fromtimestamp(expired_str)
                    else:
                        expiry_date = datetime.fromisoformat(str(expired_str).replace("Z", "+00:00"))
                    is_expired = expiry_date < datetime.now()
                except:
                    pass

            # Refresh token if expired
            if (not access_token or is_expired) and refresh_token:
                print("[AntigravitySwitcher] Token expired or missing, refreshing...")
                try:
                    from ..quota_fetchers.antigravity import AntigravityQuotaFetcher
                    fetcher = AntigravityQuotaFetcher()
                    new_access_token = await fetcher._refresh_access_token(refresh_token)
                    if new_access_token:
                        access_token = new_access_token
                        # Update auth file with new token
                        auth_data["access_token"] = new_access_token
                        auth_data["accessToken"] = new_access_token
                        with open(auth_path, "w") as f:
                            json.dump(auth_data, f, indent=2)
                        print("[AntigravitySwitcher] Token refreshed successfully")
                    else:
                        print("[AntigravitySwitcher] Token refresh failed")
                except Exception as e:
                    print(f"[AntigravitySwitcher] Error refreshing token: {e}")

            if not access_token:
                print(f"[AntigravitySwitcher] No access token found in auth file. Keys: {list(auth_data.keys())}")
                self.switch_state = SwitchState.FAILED
                return

            # Check if IDE is running
            was_ide_running = self.is_ide_running()

            # Close IDE if running
            if was_ide_running:
                if self._is_docker:
                    print("[AntigravitySwitcher] Running in Docker - IDE close skipped")
                    print("[AntigravitySwitcher] Please manually close Antigravity IDE before switching")
                else:
                    await self._close_ide()

            # Clean up WAL files to release database locks
            await self._cleanup_wal_files()

            # Wait for SQLite WAL to flush and release database lock
            import asyncio
            settle_delay = 2.0 if was_ide_running else 0.5
            await asyncio.sleep(settle_delay)

            # Update database with new token
            db_path = self._get_database_path()
            if db_path:
                await self._update_database_token(db_path, access_token, refresh_token, auth_data)
            else:
                print("[AntigravitySwitcher] Database not found, cannot update token")
                self.switch_state = SwitchState.FAILED
                return

            # Restart IDE if it was running
            if was_ide_running and should_restart_ide:
                if self._is_docker:
                    print("[AntigravitySwitcher] Running in Docker - IDE restart skipped")
                    print("[AntigravitySwitcher] Database updated successfully. Please manually restart Antigravity IDE to apply changes.")
                else:
                    await self._restart_ide()

            # Update active account
            email = auth_data.get("email") or auth_data.get("account")
            if email:
                self.current_active_account = AntigravityActiveAccount(
                    email=email,
                    detected_at=datetime.now()
                )

            self.switch_state = SwitchState.SUCCESS
        except Exception as e:
            print(f"[AntigravitySwitcher] Error executing switch: {e}")
            import traceback
            traceback.print_exc()
            self.switch_state = SwitchState.FAILED

    async def _close_ide(self):
        """Close Antigravity IDE."""
        import platform
        if platform.system() != "Darwin":
            return

        # Cannot kill host processes from Docker
        if self._is_docker:
            print("[AntigravitySwitcher] Running in Docker - cannot close IDE on host")
            print("[AntigravitySwitcher] Please manually close Antigravity IDE before switching")
            return

        try:
            subprocess.run(["pkill", "-f", "Antigravity"], timeout=5)
            # Wait a bit for process to close
            import asyncio
            await asyncio.sleep(1.0)
        except Exception as e:
            print(f"[AntigravitySwitcher] Error closing IDE: {e}")

    async def _restart_ide(self):
        """Restart Antigravity IDE."""
        import platform
        if platform.system() != "Darwin":
            return

        # Cannot launch host applications from Docker
        if self._is_docker:
            print("[AntigravitySwitcher] Running in Docker - cannot restart IDE on host")
            print("[AntigravitySwitcher] Database has been updated. Please manually restart Antigravity IDE.")
            return

        try:
            # Find Antigravity app
            app_paths = [
                Path("/Applications/Antigravity.app"),
                Path.home() / "Applications" / "Antigravity.app",
            ]

            for app_path in app_paths:
                if app_path.exists():
                    subprocess.Popen(["open", str(app_path)])
                    return
        except Exception as e:
            print(f"[AntigravitySwitcher] Error restarting IDE: {e}")

    async def _cleanup_wal_files(self):
        """Clean up WAL and SHM files to release database locks."""
        db_path = self._get_database_path()
        if not db_path:
            return

        wal_path = db_path.parent / f"{db_path.name}-wal"
        shm_path = db_path.parent / f"{db_path.name}-shm"

        try:
            if wal_path.exists():
                wal_path.unlink()
            if shm_path.exists():
                shm_path.unlink()
        except Exception as e:
            print(f"[AntigravitySwitcher] Error cleaning up WAL files: {e}")

    async def _update_database_token(self, db_path: Path, access_token: str, refresh_token: Optional[str], auth_data: dict):
        """Update database with new token.

        This updates both antigravityAuthStatus and the protobuf state.
        This is the critical part that actually switches the account.
        """
        import asyncio
        from datetime import datetime

        def update_db():
            try:
                conn = sqlite3.connect(str(db_path), timeout=10.0)
                conn.execute("PRAGMA busy_timeout = 10000")
                cursor = conn.cursor()

                # Start transaction
                cursor.execute("BEGIN IMMEDIATE TRANSACTION")

                try:
                    email = auth_data.get("email") or auth_data.get("account", "")

                    # 1. Update antigravityAuthStatus
                    auth_status = {
                        "email": email,
                        "accessToken": access_token,
                        "refreshToken": refresh_token,
                        "expiresAt": auth_data.get("expired") or auth_data.get("expires_at"),
                    }
                    auth_status_json = json.dumps(auth_status)

                    cursor.execute(
                        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                        ("antigravityAuthStatus", auth_status_json)
                    )

                    # 2. Update the protobuf state (jetskiStateSync.agentManagerInitState)
                    # This is the critical part that actually switches the account
                    state_key = "jetskiStateSync.agentManagerInitState"
                    cursor.execute(
                        "SELECT value FROM ItemTable WHERE key = ?",
                        (state_key,)
                    )
                    state_row = cursor.fetchone()

                    if state_row and state_row[0]:
                        existing_state = state_row[0]

                        # Calculate expiry timestamp
                        expiry = None
                        expired_str = auth_data.get("expired") or auth_data.get("expires_at")
                        if expired_str:
                            try:
                                if isinstance(expired_str, (int, float)):
                                    expiry = int(expired_str)
                                else:
                                    # Try to parse as ISO8601 or timestamp
                                    try:
                                        expiry_date = datetime.fromisoformat(str(expired_str).replace("Z", "+00:00"))
                                        expiry = int(expiry_date.timestamp())
                                    except:
                                        pass
                            except:
                                pass

                        # Default to 1 hour from now if no expiry
                        if expiry is None:
                            expiry = int(datetime.now().timestamp()) + 3600

                        # Inject token into protobuf
                        try:
                            from .antigravity_protobuf_handler import inject_token

                            new_state = inject_token(
                                existing_base64=existing_state,
                                access_token=access_token,
                                refresh_token=refresh_token or "",
                                expiry=expiry
                            )

                            cursor.execute(
                                "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                                (state_key, new_state)
                            )
                            print(f"[AntigravitySwitcher] Successfully injected token into protobuf state")
                        except Exception as e:
                            print(f"[AntigravitySwitcher] Error injecting token into protobuf: {e}")
                            import traceback
                            traceback.print_exc()
                            # Continue anyway - antigravityAuthStatus update might be enough
                    else:
                        print(f"[AntigravitySwitcher] Warning: No existing state found in database")

                    # 3. Set onboarding flag
                    cursor.execute(
                        "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                        ("antigravityOnboarding", "true")
                    )

                    # Commit transaction
                    conn.commit()
                    print(f"[AntigravitySwitcher] Successfully updated database with token for {email}")
                except Exception as e:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
            except Exception as e:
                print(f"[AntigravitySwitcher] Error updating database: {e}")
                import traceback
                traceback.print_exc()
                raise

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, update_db)
