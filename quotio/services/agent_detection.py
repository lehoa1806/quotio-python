"""Agent detection service."""

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from ..models.agents import CLIAgent


@dataclass
class AgentStatus:
    """Status of a CLI agent."""
    agent: CLIAgent
    installed: bool
    configured: bool
    binary_path: Optional[str] = None
    version: Optional[str] = None
    last_configured: Optional[datetime] = None


class AgentDetectionService:
    """Service for detecting installed CLI agents."""
    
    # Common binary paths to search
    COMMON_BINARY_PATHS = [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "~/.local/bin",
        "~/.cargo/bin",
        "~/.bun/bin",
        "~/.deno/bin",
        "~/.npm-global/bin",
        "~/.opencode/bin",
        "~/.volta/bin",
        "~/.asdf/shims",
        "~/.local/share/mise/shims",
    ]
    
    def __init__(self):
        """Initialize the detection service."""
        self._cache: Optional[list[AgentStatus]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 60  # 1 minute
    
    async def detect_all_agents(self, force_refresh: bool = False) -> list[AgentStatus]:
        """Detect all agents."""
        # Check cache
        if not force_refresh and self._cache and self._cache_timestamp:
            age = (datetime.now() - self._cache_timestamp).total_seconds()
            if age < self._cache_ttl:
                print(f"[AgentDetection] Using cached results ({len(self._cache)} agents)")
                return self._cache
        
        print(f"[AgentDetection] Detecting all agents (force_refresh={force_refresh})...")
        
        # Detect all agents in parallel
        import asyncio
        tasks = [self.detect_agent(agent) for agent in CLIAgent]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent = list(CLIAgent)[i]
                print(f"[AgentDetection] Error detecting {agent.display_name}: {result}")
                # Create a status indicating not installed
                valid_results.append(AgentStatus(
                    agent=agent,
                    installed=False,
                    configured=False,
                    binary_path=None,
                    version=None,
                ))
            else:
                valid_results.append(result)
                if result.installed:
                    print(f"[AgentDetection] Found {result.agent.display_name} at {result.binary_path}")
        
        # Sort by display name
        valid_results.sort(key=lambda x: x.agent.display_name)
        
        print(f"[AgentDetection] Detection complete: {sum(1 for r in valid_results if r.installed)}/{len(valid_results)} installed")
        
        # Update cache
        self._cache = valid_results
        self._cache_timestamp = datetime.now()
        
        return valid_results
    
    def invalidate_cache(self):
        """Invalidate the cache."""
        self._cache = None
        self._cache_timestamp = None
    
    async def detect_agent(self, agent: CLIAgent) -> AgentStatus:
        """Detect a specific agent."""
        # Run binary detection in executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        installed, binary_path = await loop.run_in_executor(None, self._find_binary_sync, agent.binary_names)
        version = None
        configured = False
        
        if installed and binary_path:
            version = await self._get_version(binary_path)
            configured = await self._check_configuration(agent)
        
        return AgentStatus(
            agent=agent,
            installed=installed,
            configured=configured,
            binary_path=binary_path,
            version=version,
        )
    
    def _find_binary_sync(self, names: list[str]) -> Tuple[bool, Optional[str]]:
        """Find binary using which command and common paths (synchronous)."""
        home = Path.home()
        
        for name in names:
            # Try which command
            which_path = shutil.which(name)
            if which_path:
                return True, which_path
            
            # Check common paths
            for base_path in self.COMMON_BINARY_PATHS:
                expanded = base_path.replace("~", str(home))
                binary_path = Path(expanded) / name
                if binary_path.exists() and os.access(binary_path, os.X_OK):
                    return True, str(binary_path)
        
        return False, None
    
    async def _find_binary(self, names: list[str]) -> Tuple[bool, Optional[str]]:
        """Find binary using which command and common paths (async wrapper)."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._find_binary_sync, names)
    
    async def _get_version(self, binary_path: str) -> Optional[str]:
        """Get version of binary."""
        try:
            result = subprocess.run(
                [binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Extract version from output
                output = result.stdout.strip()
                # Simple extraction - first line, first number
                lines = output.split("\n")
                if lines:
                    words = lines[0].split()
                    for word in words:
                        if word[0].isdigit():
                            return word
            return None
        except Exception:
            return None
    
    async def _check_configuration(self, agent: CLIAgent) -> bool:
        """Check if agent is configured (matches checkConfigFiles).
        
        An agent is considered configured if:
        1. Config files exist
        2. Config files contain proxy-related strings (127.0.0.1, localhost, or cliproxyapi)
        """
        home = Path.home()
        
        for config_path in agent.config_paths:
            expanded = config_path.replace("~", str(home))
            path = Path(expanded)
            if path.exists():
                try:
                    # Read config file content
                    content = path.read_text(encoding="utf-8")
                    # Check if it contains proxy-related strings (matches original logic)
                    if "127.0.0.1" in content or "localhost" in content or "cliproxyapi" in content:
                        return True
                except Exception:
                    # If we can't read the file, continue to next config path
                    continue
        
        return False
