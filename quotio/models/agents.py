"""CLI Agent models."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class AgentConfigType(str, Enum):
    """Configuration type for agents."""
    FILE = "file"
    ENVIRONMENT = "environment"
    BOTH = "both"


class CLIAgent(str, Enum):
    """Supported CLI agents."""
    CLAUDE_CODE = "claude-code"
    CODEX_CLI = "codex"
    GEMINI_CLI = "gemini-cli"
    AMP_CLI = "amp"
    OPEN_CODE = "opencode"
    FACTORY_DROID = "factory-droid"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        names = {
            self.CLAUDE_CODE: "Claude Code",
            self.CODEX_CLI: "Codex CLI",
            self.GEMINI_CLI: "Gemini CLI",
            self.AMP_CLI: "Amp CLI",
            self.OPEN_CODE: "OpenCode",
            self.FACTORY_DROID: "Factory Droid",
        }
        return names.get(self, self.value)

    @property
    def description(self) -> str:
        """Agent description."""
        descriptions = {
            self.CLAUDE_CODE: "Anthropic's official CLI for Claude models",
            self.CODEX_CLI: "OpenAI's Codex CLI for GPT-5 models",
            self.GEMINI_CLI: "Google's Gemini CLI for Gemini models",
            self.AMP_CLI: "Sourcegraph's Amp coding assistant",
            self.OPEN_CODE: "The open source AI coding agent",
            self.FACTORY_DROID: "Factory's AI coding agent",
        }
        return descriptions.get(self, "")

    @property
    def config_type(self) -> AgentConfigType:
        """Configuration type."""
        types = {
            self.CLAUDE_CODE: AgentConfigType.BOTH,
            self.CODEX_CLI: AgentConfigType.FILE,
            self.GEMINI_CLI: AgentConfigType.ENVIRONMENT,
            self.AMP_CLI: AgentConfigType.BOTH,
            self.OPEN_CODE: AgentConfigType.FILE,
            self.FACTORY_DROID: AgentConfigType.FILE,
        }
        return types.get(self, AgentConfigType.FILE)

    @property
    def binary_names(self) -> list[str]:
        """Binary names for detection."""
        names = {
            self.CLAUDE_CODE: ["claude"],
            self.CODEX_CLI: ["codex"],
            self.GEMINI_CLI: ["gemini"],
            self.AMP_CLI: ["amp"],
            self.OPEN_CODE: ["opencode", "oc"],
            self.FACTORY_DROID: ["droid", "factory-droid", "fd"],
        }
        return names.get(self, [])

    @property
    def config_paths(self) -> list[str]:
        """Configuration file paths."""
        paths = {
            self.CLAUDE_CODE: ["~/.claude/settings.json"],
            self.CODEX_CLI: ["~/.codex/config.toml", "~/.codex/auth.json"],
            self.GEMINI_CLI: [],
            self.AMP_CLI: ["~/.config/amp/settings.json", "~/.local/share/amp/secrets.json"],
            self.OPEN_CODE: ["~/.config/opencode/opencode.json"],
            self.FACTORY_DROID: ["~/.factory/config.json"],
        }
        return paths.get(self, [])

    @property
    def docs_url(self) -> Optional[str]:
        """Documentation URL."""
        urls = {
            self.CLAUDE_CODE: "https://docs.anthropic.com/en/docs/claude-code",
            self.CODEX_CLI: "https://github.com/openai/codex",
            self.GEMINI_CLI: "https://github.com/google-gemini/gemini-cli",
            self.AMP_CLI: "https://ampcode.com/manual",
            self.OPEN_CODE: "https://github.com/sst/opencode",
            self.FACTORY_DROID: "https://github.com/github/github-spark",
        }
        return urls.get(self)

    @property
    def system_icon(self) -> str:
        """System icon name."""
        icons = {
            self.CLAUDE_CODE: "brain.head.profile",
            self.CODEX_CLI: "chevron.left.forwardslash.chevron.right",
            self.GEMINI_CLI: "sparkles",
            self.AMP_CLI: "bolt.fill",
            self.OPEN_CODE: "terminal",
            self.FACTORY_DROID: "cpu",
        }
        return icons.get(self, "questionmark.circle")
