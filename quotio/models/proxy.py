"""Proxy-related models."""

from typing import Optional
from pydantic import BaseModel, Field


class ProxyStatus(BaseModel):
    """Proxy server status."""
    running: bool = False
    port: int = 8317

    @property
    def endpoint(self) -> str:
        """Proxy endpoint URL."""
        return f"http://localhost:{self.port}/v1"


class RoutingConfig(BaseModel):
    """Routing configuration."""
    strategy: str = "round-robin"  # "round-robin" or "fill-first"


class QuotaExceededConfig(BaseModel):
    """Quota exceeded behavior configuration."""
    switch_project: bool = True
    switch_preview_model: bool = True


class RemoteManagementConfig(BaseModel):
    """Remote management configuration."""
    allow_remote: bool = False
    secret_key: str = ""
    disable_control_panel: bool = False


class AppConfig(BaseModel):
    """Application configuration."""
    host: str = ""
    port: int = 8317
    auth_dir: str = "~/.cli-proxy-api"
    proxy_url: str = ""
    api_keys: list[str] = Field(default_factory=list)
    debug: bool = False
    logging_to_file: bool = False
    usage_statistics_enabled: bool = True
    request_retry: int = 3
    max_retry_interval: int = 30
    ws_auth: bool = False
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    quota_exceeded: QuotaExceededConfig = Field(default_factory=QuotaExceededConfig)
    remote_management: RemoteManagementConfig = Field(default_factory=RemoteManagementConfig)
