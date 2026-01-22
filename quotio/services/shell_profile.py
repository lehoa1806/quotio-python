"""Shell profile management service."""

import os
from pathlib import Path
from enum import Enum
from typing import Optional


class ShellType(str, Enum):
    """Shell types."""
    ZSH = "zsh"
    BASH = "bash"
    FISH = "fish"
    
    @property
    def profile_path(self) -> Path:
        """Get profile path for shell."""
        home = Path.home()
        if self == ShellType.ZSH:
            return home / ".zshrc"
        elif self == ShellType.BASH:
            return home / ".bashrc"
        elif self == ShellType.FISH:
            return home / ".config" / "fish" / "config.fish"
        return home / ".zshrc"


class ShellProfileManager:
    """Manages shell profile modifications."""
    
    def detect_shell(self) -> ShellType:
        """Detect current shell."""
        shell = os.environ.get("SHELL", "")
        if "zsh" in shell:
            return ShellType.ZSH
        elif "bash" in shell:
            return ShellType.BASH
        elif "fish" in shell:
            return ShellType.FISH
        return ShellType.ZSH  # Default
    
    def get_profile_path(self, shell: ShellType) -> Path:
        """Get profile path for shell."""
        return shell.profile_path
    
    def add_to_profile(
        self,
        shell: ShellType,
        configuration: str,
        agent_name: str
    ) -> None:
        """Add configuration to shell profile."""
        profile_path = self.get_profile_path(shell)
        marker = f"# CLIProxyAPI Configuration for {agent_name}"
        end_marker = f"# End CLIProxyAPI Configuration for {agent_name}"
        
        # Read existing content
        content = ""
        if profile_path.exists():
            with open(profile_path, "r") as f:
                content = f.read()
        
        # Remove existing configuration if present
        if marker in content and end_marker in content:
            start_idx = content.find(marker)
            end_idx = content.find(end_marker) + len(end_marker)
            # Remove newline before if present
            if start_idx > 0 and content[start_idx - 1] == "\n":
                start_idx -= 1
            # Remove newline after if present
            if end_idx < len(content) and content[end_idx] == "\n":
                end_idx += 1
            content = content[:start_idx] + content[end_idx:]
        
        # Add new configuration
        new_config = f"\n{marker}\n{configuration}\n{end_marker}\n"
        content += new_config
        
        # Write file
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(profile_path, "w") as f:
            f.write(content)
    
    def remove_from_profile(
        self,
        shell: ShellType,
        agent_name: str
    ) -> None:
        """Remove configuration from shell profile."""
        profile_path = self.get_profile_path(shell)
        
        if not profile_path.exists():
            return
        
        marker = f"# CLIProxyAPI Configuration for {agent_name}"
        end_marker = f"# End CLIProxyAPI Configuration for {agent_name}"
        
        with open(profile_path, "r") as f:
            content = f.read()
        
        if marker in content and end_marker in content:
            start_idx = content.find(marker)
            end_idx = content.find(end_marker) + len(end_marker)
            
            # Remove newline before if present
            if start_idx > 0 and content[start_idx - 1] == "\n":
                start_idx -= 1
            # Remove newline after if present
            if end_idx < len(content) and content[end_idx] == "\n":
                end_idx += 1
            
            content = content[:start_idx] + content[end_idx:]
            
            with open(profile_path, "w") as f:
                f.write(content)
    
    def is_configured_in_profile(
        self,
        shell: ShellType,
        agent_name: str
    ) -> bool:
        """Check if agent is configured in profile."""
        profile_path = self.get_profile_path(shell)
        
        if not profile_path.exists():
            return False
        
        marker = f"# CLIProxyAPI Configuration for {agent_name}"
        
        try:
            with open(profile_path, "r") as f:
                content = f.read()
            return marker in content
        except Exception:
            return False
    
    def create_backup(self, shell: ShellType) -> Path:
        """Create backup of shell profile."""
        import time
        import shutil
        
        profile_path = self.get_profile_path(shell)
        backup_path = Path(f"{profile_path}.backup.{int(time.time())}")
        
        if profile_path.exists():
            shutil.copy2(profile_path, backup_path)
        
        return backup_path
