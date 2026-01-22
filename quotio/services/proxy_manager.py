"""
CLIProxyManager - Manages the CLIProxyAPI binary and process.

WORKFLOW OVERVIEW:
==================
This module manages the lifecycle of the CLIProxyAPI binary, which is the core
proxy server that routes requests from AI coding agents to various AI providers.

KEY RESPONSIBILITIES:
1. Binary Management:
   - Downloads the CLIProxyAPI binary from GitHub releases
   - Verifies binary integrity and sets executable permissions
   - Handles cross-platform differences (macOS, Windows, Linux)

2. Process Management:
   - Starts the proxy process as a subprocess
   - Monitors process health and handles crashes
   - Stops the process cleanly on shutdown

3. Configuration Management:
   - Creates and manages config.yaml with proxy settings
   - Manages management key for API authentication
   - Handles port configuration and updates

4. State Tracking:
   - Tracks proxy status (running/stopped/starting/error)
   - Tracks download progress
   - Reports errors and status to UI

WORKFLOW:
1. __init__() - Sets up paths, loads config, generates management key
2. start() - Downloads binary if needed, starts proxy process
3. stop() - Stops proxy process, cleans up resources
4. download_and_install_binary() - Downloads binary from GitHub, verifies, installs
5. Runtime - Monitors process, updates status, handles errors
"""

import asyncio
import json
import os
import platform
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import aiohttp
import yaml

from ..models.proxy import ProxyStatus


@dataclass
class ProxyError(Exception):
    """
    Proxy-related errors.
    
    Custom exception class for proxy-specific errors with predefined
    error types for common scenarios.
    """
    message: str
    
    @classmethod
    def operation_in_progress(cls):
        """Error when an operation is already in progress."""
        return cls("Operation already in progress")
    
    @classmethod
    def no_compatible_binary(cls):
        """Error when no compatible binary is found for the system."""
        return cls("No compatible binary found for this system")
    
    @classmethod
    def network_error(cls, msg: str):
        """Error for network-related issues (download, API calls)."""
        return cls(f"Network error: {msg}")


class CLIProxyManager:
    """
    Manages CLIProxyAPI binary lifecycle and configuration.
    
    ARCHITECTURE:
    This class is responsible for the entire lifecycle of the proxy binary:
    - Downloading the binary from GitHub releases
    - Installing and verifying the binary
    - Starting/stopping the proxy process
    - Managing configuration files
    - Tracking process status and health
    
    WORKFLOW:
    1. __init__() - Sets up paths, loads settings, creates config
    2. start() - Checks if binary exists, downloads if needed, starts process
    3. Runtime - Monitors process, handles crashes, updates status
    4. stop() - Stops process, cleans up resources
    """
    
    # GitHub repository containing the CLIProxyAPI binary releases
    GITHUB_REPO = "router-for-me/CLIProxyAPIPlus"
    # Name of the binary executable
    BINARY_NAME = "CLIProxyAPI"
    
    def __init__(self):
        """
        Initialize the proxy manager.
        
        WORKFLOW:
        1. Determine platform-specific application support directory
        2. Create Quotio directory for storing binary and config
        3. Set up paths for binary, config, and auth directory
        4. Load or generate management key (for API authentication)
        5. Initialize proxy status and load port from settings
        6. Set up process tracking variables
        7. Ensure config file exists with defaults
        """
        # Cross-platform path determination
        # Different OSes store application data in different locations
        system = platform.system()
        if system == "Darwin":  # macOS
            app_support = Path.home() / "Library" / "Application Support"
        elif system == "Windows":
            app_support = Path.home() / "AppData" / "Local"
        else:  # Linux and others
            app_support = Path.home() / ".local" / "share"
        
        # Create Quotio directory for storing binary and configuration
        self.quotio_dir = app_support / "Quotio-Python"
        self.quotio_dir.mkdir(parents=True, exist_ok=True)
        
        # Set restrictive permissions on directory (owner read/write/execute only)
        # This is a security measure to prevent other users from accessing the directory
        try:
            os.chmod(self.quotio_dir, 0o700)
        except Exception:
            pass  # May fail on Windows (Windows doesn't support Unix permissions)
        
        # Paths for binary, config, and auth directory
        self.binary_path = self.quotio_dir / self.BINARY_NAME
        self.config_path = self.quotio_dir / "config.yaml"
        # Auth directory is where the proxy stores OAuth tokens and auth files
        self.auth_dir = Path.home() / ".cli-proxy-api"
        self.auth_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or generate management key
        # This key is used to authenticate with the proxy's management API
        self._load_management_key()
        
        # Initialize proxy status (tracks running state, port, etc.)
        self.proxy_status = ProxyStatus()
        self._load_port()  # Load port from settings or use default
        
        # Process tracking variables
        self._process: Optional[subprocess.Popen] = None  # The subprocess running the proxy
        self.is_starting = False  # Flag: proxy is currently starting
        self.is_downloading = False  # Flag: binary is currently downloading
        self._cancel_download = False  # Flag: cancel download if requested
        self.download_progress = 0.0  # Download progress (0.0 to 1.0)
        self.last_error: Optional[str] = None  # Last error message
        
        # Ensure config file exists with default values
        # This creates the config.yaml if it doesn't exist
        self._ensure_config_exists()
    
    def _load_management_key(self):
        """Load or generate management key using keyring for secure storage."""
        try:
            import keyring
            service_name = "quotio"
            key_name = "management_key"
            
            # Try to get existing key from keyring
            self.management_key = keyring.get_password(service_name, key_name)
            
            if not self.management_key:
                # Generate new key and store securely
                self.management_key = str(uuid.uuid4())
                keyring.set_password(service_name, key_name, self.management_key)
        except Exception:
            # Fallback to file-based storage with secure permissions
            key_file = self.quotio_dir / "management_key.txt"
            if key_file.exists():
                self.management_key = key_file.read_text().strip()
            else:
                self.management_key = str(uuid.uuid4())
                key_file.write_text(self.management_key)
                # Set restrictive permissions (owner read/write only)
                os.chmod(key_file, 0o600)
    
    def _load_port(self):
        """Load port from settings."""
        try:
            from ..utils.settings import SettingsManager
            settings = SettingsManager()
            port = settings.get("proxyPort", 8317)
            if isinstance(port, int) and 1024 <= port <= 65535:
                self.proxy_status.port = port
            else:
                self.proxy_status.port = 8317
        except Exception:
            self.proxy_status.port = 8317
    
    @property
    def port(self) -> int:
        """Get current port."""
        return self.proxy_status.port
    
    @port.setter
    def port(self, value: int):
        """Set port and update config."""
        self.proxy_status.port = value
        # Save to settings
        try:
            from ..utils.settings import SettingsManager
            settings = SettingsManager()
            settings.set("proxyPort", value)
        except Exception:
            pass
        self._update_config_port(value)
    
    @property
    def base_url(self) -> str:
        """Base URL for proxy API."""
        return f"http://127.0.0.1:{self.proxy_status.port}"
    
    @property
    def management_url(self) -> str:
        """Management API URL."""
        return f"{self.base_url}/v0/management"
    
    @property
    def client_endpoint(self) -> str:
        """Client-facing endpoint URL."""
        return f"http://127.0.0.1:{self.proxy_status.port}"
    
    @property
    def proxy_url(self) -> Optional[str]:
        """Get proxy URL from config if set."""
        # In real implementation, read from config
        return None
    
    @property
    def is_binary_installed(self) -> bool:
        """Check if binary is installed."""
        return self.binary_path.exists() and os.access(self.binary_path, os.X_OK)
    
    def _ensure_config_exists(self):
        """Ensure config file exists with defaults."""
        if self.config_path.exists():
            return
        
        default_config = {
            "host": "127.0.0.1",
            "port": self.proxy_status.port,
            "auth-dir": str(self.auth_dir),
            "proxy-url": "",
            "api-keys": [f"quotio-local-{uuid.uuid4()}"],
            "remote-management": {
                "allow-remote": False,
                "secret-key": self.management_key,
            },
            "debug": False,
            "logging-to-file": False,
            "usage-statistics-enabled": True,
            "routing": {
                "strategy": "round-robin",
            },
            "quota-exceeded": {
                "switch-project": True,
                "switch-preview-model": True,
            },
            "request-retry": 3,
            "max-retry-interval": 30,
        }
        
        # Security: Set umask to restrict file permissions
        old_umask = os.umask(0o077)
        try:
            with open(self.config_path, "w") as f:
                yaml.dump(default_config, f, default_flow_style=False)
            # Explicitly set restrictive permissions
            os.chmod(self.config_path, 0o600)
        finally:
            os.umask(old_umask)
    
    def _update_config_port(self, port: int):
        """Update port in config file."""
        self._update_config_value(r"port:\s*\d+", f"port: {port}")
    
    def _update_config_value(self, pattern: str, replacement: str):
        """Update a value in the config file using regex."""
        if not self.config_path.exists():
            return
        
        content = self.config_path.read_text()
        content = re.sub(pattern, replacement, content)
        
        # Security: Preserve file permissions when writing
        old_umask = os.umask(0o077)
        try:
            self.config_path.write_text(content)
            os.chmod(self.config_path, 0o600)
        finally:
            os.umask(old_umask)
    
    async def download_and_install_binary(self):
        """Download and install the CLIProxyAPI binary."""
        self.is_downloading = True
        self.download_progress = 0.0
        self.last_error = None
        self._cancel_download = False
        
        try:
            # Fetch latest release info
            self.download_progress = 0.1
            release_info = await self._fetch_latest_release()
            
            # Check for cancellation
            if self._cancel_download:
                raise ProxyError("Download cancelled by user")
            
            # Find compatible asset
            asset = self._find_compatible_asset(release_info)
            if not asset:
                raise ProxyError.no_compatible_binary()
            
            # Check for cancellation
            if self._cancel_download:
                raise ProxyError("Download cancelled by user")
            
            # Download binary archive
            self.download_progress = 0.3
            asset_name = asset.get("name", "")
            archive_data = await self._download_asset(asset["browser_download_url"])
            
            # Check for cancellation after download
            if self._cancel_download:
                raise ProxyError("Download cancelled by user")
            
            # Security: MANDATORY checksum verification
            # GitHub releases may include checksums in release notes or as separate assets
            expected_sha256 = None
            
            # Try to find checksum in release notes (multiple formats)
            if "body" in release_info:
                import re
                body_text = release_info.get("body", "")
                # Look for SHA256 checksum in various formats:
                # - "SHA256: abc123..."
                # - "sha256: abc123..."
                # - "SHA-256: abc123..."
                # - "abc123...  filename" (checksum file format)
                patterns = [
                    r'SHA256[:\s-]+([a-fA-F0-9]{64})',
                    r'sha256[:\s-]+([a-fA-F0-9]{64})',
                    r'SHA-256[:\s-]+([a-fA-F0-9]{64})',
                    r'^([a-fA-F0-9]{64})\s+',  # Checksum file format (checksum at start of line)
                ]
                for pattern in patterns:
                    checksum_match = re.search(pattern, body_text, re.MULTILINE | re.IGNORECASE)
                    if checksum_match:
                        expected_sha256 = checksum_match.group(1)
                        print(f"[ProxyManager] Found checksum in release notes: {expected_sha256[:16]}...")
                        break
            
            # If no checksum found in release notes, try to find a checksum file asset
            if not expected_sha256:
                asset_name_lower = asset_name.lower()
                asset_base = asset_name_lower.replace(".tar.gz", "").replace(".zip", "").replace(".tgz", "")
                
                # Look for checksum file with various naming patterns
                checksum_patterns = [
                    f"{asset_base}.sha256",
                    f"{asset_base}.sha256sum",
                    f"{asset_base}_sha256.txt",
                    f"sha256-{asset_base}.txt",
                ]
                
                for release_asset in release_info.get("assets", []):
                    asset_name_check = release_asset.get("name", "").lower()
                    # Check if this asset matches any checksum pattern
                    for pattern in checksum_patterns:
                        if pattern in asset_name_check or (asset_base in asset_name_check and "sha256" in asset_name_check):
                            try:
                                print(f"[ProxyManager] Downloading checksum file: {release_asset.get('name')}")
                                checksum_data = await self._download_asset(release_asset["browser_download_url"])
                                checksum_text = checksum_data.decode("utf-8").strip()
                                
                                # Parse checksum file (format: "checksum  filename" or just "checksum")
                                # Extract first 64-character hex string
                                checksum_match = re.search(r'([a-fA-F0-9]{64})', checksum_text)
                                if checksum_match:
                                    expected_sha256 = checksum_match.group(1)
                                    print(f"[ProxyManager] Found checksum in file: {expected_sha256[:16]}...")
                                    break
                            except Exception as e:
                                print(f"[ProxyManager] Error downloading checksum file: {e}")
                                # Continue to next asset
                                pass
                    
                    if expected_sha256:
                        break
            
            # SECURITY: Checksum verification is MANDATORY
            if not expected_sha256:
                raise ProxyError(
                    "Checksum verification failed: No SHA256 checksum found in release. "
                    "Cannot verify binary integrity. This is a security requirement. "
                    "Please ensure the release includes a checksum in release notes or as a separate asset."
                )
            
            # Check for cancellation before installation
            if self._cancel_download:
                raise ProxyError("Download cancelled by user")
            
            # Install binary with MANDATORY checksum verification (extracts from archive)
            self.download_progress = 0.8
            # expected_sha256 is guaranteed to be set at this point (checked above)
            await self._install_binary(archive_data, asset_name, expected_sha256=expected_sha256)
            
            # Check for cancellation after installation
            if self._cancel_download:
                raise ProxyError("Download cancelled by user")
            
            self.download_progress = 1.0
        except Exception as e:
            self.last_error = str(e)
            raise
        finally:
            self.is_downloading = False
    
    async def _fetch_latest_release(self) -> dict:
        """Fetch latest release info from GitHub."""
        url = f"https://api.github.com/repos/{self.GITHUB_REPO}/releases/latest"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ProxyError.network_error(f"Failed to fetch release: {response.status}")
                return await response.json()
    
    def _find_compatible_asset(self, release_info: dict) -> Optional[dict]:
        """Find compatible binary asset for current system."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Map platform to asset name patterns
        # Assets use format: CLIProxyAPIPlus_VERSION_darwin_arm64.tar.gz
        if system == "darwin":
            if "arm" in machine or "aarch64" in machine:
                pattern = "darwin_arm64"
            else:
                pattern = "darwin_amd64"
        elif system == "linux":
            if "arm" in machine or "aarch64" in machine:
                pattern = "linux_arm64"
            else:
                pattern = "linux_amd64"
        else:
            return None
        
        # Skip patterns (exclude incompatible assets)
        skip_patterns = ["windows", "checksum"]
        
        for asset in release_info.get("assets", []):
            name = asset.get("name", "").lower()
            
            # Skip incompatible assets
            should_skip = any(skip in name for skip in skip_patterns)
            if should_skip:
                continue
            
            # Check if this asset matches our platform/arch pattern
            # Asset names: CLIProxyAPIPlus_VERSION_darwin_arm64.tar.gz
            if pattern in name and "cliproxyapiplus" in name:
                return asset
        
        return None
    
    async def _download_asset(self, url: str) -> bytes:
        """Download binary asset with SSL verification."""
        # Security: Explicitly enable SSL verification
        ssl_context = None
        try:
            import ssl
            ssl_context = ssl.create_default_context()
        except ImportError:
            pass
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=ssl_context) as response:
                if response.status != 200:
                    raise ProxyError.network_error(f"Download failed: {response.status}")
                return await response.read()
    
    async def _verify_binary_checksum(self, data: bytes, expected_sha256: str) -> bool:
        """Verify binary checksum.
        
        Security: MANDATORY SHA256 checksum verification. This method will raise an error
        if no checksum is provided or if verification fails.
        
        Args:
            data: Binary data to verify
            expected_sha256: Expected SHA256 checksum (REQUIRED)
            
        Returns:
            True if checksum matches
            
        Raises:
            ProxyError: If checksum is missing or verification fails
        """
        if not data or len(data) < 1000:  # Sanity check - binaries should be larger
            raise ProxyError("Binary verification failed: File appears to be invalid or corrupted (too small)")
        
        if not expected_sha256:
            raise ProxyError(
                "Checksum verification failed: No expected checksum provided. "
                "This is a security requirement - binary cannot be verified."
            )
        
        import hashlib
        actual_sha256 = hashlib.sha256(data).hexdigest().lower()
        expected_sha256_lower = expected_sha256.lower().strip()
        
        if actual_sha256 != expected_sha256_lower:
            raise ProxyError(
                f"Binary checksum verification FAILED. "
                f"Expected: {expected_sha256_lower[:16]}... "
                f"Actual: {actual_sha256[:16]}... "
                f"Download may be corrupted or tampered with. Installation aborted for security."
            )
        
        print(f"[ProxyManager] ✓ Checksum verification passed: {actual_sha256[:16]}...")
        return True
    
    async def _install_binary(self, archive_data: bytes, asset_name: str, expected_sha256: str):
        """Install binary to target path with MANDATORY verification.
        
        Extracts the binary from tar.gz or zip archive and installs it.
        Checksum verification is REQUIRED for security.
        
        Args:
            archive_data: Archive data (tar.gz or zip)
            asset_name: Name of the asset file (e.g., "CLIProxyAPIPlus_6.7.16-0_darwin_arm64.tar.gz")
            expected_sha256: SHA256 checksum to verify against (REQUIRED)
            
        Raises:
            ProxyError: If checksum is missing or verification fails
        """
        import tempfile
        import tarfile
        import zipfile
        
        # Create temporary directory for extraction
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            archive_path = temp_path / asset_name
            
            # Write archive to temp file
            archive_path.write_bytes(archive_data)
            
            # Extract based on file type
            binary_found = None
            
            if asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
                # Extract tar.gz
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(temp_path)
                    # Find the binary in extracted files
                    for member in tar.getmembers():
                        if member.isfile() and not member.name.endswith((".txt", ".md", ".sha256")):
                            # This is likely the binary
                            extracted_path = temp_path / member.name
                            if extracted_path.exists() and os.access(extracted_path, os.X_OK):
                                binary_found = extracted_path
                                break
                    
                    # If not found by name, search for executable files
                    if not binary_found:
                        for item in temp_path.rglob("*"):
                            if item.is_file() and os.access(item, os.X_OK) and not item.name.endswith((".txt", ".md", ".sha256")):
                                binary_found = item
                                break
                                
            elif asset_name.endswith(".zip"):
                # Extract zip
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(temp_path)
                    # Find the binary in extracted files
                    for member in zip_ref.namelist():
                        if not member.endswith((".txt", ".md", ".sha256", "/")):
                            extracted_path = temp_path / member
                            if extracted_path.exists() and extracted_path.is_file():
                                # Make it executable
                                os.chmod(extracted_path, 0o755)
                                binary_found = extracted_path
                                break
            else:
                # Assume it's a direct binary (unlikely but handle it)
                binary_found = archive_path
            
            if not binary_found or not binary_found.exists():
                raise ProxyError("Binary not found in archive")
            
            # Read the extracted binary
            binary_data = binary_found.read_bytes()
            
            # Security: MANDATORY checksum verification before installation
            # This will raise ProxyError if checksum is missing or verification fails
            await self._verify_binary_checksum(binary_data, expected_sha256)
            
            # Write binary to target location
            self.binary_path.write_bytes(binary_data)
            # Make executable (user and group, not world)
            os.chmod(self.binary_path, 0o750)
    
    async def start(self):
        """Start the proxy server."""
        if self.proxy_status.running:
            return
        
        if not self.is_binary_installed:
            await self.download_and_install_binary()
        
        self.is_starting = True
        try:
            # Verify binary exists and is executable
            if not self.binary_path.exists():
                raise ProxyError(f"Binary not found at {self.binary_path}")
            
            if not os.access(self.binary_path, os.X_OK):
                raise ProxyError(f"Binary is not executable: {self.binary_path}")
            
            # Verify config exists
            if not self.config_path.exists():
                raise ProxyError(f"Config file not found at {self.config_path}")
            
            # Check if port is already in use - if so, verify it's our proxy
            if await self._check_port_listening():
                # Port is already in use - check if it's our proxy
                if await self.check_proxy_responding():
                    # It's our proxy! Just mark it as running
                    self.proxy_status.running = True
                    return  # Already running, reuse it
                else:
                    # Port is in use but not responding as our proxy
                    # Try to kill the process on that port and start fresh
                    await self._kill_process_on_port(self.proxy_status.port)
                    # Wait a moment for port to be released
                    await asyncio.sleep(0.5)
                    # Check again - if still in use, it's not our proxy
                    if await self._check_port_listening():
                        raise ProxyError(f"Port {self.proxy_status.port} is already in use by another process. Please stop it or change the port.")
            
            # Start process
            print(f"[ProxyManager] Starting proxy: {self.binary_path}")
            print(f"[ProxyManager] Config: {self.config_path}")
            print(f"[ProxyManager] Port: {self.proxy_status.port}")
            
            try:
                # Use unbuffered output to prevent blocking on pipe reads
                self._process = subprocess.Popen(
                    [str(self.binary_path), "--config", str(self.config_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(self.binary_path.parent),
                    bufsize=1,  # Line buffered
                )
                print(f"[ProxyManager] Process started with PID: {self._process.pid}")
                
                # Set pipes to non-blocking mode to prevent deadlock (Unix only)
                if platform.system() != "Windows":
                    try:
                        import fcntl
                        if self._process.stdout:
                            fd = self._process.stdout.fileno()
                            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                        if self._process.stderr:
                            fd = self._process.stderr.fileno()
                            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                    except (ImportError, OSError):
                        # fcntl not available, that's okay
                        pass
            except Exception as e:
                print(f"[ProxyManager] Failed to start process: {e}")
                import traceback
                traceback.print_exc()
                raise ProxyError(f"Failed to start proxy process: {str(e)}")
            
            # Wait a bit for startup and check if port becomes available
            max_wait = 3  # Wait up to 3 seconds
            waited = 0
            print(f"[ProxyManager] Waiting for proxy to start (max {max_wait}s)...")
            while waited < max_wait:
                await asyncio.sleep(0.5)
                waited += 0.5
                print(f"[ProxyManager] Waited {waited}s, checking process...")
                
                # Check if process is still running
                return_code = self._process.poll()
                print(f"[ProxyManager] Process return code: {return_code}")
                if return_code is None:
                    # Process is still running - check if port is listening
                    print(f"[ProxyManager] Process still running, checking port...")
                    port_listening = await self._check_port_listening()
                    print(f"[ProxyManager] Port listening: {port_listening}")
                    if port_listening:
                        self.proxy_status.running = True
                        print(f"[ProxyManager] Proxy started successfully!")
                        return  # Success!
                    # Process running but port not ready yet, continue waiting
                    print(f"[ProxyManager] Process running but port not ready yet, continuing to wait...")
                else:
                    # Process exited - check if it was a clean exit after starting
                    # Sometimes the proxy prints info and exits cleanly if port is in use
                    print(f"[ProxyManager] Process exited with code {return_code}")
                    break
            
            print(f"[ProxyManager] Wait loop completed (waited {waited}s)")
            
            # If we get here, either process exited or port never became available
            return_code = self._process.poll()
            
            # Read output to see what happened
            stdout_data = b""
            stderr_data = b""
            
            try:
                # Try to read output without blocking
                if self._process.stdout:
                    try:
                        # Try non-blocking read
                        stdout_data = self._process.stdout.read()
                    except (BlockingIOError, OSError):
                        # No data available, that's fine
                        pass
                    except Exception as e:
                        print(f"[ProxyManager] Error reading stdout: {e}")
                
                if self._process.stderr:
                    try:
                        # Try non-blocking read
                        stderr_data = self._process.stderr.read()
                    except (BlockingIOError, OSError):
                        # No data available, that's fine
                        pass
                    except Exception as e:
                        print(f"[ProxyManager] Error reading stderr: {e}")
            except Exception as e:
                print(f"[ProxyManager] Error reading process output: {e}")
            
            stdout_text = stdout_data.decode("utf-8", errors="replace").strip() if stdout_data else ""
            stderr_text = stderr_data.decode("utf-8", errors="replace").strip() if stderr_data else ""
            
            print(f"[ProxyManager] Process return code: {return_code}")
            if stdout_text:
                print(f"[ProxyManager] stdout: {stdout_text[:500]}")  # First 500 chars
            if stderr_text:
                print(f"[ProxyManager] stderr: {stderr_text[:500]}")  # First 500 chars
            
            # Check if port is already in use (common error)
            if "address already in use" in stdout_text.lower() or "address already in use" in stderr_text.lower():
                # Port conflict - check if it's actually our proxy running
                if await self._check_port_listening():
                    if await self.check_proxy_responding():
                        # It's our proxy! Just mark it as running
                        self.proxy_status.running = True
                        return  # Already running, reuse it
                    else:
                        # Port in use but not our proxy
                        raise ProxyError(f"Port {self.proxy_status.port} is already in use by another process. Please stop it or change the port.")
                else:
                    # Port should be free now, but error says it's in use - might be a race condition
                    raise ProxyError(f"Port {self.proxy_status.port} appears to be in use. Please wait a moment and try again.")
            
            # Check if port is actually listening (maybe another instance started it)
            if await self._check_port_listening():
                # Port is listening - verify it's our proxy
                if await self.check_proxy_responding():
                    self.proxy_status.running = True
                    return  # Success - proxy is running
            
            # Build error message
            error_parts = []
            if return_code is not None:
                error_parts.append(f"Process exited with code {return_code}")
            if stderr_text:
                error_parts.append(f"stderr: {stderr_text}")
            if stdout_text:
                # Only show last few lines of stdout to avoid spam
                stdout_lines = stdout_text.split("\n")
                if len(stdout_lines) > 10:
                    stdout_text = "\n".join(stdout_lines[-10:])
                error_parts.append(f"stdout: {stdout_text}")
            if not error_parts:
                error_parts.append("No error output available")
            
            error_msg = " | ".join(error_parts)
            raise ProxyError(f"Proxy failed to start: {error_msg}")
        except ProxyError:
            raise
        except Exception as e:
            self.last_error = str(e)
            raise ProxyError(f"Failed to start proxy: {str(e)}")
        finally:
            self.is_starting = False
    
    def cancel_startup(self):
        """Cancel the proxy startup process."""
        print(f"[ProxyManager] cancel_startup() called - is_starting: {self.is_starting}, is_downloading: {self.is_downloading}")
        
        cancelled = False
        
        # Cancel downloading if in progress
        if self.is_downloading:
            print("[ProxyManager] Cancelling download...")
            self._cancel_download = True
            self.is_downloading = False
            self.download_progress = 0.0
            cancelled = True
        
        # Cancel starting if in progress
        if self.is_starting:
            print("[ProxyManager] Cancelling startup...")
            # Terminate the process if it exists
            if self._process:
                try:
                    print(f"[ProxyManager] Terminating process {self._process.pid}...")
                    self._process.terminate()
                    # Wait a short time for graceful termination
                    try:
                        self._process.wait(timeout=2)
                        print("[ProxyManager] Process terminated gracefully")
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        print("[ProxyManager] Process didn't terminate, force killing...")
                        self._process.kill()
                        self._process.wait(timeout=1)
                        print("[ProxyManager] Process force killed")
                except Exception as e:
                    print(f"[ProxyManager] Error cancelling startup: {e}")
                finally:
                    self._process = None
            
            # Reset state
            self.is_starting = False
            self.proxy_status.running = False
            cancelled = True
        
        if cancelled:
            self.last_error = "Startup cancelled by user"
            print("[ProxyManager] Startup/download cancelled successfully")
        else:
            print("[ProxyManager] Nothing to cancel (not starting or downloading)")
    
    def stop(self):
        """Stop the proxy server."""
        if not self.proxy_status.running:
            return
        
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        
        self.proxy_status.running = False
    
    async def _check_port_listening(self) -> bool:
        """Check if the proxy port is actually listening."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", self.proxy_status.port))
            sock.close()
            return result == 0  # 0 means connection successful
        except Exception:
            return False
    
    async def _kill_process_on_port(self, port: int) -> None:
        """Kill any process using the specified port (macOS/Linux)."""
        import shutil
        
        # Find lsof command
        lsof_path = shutil.which("lsof")
        if not lsof_path:
            return  # Can't kill without lsof
        
        try:
            # Find PIDs using the port
            process = await asyncio.create_subprocess_exec(
                lsof_path, "-ti", f"tcp:{port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0 and stdout:
                # Parse PIDs and kill them
                pids = stdout.decode().strip().split("\n")
                for pid_str in pids:
                    try:
                        pid = int(pid_str.strip())
                        # Only kill if it's not our own process
                        if pid != os.getpid():
                            os.kill(pid, 9)  # SIGKILL
                    except (ValueError, ProcessLookupError, PermissionError):
                        pass  # PID might not exist or we don't have permission
        except Exception:
            pass  # Silent failure - process might not exist
    
    async def check_proxy_responding(self) -> bool:
        """Check if proxy is responding to requests."""
        if not self.proxy_status.running:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.management_url}/auth-files",
                    headers={"Authorization": f"Bearer {self.management_key}"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception:
            return False
    
    # Allowed authentication commands (whitelist for security)
    ALLOWED_AUTH_COMMANDS = {
        "copilot-login",
        "kiro-google-login",
        "kiro-aws-login",
        "kiro-import",
    }
    
    def run_auth_command(self, command: str) -> dict:
        """Run an authentication command (e.g., copilot login).
        
        Security: Only allows whitelisted commands to prevent command injection.
        """
        if not self.is_binary_installed:
            return {"success": False, "message": "Binary not installed"}
        
        # Security: Validate command against whitelist
        if command not in self.ALLOWED_AUTH_COMMANDS:
            return {
                "success": False,
                "message": f"Invalid command. Allowed: {', '.join(self.ALLOWED_AUTH_COMMANDS)}",
            }
        
        try:
            # Security: Use list form, command is already validated
            result = subprocess.run(
                [str(self.binary_path), command],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            return {
                "success": result.returncode == 0,
                "message": result.stdout or result.stderr,
                "device_code": self._extract_device_code(result.stdout) if result.returncode == 0 else None,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Command timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def _extract_device_code(self, output: str) -> Optional[str]:
        """Extract device code from command output."""
        # Simple extraction - in real implementation, parse properly
        match = re.search(r"device[_-]?code[:\s]+([a-z0-9-]+)", output, re.IGNORECASE)
        return match.group(1) if match else None
