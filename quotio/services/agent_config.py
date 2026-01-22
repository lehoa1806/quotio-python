"""Agent configuration service."""

import json
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..models.agents import CLIAgent


class ModelSlot(str, Enum):
    """Model slot types."""
    OPUS = "opus"
    SONNET = "sonnet"
    HAIKU = "haiku"


@dataclass
class SavedAgentConfig:
    """Currently saved configuration for an agent."""
    base_url: Optional[str]
    api_key: Optional[str]
    model_slots: Dict[ModelSlot, str]
    is_proxy_configured: bool
    backup_files: List['BackupFile']


@dataclass
class BackupFile:
    """Backup file that can be restored."""
    path: str
    timestamp: datetime
    agent: CLIAgent
    
    @property
    def display_name(self) -> str:
        """Display name for the backup."""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class AgentConfiguration:
    """Configuration to apply to an agent."""
    agent: CLIAgent
    proxy_url: str
    api_key: str
    model_slots: Dict[ModelSlot, str]
    config_storage: str = "json"  # "json", "env", "both"


class AgentConfigurationService:
    """Service for generating and managing agent configurations."""
    
    def __init__(self):
        """Initialize the service."""
        self.home = Path.home()
    
    def read_configuration(self, agent: CLIAgent) -> Optional[SavedAgentConfig]:
        """Read the current saved configuration for an agent."""
        if agent == CLIAgent.CLAUDE_CODE:
            return self._read_claude_code_config()
        elif agent == CLIAgent.CODEX_CLI:
            return self._read_codex_config()
        elif agent == CLIAgent.GEMINI_CLI:
            return self._read_gemini_cli_config()
        elif agent == CLIAgent.AMP_CLI:
            return self._read_amp_config()
        elif agent == CLIAgent.OPEN_CODE:
            return self._read_opencode_config()
        elif agent == CLIAgent.FACTORY_DROID:
            return self._read_factory_droid_config()
        return None
    
    def list_backups(self, agent: CLIAgent) -> List[BackupFile]:
        """List available backup files for an agent."""
        backups = []
        
        for config_path_str in agent.config_paths:
            config_path = Path(config_path_str.replace("~", str(self.home)))
            directory = config_path.parent
            filename = config_path.name
            
            if not directory.exists():
                continue
            
            # Find backup files
            for file in directory.iterdir():
                if file.name.startswith(f"{filename}.backup."):
                    # Extract timestamp from filename
                    timestamp_str = file.name.split(".backup.")[-1]
                    try:
                        timestamp = datetime.fromtimestamp(float(timestamp_str))
                        backups.append(BackupFile(
                            path=str(file),
                            timestamp=timestamp,
                            agent=agent
                        ))
                    except ValueError:
                        continue
        
        # Sort by most recent first
        backups.sort(key=lambda x: x.timestamp, reverse=True)
        return backups
    
    def restore_from_backup(self, backup: BackupFile) -> None:
        """Restore configuration from a backup file."""
        # Determine original path
        backup_path = Path(backup.path)
        timestamp_str = str(int(backup.timestamp.timestamp()))
        original_path = Path(backup.path.replace(f".backup.{timestamp_str}", ""))
        
        # Create backup of current config before restoring
        if original_path.exists():
            current_backup = Path(f"{original_path}.backup.{int(datetime.now().timestamp())}")
            shutil.copy2(original_path, current_backup)
            original_path.unlink()
        
        # Copy backup to original location
        shutil.copy2(backup_path, original_path)
    
    def write_configuration(self, config: AgentConfiguration) -> None:
        """Write configuration to agent's config files."""
        # Create backup first
        self._create_backup(config.agent)
        
        if config.agent == CLIAgent.CLAUDE_CODE:
            self._write_claude_code_config(config)
        elif config.agent == CLIAgent.CODEX_CLI:
            self._write_codex_config(config)
        elif config.agent == CLIAgent.GEMINI_CLI:
            self._write_gemini_cli_config(config)
        elif config.agent == CLIAgent.AMP_CLI:
            self._write_amp_config(config)
        elif config.agent == CLIAgent.OPEN_CODE:
            self._write_opencode_config(config)
        elif config.agent == CLIAgent.FACTORY_DROID:
            self._write_factory_droid_config(config)
    
    def _create_backup(self, agent: CLIAgent) -> None:
        """Create backup of current configuration (matches backup behavior)."""
        # Backup all config files for the agent
        for config_path_str in agent.config_paths:
            config_path = Path(config_path_str.replace("~", str(self.home)))
            if config_path.exists():
                backup_path = Path(f"{config_path}.backup.{int(datetime.now().timestamp())}")
                shutil.copy2(config_path, backup_path)
        
        # Also backup agent-specific auth files
        if agent == CLIAgent.CODEX_CLI:
            auth_path = self.home / ".codex" / "auth.json"
            if auth_path.exists():
                backup_path = Path(f"{auth_path}.backup.{int(datetime.now().timestamp())}")
                shutil.copy2(auth_path, backup_path)
        elif agent == CLIAgent.AMP_CLI:
            secrets_path = self.home / ".local" / "share" / "amp" / "secrets.json"
            if secrets_path.exists():
                backup_path = Path(f"{secrets_path}.backup.{int(datetime.now().timestamp())}")
                shutil.copy2(secrets_path, backup_path)
    
    def _read_claude_code_config(self) -> Optional[SavedAgentConfig]:
        """Read Claude Code configuration."""
        config_path = self.home / ".claude" / "settings.json"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            
            env = data.get("env", {})
            base_url = env.get("ANTHROPIC_BASE_URL")
            api_key = env.get("ANTHROPIC_AUTH_TOKEN")
            
            model_slots = {}
            if "ANTHROPIC_DEFAULT_OPUS_MODEL" in env:
                model_slots[ModelSlot.OPUS] = env["ANTHROPIC_DEFAULT_OPUS_MODEL"]
            if "ANTHROPIC_DEFAULT_SONNET_MODEL" in env:
                model_slots[ModelSlot.SONNET] = env["ANTHROPIC_DEFAULT_SONNET_MODEL"]
            if "ANTHROPIC_DEFAULT_HAIKU_MODEL" in env:
                model_slots[ModelSlot.HAIKU] = env["ANTHROPIC_DEFAULT_HAIKU_MODEL"]
            
            is_proxy = base_url and ("127.0.0.1" in base_url or "localhost" in base_url)
            
            return SavedAgentConfig(
                base_url=base_url,
                api_key=api_key,
                model_slots=model_slots,
                is_proxy_configured=is_proxy,
                backup_files=self.list_backups(CLIAgent.CLAUDE_CODE)
            )
        except Exception:
            return None
    
    def _write_claude_code_config(self, config: AgentConfiguration) -> None:
        """Write Claude Code configuration."""
        config_path = self.home / ".claude" / "settings.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Read existing or create new
        data = {}
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
            except Exception:
                pass
        
        # Update env section
        env = data.get("env", {})
        env["ANTHROPIC_BASE_URL"] = config.proxy_url
        env["ANTHROPIC_AUTH_TOKEN"] = config.api_key
        
        # Update model slots
        if ModelSlot.OPUS in config.model_slots:
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = config.model_slots[ModelSlot.OPUS]
        if ModelSlot.SONNET in config.model_slots:
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = config.model_slots[ModelSlot.SONNET]
        if ModelSlot.HAIKU in config.model_slots:
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = config.model_slots[ModelSlot.HAIKU]
        
        data["env"] = env
        
        # Write file
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _read_codex_config(self) -> Optional[SavedAgentConfig]:
        """Read Codex CLI configuration (matches readCodexConfig)."""
        config_path = self.home / ".codex" / "config.toml"
        auth_path = self.home / ".codex" / "auth.json"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r") as f:
                content = f.read()
            
            # Simple TOML parsing
            base_url = None
            model = None
            is_proxy = False
            
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("base_url"):
                    value = self._extract_toml_value(line)
                    base_url = value
                    is_proxy = value and ("127.0.0.1" in value or "localhost" in value)
                elif line.startswith("model ="):
                    model = self._extract_toml_value(line)
            
            model_slots = {}
            if model:
                model_slots[ModelSlot.SONNET] = model
            
            # Read API key from auth.json if it exists
            api_key = None
            if auth_path.exists():
                try:
                    with open(auth_path, "r") as f:
                        auth_data = json.load(f)
                        api_key = auth_data.get("OPENAI_API_KEY")
                except Exception:
                    pass
            
            return SavedAgentConfig(
                base_url=base_url,
                api_key=api_key,  # Read from auth.json
                model_slots=model_slots,
                is_proxy_configured=is_proxy,
                backup_files=self.list_backups(CLIAgent.CODEX_CLI)
            )
        except Exception:
            return None
    
    def _write_codex_config(self, config: AgentConfiguration) -> None:
        """Write Codex CLI configuration (matches generateCodexConfig)."""
        config_path = self.home / ".codex" / "config.toml"
        auth_path = self.home / ".codex" / "auth.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write config.toml
        # Read existing or create new
        content = ""
        if config_path.exists():
            with open(config_path, "r") as f:
                content = f.read()
        
        # Update or add base_url
        if "base_url" in content:
            # Replace existing
            import re
            content = re.sub(r'base_url\s*=\s*"[^"]*"', f'base_url = "{config.proxy_url}"', content)
        else:
            content += f'\nbase_url = "{config.proxy_url}"\n'
        
        # Update model if provided
        if config.model_slots:
            model = list(config.model_slots.values())[0]
            if "model =" in content:
                import re
                content = re.sub(r'model\s*=\s*"[^"]*"', f'model = "{model}"', content)
            else:
                content += f'model = "{model}"\n'
        
        # Write config.toml
        with open(config_path, "w") as f:
            f.write(content)
        
        # Write auth.json with API key (matches Original: authJSON)
        auth_data = {
            "OPENAI_API_KEY": config.api_key
        }
        with open(auth_path, "w") as f:
            json.dump(auth_data, f, indent=2)
    
    def _read_gemini_cli_config(self) -> Optional[SavedAgentConfig]:
        """Read Gemini CLI configuration (environment variables)."""
        # Gemini CLI uses environment variables
        # Check shell profiles
        shell_paths = [
            self.home / ".zshrc",
            self.home / ".bashrc",
            self.home / ".bash_profile",
        ]
        
        for shell_path in shell_paths:
            if shell_path.exists():
                try:
                    with open(shell_path, "r") as f:
                        content = f.read()
                    
                    # Extract GEMINI_BASE_URL and GEMINI_API_KEY
                    base_url = self._extract_env_var(content, "GEMINI_BASE_URL")
                    api_key = self._extract_env_var(content, "GEMINI_API_KEY")
                    
                    if base_url or api_key:
                        is_proxy = base_url and ("127.0.0.1" in base_url or "localhost" in base_url)
                        return SavedAgentConfig(
                            base_url=base_url,
                            api_key=api_key,
                            model_slots={},
                            is_proxy_configured=is_proxy,
                            backup_files=[]
                        )
                except Exception:
                    continue
        
        return None
    
    def _write_gemini_cli_config(self, config: AgentConfiguration) -> None:
        """Write Gemini CLI configuration to shell profile."""
        # This will be handled by ShellProfileManager
        # Placeholder for now
        pass
    
    def _read_amp_config(self) -> Optional[SavedAgentConfig]:
        """Read Amp CLI configuration (matches readAmpConfig)."""
        settings_path = self.home / ".config" / "amp" / "settings.json"
        secrets_path = self.home / ".local" / "share" / "amp" / "secrets.json"
        
        if not settings_path.exists():
            return None
        
        try:
            with open(settings_path, "r") as f:
                settings_data = json.load(f)
            
            base_url = settings_data.get("amp.url") or settings_data.get("baseURL") or settings_data.get("base_url")
            
            # Read API key from secrets.json if it exists
            api_key = None
            if secrets_path.exists():
                try:
                    with open(secrets_path, "r") as f:
                        secrets_data = json.load(f)
                        # API key is stored as "apiKey@{base_url}"
                        if base_url:
                            api_key = secrets_data.get(f"apiKey@{base_url}")
                        # Fallback: try to get any apiKey entry
                        if not api_key:
                            for key, value in secrets_data.items():
                                if key.startswith("apiKey@"):
                                    api_key = value
                                    break
                except Exception:
                    pass
            
            is_proxy = base_url and ("127.0.0.1" in base_url or "localhost" in base_url)
            
            return SavedAgentConfig(
                base_url=base_url,
                api_key=api_key,  # Read from secrets.json
                model_slots={},
                is_proxy_configured=is_proxy,
                backup_files=self.list_backups(CLIAgent.AMP_CLI)
            )
        except Exception:
            return None
    
    def _write_amp_config(self, config: AgentConfiguration) -> None:
        """Write Amp CLI configuration (matches generateAmpConfig)."""
        config_dir = self.home / ".config" / "amp"
        data_dir = self.home / ".local" / "share" / "amp"
        settings_path = config_dir / "settings.json"
        secrets_path = data_dir / "secrets.json"
        
        config_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Write settings.json (matches Original: settingsJSON)
        base_url = config.proxy_url.replace("/v1", "") if config.proxy_url.endswith("/v1") else config.proxy_url
        settings_data = {
            "amp.url": base_url
        }
        with open(settings_path, "w") as f:
            json.dump(settings_data, f, indent=2)
        
        # Write secrets.json with API key (matches Original: secretsJSON)
        secrets_data = {
            f"apiKey@{base_url}": config.api_key
        }
        with open(secrets_path, "w") as f:
            json.dump(secrets_data, f, indent=2)
    
    def _read_opencode_config(self) -> Optional[SavedAgentConfig]:
        """Read OpenCode configuration."""
        config_path = self.home / ".config" / "opencode" / "opencode.json"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            
            base_url = data.get("baseURL") or data.get("base_url")
            api_key = data.get("apiKey") or data.get("api_key")
            
            is_proxy = base_url and ("127.0.0.1" in base_url or "localhost" in base_url)
            
            return SavedAgentConfig(
                base_url=base_url,
                api_key=api_key,
                model_slots={},
                is_proxy_configured=is_proxy,
                backup_files=self.list_backups(CLIAgent.OPEN_CODE)
            )
        except Exception:
            return None
    
    def _write_opencode_config(self, config: AgentConfiguration) -> None:
        """Write OpenCode configuration."""
        config_path = self.home / ".config" / "opencode" / "opencode.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "baseURL": config.proxy_url,
            "apiKey": config.api_key,
        }
        
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _read_factory_droid_config(self) -> Optional[SavedAgentConfig]:
        """Read Factory Droid configuration."""
        config_path = self.home / ".factory" / "config.json"
        
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            
            base_url = data.get("baseURL") or data.get("base_url")
            api_key = data.get("apiKey") or data.get("api_key")
            
            is_proxy = base_url and ("127.0.0.1" in base_url or "localhost" in base_url)
            
            return SavedAgentConfig(
                base_url=base_url,
                api_key=api_key,
                model_slots={},
                is_proxy_configured=is_proxy,
                backup_files=self.list_backups(CLIAgent.FACTORY_DROID)
            )
        except Exception:
            return None
    
    def _write_factory_droid_config(self, config: AgentConfiguration) -> None:
        """Write Factory Droid configuration."""
        config_path = self.home / ".factory" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "baseURL": config.proxy_url,
            "apiKey": config.api_key,
        }
        
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _extract_toml_value(self, line: str) -> Optional[str]:
        """Extract value from TOML line."""
        if "=" not in line:
            return None
        
        value = line.split("=", 1)[1].strip()
        # Remove quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        
        return value
    
    def _extract_env_var(self, content: str, var_name: str) -> Optional[str]:
        """Extract environment variable value from shell profile."""
        import re
        # Match: export VAR="value" or export VAR=value
        pattern = rf'export\s+{var_name}=["\']?([^"\'\n]+)["\']?'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        return None
