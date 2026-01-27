"""Service for managing custom AI provider configurations."""

import json
from typing import List, Optional, Dict
from datetime import datetime
import uuid

from ..models.custom_provider import CustomProvider, CustomProviderType
from ..utils.settings import SettingsManager


class CustomProviderService:
    """Service for managing custom providers."""

    def __init__(self):
        """Initialize the service."""
        self.settings = SettingsManager()
        self.providers: List[CustomProvider] = []
        self.is_loading = False
        self.last_error: Optional[str] = None

        self._load_providers()

    def add_provider(self, provider: CustomProvider):
        """Add a new custom provider."""
        # Update timestamps
        provider.created_at = datetime.now()
        provider.updated_at = datetime.now()

        self.providers.append(provider)
        self._save_providers()

    def update_provider(self, provider: CustomProvider):
        """Update an existing custom provider."""
        index = next((i for i, p in enumerate(self.providers) if p.id == provider.id), None)
        if index is None:
            self.last_error = "Provider not found"
            return

        # Preserve created_at, update updated_at
        provider.created_at = self.providers[index].created_at
        provider.updated_at = datetime.now()

        self.providers[index] = provider
        self._save_providers()

    def delete_provider(self, provider_id: str):
        """Delete a custom provider by ID."""
        self.providers = [p for p in self.providers if p.id != provider_id]
        self._save_providers()

    def toggle_provider(self, provider_id: str):
        """Toggle provider enabled state."""
        index = next((i for i, p in enumerate(self.providers) if p.id == provider_id), None)
        if index is None:
            return

        provider = self.providers[index]
        provider.is_enabled = not provider.is_enabled
        provider.updated_at = datetime.now()
        self._save_providers()

    def get_provider(self, provider_id: str) -> Optional[CustomProvider]:
        """Get a provider by ID."""
        return next((p for p in self.providers if p.id == provider_id), None)

    @property
    def enabled_providers(self) -> List[CustomProvider]:
        """Get all enabled providers."""
        return [p for p in self.providers if p.is_enabled]

    @property
    def providers_by_type(self) -> Dict[CustomProviderType, List[CustomProvider]]:
        """Get providers grouped by type."""
        result: Dict[CustomProviderType, List[CustomProvider]] = {}
        for provider in self.providers:
            if provider.type not in result:
                result[provider.type] = []
            result[provider.type].append(provider)
        return result

    def _load_providers(self):
        """Load providers from storage."""
        self.is_loading = True
        try:
            providers_data = self.settings.get("customProviders", [])
            self.providers = [CustomProvider.from_dict(p) for p in providers_data]
        except Exception as e:
            self.last_error = f"Failed to load providers: {str(e)}"
            self.providers = []
        finally:
            self.is_loading = False

    def _save_providers(self):
        """Save providers to storage."""
        try:
            providers_data = [p.to_dict() for p in self.providers]
            self.settings.set("customProviders", providers_data)
            self.last_error = None
        except Exception as e:
            self.last_error = f"Failed to save providers: {str(e)}"

    def generate_yaml_config(self) -> str:
        """Generate YAML config sections for all enabled custom providers.

        Matches original format - groups by type and generates proper YAML sections.
        """
        # Group by type
        grouped = {}
        for provider in self.enabled_providers:
            if provider.type not in grouped:
                grouped[provider.type] = []
            grouped[provider.type].append(provider)

        yaml = ""

        # OpenAI Compatibility
        if CustomProviderType.OPENAI_COMPATIBILITY in grouped:
            yaml += "\nopenai-compatibility:\n"
            for provider in grouped[CustomProviderType.OPENAI_COMPATIBILITY]:
                yaml += provider.to_yaml_block()

        # Claude Compatibility
        if CustomProviderType.CLAUDE_COMPATIBILITY in grouped:
            yaml += "\nclaude-api-key:\n"
            for provider in grouped[CustomProviderType.CLAUDE_COMPATIBILITY]:
                yaml += provider.to_yaml_block()

        # Gemini Compatibility
        if CustomProviderType.GEMINI_COMPATIBILITY in grouped:
            yaml += "\ngemini-api-key:\n"
            for provider in grouped[CustomProviderType.GEMINI_COMPATIBILITY]:
                yaml += provider.to_yaml_block()

        # Codex Compatibility
        if CustomProviderType.CODEX_COMPATIBILITY in grouped:
            yaml += "\ncodex-api-key:\n"
            for provider in grouped[CustomProviderType.CODEX_COMPATIBILITY]:
                yaml += provider.to_yaml_block()

        # GLM Compatibility
        if CustomProviderType.GLM_COMPATIBILITY in grouped:
            yaml += "\nglm-api-key:\n"
            for provider in grouped[CustomProviderType.GLM_COMPATIBILITY]:
                yaml += provider.to_yaml_block()

        return yaml

    def sync_to_config_file(self, config_path: str) -> None:
        """Update the CLIProxyAPI config file to include custom providers.

        Args:
            config_path: Path to the config.yaml file

        Raises:
            FileNotFoundError: If config file doesn't exist
            IOError: If file cannot be read/written
        """
        import os
        from pathlib import Path

        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Read existing config
        content = config_file.read_text(encoding='utf-8')

        # Remove existing custom provider sections
        content = self._remove_custom_provider_sections(content)

        # Append new custom provider sections
        custom_provider_yaml = self.generate_yaml_config()
        if custom_provider_yaml:
            content += "\n# Custom Providers (managed by Quotio)\n"
            content += custom_provider_yaml

        # Write back
        config_file.write_text(content, encoding='utf-8')

    def _remove_custom_provider_sections(self, content: str) -> str:
        """Remove custom provider sections from config content."""
        result = content

        # Custom provider keys
        custom_provider_keys = [
            "openai-compatibility:",
            "claude-api-key:",
            "gemini-api-key:",
            "codex-api-key:",
            "glm-api-key:",
        ]

        # Remove marker comment and everything after it
        marker = "# Custom Providers (managed by Quotio)"
        if marker in result:
            marker_index = result.find(marker)
            # Find the end of custom providers section (next top-level key or end of file)
            after_marker = result[marker_index:]

            # Look for next top-level key (line starting with non-whitespace followed by colon)
            import re
            pattern = r'^[a-z][\w-]*:'
            matches = list(re.finditer(pattern, after_marker, re.MULTILINE))

            if matches:
                # Find first match that's not a custom provider key
                for match in matches:
                    key = match.group(0)
                    if key not in custom_provider_keys:
                        # Remove from marker to this key
                        end_index = marker_index + match.start()
                        result = result[:marker_index].rstrip() + "\n" + result[end_index:].lstrip()
                        break
                else:
                    # All matches are custom provider keys, remove to end
                    result = result[:marker_index].rstrip()
            else:
                # No more top-level keys, remove to end
                result = result[:marker_index].rstrip()

        # Also remove standalone custom provider sections
        for key in custom_provider_keys:
            result = self._remove_yaml_section(key, result)

        return result.strip()

    def _remove_yaml_section(self, key: str, content: str) -> str:
        """Remove a top-level YAML section by key."""
        import re

        # Find section start
        pattern = rf'^\s*{re.escape(key)}\s*$'
        match = re.search(pattern, content, re.MULTILINE)
        if not match:
            return content

        start_pos = match.start()

        # Find next top-level key
        next_key_pattern = r'^[a-z][\w-]*:'
        after_section = content[start_pos:]
        next_match = re.search(next_key_pattern, after_section[after_section.find('\n'):], re.MULTILINE)

        if next_match:
            end_pos = start_pos + after_section.find('\n') + next_match.start()
            return content[:start_pos] + content[end_pos:]
        else:
            # No more keys, remove to end
            return content[:start_pos]

    def validate_provider(self, provider: "CustomProvider") -> List[str]:
        """Validate a provider before saving."""
        errors = provider.validate()

        # Check for duplicate names (excluding current provider if updating)
        existing_names = [
            p.name.lower() for p in self.providers
            if p.id != provider.id
        ]

        if provider.name.lower() in existing_names:
            errors.append("A provider with this name already exists")

        return errors
