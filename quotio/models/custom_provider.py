"""Custom provider models for user-defined AI providers."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class CustomProviderType(str, Enum):
    """Type of custom provider compatibility."""
    OPENAI_COMPATIBILITY = "openai-compatibility"
    CLAUDE_COMPATIBILITY = "claude-api-key"
    GEMINI_COMPATIBILITY = "gemini-api-key"
    CODEX_COMPATIBILITY = "codex-api-key"
    GLM_COMPATIBILITY = "glm-api-key"
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        names = {
            self.OPENAI_COMPATIBILITY: "OpenAI Compatible",
            self.CLAUDE_COMPATIBILITY: "Claude Compatible",
            self.GEMINI_COMPATIBILITY: "Gemini Compatible",
            self.CODEX_COMPATIBILITY: "Codex Compatible",
            self.GLM_COMPATIBILITY: "GLM Compatible",
        }
        return names.get(self, self.value)
    
    @property
    def description(self) -> str:
        """Description of the provider type."""
        descriptions = {
            self.OPENAI_COMPATIBILITY: "OpenRouter, Ollama, LM Studio, vLLM, or any OpenAI-compatible API",
            self.CLAUDE_COMPATIBILITY: "Anthropic API or Claude-compatible providers",
            self.GEMINI_COMPATIBILITY: "Google Gemini API or Gemini-compatible providers",
            self.CODEX_COMPATIBILITY: "Custom Codex-compatible endpoints",
            self.GLM_COMPATIBILITY: "GLM (BigModel.cn) API",
        }
        return descriptions.get(self, "")
    
    @property
    def requires_base_url(self) -> bool:
        """Whether this provider type requires a base URL."""
        return self in {self.OPENAI_COMPATIBILITY, self.CODEX_COMPATIBILITY}
    
    @property
    def default_base_url(self) -> Optional[str]:
        """Default base URL for this provider type."""
        defaults = {
            self.CLAUDE_COMPATIBILITY: "https://api.anthropic.com",
            self.GEMINI_COMPATIBILITY: "https://generativelanguage.googleapis.com",
            self.GLM_COMPATIBILITY: "https://bigmodel.cn",
        }
        return defaults.get(self)
    
    @property
    def supports_model_mapping(self) -> bool:
        """Whether this provider type supports model alias mapping."""
        return self in {self.OPENAI_COMPATIBILITY, self.CLAUDE_COMPATIBILITY}
    
    @property
    def supports_custom_headers(self) -> bool:
        """Whether this provider type supports custom headers."""
        return self == self.GEMINI_COMPATIBILITY


@dataclass
class CustomAPIKeyEntry:
    """A single API key with optional proxy configuration."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    api_key: str = ""
    proxy_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "api-key": self.api_key,
        }
        if self.proxy_url:
            result["proxy-url"] = self.proxy_url
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "CustomAPIKeyEntry":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            api_key=data.get("api-key", data.get("api_key", "")),
            proxy_url=data.get("proxy-url", data.get("proxy_url")),
        )
    
    @property
    def masked_key(self) -> str:
        """Masked API key for display."""
        if len(self.api_key) <= 12:
            return "•" * len(self.api_key)
        return f"{self.api_key[:8]}...{self.api_key[-4:]}"


@dataclass
class ModelMapping:
    """Maps an upstream model name to a local alias with optional thinking budget."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    alias: str = ""
    thinking_budget: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "name": self.name,
            "alias": self.alias,
        }
        if self.thinking_budget:
            result["thinking-budget"] = self.thinking_budget
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "ModelMapping":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            alias=data.get("alias", ""),
            thinking_budget=data.get("thinking-budget", data.get("thinking_budget")),
        )
    
    @property
    def effective_alias(self) -> str:
        """Get effective alias with thinking budget if present."""
        if self.thinking_budget:
            return f"{self.alias}({self.thinking_budget})"
        return self.alias


@dataclass
class CustomHeader:
    """A custom HTTP header for Gemini-compatible providers."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    key: str = ""
    value: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CustomHeader":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            key=data.get("key", ""),
            value=data.get("value", ""),
        )


@dataclass
class CustomProvider:
    """User-defined custom AI provider."""
    id: str
    name: str
    type: CustomProviderType
    base_url: str
    api_keys: List[CustomAPIKeyEntry] = field(default_factory=list)
    models: List[ModelMapping] = field(default_factory=list)
    headers: List[CustomHeader] = field(default_factory=list)  # Only used for Gemini-compatible
    is_enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create(cls, name: str, type: CustomProviderType, base_url: str = "", **kwargs) -> "CustomProvider":
        """Create a new custom provider."""
        # Use default base URL if not provided and type has one
        if not base_url and type.default_base_url:
            base_url = type.default_base_url
        
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            type=type,
            base_url=base_url,
            **kwargs
        )
    
    def validate(self) -> List[str]:
        """Validate the provider configuration."""
        errors = []
        
        if not self.name.strip():
            errors.append("Provider name is required")
        
        if self.type.requires_base_url and not self.base_url.strip():
            errors.append(f"Base URL is required for {self.type.display_name}")
        
        if self.base_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(self.base_url)
                if not parsed.scheme or not parsed.netloc:
                    errors.append("Invalid base URL format")
            except Exception:
                errors.append("Invalid base URL format")
        
        if not self.api_keys:
            errors.append("At least one API key is required")
        
        for i, key_entry in enumerate(self.api_keys):
            if not key_entry.api_key.strip():
                errors.append(f"API key #{i + 1} is empty")
        
        return errors
    
    @property
    def is_valid(self) -> bool:
        """Check if provider is valid."""
        return len(self.validate()) == 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "base-url": self.base_url,
            "api-keys": [key.to_dict() for key in self.api_keys],
            "models": [model.to_dict() for model in self.models],
            "headers": [header.to_dict() for header in self.headers],
            "is-enabled": self.is_enabled,
            "created-at": self.created_at.isoformat(),
            "updated-at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CustomProvider":
        """Create from dictionary."""
        # Handle both snake_case and kebab-case keys for backward compatibility
        api_keys_data = data.get("api-keys", data.get("api_keys", []))
        models_data = data.get("models", [])
        headers_data = data.get("headers", [])
        
        # Convert old format (list of strings) to new format (list of CustomAPIKeyEntry)
        if api_keys_data and isinstance(api_keys_data[0], str):
            api_keys = [CustomAPIKeyEntry(api_key=k) for k in api_keys_data]
        else:
            api_keys = [CustomAPIKeyEntry.from_dict(k) for k in api_keys_data]
        
        # Convert old format (list of strings) to new format (list of ModelMapping)
        if models_data and isinstance(models_data[0], str):
            models = [ModelMapping(name=m, alias=m) for m in models_data]
        else:
            models = [ModelMapping.from_dict(m) for m in models_data]
        
        # Convert old format (dict) to new format (list of CustomHeader)
        if headers_data and isinstance(headers_data, dict):
            headers = [CustomHeader(key=k, value=v) for k, v in headers_data.items()]
        else:
            headers = [CustomHeader.from_dict(h) for h in headers_data]
        
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            type=CustomProviderType(data.get("type", data.get("type", "openai-compatibility"))),
            base_url=data.get("base-url", data.get("base_url", "")),
            api_keys=api_keys,
            models=models,
            headers=headers,
            is_enabled=data.get("is-enabled", data.get("is_enabled", True)),
            created_at=datetime.fromisoformat(data.get("created-at", data.get("created_at", datetime.now().isoformat()))),
            updated_at=datetime.fromisoformat(data.get("updated-at", data.get("updated_at", datetime.now().isoformat()))),
        )
    
    def to_yaml_block(self) -> str:
        """Generate YAML config block for this provider."""
        yaml = ""
        
        if self.type == CustomProviderType.OPENAI_COMPATIBILITY:
            yaml = self._generate_openai_compatibility_yaml()
        elif self.type == CustomProviderType.CLAUDE_COMPATIBILITY:
            yaml = self._generate_claude_compatibility_yaml()
        elif self.type == CustomProviderType.GEMINI_COMPATIBILITY:
            yaml = self._generate_gemini_compatibility_yaml()
        elif self.type == CustomProviderType.CODEX_COMPATIBILITY:
            yaml = self._generate_codex_compatibility_yaml()
        elif self.type == CustomProviderType.GLM_COMPATIBILITY:
            yaml = self._generate_glm_compatibility_yaml()
        
        return yaml
    
    def _generate_openai_compatibility_yaml(self) -> str:
        """Generate YAML for OpenAI-compatible provider."""
        escaped_name = self.name.replace('"', '\\"')
        yaml = f'  - name: "{escaped_name}"\n'
        yaml += f'    base-url: "{self.base_url}"\n'
        
        if self.api_keys:
            yaml += "    api-key-entries:\n"
            for key in self.api_keys:
                yaml += f'      - api-key: "{key.api_key}"\n'
                if key.proxy_url:
                    yaml += f'        proxy-url: "{key.proxy_url}"\n'
        
        if self.models:
            yaml += "    models:\n"
            for model in self.models:
                yaml += f'      - name: "{model.name}"\n'
                yaml += f'        alias: "{model.effective_alias}"\n'
        
        return yaml
    
    def _generate_claude_compatibility_yaml(self) -> str:
        """Generate YAML for Claude-compatible provider."""
        yaml = ""
        for key in self.api_keys:
            yaml += f'  - api-key: "{key.api_key}"\n'
            
            # Only include base-url if not default
            if self.base_url and self.base_url != self.type.default_base_url:
                yaml += f'    base-url: "{self.base_url}"\n'
            
            if key.proxy_url:
                yaml += f'    proxy-url: "{key.proxy_url}"\n'
            
            if self.models:
                yaml += "    models:\n"
                for model in self.models:
                    yaml += f'      - name: "{model.name}"\n'
                    yaml += f'        alias: "{model.effective_alias}"\n'
        
        return yaml
    
    def _generate_gemini_compatibility_yaml(self) -> str:
        """Generate YAML for Gemini-compatible provider."""
        yaml = ""
        for key in self.api_keys:
            yaml += f'  - api-key: "{key.api_key}"\n'
            
            # Only include base-url if not default
            if self.base_url and self.base_url != self.type.default_base_url:
                yaml += f'    base-url: "{self.base_url}"\n'
            
            if self.headers:
                yaml += "    headers:\n"
                for header in self.headers:
                    yaml += f'      {header.key}: "{header.value}"\n'
            
            if key.proxy_url:
                yaml += f'    proxy-url: "{key.proxy_url}"\n'
        
        return yaml
    
    def _generate_codex_compatibility_yaml(self) -> str:
        """Generate YAML for Codex-compatible provider."""
        yaml = ""
        for key in self.api_keys:
            yaml += f'  - api-key: "{key.api_key}"\n'
            yaml += f'    base-url: "{self.base_url}"\n'
            
            if key.proxy_url:
                yaml += f'    proxy-url: "{key.proxy_url}"\n'
        
        return yaml
    
    def _generate_glm_compatibility_yaml(self) -> str:
        """Generate YAML for GLM-compatible provider."""
        yaml = ""
        for key in self.api_keys:
            yaml += f'  - api-key: "{key.api_key}"\n'
            
            if self.base_url and self.base_url != self.type.default_base_url:
                yaml += f'    base-url: "{self.base_url}"\n'
            
            if key.proxy_url:
                yaml += f'    proxy-url: "{key.proxy_url}"\n'
        
        return yaml
