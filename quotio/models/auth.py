"""Authentication models."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from .providers import AIProvider


class OAuthStatus(str, Enum):
    """OAuth flow status."""
    WAITING = "waiting"
    POLLING = "polling"
    SUCCESS = "success"
    ERROR = "error"


class OAuthState(BaseModel):
    """OAuth authentication state."""
    provider: AIProvider
    status: OAuthStatus
    state: Optional[str] = None
    error: Optional[str] = None


class AuthFile(BaseModel):
    """Auth file from Management API."""
    id: str
    name: str
    provider: str
    label: Optional[str] = None
    status: str = "unknown"
    status_message: Optional[str] = None
    disabled: bool = False
    unavailable: bool = False
    runtime_only: Optional[bool] = None
    source: Optional[str] = None
    path: Optional[str] = None
    email: Optional[str] = None
    account_type: Optional[str] = None
    account: Optional[str] = None
    auth_index: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_refresh: Optional[str] = None

    @property
    def provider_type(self) -> Optional[AIProvider]:
        """Get AIProvider enum from provider string."""
        # Handle "copilot" alias for "github-copilot"
        if self.provider == "copilot":
            return AIProvider.COPILOT
        try:
            return AIProvider(self.provider)
        except ValueError:
            return None

    @property
    def quota_lookup_key(self) -> str:
        """Key used for quota lookup."""
        if self.email and self.email.strip():
            return self.email
        if self.account and self.account.strip():
            return self.account

        key = self.name
        if key.startswith("github-copilot-"):
            key = key[len("github-copilot-"):]
        if key.endswith(".json"):
            key = key[:-5]
        return key

    @property
    def is_ready(self) -> bool:
        """Whether this auth file is ready to use."""
        return (
            self.status == "ready"
            and not self.disabled
            and not self.unavailable
        )

    @property
    def status_color(self) -> str:
        """Status color for UI."""
        if self.status == "ready":
            return "green" if not self.disabled else "gray"
        elif self.status == "cooling":
            return "orange"
        elif self.status == "error":
            return "red"
        return "gray"


class AuthFilesResponse(BaseModel):
    """Response containing auth files."""
    files: list[AuthFile]


class OAuthURLResponse(BaseModel):
    """OAuth URL response."""
    status: str
    url: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


class OAuthStatusResponse(BaseModel):
    """OAuth status response."""
    status: str
    error: Optional[str] = None
