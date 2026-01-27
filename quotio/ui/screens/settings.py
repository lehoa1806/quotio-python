"""Settings screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QPushButton, QLineEdit, QComboBox,
    QHBoxLayout, QFrame, QMessageBox, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QSize
from PyQt6.QtGui import QFont, QIcon
import asyncio

from ...models.operating_mode import OperatingMode, RemoteConnectionConfig
from typing import Optional
from ..utils import show_message_box, get_main_window, call_on_main_thread


def run_async_coro(coro):
    """Run an async coroutine, creating task if loop is running."""
    # Import from main_window to use the shared thread-safe function
    from ..main_window import run_async_coro as main_run_async_coro
    return main_run_async_coro(coro)


class SettingsScreen(QWidget):
    """Settings screen."""

    def __init__(self, view_model=None, main_window=None):
        """Initialize the settings screen."""
        super().__init__()
        self.view_model = view_model
        self.main_window = main_window  # Store reference to MainWindow instance
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Title
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Operating mode - Dropdown selection with detailed descriptions
        mode_group = QGroupBox("Operating Mode")
        mode_layout = QVBoxLayout()

        # Mode selection
        mode_combo_layout = QHBoxLayout()
        mode_label = QLabel("Mode:")
        self.mode_combo = QComboBox()

        # Add modes with detailed descriptions
        for mode in OperatingMode:
            # Create detailed description for each mode
            if mode == OperatingMode.MONITOR:
                description = (
                    "Monitor Mode - Track quotas without running a proxy server.\n"
                    "• View quota usage for all connected providers\n"
                    "• No proxy server required\n"
                    "• Ideal for quota monitoring only\n"
                    "• CLI agents cannot route through proxy"
                )
            elif mode == OperatingMode.LOCAL_PROXY:
                description = (
                    "Local Proxy - Run proxy server on this machine.\n"
                    "• Start/stop local CLIProxyAPI server\n"
                    "• Route CLI agent requests through proxy\n"
                    "• Manage auth files and API keys\n"
                    "• Configure CLI agents (Codex, Claude Code, Gemini CLI, etc.)\n"
                    "• Full control over proxy settings and port"
                )
            elif mode == OperatingMode.REMOTE_PROXY:
                description = (
                    "Remote Proxy - Connect to remote CLIProxyAPI instance.\n"
                    "• Connect to proxy server on another machine\n"
                    "• Route CLI agent requests through remote proxy\n"
                    "• View quotas and manage accounts remotely\n"
                    "• Configure advanced routing and retry settings\n"
                    "• Requires remote proxy endpoint URL"
                )
            else:
                description = mode.description

            # Add item with display name and store mode + description
            self.mode_combo.addItem(mode.display_name, {"mode": mode, "description": description})

        # Set tooltip to show description when hovering
        self.mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
        self.mode_combo.currentIndexChanged.connect(self._update_mode_tooltip)

        mode_combo_layout.addWidget(mode_label)
        mode_combo_layout.addWidget(self.mode_combo)
        mode_combo_layout.addStretch()

        # Edit button for remote proxy config (only visible when remote is selected)
        self.edit_remote_config_btn = QPushButton("Edit Config...")
        self.edit_remote_config_btn.clicked.connect(self._on_edit_remote_config)
        self.edit_remote_config_btn.setVisible(False)
        mode_combo_layout.addWidget(self.edit_remote_config_btn)

        mode_layout.addLayout(mode_combo_layout)

        # Description label (shows current mode's description)
        self.mode_description_label = QLabel()
        self.mode_description_label.setWordWrap(True)
        self.mode_description_label.setStyleSheet("color: #666; font-size: 11px; padding: 8px; background-color: #f5f5f5; border-radius: 4px;")
        self.mode_description_label.setTextFormat(Qt.TextFormat.PlainText)
        mode_layout.addWidget(self.mode_description_label)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Store reference
        self.mode_group = mode_group

        # Update description on initial load
        self._update_mode_tooltip()

        # Remote proxy configuration (only show in remote mode or when switching to remote)
        self.remote_config_group = QGroupBox("Remote Proxy Configuration")
        remote_config_layout = QFormLayout()

        self.remote_url_input = QLineEdit()
        self.remote_url_input.setPlaceholderText("https://proxy.example.com:8317")
        remote_config_layout.addRow("Endpoint URL:", self.remote_url_input)

        self.remote_name_input = QLineEdit()
        self.remote_name_input.setPlaceholderText("My Remote Proxy")
        remote_config_layout.addRow("Display Name:", self.remote_name_input)

        self.remote_verify_ssl_checkbox = QCheckBox("Verify SSL")
        self.remote_verify_ssl_checkbox.setChecked(True)
        remote_config_layout.addRow("", self.remote_verify_ssl_checkbox)

        self.remote_save_button = QPushButton("Save Remote Config")
        self.remote_save_button.clicked.connect(self._on_save_remote_config)
        remote_config_layout.addRow("", self.remote_save_button)

        self.remote_config_group.setLayout(remote_config_layout)
        self.remote_config_group.setVisible(False)
        layout.addWidget(self.remote_config_group)

        # Advanced Remote Proxy Settings (only show in remote proxy mode when connected)
        self.advanced_remote_group = QGroupBox("Advanced Remote Proxy Settings")
        advanced_remote_layout = QVBoxLayout()

        # Upstream Proxy Section
        upstream_group = QGroupBox("Upstream Proxy")
        upstream_layout = QFormLayout()

        self.upstream_proxy_input = QLineEdit()
        self.upstream_proxy_input.setPlaceholderText("Optional: Upstream proxy URL (e.g., http://proxy.example.com:8080)")
        upstream_layout.addRow("Upstream Proxy URL:", self.upstream_proxy_input)

        self.upstream_proxy_save_btn = QPushButton("Save")
        self.upstream_proxy_save_btn.clicked.connect(self._on_save_upstream_proxy)
        upstream_layout.addRow("", self.upstream_proxy_save_btn)

        upstream_group.setLayout(upstream_layout)
        advanced_remote_layout.addWidget(upstream_group)

        # Routing Strategy Section
        routing_group = QGroupBox("Routing Strategy")
        routing_layout = QVBoxLayout()

        self.routing_strategy_combo = QComboBox()
        self.routing_strategy_combo.addItem("Round Robin", "round-robin")
        self.routing_strategy_combo.addItem("Fill First", "fill-first")
        self.routing_strategy_combo.currentIndexChanged.connect(self._on_routing_strategy_changed)
        routing_layout.addWidget(QLabel("Strategy:"))
        routing_layout.addWidget(self.routing_strategy_combo)
        routing_layout.addWidget(QLabel("Round Robin: Distribute requests evenly across accounts\nFill First: Use first account until quota exhausted"))

        routing_group.setLayout(routing_layout)
        advanced_remote_layout.addWidget(routing_group)

        # Quota Exceeded Behavior Section
        quota_exceeded_group = QGroupBox("Quota Exceeded Behavior")
        quota_exceeded_layout = QVBoxLayout()

        self.switch_project_checkbox = QCheckBox("Auto-switch to another account when quota is exceeded")
        self.switch_project_checkbox.stateChanged.connect(self._on_switch_project_changed)
        quota_exceeded_layout.addWidget(self.switch_project_checkbox)

        self.switch_preview_model_checkbox = QCheckBox("Auto-switch to preview model when quota is exceeded")
        self.switch_preview_model_checkbox.stateChanged.connect(self._on_switch_preview_model_changed)
        quota_exceeded_layout.addWidget(self.switch_preview_model_checkbox)

        quota_exceeded_group.setLayout(quota_exceeded_layout)
        advanced_remote_layout.addWidget(quota_exceeded_group)

        # Retry Configuration Section
        retry_group = QGroupBox("Retry Configuration")
        retry_layout = QFormLayout()

        self.max_retries_spinbox = QSpinBox()
        self.max_retries_spinbox.setRange(0, 10)
        self.max_retries_spinbox.setValue(3)
        self.max_retries_spinbox.valueChanged.connect(self._on_max_retries_changed)
        retry_layout.addRow("Max Retries:", self.max_retries_spinbox)

        self.max_retry_interval_spinbox = QSpinBox()
        self.max_retry_interval_spinbox.setRange(5, 300)
        self.max_retry_interval_spinbox.setSingleStep(5)
        self.max_retry_interval_spinbox.setValue(30)
        self.max_retry_interval_spinbox.setSuffix(" seconds")
        self.max_retry_interval_spinbox.valueChanged.connect(self._on_max_retry_interval_changed)
        retry_layout.addRow("Max Retry Interval:", self.max_retry_interval_spinbox)

        retry_group.setLayout(retry_layout)
        advanced_remote_layout.addWidget(retry_group)

        # Logging Section
        logging_group = QGroupBox("Logging")
        logging_layout = QVBoxLayout()

        self.logging_to_file_checkbox = QCheckBox("Log to file")
        self.logging_to_file_checkbox.stateChanged.connect(self._on_logging_to_file_changed)
        logging_layout.addWidget(self.logging_to_file_checkbox)

        self.request_log_checkbox = QCheckBox("Enable request logging")
        self.request_log_checkbox.stateChanged.connect(self._on_request_log_changed)
        logging_layout.addWidget(self.request_log_checkbox)

        self.debug_mode_checkbox = QCheckBox("Debug mode")
        self.debug_mode_checkbox.stateChanged.connect(self._on_debug_mode_changed)
        logging_layout.addWidget(self.debug_mode_checkbox)

        logging_group.setLayout(logging_layout)
        advanced_remote_layout.addWidget(logging_group)

        self.advanced_remote_group.setLayout(advanced_remote_layout)
        self.advanced_remote_group.setVisible(False)
        layout.addWidget(self.advanced_remote_group)

        # Proxy settings (only show in local proxy mode)
        # Matches original LocalProxyServerSection design
        proxy_group = QGroupBox("Proxy Server")
        proxy_group.setToolTip("Configure the local CLIProxyAPI server. Restart proxy after changing port.")
        proxy_layout = QFormLayout()
        proxy_layout.setSpacing(10)
        proxy_layout.setContentsMargins(12, 12, 12, 12)

        # Status - with Control button next to it
        status_label = QLabel("Status:")
        status_label.setStyleSheet("font-size: 12px; color: #333;")

        status_value_layout = QHBoxLayout()
        status_value_layout.setSpacing(6)
        status_value_layout.setContentsMargins(0, 0, 0, 0)

        # Status circle indicator
        self.proxy_status_circle = QLabel("●")
        self.proxy_status_circle.setStyleSheet("font-size: 12px; color: #999;")
        status_value_layout.addWidget(self.proxy_status_circle)

        # Status text
        self.proxy_status_label = QLabel("Stopped")
        self.proxy_status_label.setStyleSheet("font-size: 12px; color: #666;")
        status_value_layout.addWidget(self.proxy_status_label)
        # Make proxy status label copyable
        from ..utils import make_label_copyable
        make_label_copyable(self.proxy_status_label)
        status_value_layout.addStretch()

        # Control button next to status
        self.proxy_start_stop_button = QPushButton("Start Proxy")
        self.proxy_start_stop_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 4px;
                background-color: #007AFF;
                color: white;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)
        self.proxy_start_stop_button.clicked.connect(self._on_toggle_proxy)
        status_value_layout.addWidget(self.proxy_start_stop_button)

        # Auto-start checkbox next to control button
        self.auto_start_checkbox = QCheckBox("Auto-start proxy on launch")
        self.auto_start_checkbox.setToolTip("Automatically start the proxy server when the application launches")
        self.auto_start_checkbox.stateChanged.connect(self._on_auto_start_changed)
        status_value_layout.addWidget(self.auto_start_checkbox)

        proxy_layout.addRow(status_label, status_value_layout)

        # Auto-restart checkbox (only for local proxy mode)
        self.auto_restart_checkbox = QCheckBox("Auto-restart proxy when unresponsive")
        self.auto_restart_checkbox.setToolTip(
            "Automatically restart the proxy if it becomes unresponsive (connection timeouts). "
            "Only applies to local proxy mode. The proxy will be restarted after 3 consecutive timeout errors."
        )
        self.auto_restart_checkbox.stateChanged.connect(self._on_auto_restart_changed)
        proxy_layout.addRow(QLabel(""), self.auto_restart_checkbox)

        # Endpoint - with Port next to it
        endpoint_label = QLabel("Endpoint:")
        endpoint_label.setStyleSheet("font-size: 12px; color: #333;")

        endpoint_value_layout = QHBoxLayout()
        endpoint_value_layout.setSpacing(8)
        endpoint_value_layout.setContentsMargins(0, 0, 0, 0)

        self.proxy_endpoint_label = QLabel("http://localhost:8317/v1")
        self.proxy_endpoint_label.setStyleSheet("""
            font-size: 12px;
            font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
            color: #333;
            padding: 4px 8px;
            background-color: #f5f5f5;
            border-radius: 4px;
        """)
        self.proxy_endpoint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        endpoint_value_layout.addWidget(self.proxy_endpoint_label)
        endpoint_value_layout.addStretch()

        # Port next to endpoint
        port_label = QLabel("Port:")
        port_label.setStyleSheet("font-size: 12px; color: #333;")
        endpoint_value_layout.addWidget(port_label)

        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1024, 65535)
        self.port_spinbox.setValue(8317)
        self.port_spinbox.setStyleSheet("""
            QSpinBox {
                padding: 4px 8px;
                font-size: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                min-width: 100px;
            }
            QSpinBox:focus {
                border: 1px solid #007AFF;
            }
        """)
        self.port_spinbox.valueChanged.connect(self._on_port_changed)
        endpoint_value_layout.addWidget(self.port_spinbox)

        proxy_layout.addRow(endpoint_label, endpoint_value_layout)

        # API Keys subsection (only visible when proxy is running)
        api_keys_label = QLabel("API Keys:")
        api_keys_label.setStyleSheet("font-size: 12px; color: #333;")

        api_keys_container = QVBoxLayout()
        api_keys_container.setSpacing(8)
        api_keys_container.setContentsMargins(0, 0, 0, 0)

        # API Keys list
        self.api_keys_list = QListWidget()
        self.api_keys_list.setMaximumHeight(120)
        self.api_keys_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
            }
        """)
        api_keys_container.addWidget(self.api_keys_list)

        # API Keys controls
        api_keys_controls = QHBoxLayout()
        api_keys_controls.setSpacing(8)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter API key...")
        self.api_key_input.setStyleSheet("""
            QLineEdit {
                padding: 4px 8px;
                font-size: 11px;
                font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QLineEdit:focus {
                border: 1px solid #007AFF;
            }
        """)
        api_keys_controls.addWidget(self.api_key_input)

        self.generate_key_button = QPushButton("Generate")
        self.generate_key_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 4px;
            }
        """)
        self.generate_key_button.clicked.connect(self._on_generate_api_key)
        self.generate_key_button.setToolTip("Generate a random API key")
        api_keys_controls.addWidget(self.generate_key_button)

        self.add_key_button = QPushButton("Add")
        self.add_key_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 4px;
                background-color: #007AFF;
                color: white;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)
        self.add_key_button.clicked.connect(self._on_add_api_key)
        api_keys_controls.addWidget(self.add_key_button)

        api_keys_container.addLayout(api_keys_controls)

        # API Keys info label
        self.api_keys_info_label = QLabel("API keys are used for authenticating clients with the proxy server")
        self.api_keys_info_label.setStyleSheet("font-size: 10px; color: #666; font-style: italic;")
        self.api_keys_info_label.setWordWrap(False)  # Keep on single line
        self.api_keys_info_label.setTextFormat(Qt.TextFormat.PlainText)
        api_keys_container.addWidget(self.api_keys_info_label)

        proxy_layout.addRow(api_keys_label, api_keys_container)

        proxy_group.setLayout(proxy_layout)
        self.proxy_group = proxy_group
        layout.addWidget(proxy_group)

        # Tab Visibility Settings (only show in local proxy mode)
        tab_visibility_group = QGroupBox("Tab Visibility")
        tab_visibility_group.setToolTip("Control which tabs are visible in the main window. Changes take effect immediately.")
        tab_visibility_layout = QVBoxLayout()

        tab_visibility_desc = QLabel("Show or hide tabs in the main window:")
        tab_visibility_desc.setWordWrap(True)
        tab_visibility_desc.setStyleSheet("color: #666; font-size: 11px;")
        tab_visibility_layout.addWidget(tab_visibility_desc)

        self.show_logs_tab_checkbox = QCheckBox("Show Logs tab")
        self.show_logs_tab_checkbox.setChecked(True)  # Default: visible
        self.show_logs_tab_checkbox.stateChanged.connect(self._on_tab_visibility_changed)
        tab_visibility_layout.addWidget(self.show_logs_tab_checkbox)

        self.show_custom_providers_tab_checkbox = QCheckBox("Show Custom Providers tab")
        self.show_custom_providers_tab_checkbox.setChecked(True)  # Default: visible
        self.show_custom_providers_tab_checkbox.stateChanged.connect(self._on_tab_visibility_changed)
        tab_visibility_layout.addWidget(self.show_custom_providers_tab_checkbox)

        tab_visibility_group.setLayout(tab_visibility_layout)
        # Only show in local proxy mode (these tabs only exist in local proxy mode)
        self.tab_visibility_group = tab_visibility_group
        layout.addWidget(tab_visibility_group)

        # Auto-Refresh Settings
        auto_refresh_group = QGroupBox("Auto-Refresh Settings")
        auto_refresh_group.setToolTip("Configure automatic refresh interval for quota and provider data")
        auto_refresh_layout = QVBoxLayout()

        auto_refresh_desc = QLabel("Automatically refresh quota and provider data at regular intervals:")
        auto_refresh_desc.setWordWrap(True)
        auto_refresh_desc.setStyleSheet("color: #666; font-size: 11px;")
        auto_refresh_layout.addWidget(auto_refresh_desc)

        self.auto_refresh_enabled_checkbox = QCheckBox("Enable auto-refresh")
        self.auto_refresh_enabled_checkbox.setChecked(True)  # Default: enabled
        self.auto_refresh_enabled_checkbox.stateChanged.connect(self._on_auto_refresh_enabled_changed)
        auto_refresh_layout.addWidget(self.auto_refresh_enabled_checkbox)

        # Refresh interval
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Refresh interval:"))

        self.auto_refresh_interval_spinbox = QSpinBox()
        self.auto_refresh_interval_spinbox.setRange(1, 60)  # 1 to 60 minutes
        self.auto_refresh_interval_spinbox.setValue(5)  # Default: 5 minutes
        self.auto_refresh_interval_spinbox.setSuffix(" minutes")
        self.auto_refresh_interval_spinbox.valueChanged.connect(self._on_auto_refresh_interval_changed)
        interval_layout.addWidget(self.auto_refresh_interval_spinbox)
        interval_layout.addStretch()

        auto_refresh_layout.addLayout(interval_layout)
        auto_refresh_group.setLayout(auto_refresh_layout)
        self.auto_refresh_group = auto_refresh_group
        layout.addWidget(auto_refresh_group)

        # Spacer
        layout.addStretch()

        # Load current settings
        self._load_settings()

    def _show_remote_proxy_modal(self) -> Optional[RemoteConnectionConfig]:
        """Show modal dialog for remote proxy configuration."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Remote Proxy Configuration")
        dialog.setModal(True)
        dialog.resize(500, 300)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Description
        desc = QLabel("Configure connection to a remote CLIProxyAPI instance:")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Form
        form_layout = QFormLayout()

        url_input = QLineEdit()
        url_input.setPlaceholderText("https://proxy.example.com:8317")
        form_layout.addRow("Endpoint URL:", url_input)

        name_input = QLineEdit()
        name_input.setPlaceholderText("My Remote Proxy")
        form_layout.addRow("Display Name:", name_input)

        verify_ssl_checkbox = QCheckBox("Verify SSL")
        verify_ssl_checkbox.setChecked(True)
        form_layout.addRow("", verify_ssl_checkbox)

        layout.addLayout(form_layout)

        # Load existing config if available
        if self.view_model and self.view_model.mode_manager.current_mode == OperatingMode.REMOTE_PROXY:
            existing_config = self.view_model.mode_manager.remote_config
            if existing_config:
                url_input.setText(existing_config.endpoint_url or "")
                name_input.setText(existing_config.display_name or "")
                verify_ssl_checkbox.setChecked(existing_config.verify_ssl)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            endpoint_url = url_input.text().strip()
            display_name = name_input.text().strip()
            verify_ssl = verify_ssl_checkbox.isChecked()

            if not endpoint_url:
                show_message_box(
                    self,
                    "Invalid Configuration",
                    "Endpoint URL is required.",
                    QMessageBox.Icon.Warning
                )
                return None

            return RemoteConnectionConfig(
                endpoint_url=endpoint_url,
                display_name=display_name or endpoint_url,
                verify_ssl=verify_ssl
            )

        return None

    def _load_settings(self):
        """Load current settings."""
        if not self.view_model:
            return

        # Load operating mode and update card selection
        current_mode = self.view_model.mode_manager.current_mode
        self._update_mode_selection(current_mode)

        # Update UI based on mode
        self._update_mode_ui()

        # Load remote config if in remote mode
        if current_mode == OperatingMode.REMOTE_PROXY and self.view_model.mode_manager.remote_config:
            config = self.view_model.mode_manager.remote_config
            self.remote_url_input.setText(config.endpoint_url)
            self.remote_name_input.setText(config.display_name)
            self.remote_verify_ssl_checkbox.setChecked(config.verify_ssl)

        # Load port
        if self.view_model and hasattr(self.view_model, 'proxy_manager'):
            port = self.view_model.proxy_manager.port
            self.port_spinbox.setValue(port)

        # Load auto-start setting
        auto_start = self.view_model.settings.get("autoStartProxy", False)
        self.auto_start_checkbox.setChecked(auto_start)

        # Load tab visibility settings
        show_logs_tab = self.view_model.settings.get("showLogsTab", True)
        self.show_logs_tab_checkbox.setChecked(show_logs_tab)

        show_custom_providers_tab = self.view_model.settings.get("showCustomProvidersTab", True)
        self.show_custom_providers_tab_checkbox.setChecked(show_custom_providers_tab)

        # Load auto-refresh settings
        auto_refresh_enabled = self.view_model.settings.get("autoRefreshEnabled", True)
        self.auto_refresh_enabled_checkbox.setChecked(auto_refresh_enabled)

        auto_refresh_interval = self.view_model.settings.get("autoRefreshIntervalMinutes", 5)
        self.auto_refresh_interval_spinbox.setValue(auto_refresh_interval)

        # Load auto-restart proxy setting (only for local proxy mode)
        if self.view_model.mode_manager.is_local_proxy_mode:
            auto_restart_enabled = self.view_model.settings.get("autoRestartProxy", False)
            self.auto_restart_checkbox.setChecked(auto_restart_enabled)

        # Initialize API keys list
        self._refresh_api_keys_list()

    def _update_mode_selection(self, selected_mode: OperatingMode):
        """Update dropdown selection to match current mode."""
        for i in range(self.mode_combo.count()):
            item_data = self.mode_combo.itemData(i)
            if isinstance(item_data, dict) and item_data.get("mode") == selected_mode:
                self.mode_combo.setCurrentIndex(i)
                break
            elif item_data == selected_mode:  # Fallback for old format
                self.mode_combo.setCurrentIndex(i)
                break

    def _update_mode_tooltip(self):
        """Update mode description label and tooltip."""
        index = self.mode_combo.currentIndex()
        if index < 0:
            return

        item_data = self.mode_combo.itemData(index)
        if isinstance(item_data, dict):
            description = item_data.get("description", "")
            mode = item_data.get("mode")
        else:
            # Fallback for old format
            mode = item_data
            description = mode.description if hasattr(mode, 'description') else ""

        # Update description label
        self.mode_description_label.setText(description)

        # Update tooltip
        self.mode_combo.setToolTip(description)

    def _update_mode_ui(self):
        """Update UI based on current operating mode."""
        if not self.view_model:
            return

        mode = self.view_model.mode_manager.current_mode

        # Update mode description
        self._update_mode_tooltip()

        # Show/hide edit button for remote proxy
        self.edit_remote_config_btn.setVisible(mode == OperatingMode.REMOTE_PROXY)

        # Show/hide proxy settings based on mode
        if mode == OperatingMode.LOCAL_PROXY:
            self.proxy_group.setVisible(True)
            self.remote_config_group.setVisible(False)
            self.advanced_remote_group.setVisible(False)
            # Show tab visibility settings in local proxy mode
            self.tab_visibility_group.setVisible(True)
            # Update proxy control buttons
            self._update_proxy_control_buttons()
        elif mode == OperatingMode.REMOTE_PROXY:
            self.proxy_group.setVisible(False)
            self.remote_config_group.setVisible(False)  # Hide inline config, use modal instead
            # Hide tab visibility settings in remote mode (tabs don't exist)
            self.tab_visibility_group.setVisible(False)
            # Show advanced settings only if connected
            is_connected = (
                self.view_model.mode_manager.connection_status.status == "connected"
                if hasattr(self.view_model.mode_manager, 'connection_status') else False
            )
            self.advanced_remote_group.setVisible(is_connected)
            if is_connected:
                # Load advanced settings
                run_async_coro(self._load_advanced_remote_settings())
        else:  # MONITOR
            self.proxy_group.setVisible(False)
            self.remote_config_group.setVisible(False)
            self.advanced_remote_group.setVisible(False)
            # Hide tab visibility settings in monitor mode (tabs don't exist)
            self.tab_visibility_group.setVisible(False)

    def _on_mode_combo_changed(self, index: int):
        """Handle mode dropdown selection change."""
        if not self.view_model:
            return

        item_data = self.mode_combo.itemData(index)
        if isinstance(item_data, dict):
            mode = item_data.get("mode")
        else:
            mode = item_data  # Fallback for old format

        if not mode:
            return

        # Show/hide edit button for remote proxy
        self.edit_remote_config_btn.setVisible(mode == OperatingMode.REMOTE_PROXY)

        # If switching to remote and no config exists, show modal
        if mode == OperatingMode.REMOTE_PROXY and not self.view_model.mode_manager.remote_config:
            config = self._show_remote_proxy_modal()
            if not config:
                # User cancelled, revert dropdown
                self._update_mode_selection(self.view_model.mode_manager.current_mode)
                return

            # Save config and switch mode
            from ..main_window import run_async_coro
            def switch_to_remote():
                self.view_model.mode_manager.switch_to_remote(config, management_key="", from_onboarding=False)
                self._update_mode_ui()
                run_async_coro(self.view_model._initialize_remote_mode())

            call_on_main_thread(switch_to_remote)
            return

        # If switching FROM local proxy mode, confirm first
        if self.view_model.mode_manager.current_mode == OperatingMode.LOCAL_PROXY and mode != OperatingMode.LOCAL_PROXY:
            main_window = get_main_window(self)
            reply = show_message_box(
                self,
                "Switch Operating Mode",
                f"Switching to {mode.display_name} will stop the local proxy server.\n\nDo you want to continue?",
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                main_window
            )
            if reply != QMessageBox.StandardButton.Yes:
                # User cancelled, revert dropdown
                self._update_mode_selection(self.view_model.mode_manager.current_mode)
                return

        # Switch mode
        self.view_model.switch_operating_mode(mode)
        self._update_mode_ui()

        # Reinitialize if needed
        if mode == OperatingMode.REMOTE_PROXY:
            from ..main_window import run_async_coro
            run_async_coro(self.view_model._initialize_remote_mode())

    def _on_edit_remote_config(self):
        """Handle edit remote config button click."""
        if not self.view_model:
            return

        config = self._show_remote_proxy_modal()
        if config:
            # Update config and reinitialize
            from ..main_window import run_async_coro
            def update_remote():
                self.view_model.mode_manager.switch_to_remote(config, management_key="", from_onboarding=False)
                self._update_mode_ui()
                run_async_coro(self.view_model._initialize_remote_mode())

            call_on_main_thread(update_remote)

    def _on_save_remote_config(self):
        """Handle save remote config button click."""
        if not self.view_model:
            return

        url = self.remote_url_input.text().strip()
        name = self.remote_name_input.text().strip()

        if not url or not name:
            show_message_box(
                self,
                "Invalid Configuration",
                "Please provide both endpoint URL and display name.",
                QMessageBox.Icon.Warning,
                QMessageBox.StandardButton.Ok,
                get_main_window(self)
            )
            return

        # Create remote config
        config = RemoteConnectionConfig(
            endpoint_url=url,
            display_name=name,
            verify_ssl=self.remote_verify_ssl_checkbox.isChecked()
        )

        # Switch to remote mode
        from ..main_window import run_async_coro
        def switch_to_remote():
            self.view_model.mode_manager.switch_to_remote(config, management_key="", from_onboarding=False)
            self._update_mode_selection(OperatingMode.REMOTE_PROXY)
            self._update_mode_ui()
            run_async_coro(self.view_model._initialize_remote_mode())

        call_on_main_thread(switch_to_remote)

    def _update_proxy_control_buttons(self):
        """Update proxy start/stop button and status based on current state.
        Matches original LocalProxyServerSection design.
        """
        if not self.view_model:
            return

        proxy_manager = self.view_model.proxy_manager
        proxy_status = proxy_manager.proxy_status
        is_running = proxy_status.running
        port = proxy_manager.port

        # Update endpoint URL
        endpoint = f"http://localhost:{port}/v1"
        self.proxy_endpoint_label.setText(endpoint)

        if is_running:
            # Running state
            self.proxy_start_stop_button.setText("Stop Proxy")
            self.proxy_start_stop_button.setStyleSheet("""
                QPushButton {
                    padding: 4px 12px;
                    font-size: 11px;
                    border-radius: 4px;
                    background-color: #FF3B30;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #D32F2F;
                }
                QPushButton:disabled {
                    background-color: #ccc;
                    color: #666;
                }
            """)
            self.proxy_status_label.setText("Running")
            self.proxy_status_label.setStyleSheet("font-size: 12px; color: #333;")
            self.proxy_status_circle.setStyleSheet("font-size: 12px; color: #34C759;")
            self.proxy_start_stop_button.setEnabled(True)

            # Refresh API keys when proxy starts
            self._refresh_api_keys_list()
        else:
            # Stopped or starting state
            self.proxy_start_stop_button.setText("Start Proxy")
            self.proxy_start_stop_button.setStyleSheet("""
                QPushButton {
                    padding: 4px 12px;
                    font-size: 11px;
                    border-radius: 4px;
                    background-color: #007AFF;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #0051D5;
                }
                QPushButton:disabled {
                    background-color: #ccc;
                    color: #666;
                }
            """)
            # Check proxy_manager.is_starting (not proxy_status.is_starting)
            if proxy_manager.is_starting or (self.view_model.status_message and "starting" in self.view_model.status_message.lower()):
                self.proxy_status_label.setText("Starting...")
                self.proxy_status_label.setStyleSheet("font-size: 12px; color: #333;")
                self.proxy_status_circle.setStyleSheet("font-size: 12px; color: #FF9500;")
                self.proxy_start_stop_button.setEnabled(False)
            else:
                self.proxy_status_label.setText("Stopped")
                self.proxy_status_label.setStyleSheet("font-size: 12px; color: #666;")
                self.proxy_status_circle.setStyleSheet("font-size: 12px; color: #999;")
                self.proxy_start_stop_button.setEnabled(True)

            # Hide API keys when proxy is stopped
            self._refresh_api_keys_list()

    def _on_toggle_proxy(self):
        """Handle start/stop proxy button click."""
        if not self.view_model:
            return

        proxy_status = self.view_model.proxy_manager.proxy_status

        if proxy_status.running:
            # Stop proxy
            self.view_model.stop_proxy()
            call_on_main_thread(self._update_proxy_control_buttons)
        else:
            # Start proxy - disable button to prevent multiple clicks
            self.proxy_start_stop_button.setEnabled(False)
            self.proxy_start_stop_button.setText("Starting...")

            async def start():
                try:
                    await self.view_model.start_proxy()
                finally:
                    call_on_main_thread(self._update_proxy_control_buttons)
                    self.proxy_start_stop_button.setEnabled(True)

            run_async_coro(start())

    def _on_port_changed(self, value: int):
        """Handle port change."""
        if self.view_model:
            self.view_model.proxy_manager.port = value
            # Save port to settings
            self.view_model.settings.set("proxyPort", value)
            # Update endpoint URL
            endpoint = f"http://localhost:{value}/v1"
            self.proxy_endpoint_label.setText(endpoint)
            # Update status if proxy is running
            if self.view_model.proxy_manager.proxy_status.running:
                self._update_proxy_control_buttons()

    def _on_auto_start_changed(self, state: int):
        """Handle auto-start checkbox change."""
        if self.view_model:
            # state is 0 (Unchecked), 1 (PartiallyChecked), or 2 (Checked)
            checked = state == Qt.CheckState.Checked.value
            self.view_model.settings.set("autoStartProxy", checked)
            # Update view model's internal state
            self.view_model._auto_start = checked

    def _on_auto_restart_changed(self, state: int):
        """Handle auto-restart checkbox change."""
        if self.view_model:
            # state is 0 (Unchecked), 1 (PartiallyChecked), or 2 (Checked)
            checked = state == Qt.CheckState.Checked.value
            self.view_model.settings.set("autoRestartProxy", checked)

    def _on_generate_api_key(self):
        """Generate a random API key."""
        import random
        import string
        prefix = "sk-"
        characters = string.ascii_letters + string.digits
        random_part = ''.join(random.choice(characters) for _ in range(32))
        generated_key = prefix + random_part
        self.api_key_input.setText(generated_key)

    def _on_add_api_key(self):
        """Handle add API key button click."""
        key = self.api_key_input.text().strip()
        if not key:
            return

        if self.view_model:
            async def add_key():
                await self.view_model.add_api_key(key)
                call_on_main_thread(self._refresh_api_keys_list)

            run_async_coro(add_key())
            self.api_key_input.clear()

    def _refresh_api_keys_list(self):
        """Refresh the API keys list display."""
        if not self.view_model:
            return

        self.api_keys_list.clear()

        # Only show if proxy is running
        if not (self.view_model.proxy_manager.proxy_status.running and self.view_model.api_client):
            self.api_keys_list.setVisible(False)
            self.api_key_input.setVisible(False)
            self.generate_key_button.setVisible(False)
            self.add_key_button.setVisible(False)
            self.api_keys_info_label.setText("Start the proxy server to manage API keys")
            self.api_keys_info_label.setWordWrap(False)  # Ensure single line
            return

        # Show controls when proxy is running
        self.api_keys_list.setVisible(True)
        self.api_key_input.setVisible(True)
        self.generate_key_button.setVisible(True)
        self.add_key_button.setVisible(True)

        # Load and display API keys
        if hasattr(self.view_model, 'api_keys') and self.view_model.api_keys:
            for key in self.view_model.api_keys:
                # Create list item
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, key)  # Store full key for operations
                item.setSizeHint(QSize(0, 32))  # Set item height

                # Create custom widget with key text and delete button
                item_widget = QWidget()
                item_layout = QHBoxLayout()
                item_layout.setContentsMargins(8, 4, 8, 4)
                item_layout.setSpacing(8)

                # Key label (masked)
                key_label = QLabel(self._mask_api_key(key))
                key_label.setStyleSheet("""
                    font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
                    font-size: 11px;
                    color: #333;
                """)
                key_label.setToolTip("Double-click to copy, right-click for menu")
                item_layout.addWidget(key_label)
                item_layout.addStretch()

                # Copy button (icon-style, matches original design)
                copy_btn = QPushButton("📋")
                copy_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 9px;
                        padding: 1px 3px;
                        border: none;
                        background-color: transparent;
                        border-radius: 3px;
                        min-width: 18px;
                        min-height: 18px;
                    }
                    QPushButton:hover {
                        background-color: #e3f2fd;
                    }
                    QPushButton:pressed {
                        background-color: #bbdefb;
                    }
                """)
                copy_btn.setToolTip("Copy API key to clipboard")
                copy_btn.clicked.connect(lambda checked, k=key: self._copy_api_key(k))
                item_layout.addWidget(copy_btn)

                # Delete button (icon-style, matches original design)
                delete_btn = QPushButton("🗑")
                delete_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 9px;
                        padding: 1px 3px;
                        border: none;
                        background-color: transparent;
                        border-radius: 3px;
                        min-width: 18px;
                        min-height: 18px;
                        color: #FF3B30;
                    }
                    QPushButton:hover {
                        background-color: #FFEBEE;
                    }
                    QPushButton:pressed {
                        background-color: #FFCDD2;
                    }
                """)
                delete_btn.setToolTip("Delete API key")
                delete_btn.clicked.connect(lambda checked, k=key: self._delete_api_key(k))
                item_layout.addWidget(delete_btn)

                item_widget.setLayout(item_layout)

                self.api_keys_list.addItem(item)
                self.api_keys_list.setItemWidget(item, item_widget)

            self.api_keys_info_label.setText(f"{len(self.view_model.api_keys)} API key(s) configured")
            self.api_keys_info_label.setWordWrap(False)
        else:
            self.api_keys_info_label.setText("No API keys configured. Add one to secure proxy access.")
            self.api_keys_info_label.setWordWrap(False)

        # Connect list widget signals
        self.api_keys_list.itemDoubleClicked.connect(self._on_api_key_double_clicked)
        self.api_keys_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.api_keys_list.customContextMenuRequested.connect(self._on_api_key_context_menu)

    def _mask_api_key(self, key: str) -> str:
        """Mask API key for display (show first 6 and last 4 characters)."""
        if len(key) <= 8:
            return "•" * len(key)
        prefix = key[:6]
        suffix = key[-4:]
        return f"{prefix}••••••••{suffix}"

    def _on_api_key_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on API key item - copy to clipboard."""
        full_key = item.data(Qt.ItemDataRole.UserRole)
        if full_key:
            clipboard = QApplication.clipboard()
            clipboard.setText(full_key)
            # Show brief feedback
            self.api_keys_info_label.setText("API key copied to clipboard")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self._refresh_api_keys_list())

    def _on_api_key_context_menu(self, position):
        """Show context menu for API key item."""
        item = self.api_keys_list.itemAt(position)
        if not item:
            return

        full_key = item.data(Qt.ItemDataRole.UserRole)
        if not full_key:
            return

        menu = QMenu(self)

        copy_action = menu.addAction("Copy")
        copy_action.triggered.connect(lambda: self._copy_api_key(full_key))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_api_key(full_key))

        # Show menu at cursor position
        menu.exec(self.api_keys_list.mapToGlobal(position))

    def _copy_api_key(self, key: str):
        """Copy API key to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(key)
        self.api_keys_info_label.setText("API key copied to clipboard")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._refresh_api_keys_list())

    def _delete_api_key(self, key: str):
        """Delete an API key."""
        if not self.view_model:
            return

        reply = show_message_box(
            self,
            "Delete API Key",
            f"Are you sure you want to delete this API key?\n\n{self._mask_api_key(key)}",
            QMessageBox.Icon.Question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            get_main_window(self)
        )

        if reply == QMessageBox.StandardButton.Yes:
            async def delete_key():
                await self.view_model.delete_api_key(key)
                call_on_main_thread(self._refresh_api_keys_list)

            run_async_coro(delete_key())

    # MARK: - Advanced Remote Proxy Settings Handlers

    async def _load_advanced_remote_settings(self):
        """Load advanced remote proxy settings."""
        if not self.view_model or not self.view_model.api_client:
            return

        try:
            # Load config in parallel
            import asyncio
            config_task = self.view_model.api_client.fetch_config()
            routing_task = self.view_model.api_client.get_routing_strategy()

            config, routing_strategy = await asyncio.gather(config_task, routing_task)

            # Update UI on main thread
            def update_ui():
                # Upstream proxy
                proxy_url = config.get("proxy-url", config.get("proxyURL", ""))
                self.upstream_proxy_input.setText(proxy_url)

                # Routing strategy
                strategy = routing_strategy or config.get("routing", {}).get("strategy", "round-robin")
                index = self.routing_strategy_combo.findData(strategy)
                if index >= 0:
                    self.routing_strategy_combo.setCurrentIndex(index)

                # Quota exceeded behavior
                quota_exceeded = config.get("quota-exceeded", config.get("quotaExceeded", {}))
                self.switch_project_checkbox.setChecked(quota_exceeded.get("switch-project", quota_exceeded.get("switchProject", True)))
                self.switch_preview_model_checkbox.setChecked(quota_exceeded.get("switch-preview-model", quota_exceeded.get("switchPreviewModel", True)))

                # Retry configuration
                self.max_retries_spinbox.setValue(config.get("request-retry", config.get("requestRetry", 3)))
                self.max_retry_interval_spinbox.setValue(config.get("max-retry-interval", config.get("maxRetryInterval", 30)))

                # Logging
                self.logging_to_file_checkbox.setChecked(config.get("logging-to-file", config.get("loggingToFile", True)))
                self.request_log_checkbox.setChecked(config.get("request-log", config.get("requestLog", False)))
                self.debug_mode_checkbox.setChecked(config.get("debug", False))

            call_on_main_thread(update_ui)
        except Exception as e:
            print(f"[Settings] Failed to load advanced remote settings: {e}")

    def _on_save_upstream_proxy(self):
        """Handle save upstream proxy button click."""
        if not self.view_model or not self.view_model.api_client:
            return

        url = self.upstream_proxy_input.text().strip()

        async def save():
            try:
                if url:
                    await self.view_model.api_client.set_proxy_url(url)
                else:
                    await self.view_model.api_client.delete_proxy_url()
            except Exception as e:
                print(f"[Settings] Failed to save upstream proxy: {e}")

        run_async_coro(save())

    def _on_routing_strategy_changed(self, index: int):
        """Handle routing strategy change."""
        if not self.view_model or not self.view_model.api_client:
            return

        strategy = self.routing_strategy_combo.currentData()

        async def save():
            try:
                await self.view_model.api_client.set_routing_strategy(strategy)
            except Exception as e:
                print(f"[Settings] Failed to save routing strategy: {e}")

        run_async_coro(save())

    def _on_switch_project_changed(self, state: int):
        """Handle switch project checkbox change."""
        if not self.view_model or not self.view_model.api_client:
            return

        enabled = state == Qt.CheckState.Checked.value

        async def save():
            try:
                await self.view_model.api_client.set_quota_exceeded_switch_project(enabled)
            except Exception as e:
                print(f"[Settings] Failed to save switch project setting: {e}")

        run_async_coro(save())

    def _on_switch_preview_model_changed(self, state: int):
        """Handle switch preview model checkbox change."""
        if not self.view_model or not self.view_model.api_client:
            return

        enabled = state == Qt.CheckState.Checked.value

        async def save():
            try:
                await self.view_model.api_client.set_quota_exceeded_switch_preview_model(enabled)
            except Exception as e:
                print(f"[Settings] Failed to save switch preview model setting: {e}")

        run_async_coro(save())

    def _on_max_retries_changed(self, value: int):
        """Handle max retries change."""
        if not self.view_model or not self.view_model.api_client:
            return

        async def save():
            try:
                await self.view_model.api_client.set_request_retry(value)
            except Exception as e:
                print(f"[Settings] Failed to save max retries: {e}")

        run_async_coro(save())

    def _on_max_retry_interval_changed(self, value: int):
        """Handle max retry interval change."""
        if not self.view_model or not self.view_model.api_client:
            return

        async def save():
            try:
                await self.view_model.api_client.set_max_retry_interval(value)
            except Exception as e:
                print(f"[Settings] Failed to save max retry interval: {e}")

        run_async_coro(save())

    def _on_logging_to_file_changed(self, state: int):
        """Handle logging to file checkbox change."""
        if not self.view_model or not self.view_model.api_client:
            return

        enabled = state == Qt.CheckState.Checked.value

        async def save():
            try:
                await self.view_model.api_client.set_logging_to_file(enabled)
            except Exception as e:
                print(f"[Settings] Failed to save logging to file setting: {e}")

        run_async_coro(save())

    def _on_request_log_changed(self, state: int):
        """Handle request log checkbox change."""
        if not self.view_model or not self.view_model.api_client:
            return

        enabled = state == Qt.CheckState.Checked.value

        async def save():
            try:
                await self.view_model.api_client.set_request_log(enabled)
            except Exception as e:
                print(f"[Settings] Failed to save request log setting: {e}")

        run_async_coro(save())

    def _on_debug_mode_changed(self, state: int):
        """Handle debug mode checkbox change."""
        if not self.view_model or not self.view_model.api_client:
            return

        enabled = state == Qt.CheckState.Checked.value

        async def save():
            try:
                await self.view_model.api_client.set_debug(enabled)
            except Exception as e:
                print(f"[Settings] Failed to save debug mode setting: {e}")

        run_async_coro(save())


    def _on_tab_visibility_changed(self, state: int):
        """Handle tab visibility checkbox changes."""
        if not self.view_model:
            return

        checked = state == Qt.CheckState.Checked.value

        # Determine which checkbox was changed
        sender = self.sender()
        if sender == self.show_logs_tab_checkbox:
            self.view_model.settings.set("showLogsTab", checked)
            # Notify main window to update tab visibility
            self._update_tab_visibility("Logs", checked)
        elif sender == self.show_custom_providers_tab_checkbox:
            self.view_model.settings.set("showCustomProvidersTab", checked)
            # Notify main window to update tab visibility
            self._update_tab_visibility("Custom Providers", checked)

    def _update_tab_visibility(self, tab_name: str, visible: bool):
        """Update tab visibility in main window."""
        from PyQt6.QtCore import QTimer

        def update_tabs():
            """Update tabs on main thread."""
            # Use stored reference to MainWindow instance
            main_window = self.main_window
            if not main_window:
                print(f"[Settings] MainWindow reference not available")
                return

            if not hasattr(main_window, 'tabs'):
                print(f"[Settings] MainWindow does not have 'tabs' attribute")
                return

            # Only update if in local proxy mode (these tabs only exist in local proxy mode)
            if not (main_window.view_model and main_window.view_model.mode_manager.is_local_proxy_mode):
                print(f"[Settings] Not in local proxy mode, skipping tab visibility update")
                return

            # Find tab by name
            tab_index = None
            for i in range(main_window.tabs.count()):
                if main_window.tabs.tabText(i) == tab_name:
                    tab_index = i
                    break

            if visible:
                # Show tab - need to add it if it doesn't exist
                if tab_index is None:
                    print(f"[Settings] Adding tab: {tab_name}")
                    # Determine where to insert based on tab name
                    insert_index = None
                    screen = None

                    if tab_name == "Logs":
                        # Insert after Agents tab
                        for i in range(main_window.tabs.count()):
                            if main_window.tabs.tabText(i) == "Agents":
                                insert_index = i + 1
                                break
                        if hasattr(main_window, 'logs_screen'):
                            screen = main_window.logs_screen
                    elif tab_name == "Custom Providers":
                        # Insert after Logs tab (or after Agents if Logs doesn't exist)
                        for i in range(main_window.tabs.count()):
                            if main_window.tabs.tabText(i) == "Logs":
                                insert_index = i + 1
                                break
                        if insert_index is None:
                            # Logs doesn't exist, insert after Agents
                            for i in range(main_window.tabs.count()):
                                if main_window.tabs.tabText(i) == "Agents":
                                    insert_index = i + 1
                                    break
                        if hasattr(main_window, 'custom_providers_screen'):
                            screen = main_window.custom_providers_screen

                    if insert_index is not None and screen is not None:
                        main_window.tabs.insertTab(insert_index, screen, tab_name)
                        print(f"[Settings] Successfully added tab '{tab_name}' at index {insert_index}")
                    else:
                        print(f"[Settings] Could not add tab '{tab_name}': insert_index={insert_index}, screen={screen}")
                else:
                    print(f"[Settings] Tab '{tab_name}' already exists at index {tab_index}")
            else:
                # Hide tab by removing it
                if tab_index is not None:
                    print(f"[Settings] Removing tab: {tab_name} at index {tab_index}")
                    main_window.tabs.removeTab(tab_index)
                    print(f"[Settings] Successfully removed tab '{tab_name}'")
                else:
                    print(f"[Settings] Tab '{tab_name}' not found, nothing to remove")

        # Schedule on main thread to ensure UI updates work correctly
        QTimer.singleShot(0, update_tabs)

    def _on_auto_refresh_enabled_changed(self, state: int):
        """Handle auto-refresh enabled checkbox change."""
        if not self.view_model:
            return

        enabled = state == Qt.CheckState.Checked.value
        self.view_model.settings.set("autoRefreshEnabled", enabled)

        # Update main window timer (schedule on main thread)
        from PyQt6.QtCore import QTimer
        main_window = get_main_window(self)
        if main_window and hasattr(main_window, '_update_auto_refresh_timer'):
            QTimer.singleShot(0, main_window._update_auto_refresh_timer)

    def _on_auto_refresh_interval_changed(self, value: int):
        """Handle auto-refresh interval change."""
        if not self.view_model:
            return

        self.view_model.settings.set("autoRefreshIntervalMinutes", value)

        # Update main window timer (schedule on main thread)
        from PyQt6.QtCore import QTimer
        main_window = get_main_window(self)
        if main_window and hasattr(main_window, '_update_auto_refresh_timer'):
            QTimer.singleShot(0, main_window._update_auto_refresh_timer)

    def showEvent(self, event: QEvent):
        """Handle show event - refresh proxy status when tab is shown."""
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        """Refresh the display."""
        self._load_settings()
        # Update proxy control buttons
        if self.view_model and self.view_model.mode_manager.is_local_proxy_mode:
            self._update_proxy_control_buttons()
            # Load API keys if proxy is running
            # First verify proxy is actually responding before trying to fetch API keys
            if self.view_model.proxy_manager.proxy_status.running and self.view_model.api_client:
                async def load_keys():
                    try:
                        print(f"[Settings] Checking if proxy is responding before loading API keys...")
                        # Check if proxy is actually responding
                        is_responding = await self.view_model.api_client.check_proxy_responding()
                        if not is_responding:
                            print(f"[Settings] Proxy is marked as running but not responding to requests - skipping API keys load")
                            return

                        print(f"[Settings] Proxy is responding, loading API keys...")
                        self.view_model.api_keys = await self.view_model.api_client.fetch_api_keys()
                        print(f"[Settings] Successfully loaded {len(self.view_model.api_keys) if self.view_model.api_keys else 0} API key(s)")
                        call_on_main_thread(self._refresh_api_keys_list)
                    except Exception as e:
                        error_msg = str(e) if e else "Unknown error"
                        print(f"[Settings] Failed to load API keys: {type(e).__name__}: {error_msg}")
                        import traceback
                        traceback.print_exc()
                run_async_coro(load_keys())
            else:
                if not self.view_model.proxy_manager.proxy_status.running:
                    print(f"[Settings] Proxy not running, skipping API keys load")
                elif not self.view_model.api_client:
                    print(f"[Settings] API client not available, skipping API keys load")
        # Also refresh advanced remote settings if in remote mode
        if (self.view_model and
            self.view_model.mode_manager.current_mode == OperatingMode.REMOTE_PROXY and
            self.advanced_remote_group.isVisible()):
            run_async_coro(self._load_advanced_remote_settings())
