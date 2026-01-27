"""AI Provider models."""

from enum import Enum
from typing import Optional
from dataclasses import dataclass


class AIProvider(str, Enum):
    """Supported AI providers."""

    GEMINI = "gemini-cli"
    CLAUDE = "claude"
    CODEX = "codex"
    QWEN = "qwen"
    IFLOW = "iflow"
    ANTIGRAVITY = "antigravity"
    VERTEX = "vertex"
    KIRO = "kiro"
    COPILOT = "github-copilot"
    CURSOR = "cursor"
    TRAE = "trae"
    GLM = "glm"
    WARP = "warp"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        names = {
            self.GEMINI: "Gemini CLI",
            self.CLAUDE: "Claude Code",
            self.CODEX: "Codex (OpenAI)",
            self.QWEN: "Qwen Code",
            self.IFLOW: "iFlow",
            self.ANTIGRAVITY: "Antigravity",
            self.VERTEX: "Vertex AI",
            self.KIRO: "Kiro (CodeWhisperer)",
            self.COPILOT: "GitHub Copilot",
            self.CURSOR: "Cursor",
            self.TRAE: "Trae",
            self.GLM: "GLM",
            self.WARP: "Warp",
        }
        return names.get(self, self.value)

    @property
    def icon_name(self) -> str:
        """SF Symbol or icon name."""
        icons = {
            self.GEMINI: "sparkles",
            self.CLAUDE: "brain.head.profile",
            self.CODEX: "chevron.left.forwardslash.chevron.right",
            self.QWEN: "cloud",
            self.IFLOW: "arrow.triangle.branch",
            self.ANTIGRAVITY: "wand.and.stars",
            self.VERTEX: "cube",
            self.KIRO: "cloud.fill",
            self.COPILOT: "chevron.left.forwardslash.chevron.right",
            self.CURSOR: "cursorarrow.rays",
            self.TRAE: "cursorarrow.rays",
            self.GLM: "brain",
            self.WARP: "terminal.fill",
        }
        return icons.get(self, "questionmark.circle")

    @property
    def color_hex(self) -> str:
        """Provider color in hex format."""
        colors = {
            self.GEMINI: "4285F4",
            self.CLAUDE: "D97706",
            self.CODEX: "10A37F",
            self.QWEN: "7C3AED",
            self.IFLOW: "06B6D4",
            self.ANTIGRAVITY: "EC4899",
            self.VERTEX: "EA4335",
            self.KIRO: "9046FF",
            self.COPILOT: "238636",
            self.CURSOR: "00D4AA",
            self.TRAE: "00B4D8",
            self.GLM: "3B82F6",
            self.WARP: "01E5FF",
        }
        return colors.get(self, "000000")

    @property
    def oauth_endpoint(self) -> str:
        """OAuth endpoint path."""
        endpoints = {
            self.GEMINI: "/gemini-cli-auth-url",
            self.CLAUDE: "/anthropic-auth-url",
            self.CODEX: "/codex-auth-url",
            self.QWEN: "/qwen-auth-url",
            self.IFLOW: "/iflow-auth-url",
            self.ANTIGRAVITY: "/antigravity-auth-url",
            self.VERTEX: "",
            self.KIRO: "",
            self.COPILOT: "",
            self.CURSOR: "",
            self.TRAE: "",
            self.GLM: "",
            self.WARP: "",
        }
        return endpoints.get(self, "")

    @property
    def menu_bar_symbol(self) -> str:
        """Short symbol for menu bar display."""
        symbols = {
            self.GEMINI: "G",
            self.CLAUDE: "C",
            self.CODEX: "O",
            self.QWEN: "Q",
            self.IFLOW: "F",
            self.ANTIGRAVITY: "A",
            self.VERTEX: "V",
            self.KIRO: "K",
            self.COPILOT: "CP",
            self.CURSOR: "CR",
            self.TRAE: "TR",
            self.GLM: "G",
            self.WARP: "W",
        }
        return symbols.get(self, "?")

    @property
    def supports_quota_only_mode(self) -> bool:
        """Whether this provider supports quota tracking in quota-only mode."""
        return self in {
            self.CLAUDE,
            self.CODEX,
            self.CURSOR,
            self.GEMINI,
            self.ANTIGRAVITY,
            self.COPILOT,
            self.TRAE,
            self.GLM,
            self.WARP,
        }

    @property
    def uses_browser_auth(self) -> bool:
        """Whether this provider uses browser cookies for auth."""
        return self in {self.CURSOR, self.TRAE}

    @property
    def uses_cli_quota(self) -> bool:
        """Whether this provider uses CLI commands for quota."""
        return self in {self.CLAUDE, self.CODEX, self.GEMINI}

    @property
    def supports_manual_auth(self) -> bool:
        """Whether this provider can be added manually."""
        # Cursor, Trae, GLM are excluded
        return self not in {self.CURSOR, self.TRAE, self.GLM}

    @property
    def uses_api_key_auth(self) -> bool:
        """Whether this provider uses API key authentication."""
        return self in {self.GLM, self.WARP}

    @property
    def is_quota_tracking_only(self) -> bool:
        """Whether this provider is quota-tracking only (not a real provider)."""
        return self in {self.CURSOR, self.TRAE, self.WARP}
