"""Agent connection models for multiple named connections per agent type."""

from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime
from enum import Enum

from .agents import CLIAgent
from .providers import AIProvider


@dataclass
class NamedAgentConnection:
    """A named connection for an agent with a specific API key."""
    id: str  # Unique identifier
    name: str  # User-defined name for this connection
    agent: CLIAgent  # Agent type
    api_key: str  # API key for this connection
    proxy_url: Optional[str] = None  # Proxy URL (if configured)
    model_slots: Optional[Dict[str, str]] = None  # Model slots if applicable
    created_at: Optional[datetime] = None  # When this connection was created
    last_used: Optional[datetime] = None  # When this connection was last used

    def __post_init__(self):
        """Initialize default values."""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.model_slots is None:
            self.model_slots = {}

    @property
    def display_name(self) -> str:
        """Display name for this connection."""
        return f"{self.name} ({self.agent.display_name})"

    @property
    def provider(self) -> Optional[AIProvider]:
        """Map agent to provider for quota lookup."""
        mapping = {
            CLIAgent.CODEX_CLI: AIProvider.CODEX,
            CLIAgent.CLAUDE_CODE: AIProvider.CLAUDE,
            CLIAgent.GEMINI_CLI: AIProvider.GEMINI,
        }
        return mapping.get(self.agent)


@dataclass
class AgentConnectionConfig:
    """Configuration for an agent connection (used when writing config files)."""
    connection: NamedAgentConnection
    config_storage: str = "json"  # "json", "env", "both"

    def to_agent_configuration(self):
        """Convert to AgentConfiguration for writing."""
        from ..services.agent_config import AgentConfiguration, ModelSlot

        # Convert model_slots dict to ModelSlot enum keys
        model_slots = {}
        if self.connection.model_slots:
            for key, value in self.connection.model_slots.items():
                try:
                    slot = ModelSlot(key)
                    model_slots[slot] = value
                except (ValueError, TypeError):
                    pass

        return AgentConfiguration(
            agent=self.connection.agent,
            proxy_url=self.connection.proxy_url or "",
            api_key=self.connection.api_key,
            model_slots=model_slots,
            config_storage=self.config_storage
        )
