"""Direct Auth File Service - filesystem scanning for quota-only mode."""

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..models.providers import AIProvider


class AuthFileSource(str, Enum):
    """Source location of the auth file."""
    CLI_PROXY_API = "~/.cli-proxy-api"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return "CLI Proxy API"


@dataclass
class DirectAuthFile:
    """Represents an auth file discovered directly from filesystem."""
    id: str
    provider: AIProvider
    email: Optional[str] = None
    login: Optional[str] = None  # GitHub username (for Copilot)
    expired: Optional[datetime] = None
    account_type: Optional[str] = None  # pro, free, etc.
    file_path: str = ""
    source: AuthFileSource = AuthFileSource.CLI_PROXY_API
    filename: str = ""

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expired:
            return False
        return self.expired < datetime.now()

    @property
    def display_name(self) -> str:
        """Display name for UI (email > login > filename)."""
        if self.email:
            return self.email
        if self.login:
            return self.login
        return self.filename


class DirectAuthFileService:
    """Service for scanning auth files directly from filesystem.

    Used in Quota-Only mode where proxy server is not running.
    """

    def __init__(self):
        self.file_manager = Path

    def expand_path(self, path: str) -> str:
        """Expand tilde in path."""
        return os.path.expanduser(path)

    async def scan_all_auth_files(self) -> List[DirectAuthFile]:
        """Scan all known auth file locations."""
        # Only scan ~/.cli-proxy-api (CLIProxyAPI managed)
        return await self._scan_cli_proxy_api_directory()

    async def _scan_cli_proxy_api_directory(self) -> List[DirectAuthFile]:
        """Scan ~/.cli-proxy-api for managed auth files."""
        path = self.expand_path("~/.cli-proxy-api")
        path_obj = Path(path)

        if not path_obj.exists() or not path_obj.is_dir():
            return []

        auth_files: List[DirectAuthFile] = []

        for file_path in path_obj.glob("*.json"):
            filename = file_path.name

            # Try to parse JSON content first
            auth_file = self._parse_auth_file_json(str(file_path), filename)
            if auth_file:
                auth_files.append(auth_file)
                continue

            # Fallback: parse from filename if JSON parsing fails
            result = self._parse_auth_file_name(filename)
            if result:
                provider, email = result
                auth_files.append(DirectAuthFile(
                    id=str(file_path),
                    provider=provider,
                    email=email,
                    login=None,
                    expired=None,
                    account_type=None,
                    file_path=str(file_path),
                    source=AuthFileSource.CLI_PROXY_API,
                    filename=filename
                ))

        return auth_files

    def _parse_auth_file_json(self, file_path: str, filename: str) -> Optional[DirectAuthFile]:
        """Parse auth file JSON content to extract provider, email, and metadata."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        if not isinstance(json_data, dict):
            return None

        # Get provider from "type" field
        type_string = json_data.get("type")
        if not type_string:
            return None

        provider = self._map_type_to_provider(type_string)
        if not provider:
            return None

        # Extract metadata
        email = json_data.get("email")
        login = json_data.get("login")
        account_type = json_data.get("account_type")

        # For Kiro: if email is empty, try to use provider (e.g., "Google") as identifier
        if provider == AIProvider.KIRO and (not email or not email.strip()):
            auth_provider = json_data.get("provider")
            if auth_provider:
                email = f"Kiro ({auth_provider})"

        # Parse expired date
        expired_date = None
        expired_value = json_data.get("expired")
        if expired_value:
            if isinstance(expired_value, str):
                expired_date = self._parse_iso8601_date(expired_value)
            elif isinstance(expired_value, (int, float)):
                expired_date = datetime.fromtimestamp(expired_value)

        return DirectAuthFile(
            id=file_path,
            provider=provider,
            email=email,
            login=login,
            expired=expired_date,
            account_type=account_type,
            file_path=file_path,
            source=AuthFileSource.CLI_PROXY_API,
            filename=filename
        )

    def _map_type_to_provider(self, type_string: str) -> Optional[AIProvider]:
        """Map JSON "type" field to AIProvider."""
        type_map: Dict[str, AIProvider] = {
            "antigravity": AIProvider.ANTIGRAVITY,
            "claude": AIProvider.CLAUDE,
            "codex": AIProvider.CODEX,
            "copilot": AIProvider.COPILOT,
            "github-copilot": AIProvider.COPILOT,
            "gemini": AIProvider.GEMINI,
            "gemini-cli": AIProvider.GEMINI,
            "qwen": AIProvider.QWEN,
            "iflow": AIProvider.IFLOW,
            "kiro": AIProvider.KIRO,
            "vertex": AIProvider.VERTEX,
            "cursor": AIProvider.CURSOR,
            "trae": AIProvider.TRAE,
        }
        return type_map.get(type_string.lower())

    def _parse_iso8601_date(self, date_string: str) -> Optional[datetime]:
        """Parse ISO8601 date string with multiple format support."""
        # Try standard datetime parsing first
        try:
            # Try with 'Z' suffix
            if date_string.endswith('Z'):
                return datetime.fromisoformat(date_string[:-1] + '+00:00')
            # Try standard ISO format
            return datetime.fromisoformat(date_string)
        except (ValueError, TypeError):
            pass

        # Fallback to dateutil if available
        try:
            from dateutil import parser
            return parser.isoparse(date_string)
        except (ImportError, ValueError, TypeError):
            return None

    def _parse_auth_file_name(self, filename: str) -> Optional[tuple[AIProvider, Optional[str]]]:
        """Parse auth file name to extract provider and email."""
        prefixes: List[tuple[str, AIProvider]] = [
            ("antigravity-", AIProvider.ANTIGRAVITY),
            ("codex-", AIProvider.CODEX),
            ("github-copilot-", AIProvider.COPILOT),
            ("claude-", AIProvider.CLAUDE),
            ("gemini-cli-", AIProvider.GEMINI),
            ("qwen-", AIProvider.QWEN),
            ("iflow-", AIProvider.IFLOW),
            ("kiro-", AIProvider.KIRO),
            ("vertex-", AIProvider.VERTEX),
        ]

        for prefix, provider in prefixes:
            if filename.startswith(prefix):
                email = self._extract_email_from_filename(filename, prefix)
                return (provider, email)

        return None

    def _extract_email_from_filename(self, filename: str, prefix: str) -> Optional[str]:
        """Extract email from filename pattern: prefix-email.json."""
        name = filename.replace(prefix, "").replace(".json", "")

        # Handle underscore -> dot conversion for email
        # e.g., user_example_com -> user.example.com
        # But we need to be smart about @ sign

        # Check for common email domain patterns
        email_domains = [
            "gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
            "yahoo.com", "icloud.com", "protonmail.com", "proton.me"
        ]

        for domain in email_domains:
            underscore_domain = domain.replace(".", "_")
            if name.endswith(f"_{underscore_domain}"):
                prefix_part = name[:-len(underscore_domain) - 1]
                return f"{prefix_part}@{domain}"

        # Fallback: try to detect @ pattern
        # Common pattern: user_domain_com -> user@domain.com
        parts = name.split("_")
        if len(parts) >= 3:
            # Assume last two parts are domain (e.g., domain_com)
            user = ".".join(parts[:-2])
            domain = ".".join(parts[-2:])
            return f"{user}@{domain}"
        elif len(parts) == 2:
            # Could be user_domain or user_com
            return "@".join(parts)

        return name

    async def read_auth_token(self, file: DirectAuthFile) -> Optional[Dict[str, Any]]:
        """Read auth token from file for quota fetching.

        Returns a dictionary with token data in a format suitable for quota fetchers.
        """
        try:
            with open(file.file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        if not isinstance(json_data, dict):
            return None

        # Different providers store tokens differently
        token_data: Dict[str, Any] = {}

        if file.provider in [AIProvider.ANTIGRAVITY, AIProvider.GEMINI]:
            # Google OAuth format
            if "access_token" in json_data:
                token_data["access_token"] = json_data["access_token"]
                token_data["refresh_token"] = json_data.get("refresh_token")
                token_data["expires_at"] = json_data.get("expiry") or json_data.get("expires_at")

        elif file.provider == AIProvider.CODEX:
            # OpenAI format - uses bearer token or API key
            token = json_data.get("access_token") or json_data.get("api_key")
            if token:
                token_data["access_token"] = token

        elif file.provider == AIProvider.COPILOT:
            # GitHub OAuth format
            token = json_data.get("access_token") or json_data.get("oauth_token")
            if token:
                token_data["access_token"] = token

        elif file.provider == AIProvider.CLAUDE:
            # Anthropic OAuth
            session_key = json_data.get("session_key") or json_data.get("access_token")
            if session_key:
                token_data["access_token"] = session_key

        elif file.provider == AIProvider.KIRO:
            # Kiro (AWS CodeWhisperer) format
            if "access_token" in json_data:
                token_data["access_token"] = json_data["access_token"]
                token_data["refresh_token"] = json_data.get("refresh_token")
                expires_at = json_data.get("expires_at") or json_data.get("expiry")
                if expires_at:
                    token_data["expires_at"] = expires_at

        return token_data if token_data else None
