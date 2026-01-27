"""AgentSetupViewModel - Agent configuration state management."""

from typing import Optional, List
from dataclasses import dataclass, field

from ..models.agents import CLIAgent
from ..services.agent_detection import AgentDetectionService, AgentStatus
from ..services.proxy_manager import CLIProxyManager
from .quota_viewmodel import QuotaViewModel


@dataclass
class AgentSetupViewModel:
    """View model for agent setup and configuration."""

    detection_service: AgentDetectionService = field(default_factory=AgentDetectionService)
    agent_statuses: List[AgentStatus] = field(default_factory=list)
    isLoading: bool = False
    isConfiguring: bool = False
    selected_agent: Optional[CLIAgent] = None
    error_message: Optional[str] = None

    # References
    proxy_manager: Optional[CLIProxyManager] = None
    quota_viewmodel: Optional[QuotaViewModel] = None

    def setup(self, proxy_manager: CLIProxyManager, quota_viewmodel: Optional[QuotaViewModel] = None):
        """Setup the view model with dependencies."""
        self.proxy_manager = proxy_manager
        self.quota_viewmodel = quota_viewmodel

    async def refresh_agent_statuses(self, force_refresh: bool = False):
        """Refresh agent detection status."""
        self.isLoading = True
        try:
            self.agent_statuses = await self.detection_service.detect_all_agents(force_refresh)
        finally:
            self.isLoading = False

    def status_for_agent(self, agent: CLIAgent) -> Optional[AgentStatus]:
        """Get status for a specific agent."""
        return next((s for s in self.agent_statuses if s.agent == agent), None)

    async def start_configuration(
        self,
        agent: CLIAgent,
        api_key: str,
        proxy_url: Optional[str] = None,
        model_slots: Optional[dict] = None
    ):
        """Start configuration for an agent."""
        self.selected_agent = agent
        self.isConfiguring = True
        self.error_message = None

        try:
            from ..services.agent_config import AgentConfigurationService, AgentConfiguration, ModelSlot

            if not self.proxy_manager:
                self.error_message = "Proxy manager not available"
                return

            # Get proxy URL
            if not proxy_url:
                port = self.proxy_manager.port
                proxy_url = f"http://localhost:{port}"

            # Default model slots
            if not model_slots:
                model_slots = {ModelSlot.SONNET: "claude-sonnet-4-20250514"}

            # Create configuration
            config = AgentConfiguration(
                agent=agent,
                proxy_url=proxy_url,
                api_key=api_key,
                model_slots=model_slots,
            )

            # Write configuration
            config_service = AgentConfigurationService()
            config_service.write_configuration(config)

            self.error_message = None
        except Exception as e:
            self.error_message = f"Failed to configure agent: {str(e)}"
        finally:
            self.isConfiguring = False
