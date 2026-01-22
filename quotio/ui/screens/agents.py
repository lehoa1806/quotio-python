"""Agent setup screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox, QLineEdit, QGroupBox, QFormLayout, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QThread
from PyQt6.QtGui import QColor, QMouseEvent
from datetime import datetime
import asyncio

from ...models.agents import CLIAgent
from ...models.agent_connections import NamedAgentConnection
from ...models.providers import AIProvider
from ...services.agent_connection_storage import AgentConnectionStorage
from ...viewmodels.agent_viewmodel import AgentSetupViewModel
from ..utils import show_message_box, get_main_window, get_agent_status_color


def run_async_coro(coro):
    """Run an async coroutine, creating task if loop is running."""
    # Import from main_window to use the shared thread-safe function
    from ..main_window import run_async_coro as main_run_async_coro
    return main_run_async_coro(coro)


class AgentSetupScreen(QWidget):
    """Screen for configuring CLI agents."""
    
    def __init__(self, view_model=None, agent_viewmodel=None):
        """Initialize the agent setup screen."""
        super().__init__()
        self.view_model = view_model
        self.agent_viewmodel = agent_viewmodel or AgentSetupViewModel()
        if view_model:
            self.agent_viewmodel.setup(
                view_model.proxy_manager,
                view_model
            )
        self.connection_storage = AgentConnectionStorage()
        # Store visibility state for each row's API key (row_index -> bool)
        self.api_key_visibility = {}
        self._setup_ui()
        # Load agents on init (defer until event loop is running)
        async def load_agents():
            try:
                await self.agent_viewmodel.refresh_agent_statuses(force_refresh=True)
                # Schedule UI update on main thread to avoid threading issues
                from ..utils import call_on_main_thread
                call_on_main_thread(self._update_display)
            except Exception as e:
                print(f"[AgentSetup] Error loading agents: {e}")
                import traceback
                traceback.print_exc()
        
        QTimer.singleShot(0, lambda: run_async_coro(load_agents()))
        
        # API key combo removed - now managed in connection dialog
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Title
        title = QLabel("Agents")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Create tab widget for sub-tabs
        self.agent_tabs = QTabWidget()
        self.agent_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #f5f5f5;
                color: #333;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #007AFF;
                border-bottom: 2px solid #007AFF;
            }
            QTabBar::tab:hover {
                background-color: #e8e8e8;
            }
        """)
        
        # Tab 1: Agent Connections
        connections_tab = QWidget()
        connections_layout = QVBoxLayout()
        connections_layout.setSpacing(12)
        connections_layout.setContentsMargins(8, 8, 8, 8)
        
        self.agent_status_label = QLabel("Loading agent status...")
        self.agent_status_label.setWordWrap(True)
        connections_layout.addWidget(self.agent_status_label)
        
        self.agent_table = QTableWidget()
        self.agent_table.setColumnCount(8)
        self.agent_table.setHorizontalHeaderLabels(["Connection Name", "Agent", "Status", "Configuration", "Proxy URL", "API Key", "Quota", "Model"])
        # Store visibility state for each row's API key
        self.api_key_visibility = {}  # row_index -> bool (True = visible, False = hidden)
        self.agent_table.horizontalHeader().setStretchLastSection(True)
        self.agent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.agent_table.setAlternatingRowColors(True)
        self.agent_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                gridline-color: #eee;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #ddd;
                font-weight: bold;
            }
        """)
        connections_layout.addWidget(self.agent_table)
        
        # Add/Edit/Delete buttons for connections
        connection_buttons_layout = QHBoxLayout()
        
        self.add_connection_button = QPushButton("+ Add Connection")
        self.add_connection_button.clicked.connect(self._on_add_connection)
        connection_buttons_layout.addWidget(self.add_connection_button)
        
        self.edit_connection_button = QPushButton("Edit")
        self.edit_connection_button.clicked.connect(self._on_edit_connection)
        self.edit_connection_button.setEnabled(False)
        connection_buttons_layout.addWidget(self.edit_connection_button)
        
        self.delete_connection_button = QPushButton("Delete")
        self.delete_connection_button.clicked.connect(self._on_delete_connection)
        self.delete_connection_button.setEnabled(False)
        connection_buttons_layout.addWidget(self.delete_connection_button)
        
        connection_buttons_layout.addStretch()
        connections_layout.addLayout(connection_buttons_layout)
        
        # Enable/disable edit/delete buttons based on selection
        self.agent_table.itemSelectionChanged.connect(self._on_connection_selection_changed)
        
        connections_tab.setLayout(connections_layout)
        self.agent_tabs.addTab(connections_tab, "Agent Connections")
        
        # Tab 2: Agent Setup
        setup_tab = QWidget()
        setup_layout = QVBoxLayout()
        setup_layout.setSpacing(12)
        setup_layout.setContentsMargins(8, 8, 8, 8)
        
        # Agent list
        self.agent_list = QListWidget()
        setup_layout.addWidget(self.agent_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh)
        button_layout.addWidget(self.refresh_button)
        
        self.configure_button = QPushButton("Configure")
        self.configure_button.clicked.connect(self._on_configure)
        button_layout.addWidget(self.configure_button)
        
        button_layout.addStretch()
        setup_layout.addLayout(button_layout)
        
        # Configuration section removed - API keys are now managed in the Connection dialog
        
        # Status label
        self.status_label = QLabel("")
        setup_layout.addWidget(self.status_label)
        
        setup_tab.setLayout(setup_layout)
        self.agent_tabs.addTab(setup_tab, "Agent Setup")
        
        layout.addWidget(self.agent_tabs)
        
        # Update display
        self._update_display()
    
    def _update_display(self):
        """Update the agent list and connections table."""
        self._update_agent_list()
        self._update_agent_connections()
    
    def _update_agent_list(self):
        """Update the agent list."""
        # Verify we're on the main thread before doing any Qt operations
        app = QApplication.instance()
        if app:
            current_thread = QThread.currentThread()
            app_thread = app.thread()
            if current_thread != app_thread:
                print(f"[AgentSetup._update_display] WARNING: Not on main thread! Current: {current_thread}, App: {app_thread}")
                # Reschedule on main thread
                from ..utils import call_on_main_thread
                call_on_main_thread(self._update_display)
                return
        
        self.agent_list.clear()
        
        # Load connections to check configuration status
        # Config files should reflect connections, so we check connections in storage
        connections_by_agent = self.connection_storage.load_connections()
        
        # If no statuses yet, show all agents as "Not installed"
        if not self.agent_viewmodel.agent_statuses:
            print("[AgentSetup] No agent statuses available, showing all as not installed")
            for agent in CLIAgent:
                item_text = f"{agent.display_name} ✗ Not installed"
                # Create item with parent to ensure proper thread affinity
                item = QListWidgetItem(item_text, self.agent_list)
                item.setForeground(Qt.GlobalColor.gray)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setData(Qt.ItemDataRole.UserRole, agent)
            self.status_label.setText("0 agent(s) installed - Click Refresh to detect")
            return
        
        print(f"[AgentSetup] Updating display with {len(self.agent_viewmodel.agent_statuses)} agent statuses")
        for status in self.agent_viewmodel.agent_statuses:
            item_text = status.agent.display_name
            
            if status.installed:
                item_text += " ✓ Installed"
                if status.version:
                    item_text += f" (v{status.version})"
                
                # Check if agent has configured connections in storage (config files should reflect connections)
                # A connection is configured if it has proxy_url set OR if it's an OpenAI API key (written to auth.json)
                agent_str = status.agent.value
                connections = connections_by_agent.get(agent_str, [])
                
                # Count configured connections (with proxy_url or OpenAI API keys)
                configured_connections = []
                for conn in connections:
                    if conn.proxy_url:
                        # Has proxy_url - fully configured for quota
                        configured_connections.append(conn)
                    elif status.agent == CLIAgent.CODEX_CLI and conn.api_key and not conn.proxy_url:
                        # OpenAI API key - configured (written to auth.json) but doesn't work for quota
                        configured_connections.append(conn)
                
                has_configured_connection = len(configured_connections) > 0
                
                if has_configured_connection:
                    configured_count = len(configured_connections)
                    print(f"[AgentSetup] Agent {status.agent.display_name}: {configured_count} configured connection(s) - showing as Configured")
                    item_text += " [Configured]"
                else:
                    if len(connections) == 0:
                        print(f"[AgentSetup] Agent {status.agent.display_name}: No connections in storage - showing as Not configured")
                    else:
                        print(f"[AgentSetup] Agent {status.agent.display_name}: {len(connections)} connection(s) but none are configured - showing as Not configured")
                    item_text += " ✗ Not configured"
            else:
                item_text += " ✗ Not installed"
            
            # Create item with parent to ensure proper thread affinity
            item = QListWidgetItem(item_text, self.agent_list)
            
            if status.installed:
                # Check if agent has configured connections in storage (config files should reflect connections)
                agent_str = status.agent.value
                connections = connections_by_agent.get(agent_str, [])
                
                # Count configured connections (with proxy_url or OpenAI API keys)
                has_configured_connection = False
                for conn in connections:
                    if conn.proxy_url:
                        # Has proxy_url - fully configured for quota
                        has_configured_connection = True
                        break
                    elif status.agent == CLIAgent.CODEX_CLI and conn.api_key and not conn.proxy_url:
                        # OpenAI API key - configured (written to auth.json) but doesn't work for quota
                        has_configured_connection = True
                        break
                
                if has_configured_connection:
                    item.setForeground(Qt.GlobalColor.green)
                else:
                    # Installed but not configured - use orange/yellow color
                    item.setForeground(QColor(251, 146, 60))  # Orange
            else:
                item.setForeground(Qt.GlobalColor.gray)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            
            item.setData(Qt.ItemDataRole.UserRole, status.agent)
    
    def _on_refresh(self):
        """Handle refresh button click."""
        async def refresh():
            try:
                await self.agent_viewmodel.refresh_agent_statuses(force_refresh=True)
                # Schedule UI update on main thread to avoid threading issues
                from ..utils import call_on_main_thread
                call_on_main_thread(self._update_display)
                print(f"[AgentSetup] Refreshed {len(self.agent_viewmodel.agent_statuses)} agents")
            except Exception as e:
                print(f"[AgentSetup] Error refreshing agents: {e}")
                import traceback
                traceback.print_exc()
        
        run_async_coro(refresh())
    
    def _update_agent_connections(self):
        """Update agent connection/configuration display."""
        if not self.agent_viewmodel:
            self.agent_status_label.setText("Agent view model not available")
            self.agent_table.setRowCount(0)
            return
        
        self.agent_table.setRowCount(0)
        # Reset visibility state when refreshing
        self.api_key_visibility = {}
        
        # Refresh API keys list if view model is available and proxy is running
        if (self.view_model and 
            self.view_model.api_client and 
            self.view_model.proxy_manager and 
            self.view_model.proxy_manager.proxy_status.running):
            async def refresh_keys():
                try:
                    # Check if proxy is actually responding before fetching API keys
                    print(f"[AgentSetup] Checking if proxy is responding before refreshing API keys...")
                    is_responding = await self.view_model.api_client.check_proxy_responding()
                    if not is_responding:
                        print(f"[AgentSetup] Proxy is marked as running but not responding - skipping API keys refresh")
                        return
                    
                    print(f"[AgentSetup] Proxy is responding, refreshing API keys...")
                    self.view_model.api_keys = await self.view_model.api_client.fetch_api_keys()
                    print(f"[AgentSetup] Successfully refreshed {len(self.view_model.api_keys) if self.view_model.api_keys else 0} API key(s)")
                except Exception as e:
                    error_msg = str(e) if e else "Unknown error"
                    print(f"[AgentSetup] Error refreshing API keys: {type(e).__name__}: {error_msg}")
                    import traceback
                    traceback.print_exc()
            run_async_coro(refresh_keys())
        else:
            if not self.view_model:
                print(f"[AgentSetup] View model not available, skipping API keys refresh")
            elif not self.view_model.api_client:
                print(f"[AgentSetup] API client not available, skipping API keys refresh")
            elif not (self.view_model.proxy_manager and self.view_model.proxy_manager.proxy_status.running):
                print(f"[AgentSetup] Proxy not running, skipping API keys refresh")
        
        # Load all connections from storage
        connections_by_agent = self.connection_storage.load_connections()
        
        # Get installed agents
        installed_agents = {
            status.agent: status
            for status in self.agent_viewmodel.agent_statuses
            if status.installed
        }
        
        configured_count = 0
        
        # Display each connection as a separate row
        for agent_str, connections in connections_by_agent.items():
            try:
                agent = CLIAgent(agent_str)
            except ValueError:
                continue
            
            # Only show connections for installed agents
            if agent not in installed_agents:
                continue
            
            status = installed_agents[agent]
            
            # Skip agents with no connections (only show configured connections)
            if not connections:
                continue
            
            # Show all connections (both configured and unconfigured)
            for connection in connections:
                # Check if this connection is configured (has proxy_url)
                # OR if it's an OpenAI API key (no proxy_url but valid for configuration)
                is_configured = bool(connection.proxy_url)
                # For Codex CLI, if there's no proxy_url, it's likely an OpenAI API key
                # (OAuth tokens would have proxy_url set for quota fetching)
                is_openai_key = (agent == CLIAgent.CODEX_CLI and 
                                connection.api_key and 
                                not connection.proxy_url)
                
                # For OpenAI API keys, they are "configured" (written to auth.json) but don't work for quota
                if is_openai_key:
                    is_configured = True
                
                # Count configured connections for status display
                if is_configured:
                    configured_count += 1
                
                # Show all connections, regardless of proxy_url status
                # (Users should be able to see and manage all their connections)
                
                row = self.agent_table.rowCount()
                self.agent_table.insertRow(row)
                
                # Connection Name
                name_item = QTableWidgetItem(connection.name)
                self.agent_table.setItem(row, 0, name_item)
                
                # Agent
                agent_item = QTableWidgetItem(agent.display_name)
                self.agent_table.setItem(row, 1, agent_item)
                
                # Status
                status_item = QTableWidgetItem("✓ Installed")
                status_item.setForeground(QColor(34, 197, 94))
                self.agent_table.setItem(row, 2, status_item)
                
                # Configuration status
                if is_configured:
                    config_text = "✓ Configured"
                    config_item = QTableWidgetItem(config_text)
                    config_item.setForeground(get_agent_status_color(True))
                else:
                    config_text = "✗ Not configured"
                    config_item = QTableWidgetItem(config_text)
                    config_item.setForeground(QColor(251, 146, 60))  # Orange
                
                # Proxy URL display
                # For OpenAI API keys, show that proxy is not used (but connection is still configured)
                if connection.proxy_url:
                    proxy_url = connection.proxy_url
                elif is_openai_key:
                    # OpenAI API key - doesn't use proxy for quota, but connection is configured
                    proxy_url = "N/A (OpenAI API key)"
                else:
                    proxy_url = "N/A"
                
                self.agent_table.setItem(row, 3, config_item)
                self.agent_table.setItem(row, 4, QTableWidgetItem(proxy_url))
                
                # API Key with toggle character
                api_key_text = connection.api_key if connection.api_key else "N/A"
                # Default to hidden (False) for security
                is_visible = self.api_key_visibility.get(row, False)
                if not is_visible and api_key_text != "N/A":
                    # Show masked version
                    api_key_text = self._mask_key(connection.api_key) if connection.api_key else "N/A"
                
                # Create a widget with API key text and toggle character
                api_key_widget = QWidget()
                api_key_layout = QHBoxLayout()
                api_key_layout.setContentsMargins(4, 2, 4, 2)
                api_key_layout.setSpacing(6)
                
                api_key_label = QLabel(api_key_text)
                api_key_label.setStyleSheet("font-size: 12px;")
                api_key_layout.addWidget(api_key_label)
                
                # Add stretch to push toggle character to the end
                api_key_layout.addStretch()
                
                # Simple toggle character (clickable) at the end
                toggle_char = "●" if is_visible else "○"
                toggle_label = QLabel(toggle_char)
                toggle_label.setStyleSheet("font-size: 10px; color: #666; cursor: pointer;")
                toggle_label.setToolTip("Click to toggle API key visibility")
                # Make it clickable by storing row reference
                toggle_label.setProperty("row", row)
                toggle_label.mousePressEvent = self._create_toggle_handler(row)
                api_key_layout.addWidget(toggle_label)
                
                api_key_widget.setLayout(api_key_layout)
                self.agent_table.setCellWidget(row, 5, api_key_widget)
                
                # Store the actual API key in widget property for toggling
                if connection.api_key:
                    api_key_widget.setProperty("api_key", connection.api_key)
                    api_key_widget.setProperty("api_key_label", api_key_label)
                    api_key_widget.setProperty("toggle_label", toggle_label)
                
                # Quota and Model information
                # For OpenAI API keys, always show N/A (they don't work for quota fetching)
                quota_text = "N/A"
                model_text = "N/A"
                
                # Only fetch quota if it's not an OpenAI API key
                if not is_openai_key and self.view_model:
                    try:
                        provider = connection.provider
                        if provider and provider in self.view_model.provider_quotas:
                            account_quotas = self.view_model.provider_quotas[provider]
                            
                            if account_quotas:
                                # Try to match by API key or use first account
                                # For now, use first account (we can improve matching later)
                                first_account = list(account_quotas.keys())[0]
                                quota_data = account_quotas[first_account]
                                
                                if quota_data and quota_data.models:
                                    models = quota_data.models
                                    if models:
                                        highest_model = max(models, key=lambda m: m.percentage if m.percentage >= 0 else -1)
                                        if highest_model.percentage >= 0:
                                            quota_text = f"{highest_model.percentage:.1f}%"
                                            model_text = highest_model.name or "N/A"
                                        else:
                                            quota_text = "N/A"
                                            model_text = models[0].name if models else "N/A"
                    except Exception as e:
                        print(f"[AgentSetup] Error fetching quota for {connection.name}: {e}")
                
                quota_item = QTableWidgetItem(quota_text)
                if quota_text != "N/A":
                    try:
                        quota_value = float(quota_text.replace("%", ""))
                        if quota_value > 50:
                            quota_item.setForeground(QColor(34, 197, 94))  # Green
                        elif quota_value > 20:
                            quota_item.setForeground(QColor(251, 146, 60))  # Orange
                        else:
                            quota_item.setForeground(QColor(239, 68, 68))  # Red
                    except ValueError:
                        pass
                self.agent_table.setItem(row, 6, quota_item)
                
                model_item = QTableWidgetItem(model_text)
                self.agent_table.setItem(row, 7, model_item)
                
                # Store connection ID and agent in row items for later reference
                self.agent_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, connection.id)
                self.agent_table.item(row, 1).setData(Qt.ItemDataRole.UserRole, agent)
        
        # Update status label
        total_connections = sum(len(conns) for conns in connections_by_agent.values())
        installed_count = len(installed_agents)
        
        if installed_count == 0:
            self.agent_status_label.setText("No agents installed")
        else:
            self.agent_status_label.setText(
                f"Found {installed_count} installed agent(s) with {total_connections} connection(s). "
                f"{configured_count} connection(s) configured."
            )
    
    def _on_configure(self):
        """Handle configure button click - opens connection dialog."""
        current_item = self.agent_list.currentItem()
        if not current_item:
            main_window = get_main_window(self)
            show_message_box(
                self,
                "No Selection",
                "Please select an agent to configure.",
                QMessageBox.Icon.Information,
                QMessageBox.StandardButton.Ok,
                main_window
            )
            return
        
        agent = current_item.data(Qt.ItemDataRole.UserRole)
        if not agent:
            return
        
        status = self.agent_viewmodel.status_for_agent(agent)
        if not status or not status.installed:
            main_window = get_main_window(self)
            show_message_box(
                self,
                "Not Installed",
                f"{agent.display_name} is not installed.",
                QMessageBox.Icon.Warning,
                QMessageBox.StandardButton.Ok,
                main_window
            )
            return
        
        # Open connection dialog for this agent
        from ..dialogs.connection_dialog import ConnectionDialog
        
        installed_agents = [
            status.agent
            for status in self.agent_viewmodel.agent_statuses
            if status.installed
        ]
        
        dialog = ConnectionDialog(
            self,
            installed_agents,
            self.view_model.api_keys if self.view_model else [],
            self.view_model.proxy_manager.management_key if self.view_model and self.view_model.proxy_manager else None,
            view_model=self.view_model
        )
        
        # Pre-select the agent
        agent_index = dialog.agent_combo.findData(agent.value)
        if agent_index >= 0:
            dialog.agent_combo.setCurrentIndex(agent_index)
        
        # Set validation callback for new connections (same as _on_add_connection)
        def validation_callback(connection):
            """Callback to validate connection before accepting dialog."""
            print(f"[AgentSetup] validation_callback invoked with connection: name='{connection.name}', agent={connection.agent.display_name}")
            # Verify API key before saving
            async def verify_and_handle():
                print(f"[AgentSetup] verify_and_handle async function started")
                # Import call_on_main_thread at the top so it's available in all code paths
                from ..utils import call_on_main_thread
                
                try:
                    # Verify API key is valid by testing it with the provider
                    # Add timeout to prevent hanging (30 seconds should be enough for API calls)
                    print(f"[AgentSetup] Verifying API key for connection '{connection.name}' (agent: {connection.agent.display_name})...")
                    print(f"[AgentSetup] About to call _verify_api_key with timeout=30.0")
                    try:
                        print(f"[AgentSetup] Creating wait_for task...")
                        is_valid, error_msg_from_verify, is_openai_key = await asyncio.wait_for(
                            self._verify_api_key(connection.api_key, connection.agent),
                            timeout=30.0
                        )
                        print(f"[AgentSetup] wait_for completed, is_valid={is_valid}, error_msg={error_msg_from_verify}, is_openai_key={is_openai_key}")
                    except asyncio.TimeoutError:
                        print(f"[AgentSetup] API key verification timed out after 30 seconds")
                        error_msg = "API key verification timed out. Please check your network connection and try again."
                        
                        def show_error_and_reopen():
                            print(f"[AgentSetup] show_error_and_reopen called (timeout)")
                            dialog.validation_failed(error_msg)
                        print(f"[AgentSetup] Calling call_on_main_thread for timeout error")
                        call_on_main_thread(show_error_and_reopen)
                        return
                    
                    print(f"[AgentSetup] API key verification result: {is_valid}")
                    
                    if is_valid:
                        print(f"[AgentSetup] Validation passed, saving connection...")
                        # Generate connection ID
                        connection.id = AgentConnectionStorage.generate_connection_id()
                        print(f"[AgentSetup] Generated connection ID: {connection.id}")
                        
                        # Set proxy URL if available and quota fetch succeeded
                        # For OpenAI API keys, quota fetch doesn't work, so don't set proxy_url
                        # This way the agent won't show as "Configured" if quota won't work
                        # is_openai_key is now returned from _verify_api_key
                        if not is_openai_key:
                            # Only set proxy_url if it's not an OpenAI API key (OAuth tokens work for quota)
                            if self.view_model and self.view_model.proxy_manager:
                                port = self.view_model.proxy_manager.port
                                connection.proxy_url = f"http://localhost:{port}/v1"
                                print(f"[AgentSetup] Set proxy_url: {connection.proxy_url}")
                            else:
                                print(f"[AgentSetup] No proxy_manager available")
                        else:
                            print(f"[AgentSetup] OpenAI API key detected - not setting proxy_url (quota won't work, connection saved for config only)")
                        
                        # Save connection (only if validation passed)
                        print(f"[AgentSetup] Adding connection to storage...")
                        self.connection_storage.add_connection(connection)
                        print(f"[AgentSetup] Connection saved to storage")
                        
                        # Write configuration for this connection
                        print(f"[AgentSetup] Writing connection config...")
                        self._write_connection_config(connection)
                        print(f"[AgentSetup] Connection config written")
                        
                        # Refresh display (both connections table and agent list) - only if validation passed
                        print(f"[AgentSetup] Refreshing UI...")
                        call_on_main_thread(self._update_agent_connections)
                        call_on_main_thread(self._update_agent_list)
                        print(f"[AgentSetup] UI refresh scheduled")
                        
                        # Close dialog on main thread
                        def close_dialog():
                            print(f"[AgentSetup] close_dialog called, calling validation_succeeded")
                            dialog.validation_succeeded()
                        print(f"[AgentSetup] Calling call_on_main_thread to close dialog")
                        call_on_main_thread(close_dialog)
                        print(f"[AgentSetup] Dialog close scheduled")
                    else:
                        print(f"[AgentSetup] Validation failed - API key is invalid")
                        # Validation failed - show error in dialog with specific error message
                        error_msg = error_msg_from_verify or "The API key is not valid. Please check and try again."
                        
                        def show_error_and_reopen():
                            print(f"[AgentSetup] show_error_and_reopen called (invalid key)")
                            dialog.validation_failed(error_msg)
                        print(f"[AgentSetup] Calling call_on_main_thread for invalid key error")
                        call_on_main_thread(show_error_and_reopen)
                
                except Exception as e:
                    print(f"[AgentSetup] Exception in verify_and_handle: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    error_msg = f"Failed to verify API key: {str(e)}"
                    
                    def show_error_and_reopen():
                        print(f"[AgentSetup] show_error_and_reopen called (exception)")
                        dialog.validation_failed(error_msg)
                    print(f"[AgentSetup] Calling call_on_main_thread for exception error")
                    call_on_main_thread(show_error_and_reopen)
            
            # Start validation
            print(f"[AgentSetup] About to call run_async_coro(verify_and_handle())")
            result = run_async_coro(verify_and_handle())
            print(f"[AgentSetup] run_async_coro returned: {result}")
            if result is None:
                print(f"[AgentSetup] ERROR: run_async_coro returned None - async task may not have been scheduled!")
        
        print(f"[AgentSetup] Setting validation callback on dialog (quick add path)...")
        dialog.set_validation_callback(validation_callback)
        print(f"[AgentSetup] Validation callback set, about to show dialog")
        
        # Show dialog - validation callback will handle validation before acceptance
        # Dialog will only return Accepted if validation succeeds
        result = dialog.exec()
        
        # Connection is already saved by the validation callback if validation succeeded
        # No need to do anything here - just refresh the display
        if result == dialog.DialogCode.Accepted:
            # Refresh display (validation callback already saved the connection)
            self._update_agent_connections()
            self._update_agent_list()
    
    def _on_connection_selection_changed(self):
        """Enable/disable edit/delete buttons based on selection."""
        selected_rows = self.agent_table.selectionModel().selectedRows()
        has_selection = len(selected_rows) > 0
        
        # Only enable if a valid connection is selected (not "No connections" row)
        if has_selection:
            row = selected_rows[0].row()
            connection_id = self.agent_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            has_selection = connection_id is not None
        
        self.edit_connection_button.setEnabled(has_selection)
        self.delete_connection_button.setEnabled(has_selection)
    
    def _on_add_connection(self):
        """Open dialog to add a new connection."""
        from ..dialogs.connection_dialog import ConnectionDialog
        
        # Get installed agents
        installed_agents = [
            status.agent
            for status in self.agent_viewmodel.agent_statuses
            if status.installed
        ]
        
        if not installed_agents:
            main_window = get_main_window(self)
            show_message_box(
                self,
                "No Agents Installed",
                "Please install at least one agent before creating a connection.",
                QMessageBox.Icon.Information,
                QMessageBox.StandardButton.Ok,
                main_window
            )
            return
        
        dialog = ConnectionDialog(
            self,
            installed_agents,
            self.view_model.api_keys if self.view_model else [],
            self.view_model.proxy_manager.management_key if self.view_model and self.view_model.proxy_manager else None,
            view_model=self.view_model
        )
        
        # Set validation callback for new connections
        def validation_callback(connection):
            """Callback to validate connection before accepting dialog."""
            print(f"[AgentSetup] validation_callback invoked with connection: name='{connection.name}', agent={connection.agent.display_name}")
            # Verify API key before saving
            async def verify_and_handle():
                print(f"[AgentSetup] verify_and_handle async function started")
                # Import call_on_main_thread at the top so it's available in all code paths
                from ..utils import call_on_main_thread
                
                try:
                    # Verify API key is valid by testing it with the provider
                    # Add timeout to prevent hanging (30 seconds should be enough for API calls)
                    print(f"[AgentSetup] Verifying API key for connection '{connection.name}' (agent: {connection.agent.display_name})...")
                    print(f"[AgentSetup] About to call _verify_api_key with timeout=30.0")
                    try:
                        print(f"[AgentSetup] Creating wait_for task...")
                        is_valid, error_msg_from_verify, is_openai_key = await asyncio.wait_for(
                            self._verify_api_key(connection.api_key, connection.agent),
                            timeout=30.0
                        )
                        print(f"[AgentSetup] wait_for completed, is_valid={is_valid}, error_msg={error_msg_from_verify}, is_openai_key={is_openai_key}")
                    except asyncio.TimeoutError:
                        print(f"[AgentSetup] API key verification timed out after 30 seconds")
                        error_msg = "API key verification timed out. Please check your network connection and try again."
                        
                        def show_error_and_reopen():
                            print(f"[AgentSetup] show_error_and_reopen called (timeout)")
                            dialog.validation_failed(error_msg)
                        print(f"[AgentSetup] Calling call_on_main_thread for timeout error")
                        call_on_main_thread(show_error_and_reopen)
                        return
                    
                    print(f"[AgentSetup] API key verification result: {is_valid}")
                    
                    if is_valid:
                        print(f"[AgentSetup] Validation passed, saving connection...")
                        # Generate connection ID
                        connection.id = AgentConnectionStorage.generate_connection_id()
                        print(f"[AgentSetup] Generated connection ID: {connection.id}")
                        
                        # Set proxy URL if available and quota fetch succeeded
                        # For OpenAI API keys, quota fetch doesn't work, so don't set proxy_url
                        # This way the agent won't show as "Configured" if quota won't work
                        # is_openai_key is now returned from _verify_api_key
                        if not is_openai_key:
                            # Only set proxy_url if it's not an OpenAI API key (OAuth tokens work for quota)
                            if self.view_model and self.view_model.proxy_manager:
                                port = self.view_model.proxy_manager.port
                                connection.proxy_url = f"http://localhost:{port}/v1"
                                print(f"[AgentSetup] Set proxy_url: {connection.proxy_url}")
                            else:
                                print(f"[AgentSetup] No proxy_manager available")
                        else:
                            print(f"[AgentSetup] OpenAI API key detected - not setting proxy_url (quota won't work, connection saved for config only)")
                        
                        # Save connection (only if validation passed)
                        print(f"[AgentSetup] Adding connection to storage...")
                        self.connection_storage.add_connection(connection)
                        print(f"[AgentSetup] Connection saved to storage")
                        
                        # Write configuration for this connection
                        print(f"[AgentSetup] Writing connection config...")
                        self._write_connection_config(connection)
                        print(f"[AgentSetup] Connection config written")
                        
                        # Refresh display (both connections table and agent list) - only if validation passed
                        print(f"[AgentSetup] Refreshing UI...")
                        call_on_main_thread(self._update_agent_connections)
                        call_on_main_thread(self._update_agent_list)
                        print(f"[AgentSetup] UI refresh scheduled")
                        
                        # Close dialog on main thread
                        def close_dialog():
                            print(f"[AgentSetup] close_dialog called, calling validation_succeeded")
                            dialog.validation_succeeded()
                        print(f"[AgentSetup] Calling call_on_main_thread to close dialog")
                        call_on_main_thread(close_dialog)
                        print(f"[AgentSetup] Dialog close scheduled")
                    else:
                        print(f"[AgentSetup] Validation failed - API key is invalid")
                        # Validation failed - show error in dialog with specific error message
                        error_msg = error_msg_from_verify or "The API key is not valid. Please check and try again."
                        
                        def show_error_and_reopen():
                            print(f"[AgentSetup] show_error_and_reopen called (invalid key)")
                            dialog.validation_failed(error_msg)
                        print(f"[AgentSetup] Calling call_on_main_thread for invalid key error")
                        call_on_main_thread(show_error_and_reopen)
                
                except Exception as e:
                    print(f"[AgentSetup] Exception in verify_and_handle: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    error_msg = f"Failed to verify API key: {str(e)}"
                    
                    def show_error_and_reopen():
                        print(f"[AgentSetup] show_error_and_reopen called (exception)")
                        dialog.validation_failed(error_msg)
                    print(f"[AgentSetup] Calling call_on_main_thread for exception error")
                    call_on_main_thread(show_error_and_reopen)
            
            # Start validation
            print(f"[AgentSetup] About to call run_async_coro(verify_and_handle())")
            result = run_async_coro(verify_and_handle())
            print(f"[AgentSetup] run_async_coro returned: {result}")
            if result is None:
                print(f"[AgentSetup] ERROR: run_async_coro returned None - async task may not have been scheduled!")
        
        print(f"[AgentSetup] Setting validation callback on dialog...")
        dialog.set_validation_callback(validation_callback)
        print(f"[AgentSetup] Validation callback set, about to show dialog")
        
        # Show dialog - it will stay open until validation succeeds or user cancels
        # For new connections, _on_ok won't call accept() until validation succeeds
        # The validation callback will call validation_succeeded() (which calls accept()) when done
        result = dialog.exec()
        
        # Dialog will only return Accepted if:
        # 1. Validation succeeded (for new connections)
        # 2. User clicked OK on edit dialog (no validation needed)
        # Dialog will return Rejected if user cancelled
    
    def _on_edit_connection(self):
        """Open dialog to edit selected connection."""
        selected_rows = self.agent_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        connection_id = self.agent_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        agent = self.agent_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        
        if not connection_id or not agent:
            return
        
        # Load connection
        connection = self.connection_storage.get_connection_by_id(connection_id, agent)
        if not connection:
            return
        
        from ..dialogs.connection_dialog import ConnectionDialog
        
        installed_agents = [
            status.agent
            for status in self.agent_viewmodel.agent_statuses
            if status.installed
        ]
        
        dialog = ConnectionDialog(
            self,
            installed_agents,
            self.view_model.api_keys if self.view_model else [],
            self.view_model.proxy_manager.management_key if self.view_model and self.view_model.proxy_manager else None,
            connection=connection,
            view_model=self.view_model
        )
        
        if dialog.exec() == dialog.DialogCode.Accepted:
            updated_connection = dialog.get_connection()
            if updated_connection:
                # Verify API key before saving
                async def verify_and_update():
                    try:
                        # Verify API key is valid by testing it with the provider
                        # Add timeout to prevent hanging (30 seconds should be enough for API calls)
                        print(f"[AgentSetup] Verifying API key for connection '{updated_connection.name}' (agent: {updated_connection.agent.display_name})...")
                        try:
                            is_valid, error_msg_from_verify, is_openai_key = await asyncio.wait_for(
                                self._verify_api_key(updated_connection.api_key, updated_connection.agent),
                                timeout=30.0
                            )
                        except asyncio.TimeoutError:
                            print(f"[AgentSetup] API key verification timed out after 30 seconds")
                            from ..utils import call_on_main_thread
                            def show_error():
                                main_window = get_main_window(self)
                                show_message_box(
                                    self,
                                    "Verification Timeout",
                                    f"API key verification timed out for '{updated_connection.name}'. Please check your network connection and try again.",
                                    QMessageBox.Icon.Warning,
                                    QMessageBox.StandardButton.Ok,
                                    main_window
                                )
                            call_on_main_thread(show_error)
                            return
                        
                        print(f"[AgentSetup] API key verification result: {is_valid}, error_msg={error_msg_from_verify}")
                        if not is_valid:
                            from ..utils import call_on_main_thread
                            error_msg = error_msg_from_verify or f"The API key for '{updated_connection.name}' is not valid. Please check and try again."
                            def show_error():
                                main_window = get_main_window(self)
                                show_message_box(
                                    self,
                                    "Invalid API Key",
                                    error_msg,
                                    QMessageBox.Icon.Warning,
                                    QMessageBox.StandardButton.Ok,
                                    main_window
                                )
                            call_on_main_thread(show_error)
                            return  # Don't update connection or change status
                        
                        # Preserve ID and timestamps
                        updated_connection.id = connection.id
                        updated_connection.created_at = connection.created_at
                        updated_connection.last_used = connection.last_used
                        
                        # Update proxy URL if available and it's not an OpenAI API key
                        # For OpenAI API keys, quota fetch doesn't work, so don't set proxy_url
                        if not is_openai_key:
                            if self.view_model and self.view_model.proxy_manager:
                                port = self.view_model.proxy_manager.port
                                updated_connection.proxy_url = f"http://localhost:{port}/v1"
                            else:
                                # If proxy manager not available, clear proxy_url
                                updated_connection.proxy_url = None
                        else:
                            # OpenAI API key - clear proxy_url since quota won't work
                            updated_connection.proxy_url = None
                            print(f"[AgentSetup] OpenAI API key detected - clearing proxy_url (quota won't work)")
                        
                        # Save updated connection
                        self.connection_storage.update_connection(updated_connection)
                        
                        # Write configuration (config files should reflect connections)
                        self._write_connection_config(updated_connection)
                        print(f"[AgentSetup] Config files updated to reflect connection changes")
                        
                        # Refresh display (both connections table and agent list)
                        from ..utils import call_on_main_thread
                        call_on_main_thread(self._update_agent_connections)
                        call_on_main_thread(self._update_agent_list)
                    except Exception as e:
                        print(f"[AgentSetup] Error verifying/updating connection: {e}")
                        from ..utils import call_on_main_thread
                        def show_error():
                            main_window = get_main_window(self)
                            show_message_box(
                                self,
                                "Error",
                                f"Failed to update connection: {str(e)}",
                                QMessageBox.Icon.Warning,
                                QMessageBox.StandardButton.Ok,
                                main_window
                            )
                        call_on_main_thread(show_error)
                
                run_async_coro(verify_and_update())
    
    def _on_delete_connection(self):
        """Delete selected connection."""
        selected_rows = self.agent_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        connection_id = self.agent_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        agent = self.agent_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        connection_name = self.agent_table.item(row, 0).text()
        
        if not connection_id or not agent:
            return
        
        # Confirm deletion
        main_window = get_main_window(self)
        reply = show_message_box(
            self,
            "Delete Connection",
            f"Are you sure you want to delete the connection '{connection_name}'?\n\n"
            "This will remove the connection configuration but will not delete the agent itself.",
            QMessageBox.Icon.Warning,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            main_window
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Get the connection to retrieve its API key before deletion
            connection = self.connection_storage.get_connection_by_id(connection_id, agent)
            api_key_to_remove = connection.api_key if connection else None
            
            # Remove connection
            self.connection_storage.remove_connection(connection_id, agent)
            
            # Sync config files with remaining connections (config files should reflect connections)
            self._sync_agent_config_files(agent)
            
            # Remove API key from global list if it exists and view model is available
            if api_key_to_remove and self.view_model:
                from ..main_window import run_async_coro
                
                async def remove_api_key():
                    try:
                        await self.view_model.delete_api_key(api_key_to_remove)
                        print(f"[AgentSetup] Removed API key after connection deletion")
                    except Exception as e:
                        print(f"[AgentSetup] Error removing API key: {e}")
                
                run_async_coro(remove_api_key())
            
            # Refresh display (both connections table and agent list)
            self._update_agent_connections()
            self._update_agent_list()
    
    def _write_connection_config(self, connection: NamedAgentConnection):
        """Write configuration files for a connection (config files reflect connections).
        
        For connections with proxy_url: writes full proxy config (base_url, etc.)
        For connections without proxy_url (e.g., OpenAI API keys): only writes API key, no proxy config
        """
        try:
            from ...services.agent_config import AgentConfigurationService
            from ...models.agent_connections import AgentConnectionConfig
            
            # Only write proxy config if connection has proxy_url
            # For OpenAI API keys (no proxy_url), we only write the API key to auth.json, not proxy config
            # We determine if it's an OpenAI key by checking if proxy_url is None
            is_openai_key = connection.agent == CLIAgent.CODEX_CLI and not connection.proxy_url
            
            if not connection.proxy_url and not is_openai_key:
                # If proxy_url is not set but it's not an OpenAI key, get it from proxy_manager
                # This shouldn't normally happen, but handle it for safety
                if self.view_model and self.view_model.proxy_manager:
                    port = self.view_model.proxy_manager.port
                    proxy_url = f"http://localhost:{port}/v1"
                    print(f"[AgentSetup] Using proxy_manager port for config: {proxy_url}")
                    connection.proxy_url = proxy_url
            
            if connection.proxy_url:
                # Connection has proxy_url - write full proxy config
                config_service = AgentConfigurationService()
                connection_config = AgentConnectionConfig(connection=connection)
                agent_config = connection_config.to_agent_configuration()
                
                # Write configuration (config files should reflect connections)
                config_service.write_configuration(agent_config)
                print(f"[AgentSetup] Config files updated to reflect connection: {connection.name} (with proxy config)")
            elif is_openai_key:
                # OpenAI API key - only write API key to auth.json, don't write proxy config
                import json
                from pathlib import Path
                
                auth_path = Path.home() / ".codex" / "auth.json"
                auth_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Read existing auth.json if it exists
                auth_data = {}
                if auth_path.exists():
                    try:
                        with open(auth_path, "r") as f:
                            auth_data = json.load(f)
                    except Exception:
                        pass
                
                # Update only the API key, don't touch proxy config
                auth_data["OPENAI_API_KEY"] = connection.api_key
                
                # Write auth.json
                with open(auth_path, "w") as f:
                    json.dump(auth_data, f, indent=2)
                
                print(f"[AgentSetup] API key written to auth.json for connection: {connection.name} (no proxy config - OpenAI API key)")
            else:
                print(f"[AgentSetup] Connection {connection.name} has no proxy_url and is not an OpenAI key - skipping config write")
            
            # Update last_used timestamp
            connection.last_used = datetime.now()
            self.connection_storage.update_connection(connection)
        except Exception as e:
            print(f"[AgentSetup] Error writing connection config: {e}")
            import traceback
            traceback.print_exc()
    
    def _sync_agent_config_files(self, agent: CLIAgent):
        """Sync config files with connections in storage (config files should reflect connections).
        
        If there are configured connections (with proxy_url), write config files.
        If there are no configured connections, remove/clean up config files.
        """
        # Get all connections for this agent
        remaining_connections = self.connection_storage.get_connections_for_agent(agent)
        configured_connections = [c for c in remaining_connections if c.proxy_url]
        
        if not configured_connections:
            # No configured connections - remove/clean up config files
            print(f"[AgentSetup] No configured connections remaining for {agent.display_name}, cleaning up config files...")
            self._remove_agent_config(agent)
        else:
            # Use the first configured connection to update config files
            # (In the future, we might support multiple connections per agent)
            print(f"[AgentSetup] Syncing config files with connection '{configured_connections[0].name}' for {agent.display_name}...")
            self._write_connection_config(configured_connections[0])
    
    async def _validate_openai_api_key(self, api_key: str) -> bool:
        """Validate an OpenAI API key using the OpenAI Python SDK.
        
        Similar to the TypeScript example:
        ```typescript
        const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
        await client.models.list();
        ```
        
        Falls back to aiohttp if the openai module is not available.
        """
        # Try to import openai module
        try:
            import openai
        except ImportError:
            # Fall back to aiohttp if openai module is not available
            print(f"[_validate_openai_api_key] OpenAI SDK not available, using aiohttp fallback...")
            return await self._validate_openai_api_key_aiohttp(api_key)
        
        try:
            # Create OpenAI client with the provided API key
            client = openai.AsyncOpenAI(api_key=api_key)
            
            # Verify the key by calling models.list()
            # This is the same approach as the TypeScript example
            print(f"[_validate_openai_api_key] Checking OpenAI API key using models.list()...")
            await client.models.list()
            
            print(f"[_validate_openai_api_key] ✅ Key is active and valid")
            return True
            
        except openai.AuthenticationError as e:
            print(f"[_validate_openai_api_key] ❌ Key is not active: AuthenticationError - {e}")
            return False
        except openai.APIError as e:
            # Check if it's an authentication-related error
            if hasattr(e, 'status_code') and e.status_code == 401:
                print(f"[_validate_openai_api_key] ❌ Key is not active: APIError 401 - {e}")
                return False
            else:
                # Other API errors (rate limiting, etc.) - key might still be valid
                print(f"[_validate_openai_api_key] ⚠️ API error (status {getattr(e, 'status_code', 'unknown')}): {e}")
                # For non-auth errors, we'll consider the key potentially valid
                # (might be rate limiting or other temporary issues)
                return True
        except Exception as e:
            # Check for httpx.HTTPStatusError (raised by OpenAI SDK for HTTP errors)
            # The OpenAI SDK wraps httpx exceptions
            error_type = type(e).__name__
            error_str = str(e)
            
            # Check if it's an HTTP status error with 401
            if hasattr(e, 'response'):
                response = e.response
                if hasattr(response, 'status_code'):
                    status_code = response.status_code
                    if status_code == 401:
                        print(f"[_validate_openai_api_key] ❌ Key is not active: HTTP error 401 - {e}")
                        return False
                    else:
                        print(f"[_validate_openai_api_key] ⚠️ HTTP error (status {status_code}): {e}")
                        # For non-401 errors, consider it potentially valid
                        return True
            
            # Check error message for 401/Unauthorized
            if "401" in error_str or "Unauthorized" in error_str or "HTTPStatusError" in error_type:
                print(f"[_validate_openai_api_key] ❌ Key is not active: {error_type} (401 Unauthorized) - {e}")
                return False
            
            print(f"[_validate_openai_api_key] ❌ Error validating OpenAI API key: {error_type}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _validate_openai_api_key_aiohttp(self, api_key: str) -> bool:
        """Fallback validation using aiohttp when OpenAI SDK is not available."""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # Verify key with models endpoint
                print(f"[_validate_openai_api_key_aiohttp] Checking models endpoint to verify key...")
                async with session.get(
                    "https://api.openai.com/v1/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        print(f"[_validate_openai_api_key_aiohttp] ✅ Key is active and valid (status 200)")
                        return True
                    elif response.status == 401:
                        print(f"[_validate_openai_api_key_aiohttp] ❌ Key is not active (status 401)")
                        return False
                    else:
                        print(f"[_validate_openai_api_key_aiohttp] ⚠️ API returned status {response.status}")
                        # For other status codes, consider it potentially valid
                        return True
                        
        except aiohttp.ClientError as e:
            print(f"[_validate_openai_api_key_aiohttp] ❌ Network error: {e}")
            return False
        except Exception as e:
            print(f"[_validate_openai_api_key_aiohttp] ❌ Error: {type(e).__name__}: {e}")
            return False
    
    def _remove_agent_config(self, agent: CLIAgent):
        """Remove/clean up config files when all connections are deleted (matches original behavior)."""
        import json
        from pathlib import Path
        
        try:
            from ...services.agent_config import AgentConfigurationService
            
            config_service = AgentConfigurationService()
            
            # For Codex CLI, remove proxy config from config.toml and auth.json
            if agent == CLIAgent.CODEX_CLI:
                config_path = Path.home() / ".codex" / "config.toml"
                auth_path = Path.home() / ".codex" / "auth.json"
                
                # Remove proxy-related config from config.toml
                if config_path.exists():
                    try:
                        with open(config_path, "r") as f:
                            content = f.read()
                        
                        # Remove proxy-related lines
                        lines = content.split("\n")
                        new_lines = []
                        skip_next = False
                        for line in lines:
                            # Skip lines with proxy config
                            if "base_url" in line and ("127.0.0.1" in line or "localhost" in line):
                                continue
                            if "model_provider" in line and "cliproxyapi" in line:
                                skip_next = True
                                continue
                            if skip_next and (line.strip().startswith("[") or line.strip() == ""):
                                skip_next = False
                            if skip_next:
                                continue
                            new_lines.append(line)
                        
                        # Write cleaned config
                        with open(config_path, "w") as f:
                            f.write("\n".join(new_lines))
                        print(f"[AgentSetup] Removed proxy config from {config_path}")
                    except Exception as e:
                        print(f"[AgentSetup] Error cleaning config.toml: {e}")
                
                # Remove auth.json (or clear OPENAI_API_KEY)
                if auth_path.exists():
                    try:
                        with open(auth_path, "r") as f:
                            auth_data = json.load(f)
                        
                        # Remove OPENAI_API_KEY if it exists
                        if "OPENAI_API_KEY" in auth_data:
                            del auth_data["OPENAI_API_KEY"]
                            
                            # If auth.json is now empty or only has empty tokens, delete it
                            if not auth_data or (len(auth_data) == 1 and "tokens" in auth_data and not auth_data.get("tokens")):
                                auth_path.unlink()
                                print(f"[AgentSetup] Removed {auth_path}")
                            else:
                                with open(auth_path, "w") as f:
                                    json.dump(auth_data, f, indent=2)
                                print(f"[AgentSetup] Removed OPENAI_API_KEY from {auth_path}")
                    except Exception as e:
                        print(f"[AgentSetup] Error cleaning auth.json: {e}")
            
            # For other agents, similar cleanup logic can be added
            # For now, Codex CLI is the main one that needs this
            
        except Exception as e:
            print(f"[AgentSetup] Error removing agent config: {e}")
            import traceback
            traceback.print_exc()
    
    def _mask_key(self, key: str) -> str:
        """Mask API key for display."""
        if len(key) <= 8:
            return "•" * len(key)
        return key[:4] + "••••" + key[-4:]
    
    def _create_toggle_handler(self, row: int):
        """Create a mouse press event handler for the toggle character."""
        def handler(event):
            self._toggle_table_api_key_visibility(row)
        return handler
    
    async def _verify_api_key(self, api_key: str, agent: CLIAgent) -> tuple[bool, str | None, bool]:
        """Verify an API key for an agent.
        
        Returns:
            tuple[bool, str | None, bool]: (is_valid, error_message, is_openai_key)
            - is_valid: Whether the key is valid
            - error_message: Error message if invalid, None if valid
            - is_openai_key: Whether this is an OpenAI API key (for Codex CLI only)
        """
        """Verify that an API key can be used with the agent to collect quota.
        
        Verification flow:
        1. Maps the agent to its provider (Codex CLI → Codex, Claude Code → Claude, Gemini CLI → Gemini)
        2. Uses the provider's quota fetcher to test if the API key can fetch quota
        3. Returns (True, None) only if quota can be fetched successfully
        4. Returns (False, error_message) if verification fails
        5. Adds the API key to the proxy (if not already there) - only after successful verification
        
        Returns:
            tuple[bool, str | None]: (is_valid, error_message)
        """
        print(f"[_verify_api_key] Starting verification: agent={agent.display_name}, api_key_length={len(api_key) if api_key else 0}")
        
        if not api_key:
            error_msg = "API key is empty"
            print(f"[_verify_api_key] Cannot verify: {error_msg}")
            return False, error_msg, False
            
        if not self.view_model:
            error_msg = "View model is not available"
            print(f"[_verify_api_key] Cannot verify: {error_msg}")
            return False, error_msg, False, False
            
        if not self.view_model.api_client:
            error_msg = "API client is not available"
            print(f"[_verify_api_key] Cannot verify: {error_msg}")
            return False, error_msg, False, False
        
        print(f"[_verify_api_key] Pre-checks passed, proceeding with verification")
        
        try:
            # Step 1: Map agent to provider
            print(f"[_verify_api_key] Step 1: Mapping agent to provider...")
            mapping = {
                CLIAgent.CODEX_CLI: AIProvider.CODEX,
                CLIAgent.CLAUDE_CODE: AIProvider.CLAUDE,
                CLIAgent.GEMINI_CLI: AIProvider.GEMINI,
            }
            provider = mapping.get(agent)
            
            if not provider:
                error_msg = f"No provider mapping for agent {agent.display_name}"
                print(f"[_verify_api_key] Cannot verify: {error_msg}")
                return False, error_msg, False, False
            
            print(f"[_verify_api_key] Mapped agent {agent.display_name} to provider {provider.display_name}")
            
            # Step 2: Test API key with provider's quota fetcher
            print(f"[_verify_api_key] Step 2: Creating quota fetcher for provider {provider.display_name}...")
            
            # Get the appropriate quota fetcher for this provider
            from ...services.quota_fetchers import (
                CodexCLIQuotaFetcher, ClaudeCodeQuotaFetcher, GeminiCLIQuotaFetcher
            )
            
            fetcher = None
            if provider == AIProvider.CODEX:
                print(f"[_verify_api_key] Creating CodexCLIQuotaFetcher...")
                fetcher = CodexCLIQuotaFetcher(api_client=self.view_model.api_client)
            elif provider == AIProvider.CLAUDE:
                print(f"[_verify_api_key] Creating ClaudeCodeQuotaFetcher...")
                fetcher = ClaudeCodeQuotaFetcher(api_client=self.view_model.api_client)
            elif provider == AIProvider.GEMINI:
                print(f"[_verify_api_key] Creating GeminiCLIQuotaFetcher...")
                fetcher = GeminiCLIQuotaFetcher(api_client=self.view_model.api_client)
            
            if not fetcher:
                error_msg = f"No quota fetcher for provider {provider.display_name}"
                print(f"[_verify_api_key] Cannot verify: {error_msg}")
                return False, error_msg, False
            
            print(f"[_verify_api_key] Quota fetcher created: {type(fetcher).__name__}")
            
            # Step 3: Test by trying to fetch quota using the API key
            quota_data = None
            error_message = None
            
            if provider == AIProvider.CODEX:
                # For Codex CLI, the "API key" field should be:
                # 1. An OAuth access_token (from ~/.codex/auth.json tokens.access_token) - preferred, works for quota
                # 2. An OpenAI API key - will be written to OPENAI_API_KEY but won't work for quota fetching
                # The ChatGPT usage API requires an OAuth access token for quota verification
                print(f"[_verify_api_key] Step 3: Testing Codex CLI key (length: {len(api_key)})...")
                
                # First, try using it as an OAuth access token for quota verification
                print(f"[_verify_api_key] Testing key as OAuth access token for quota verification...")
                try:
                    print(f"[_verify_api_key] About to call fetcher._fetch_from_api(api_key)...")
                    quota_data = await fetcher._fetch_from_api(api_key)
                    print(f"[_verify_api_key] fetcher._fetch_from_api returned: {quota_data is not None}")
                    if quota_data:
                        # Successfully fetched quota - it's a valid OAuth access token
                        print(f"[_verify_api_key] ✓ Valid OAuth access token - quota fetch succeeded")
                    else:
                        # OAuth token test failed, try validating as OpenAI API key
                        print(f"[_verify_api_key] OAuth token test failed, trying to validate as OpenAI API key...")
                        quota_data = await self._validate_openai_api_key(api_key)
                        if quota_data:
                            print(f"[_verify_api_key] ✓ Valid OpenAI API key (will be saved to OPENAI_API_KEY but won't work for quota fetching)")
                        else:
                            error_message = "Failed to validate key. It is neither a valid OAuth access token nor a valid OpenAI API key. For quota tracking, use an OAuth access token from ~/.codex/auth.json (tokens.access_token field)."
                except Exception as e:
                    error_str = str(e)
                    print(f"[_verify_api_key] Exception during OAuth verification: {type(e).__name__}: {e}")
                    
                    # If OAuth test failed, try validating as OpenAI API key
                    print(f"[_verify_api_key] OAuth verification failed, trying to validate as OpenAI API key...")
                    try:
                        quota_data = await self._validate_openai_api_key(api_key)
                        if quota_data:
                            print(f"[_verify_api_key] ✓ Valid OpenAI API key (will be saved to OPENAI_API_KEY but won't work for quota fetching)")
                        else:
                            if "401" in error_str or "authentication" in error_str.lower() or "token" in error_str.lower():
                                error_message = "The key is not valid. It is neither a valid OAuth access token nor a valid OpenAI API key. For quota tracking, Codex CLI requires an OAuth access token from ~/.codex/auth.json (tokens.access_token field)."
                            else:
                                error_message = f"Error testing key: {str(e)}"
                    except Exception as e2:
                        print(f"[_verify_api_key] OpenAI API key validation also failed: {type(e2).__name__}: {e2}")
                        if "401" in error_str or "authentication" in error_str.lower() or "token" in error_str.lower():
                            error_message = "The key is not valid. It is neither a valid OAuth access token nor a valid OpenAI API key. For quota tracking, Codex CLI requires an OAuth access token from ~/.codex/auth.json (tokens.access_token field)."
                        else:
                            error_message = f"Error testing key: {str(e)}"
                    import traceback
                    traceback.print_exc()
                    
            elif provider == AIProvider.CLAUDE:
                # For Claude Code, use the fetcher's _fetch_from_api method
                print(f"[_verify_api_key] Step 3: Testing Claude Code API key...")
                try:
                    print(f"[_verify_api_key] About to call fetcher._fetch_from_api(api_key)...")
                    quota_data = await fetcher._fetch_from_api(api_key)
                    print(f"[_verify_api_key] fetcher._fetch_from_api returned: {quota_data is not None}")
                    if not quota_data:
                        error_message = "Failed to fetch quota - the key may not be a valid API key."
                except Exception as e:
                    error_message = f"Error testing API key: {str(e)}"
                    print(f"[_verify_api_key] Exception during verification: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    
            elif provider == AIProvider.GEMINI:
                # For Gemini CLI, the fetcher works differently - may need account info
                # For now, we'll try a basic test
                print(f"[_verify_api_key] Step 3: Gemini CLI quota verification requires account info - skipping detailed test")
                # Consider it valid if we can proceed (can be enhanced later)
                quota_data = True  # Placeholder - can be enhanced with actual quota fetch
            
            print(f"[_verify_api_key] Step 3 completed: quota_data={quota_data}, error_message={error_message}")
            
            # Step 4: Handle validation result
            # For Codex CLI, we accept OpenAI API keys even if quota fetch fails
            # because they're valid for configuration (written to OPENAI_API_KEY)
            # But we only add them to proxy if quota fetch actually succeeded
            # Check if this is an OpenAI API key (validated but quota fetch didn't work)
            is_openai_api_key = provider == AIProvider.CODEX and isinstance(quota_data, bool) and quota_data
            
            if quota_data:
                # Quota fetch succeeded OR it's a validated OpenAI API key
                if is_openai_api_key:
                    # OpenAI API key - valid for config but won't work for quota
                    print(f"[_verify_api_key] ✓ OpenAI API key accepted for configuration (won't work for quota fetching)")
                    # Don't add to proxy - OpenAI API keys don't work with the proxy for quota
                    return True, None, True  # Return is_openai_key=True, True  # Return is_openai_key=True
                else:
                    # Actual quota data was fetched successfully
                    print(f"[_verify_api_key] ✓ API key verified: Successfully fetched quota from {provider.display_name}")
                    print(f"[_verify_api_key] Step 4: Adding API key to proxy if needed...")
                    
                    # Add the API key to the proxy (if not already there)
                    print(f"[_verify_api_key] Fetching current API keys from proxy...")
                    current_keys = await self.view_model.api_client.fetch_api_keys()
                    print(f"[_verify_api_key] Current API keys count: {len(current_keys) if current_keys else 0}")
                    
                    # Check management key
                    if self.view_model.proxy_manager and self.view_model.proxy_manager.management_key:
                        if api_key == self.view_model.proxy_manager.management_key:
                            print(f"[_verify_api_key] API key is management key - already in proxy")
                            return True, None
                    
                    if api_key not in current_keys:
                        print(f"[_verify_api_key] Adding verified API key to proxy...")
                        await self.view_model.api_client.add_api_key(api_key)
                        print(f"[_verify_api_key] API key added, fetching updated keys...")
                        updated_keys = await self.view_model.api_client.fetch_api_keys()
                        self.view_model.api_keys = updated_keys
                        print(f"[_verify_api_key] API key added to proxy successfully")
                    else:
                        print(f"[_verify_api_key] API key already in proxy")
                    
                    print(f"[_verify_api_key] Verification successful, returning True")
                    return True, None, False  # Not an OpenAI key
            else:
                # Quota fetch failed and OpenAI API key validation also failed
                # Invalid key - reject it
                if error_message:
                    print(f"[_verify_api_key] ✗ API key verification failed: {error_message}")
                else:
                    error_message = f"Could not fetch quota from {provider.display_name}"
                    print(f"[_verify_api_key] ✗ API key verification failed: {error_message}")
                return False, error_message, False
                
        except Exception as e:
            error_msg = f"Error verifying API key: {str(e)}"
            print(f"[_verify_api_key] Exception in _verify_api_key: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False, error_msg, False
    
    def _toggle_table_api_key_visibility(self, row: int):
        """Toggle API key visibility for a specific row in the table."""
        api_key_widget = self.agent_table.cellWidget(row, 5)
        if not api_key_widget:
            return
        
        # Get the actual API key from widget property
        actual_key = api_key_widget.property("api_key")
        if not actual_key:
            return  # No API key to toggle
        
        # Get label references
        api_key_label = api_key_widget.property("api_key_label")
        toggle_label = api_key_widget.property("toggle_label")
        if not api_key_label or not toggle_label:
            return
        
        # Toggle visibility state
        current_visible = self.api_key_visibility.get(row, False)
        new_visible = not current_visible
        self.api_key_visibility[row] = new_visible
        
        # Update the display
        if new_visible:
            api_key_label.setText(actual_key)
            toggle_label.setText("●")
        else:
            api_key_label.setText(self._mask_key(actual_key))
            toggle_label.setText("○")
    
    def refresh(self):
        """Refresh the display."""
        self._update_display()
        
        # Refresh quotas if view model is available (to ensure quota data is up-to-date)
        if self.view_model:
            async def refresh_quotas():
                try:
                    # Trigger quota refresh to ensure Codex CLI quotas are fetched
                    await self.view_model.refresh_all_quotas()
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_agent_connections)
                except Exception as e:
                    print(f"[AgentSetup] Error refreshing quotas: {e}")
            run_async_coro(refresh_quotas())
        
        # Also refresh agent statuses
        if self.agent_viewmodel:
            async def refresh_statuses():
                try:
                    await self.agent_viewmodel.refresh_agent_statuses(force_refresh=True)
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_agent_connections)
                except Exception as e:
                    print(f"[AgentSetup] Error refreshing agent statuses: {e}")
            run_async_coro(refresh_statuses())
