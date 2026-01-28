"""Merged Dashboard screen - combines proxy status, stats, and quota information."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QGroupBox, QPushButton,
    QMessageBox, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QLineEdit, QGridLayout, QSizePolicy,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QTabWidget, QMenu
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QAction
import asyncio
from typing import Optional, Any

from ...models.providers import AIProvider
from ...models.subscription import SubscriptionInfo
from ...models.operating_mode import OperatingMode
from ..utils import (
    show_message_box, get_main_window, call_on_main_thread,
    get_quota_status_color, get_agent_status_color, to_local_dt
)


def run_async_coro(coro) -> Any:
    """Run an async coroutine, creating task if loop is running."""
    from ..main_window import run_async_coro as main_run_async_coro
    return main_run_async_coro(coro)


class DashboardScreen(QWidget):
    """Merged Dashboard screen showing proxy status, stats, and quota information."""

    def __init__(self, view_model=None, agent_viewmodel=None):
        """Initialize the dashboard."""
        super().__init__()
        self.view_model = view_model
        self.agent_viewmodel = agent_viewmodel
        self._filtered_data = []
        self._updating_filters = False  # Guard to prevent recursive filter updates
        self._ignored_models = set()  # Set of model names to ignore
        self._favorites = self._load_favorites()  # Load favorites from settings
        self._setup_ui()

        # Register for quota update notifications
        if self.view_model:
            self.view_model.register_quota_update_callback(self._update_display)
            self._quota_callback_registered = True

    def _setup_ui(self):
        """Set up the UI."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)
        self.setLayout(main_layout)

        # Title and refresh button
        header_layout = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 8px;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-size: 14px;
                border-radius: 4px;
                background-color: #007AFF;
                color: white;
            }
            QPushButton:hover {
                background-color: #0051D5;
            }
        """)
        self.refresh_button.clicked.connect(self._on_refresh)
        header_layout.addWidget(self.refresh_button)

        main_layout.addLayout(header_layout)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setSpacing(16)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # ===== PROXY STATUS SECTION =====
        proxy_group = QGroupBox("Proxy Status")
        proxy_group.setStyleSheet(self._get_groupbox_style())
        proxy_layout = QVBoxLayout()
        proxy_layout.setSpacing(12)

        # Status row with port inline
        status_row = QHBoxLayout()
        self.status_label = QLabel("Status: Not running")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: 500;")
        status_row.addWidget(self.status_label)
        # Make status label copyable
        from ..utils import make_label_copyable
        make_label_copyable(self.status_label)

        self.port_label = QLabel("")
        self.port_label.setStyleSheet("font-size: 14px; font-weight: 500; color: #666;")
        self.port_label.setVisible(False)  # Hidden by default, shown when proxy is running/starting
        status_row.addWidget(self.port_label)

        status_row.addStretch()

        # Control buttons (moved to end of status row)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.start_stop_button = QPushButton("Start Proxy")
        self.start_stop_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 4px;
                background-color: #34C759;
                color: white;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #28A745;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.start_stop_button.clicked.connect(self._on_toggle_proxy)
        button_layout.addWidget(self.start_stop_button)

        # Starting label (shown when proxy is starting)
        self.starting_label = QLabel("Starting...")
        self.starting_label.setStyleSheet("""
            QLabel {
                padding: 8px 16px;
                font-size: 14px;
                color: #007AFF;
                font-weight: 500;
            }
        """)
        self.starting_label.setVisible(False)
        button_layout.addWidget(self.starting_label)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet("""
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
        """)
        self.cancel_button.clicked.connect(self._on_cancel_startup)
        self.cancel_button.setVisible(False)
        button_layout.addWidget(self.cancel_button)

        status_row.addLayout(button_layout)
        proxy_layout.addLayout(status_row)

        # Download progress label (hidden by default)
        self.download_label = QLabel("")
        self.download_label.setStyleSheet("color: blue; font-size: 12px;")
        self.download_label.hide()
        proxy_layout.addWidget(self.download_label)

        proxy_group.setLayout(proxy_layout)

        # ===== QUOTA & AGENT SECTION =====
        merged_group = QGroupBox("Quotas & Agents")
        merged_group.setStyleSheet(self._get_groupbox_style())
        merged_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        merged_layout = QVBoxLayout()
        merged_layout.setSpacing(12)
        merged_layout.setContentsMargins(8, 8, 8, 8)

        # Tab widget for Favorites and All
        self.quota_tabs = QTabWidget()
        self.quota_tabs.currentChanged.connect(self._on_quota_tab_changed)
        self.quota_tabs.setStyleSheet("""
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

        # Tab 1: Favorites (default)
        favorites_tab = QWidget()
        favorites_layout = QVBoxLayout()
        favorites_layout.setContentsMargins(0, 0, 0, 0)
        
        self.favorites_status_label = QLabel("No favorites yet. Right-click on a row in the 'All' tab to add to favorites.")
        self.favorites_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.favorites_status_label.setWordWrap(True)
        self.favorites_status_label.setStyleSheet("color: #666; padding: 20px;")
        favorites_layout.addWidget(self.favorites_status_label)

        # Favorites table
        self.favorites_table = QTableWidget()
        self.favorites_table.setColumnCount(6)
        self.favorites_table.setHorizontalHeaderLabels(["Provider", "Account", "Model", "Usage", "Status", "⭐"])
        favorites_header = self.favorites_table.horizontalHeader()
        favorites_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Provider
        favorites_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Account
        favorites_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Model
        favorites_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Usage
        favorites_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Status
        favorites_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Star
        self.favorites_table.setAlternatingRowColors(True)
        self.favorites_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.favorites_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorites_table.customContextMenuRequested.connect(self._on_favorites_table_context_menu)
        self.favorites_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                gridline-color: #eee;
                background-color: white;
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
        # Initially hide the table until we have favorites
        self.favorites_table.hide()
        favorites_layout.addWidget(self.favorites_table, 1)
        favorites_tab.setLayout(favorites_layout)
        self.quota_tabs.addTab(favorites_tab, "Favorites")

        # Tab 2: All Quotas
        all_tab = QWidget()
        all_layout = QVBoxLayout()
        all_layout.setContentsMargins(0, 0, 0, 0)
        
        self.quota_status_label = QLabel("No quota data available")
        self.quota_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quota_status_label.setStyleSheet("color: #666; padding: 20px;")
        all_layout.addWidget(self.quota_status_label)

        # All quotas table
        self.quota_table = QTableWidget()
        self.quota_table.setColumnCount(6)  # Added Favorites column
        self.quota_table.setHorizontalHeaderLabels(["Provider", "Account", "Model", "Usage", "Status", "⭐"])
        # Set column resize modes: resize to contents with max widths
        header = self.quota_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Provider
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Account
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Model
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Usage
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Status (stretches to fill)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Star
        self.quota_table.setAlternatingRowColors(True)
        self.quota_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.quota_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.quota_table.customContextMenuRequested.connect(self._on_quota_table_context_menu)
        self.quota_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                gridline-color: #eee;
                background-color: white;
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
        all_layout.addWidget(self.quota_table, 1)  # Stretch factor to expand vertically
        all_tab.setLayout(all_layout)
        self.quota_tabs.addTab(all_tab, "All")
        
        # Set Favorites tab as default (index 0)
        self.quota_tabs.setCurrentIndex(0)
        
        # Update favorites display on initial load
        self._update_favorites_display()

        merged_layout.addWidget(self.quota_tabs, 1)  # Stretch factor to expand vertically
        merged_group.setLayout(merged_layout)

        # ===== PROXY STATUS SECTION =====
        scroll_layout.addWidget(proxy_group)

        # ===== STATISTICS SECTION =====
        stats_group = QGroupBox("Statistics")
        stats_group.setStyleSheet(self._get_groupbox_style())
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        # Create compact stat cards (only most important ones)
        self.accounts_card = self._create_stat_card("Accounts", "0")
        self.providers_card = self._create_stat_card("Providers", "0")
        self.requests_card = self._create_stat_card("Requests", "—")
        self.success_rate_card = self._create_stat_card("Success Rate", "—")

        stats_layout.addWidget(self.accounts_card)
        stats_layout.addWidget(self.providers_card)
        stats_layout.addWidget(self.requests_card)
        stats_layout.addWidget(self.success_rate_card)
        stats_layout.addStretch()

        stats_group.setLayout(stats_layout)
        scroll_layout.addWidget(stats_group)

        # ===== QUOTA FILTERS SECTION =====
        filter_group = QGroupBox("Quota Filters")
        filter_group.setStyleSheet(self._get_groupbox_style())
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)

        filter_layout.addWidget(QLabel("Provider:"))
        self.provider_filter = QComboBox()
        self.provider_filter.addItem("All Providers")
        self.provider_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.provider_filter)

        filter_layout.addWidget(QLabel("Account:"))
        self.account_filter = QComboBox()
        self.account_filter.setEditable(False)
        self.account_filter.addItem("All Accounts")
        self.account_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.account_filter)

        filter_layout.addWidget(QLabel("Model:"))
        self.model_filter = QComboBox()
        self.model_filter.setEditable(False)
        self.model_filter.addItem("All Models")
        self.model_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.model_filter)

        # Ignore Models button
        self.ignore_models_button = QPushButton("Ignore Models...")
        self.ignore_models_button.setToolTip("Select models to hide from the table")
        self.ignore_models_button.clicked.connect(self._on_ignore_models_clicked)
        filter_layout.addWidget(self.ignore_models_button)

        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        filter_layout.addWidget(self.clear_filters_button)

        filter_layout.addStretch()
        filter_group.setLayout(filter_layout)
        scroll_layout.addWidget(filter_group)

        # ===== QUOTAS & AGENTS SECTION (at bottom) =====
        scroll_layout.addWidget(merged_group, 1)  # Stretch factor to expand to bottom

        # Load ignored models from settings
        self._load_ignored_models()

        # Update display
        self._update_display()

        # Check for auto-start on initial load (immediately and after a short delay)
        # Immediate check handles case where auto-start is already in progress
        self._check_auto_start()
        # Delayed check handles case where auto-start begins after dashboard loads
        QTimer.singleShot(100, self._check_auto_start)
        QTimer.singleShot(500, self._check_auto_start)  # Additional check after 500ms

    def _get_groupbox_style(self) -> str:
        """Get consistent styling for group boxes."""
        return """
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #333;
            }
        """

    def _create_stat_card(self, title: str, value: str, icon: str = "") -> QWidget:
        """Create a compact statistics card widget."""
        card = QGroupBox()
        card.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: white;
                min-width: 100px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0px;
            }
        """)
        card_layout = QVBoxLayout()
        card_layout.setSpacing(2)
        card_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 11px; color: #666;")
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        value_label.setObjectName("value")
        card_layout.addWidget(value_label)

        card.setLayout(card_layout)
        return card

    def _update_stat_card(self, card: QWidget, value: str) -> None:
        """Update the value in a stat card."""
        value_label = card.findChild(QLabel, "value")
        if value_label:
            value_label.setText(value)

    def _on_refresh(self) -> None:
        """Handle refresh button click."""
        if not self.view_model:
            return

        async def refresh_all():
            try:
                await self.view_model.refresh_quotas_unified()
                call_on_main_thread(self._update_display)
            except Exception as e:
                print(f"[Dashboard] Error refreshing: {e}")

        run_async_coro(refresh_all())

    def _on_toggle_proxy(self) -> None:
        """Handle start/stop proxy button click."""
        if not self.view_model:
            return

        if self.view_model.proxy_manager.proxy_status.running:
            # Stop proxy
            self.view_model.stop_proxy()
            call_on_main_thread(self._update_display)
        else:
            # Start proxy - disable button to prevent multiple clicks
            self.start_stop_button.setEnabled(False)
            self.start_stop_button.setText("Starting...")
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)

            async def start():
                try:
                    await self.view_model.start_proxy()
                finally:
                    call_on_main_thread(self._update_display)

            run_async_coro(start())

    def _on_cancel_startup(self) -> None:
        """Handle cancel startup button click."""
        if not self.view_model:
            return


        # Cancel via view model (which handles both task and proxy manager)
        self.view_model.cancel_proxy_startup()

        # Update UI immediately
        self._update_proxy_status()
        self._update_display()

    def _on_filter_changed(self) -> None:
        """Handle filter changes."""
        # Prevent recursive calls
        if self._updating_filters:
            return

        # If provider filter changed, update account and model filters to show only relevant items
        sender = self.sender()
        if sender == self.provider_filter:
            self._update_account_filter()
            self._update_model_filter()
        self._update_quota_display()
        
        # Update favorites display if on favorites tab (index 0)
        if hasattr(self, 'quota_tabs') and self.quota_tabs.currentIndex() == 0:
            self._update_favorites_display()

    def _clear_filters(self) -> None:
        """Clear all filters."""
        self.provider_filter.setCurrentIndex(0)  # "All Providers"
        self.account_filter.setCurrentIndex(0)  # "All Accounts"
        self.model_filter.setCurrentIndex(0)  # "All Models"
        self._update_quota_display()

    def _update_display(self) -> None:
        """Update the entire display."""
        if not self.view_model:
            return

        # Reload favorites from settings to ensure we have the latest persisted state
        self._favorites = self._load_favorites()

        # Update proxy status
        self._update_proxy_status()

        # Update statistics
        self._update_statistics()

        # Update provider filter (this also updates account and model filters)
        self._update_provider_filter()

        # Update quota display
        self._update_quota_display()

        # Update favorites display if favorites tab is active
        if hasattr(self, 'quota_tabs') and self.quota_tabs.currentIndex() == 0:
            self._update_favorites_display()

        # Force widget repaint to ensure UI updates are visible immediately
        # This is critical when updates come from background threads
        self.update()
        if hasattr(self, 'quota_table'):
            self.quota_table.update()
            self.quota_table.viewport().update()
        if hasattr(self, 'quota_status_label'):
            self.quota_status_label.update()
        if hasattr(self, 'favorites_table'):
            self.favorites_table.update()
            self.favorites_table.viewport().update()

        # Force Qt event processing to ensure UI updates are rendered immediately
        # This ensures quotas are visible without requiring user interaction
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()


    def _update_proxy_status(self) -> None:
        """Update proxy status section."""
        if not self.view_model:
            return

        mode = self.view_model.mode_manager.current_mode
        proxy_manager = self.view_model.proxy_manager

        # Show/hide proxy controls based on mode
        if mode == OperatingMode.LOCAL_PROXY:
            # Button visibility will be set based on proxy state below
            pass
        else:
            self.start_stop_button.setVisible(False)
            self.starting_label.setVisible(False)
            self.cancel_button.setVisible(False)

        # Update status based on mode
        if mode == OperatingMode.MONITOR:
            self.status_label.setText("Status: Monitor Mode (No Proxy)")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: gray;")
            self.port_label.setVisible(False)
        elif mode == OperatingMode.REMOTE_PROXY:
            conn_status = self.view_model.mode_manager.connection_status
            if conn_status.status == "connected":
                remote_name = self.view_model.mode_manager.remote_config.display_name if self.view_model.mode_manager.remote_config else "Remote"
                self.status_label.setText(f"Status: Connected to {remote_name}")
                self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: green;")
            else:
                self.status_label.setText(f"Status: {conn_status.status.title()}")
                self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: red;")
            self.port_label.setVisible(False)
        elif mode == OperatingMode.LOCAL_PROXY:
            port = proxy_manager.port

            if proxy_manager.proxy_status.running:
                self.status_label.setText("Status: Running")
                self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: green;")
                # Show port inline: "on Port: 8317"
                self.port_label.setText(f"on Port: {port}")
                self.port_label.setVisible(True)
                self.start_stop_button.setText("Stop Proxy")
                self.start_stop_button.setStyleSheet("""
                    QPushButton {
                        padding: 4px 12px;
                        font-size: 11px;
                        border-radius: 4px;
                        background-color: #FF3B30;
                        color: white;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #D32F2F;
                    }
                    QPushButton:disabled {
                        background-color: #ccc;
                    }
                """)
                self.start_stop_button.setEnabled(True)
                self.start_stop_button.setVisible(True)
                self.starting_label.setVisible(False)
                self.cancel_button.setVisible(False)
                self.download_label.hide()
            elif proxy_manager.is_starting or (self.view_model.status_message and "starting" in self.view_model.status_message.lower()):
                status_text = self.view_model.status_message or "Starting proxy..."
                # Check if auto-start is enabled (from settings or status message)
                is_auto_start = (
                    "auto" in status_text.lower() or
                    hasattr(self.view_model, '_auto_start') and self.view_model._auto_start or
                    getattr(self.view_model.settings, 'get', lambda k, d: False)("autoStartProxy", False)
                )

                if is_auto_start:
                    # Auto-start: show "Starting up on Port: ..." and Cancel button
                    self.status_label.setText("Status: Starting up")
                    self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: blue;")
                    # Show port inline: "on Port: 8317"
                    self.port_label.setText(f"on Port: {port}")
                    self.port_label.setVisible(True)
                    # Hide Start Proxy button, show Cancel button
                    self.start_stop_button.setVisible(False)
                    self.starting_label.setVisible(False)  # Don't show "Starting..." label
                    self.cancel_button.setVisible(True)
                    self.cancel_button.setEnabled(True)
                else:
                    # Manual start: show "Starting" with label and Cancel button
                    self.status_label.setText("Status: Starting")
                    self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: blue;")
                    # Show port inline: "on Port: 8317"
                    self.port_label.setText(f"on Port: {port}")
                    self.port_label.setVisible(True)
                    # Hide Start Proxy button, show Starting label and Cancel button
                    self.start_stop_button.setVisible(False)
                    self.starting_label.setText("Starting...")
                    self.starting_label.setVisible(True)
                    self.cancel_button.setVisible(True)
                    self.cancel_button.setEnabled(True)
                self.download_label.hide()
            elif proxy_manager.is_downloading:
                self.status_label.setText("Status: Downloading")
                self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: blue;")
                # Hide port during download (not started yet)
                self.port_label.setVisible(False)
                # Hide Start Proxy button, show Downloading label and Cancel button
                self.start_stop_button.setVisible(False)
                self.starting_label.setText("Downloading...")
                self.starting_label.setVisible(True)
                self.cancel_button.setVisible(True)
                self.cancel_button.setEnabled(True)
                progress = int(proxy_manager.download_progress * 100)
                self.download_label.setText(f"Download progress: {progress}%")
                self.download_label.show()
            else:
                error_msg = ""
                if self.view_model.error_message:
                    error_msg = f" - {self.view_model.error_message[:60]}"
                elif proxy_manager.last_error:
                    error_msg = f" - {proxy_manager.last_error[:60]}"

                self.status_label.setText(f"Status: Stopped{error_msg}")
                self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: red;" if error_msg else "font-size: 14px; font-weight: 500; color: gray;")
                # Hide port when stopped
                self.port_label.setVisible(False)
                self.start_stop_button.setText("Start Proxy")
                self.start_stop_button.setStyleSheet("""
                    QPushButton {
                        padding: 4px 12px;
                        font-size: 11px;
                        border-radius: 4px;
                        background-color: #34C759;
                        color: white;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: #28A745;
                    }
                    QPushButton:disabled {
                        background-color: #ccc;
                    }
                """)
                self.start_stop_button.setEnabled(True)
                self.start_stop_button.setVisible(True)
                self.starting_label.setVisible(False)
                self.cancel_button.setVisible(False)
                self.download_label.hide()

                if proxy_manager.last_error or self.view_model.error_message:
                    error_text = self.view_model.error_message or proxy_manager.last_error
                    self.download_label.setText(f"Error: {error_text}")
                    self.download_label.setStyleSheet("color: red; font-size: 12px;")
                    self.download_label.show()

        # Update port for other modes (hide it)
        if mode != OperatingMode.LOCAL_PROXY:
            self.port_label.setVisible(False)

    def _check_auto_start(self) -> None:
        """Check if auto-start is enabled and update UI accordingly during startup."""
        if not self.view_model:
            return

        mode = self.view_model.mode_manager.current_mode
        if mode != OperatingMode.LOCAL_PROXY:
            return

        # Check if auto-start is enabled (from view model attribute or settings)
        auto_start_enabled = (
            getattr(self.view_model, '_auto_start', False) or
            (hasattr(self.view_model, 'settings') and
             self.view_model.settings.get("autoStartProxy", False))
        )

        if not auto_start_enabled:
            return

        proxy_manager = self.view_model.proxy_manager

        # If auto-start is enabled, always hide Start button and show Cancel button
        # This applies whether proxy is starting, downloading, or about to start
        if proxy_manager.is_downloading:
            # Downloading state
            self.status_label.setText("Status: Downloading...")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: blue;")
            self.port_label.setVisible(False)  # Hide port during download
            self.start_stop_button.setVisible(False)  # Hide Start button
            self.starting_label.setText("Downloading...")
            self.starting_label.setVisible(True)
            self.cancel_button.setVisible(True)
            self.cancel_button.setEnabled(True)
            progress = int(proxy_manager.download_progress * 100) if hasattr(proxy_manager, 'download_progress') else 0
            self.download_label.setText(f"Download progress: {progress}%")
            self.download_label.show()
        elif proxy_manager.is_starting or (
            self.view_model.status_message and
            ("starting" in self.view_model.status_message.lower() or
             "auto-start" in self.view_model.status_message.lower())
        ):
            # Starting state (auto-start) - show "Starting up on Port: ..."
            port = proxy_manager.port
            self.status_label.setText("Status: Starting up")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: blue;")
            # Show port inline: "on Port: 8317"
            self.port_label.setText(f"on Port: {port}")
            self.port_label.setVisible(True)
            self.start_stop_button.setVisible(False)  # Hide Start button during auto-start
            self.starting_label.setVisible(False)  # Don't show "Starting..." label, status text is enough
            self.cancel_button.setVisible(True)  # Show Cancel button
            self.cancel_button.setEnabled(True)
            self.download_label.hide()
        elif not proxy_manager.proxy_status.running:
            # Auto-start enabled but proxy hasn't started yet - still hide Start button
            # This handles the case where auto-start is about to begin
            port = proxy_manager.port
            self.status_label.setText("Status: Starting up")
            self.status_label.setStyleSheet("font-size: 14px; font-weight: 500; color: blue;")
            # Show port inline: "on Port: 8317"
            self.port_label.setText(f"on Port: {port}")
            self.port_label.setVisible(True)
            self.start_stop_button.setVisible(False)  # Hide Start button
            self.starting_label.setVisible(False)
            self.cancel_button.setVisible(True)  # Show Cancel button
            self.cancel_button.setEnabled(True)
            self.download_label.hide()

    def _update_statistics(self) -> None:
        """Update statistics cards."""
        if not self.view_model:
            return

        # Accounts: Count from both auth_files and provider_quotas
        # Deduplicate by account identifier (email/account name)
        account_set = set()

        # Add accounts from auth_files
        for auth_file in self.view_model.auth_files:
            account_id = auth_file.email or auth_file.account or auth_file.name or auth_file.id
            if account_id:
                account_set.add(account_id)

        # Add accounts from provider_quotas (includes IDE scan results like Cursor/Trae)
        if self.view_model.provider_quotas:
            for provider, account_quotas in self.view_model.provider_quotas.items():
                for account_key in account_quotas.keys():
                    account_set.add(account_key)

        account_count = len(account_set)
        self._update_stat_card(self.accounts_card, str(account_count))

        # Providers: Count from both auth_files and provider_quotas
        provider_set = set()

        # Add providers from auth_files
        for auth_file in self.view_model.auth_files:
            if auth_file.provider:
                provider_set.add(auth_file.provider)
            if auth_file.provider_type:
                provider_set.add(auth_file.provider_type.value)

        # Add providers from provider_quotas (includes IDE scan results like Cursor/Trae)
        if self.view_model.provider_quotas:
            for provider in self.view_model.provider_quotas.keys():
                provider_set.add(provider.value)

        provider_count = len(provider_set)
        self._update_stat_card(self.providers_card, str(provider_count))

        # Usage stats
        if self.view_model.usage_stats and self.view_model.usage_stats.usage:
            usage = self.view_model.usage_stats.usage
            total_requests = usage.total_requests or 0
            success_rate = usage.success_rate
            total_tokens = usage.total_tokens or 0

            # Format tokens
            def format_tokens(tokens: int) -> str:
                if tokens >= 1_000_000:
                    return f"{tokens / 1_000_000:.1f}M"
                elif tokens >= 1_000:
                    return f"{tokens / 1_000:.1f}K"
                return str(tokens)

            self._update_stat_card(self.requests_card, str(total_requests))
            self._update_stat_card(self.success_rate_card, f"{success_rate:.1f}%")
        else:
            self._update_stat_card(self.requests_card, "—")
            self._update_stat_card(self.success_rate_card, "—")

    def _update_provider_filter(self) -> None:
        """Update provider filter dropdown."""
        if not self.view_model:
            return

        # Block signals to prevent recursive calls
        self._updating_filters = True
        try:
            current_text = self.provider_filter.currentText()
            self.provider_filter.blockSignals(True)
            self.provider_filter.clear()
            self.provider_filter.addItem("All Providers")

            for provider in sorted(self.view_model.provider_quotas.keys(), key=lambda p: p.display_name):
                self.provider_filter.addItem(provider.display_name)

            index = self.provider_filter.findText(current_text)
            if index >= 0:
                self.provider_filter.setCurrentIndex(index)
            else:
                # If current text not found, default to "All Providers"
                self.provider_filter.setCurrentIndex(0)

            self.provider_filter.blockSignals(False)

            # Also update account and model filters when provider changes
            self._update_account_filter()
            self._update_model_filter()
        finally:
            self._updating_filters = False

    def _update_account_filter(self) -> None:
        """Update account filter dropdown with all current accounts."""
        if not self.view_model or not self.view_model.provider_quotas:
            return

        # Safety check: ensure account_filter is a QComboBox
        if not hasattr(self.account_filter, 'currentText'):
            return

        # Block signals to prevent recursive calls
        self.account_filter.blockSignals(True)
        try:
            current_text = self.account_filter.currentText()
            self.account_filter.clear()
            self.account_filter.addItem("All Accounts")

            # Check if a specific provider is selected
            selected_provider_text = self.provider_filter.currentText()
            if selected_provider_text != "All Providers":
                # Filter accounts for selected provider only
                selected_provider = None
                for provider in self.view_model.provider_quotas.keys():
                    if provider.display_name == selected_provider_text:
                        selected_provider = provider
                        break

                if selected_provider and selected_provider in self.view_model.provider_quotas:
                    accounts = list(self.view_model.provider_quotas[selected_provider].keys())
                    
                    # For Antigravity, sort accounts with favorites first
                    if selected_provider == AIProvider.ANTIGRAVITY:
                        accounts = self._sort_accounts_with_favorites_first(selected_provider, accounts)
                    else:
                        accounts = sorted(accounts)
                    
                    for account in accounts:
                        self.account_filter.addItem(account)
            else:
                # Collect all unique accounts across all providers
                all_accounts = set()
                for account_quotas in self.view_model.provider_quotas.values():
                    all_accounts.update(account_quotas.keys())

                # Add accounts sorted alphabetically
                for account in sorted(all_accounts):
                    self.account_filter.addItem(account)

            # Restore selection if still available
            index = self.account_filter.findText(current_text)
            if index >= 0:
                self.account_filter.setCurrentIndex(index)
            else:
                # If current text not found, default to "All Accounts"
                self.account_filter.setCurrentIndex(0)
        finally:
            self.account_filter.blockSignals(False)

    def _update_model_filter(self) -> None:
        """Update model filter dropdown with all current models."""
        if not self.view_model or not self.view_model.provider_quotas:
            return

        # Safety check: ensure model_filter is a QComboBox
        if not hasattr(self.model_filter, 'currentText'):
            return

        # Block signals to prevent recursive calls
        self.model_filter.blockSignals(True)
        try:
            current_text = self.model_filter.currentText()
            self.model_filter.clear()
            self.model_filter.addItem("All Models")

            # Check if a specific provider is selected
            selected_provider_text = self.provider_filter.currentText()
            if selected_provider_text != "All Providers":
                # Filter models for selected provider only
                selected_provider = None
                for provider in self.view_model.provider_quotas.keys():
                    if provider.display_name == selected_provider_text:
                        selected_provider = provider
                        break

                if selected_provider and selected_provider in self.view_model.provider_quotas:
                    # Collect model objects with their usage data
                    model_list = []
                    for quota_data in self.view_model.provider_quotas[selected_provider].values():
                        for model in quota_data.models:
                            # Avoid duplicates by name, but keep the one with the best (lowest) usage
                            existing = next((m for m in model_list if m.name == model.name), None)
                            if existing is None:
                                model_list.append(model)
                            else:
                                # If we have a model with better (lower) usage, prefer it
                                # Use -1 (unknown) as worst case
                                existing_percentage = existing.percentage if existing.percentage >= 0 else float('inf')
                                model_percentage = model.percentage if model.percentage >= 0 else float('inf')
                                if model_percentage < existing_percentage:
                                    model_list.remove(existing)
                                    model_list.append(model)

                    # Sort by usage (percentage) ASC, then by name ASC
                    # Models with -1 (unknown) percentage go last
                    def sort_key(m):
                        # Use a large number for unknown percentages so they sort last
                        percentage = m.percentage if m.percentage >= 0 else float('inf')
                        return (percentage, m.name.lower())

                    sorted_models = sorted(model_list, key=sort_key)

                    # Add sorted model names to dropdown
                    for model in sorted_models:
                        self.model_filter.addItem(model.name)
            else:
                # Collect all unique model objects across all providers and accounts
                # Use a dict to track best (lowest) usage per model name
                model_dict = {}
                for account_quotas in self.view_model.provider_quotas.values():
                    for quota_data in account_quotas.values():
                        for model in quota_data.models:
                            # Keep the model with the best (lowest) usage percentage
                            if model.name not in model_dict:
                                model_dict[model.name] = model
                            else:
                                existing = model_dict[model.name]
                                # Prefer model with lower usage (but not -1 if we have a valid one)
                                existing_percentage = existing.percentage if existing.percentage >= 0 else float('inf')
                                model_percentage = model.percentage if model.percentage >= 0 else float('inf')
                                if model_percentage < existing_percentage:
                                    model_dict[model.name] = model

                # Convert to list and sort by usage (percentage) ASC, then by name ASC
                model_list = list(model_dict.values())

                def sort_key(m):
                    # Use a large number for unknown percentages so they sort last
                    percentage = m.percentage if m.percentage >= 0 else float('inf')
                    return (percentage, m.name.lower())

                sorted_models = sorted(model_list, key=sort_key)

                # Add sorted model names to dropdown
                for model in sorted_models:
                    self.model_filter.addItem(model.name)

            # Restore selection if still available
            index = self.model_filter.findText(current_text)
            if index >= 0:
                self.model_filter.setCurrentIndex(index)
            else:
                # If current text not found, default to "All Models"
                self.model_filter.setCurrentIndex(0)
        finally:
            self.model_filter.blockSignals(False)

    def _update_quota_display(self) -> None:
        """Update the quota table."""
        self.quota_table.setRowCount(0)

        if not self.view_model or not self.view_model.provider_quotas:
            self.quota_status_label.setText("No quota data available. Click Refresh to load.")
            self.quota_status_label.show()
            self.quota_table.hide()
            return

        self.quota_status_label.hide()
        self.quota_table.show()

        # Get filter values
        selected_provider_text = self.provider_filter.currentText()
        account_filter_text = self.account_filter.currentText()
        model_filter_text = self.model_filter.currentText()

        # Get selected provider
        selected_provider = None
        if selected_provider_text != "All Providers":
            for provider in self.view_model.provider_quotas.keys():
                if provider.display_name == selected_provider_text:
                    selected_provider = provider
                    break

        # Group by provider
        provider_data = {}
        total_rows = 0

        for provider, account_quotas in self.view_model.provider_quotas.items():
            if selected_provider and provider != selected_provider:
                continue

            if not account_quotas:
                continue

            provider_rows = []
            for account_key, quota_data in account_quotas.items():
                # Filter by account (exact match or "All Accounts")
                if account_filter_text != "All Accounts" and account_key != account_filter_text:
                    continue

                # Show account even if no models (with "No model data" indicator)
                if not quota_data.models:
                    # Add a placeholder row to show the account exists
                    provider_rows.append({
                        'provider': provider,
                        'account': account_key,
                        'model': None,  # No model data
                        'quota_data': quota_data
                    })
                    total_rows += 1
                    continue

                for model in quota_data.models:
                    # Filter by model (exact match or "All Models")
                    if model_filter_text != "All Models" and model.name != model_filter_text:
                        continue

                    # Filter out ignored models
                    if model.name in self._ignored_models:
                        continue

                    provider_rows.append({
                        'provider': provider,
                        'account': account_key,
                        'model': model,
                        'quota_data': quota_data
                    })
                    total_rows += 1

            if provider_rows:
                provider_data[provider] = provider_rows

        # Collect all rows from all providers into a single list for sorting
        all_rows = []
        for provider, provider_rows in provider_data.items():
            all_rows.extend(provider_rows)

        # Sort by: Provider (display_name), Account, Usage ASC (percentage), Model ASC (name)
        def sort_key(item_data):
            provider = item_data['provider']
            account_key = item_data['account']
            model = item_data['model']

            # Provider name (for sorting)
            provider_name = provider.display_name.lower()

            # Account name (for sorting)
            account_name = account_key.lower()

            # Usage percentage (ASC - lowest first)
            # Use -1 (unknown) as float('inf') so they sort last
            if model and model.percentage is not None and model.percentage >= 0:
                usage_percentage = model.percentage
            else:
                usage_percentage = float('inf')

            # Model name (ASC - alphabetical)
            if model and model.name:
                model_name = model.name.lower()
            else:
                model_name = ""  # Empty string for "No model data" rows

            return (provider_name, account_name, usage_percentage, model_name)

        # Sort all rows
        sorted_rows = sorted(all_rows, key=sort_key)

        # Populate table with sorted rows
        row = 0
        for item_data in sorted_rows:
                self.quota_table.insertRow(row)

                provider = item_data['provider']
                account_key = item_data['account']

                # Check for subscription info
                subscription_info = None
                if provider in self.view_model.subscription_infos:
                    subscription_info = self.view_model.subscription_infos[provider].get(account_key)

                # Provider
                provider_item = QTableWidgetItem(provider.display_name)
                provider_item.setFont(QFont("", -1, QFont.Weight.Bold))
                self.quota_table.setItem(row, 0, provider_item)

                # Account (with subscription badge if available)
                account_text = account_key
                subscription_details = []

                # Check subscription info from view model (for Antigravity, etc.)
                # Only add if we have valid tier info (not "Unknown")
                if subscription_info:
                    tier_name = subscription_info.tier_display_name
                    # Don't show "Unknown" - it doesn't make sense to the user
                    if tier_name and tier_name != "Unknown" and tier_name != "unknown":
                        subscription_details.append(tier_name)

                # Check plan type from quota data (for Cursor, etc.)
                quota_data = item_data['quota_data']
                if quota_data.plan_type:
                    subscription_details.append(quota_data.plan_type)

                # Add subscription details to account text
                # Only show if we have meaningful subscription info
                if subscription_details:
                    # Use the first available subscription info
                    account_text = f"{account_text} ({subscription_details[0]})"

                # Add subscription cap if available (from plan usage limit)
                cap_info = []
                for model in quota_data.models:
                    if model.name == "Plan Usage" and model.limit:
                        cap_info.append(f"Cap: {model.limit}")
                        break

                # Create account item with tooltip showing full details
                account_item = QTableWidgetItem(account_text)
                tooltip_parts = [account_key]
                if subscription_details:
                    tooltip_parts.append(f"Subscription: {', '.join(subscription_details)}")
                if quota_data.subscription_status:
                    tooltip_parts.append(f"Status: {quota_data.subscription_status}")
                if cap_info:
                    tooltip_parts.append(cap_info[0])
                account_item.setToolTip("\n".join(tooltip_parts))

                # Color coding for paid tiers
                if subscription_info and subscription_info.is_paid_tier:
                    account_item.setForeground(QColor(0, 128, 0))  # Green for paid tiers
                elif quota_data.plan_type and ("pro" in quota_data.plan_type.lower() or "ultra" in quota_data.plan_type.lower()):
                    account_item.setForeground(QColor(0, 128, 0))  # Green for paid Cursor plans

                self.quota_table.setItem(row, 1, account_item)

                # Model
                model = item_data['model']
                if model is None:
                    # No model data available
                    model_item = QTableWidgetItem("No model data")
                    model_item.setForeground(QColor(128, 128, 128))  # Gray
                    self.quota_table.setItem(row, 2, model_item)

                    # Usage percentage - N/A
                    self.quota_table.setItem(row, 3, QTableWidgetItem("N/A"))

                    # Status
                    status_item = QTableWidgetItem("No data available")
                    status_item.setForeground(QColor(128, 128, 128))  # Gray
                    self.quota_table.setItem(row, 4, status_item)
                    
                    # No model - empty star column
                    star_item = QTableWidgetItem("")
                    self.quota_table.setItem(row, 5, star_item)

                    row += 1
                    continue

                model_item = QTableWidgetItem(model.name)
                self.quota_table.setItem(row, 2, model_item)

                # Usage column - only show percentage
                quota_data = item_data['quota_data']
                if model.percentage >= 0:
                    usage_text = f"{model.percentage:.1f}%"
                    tooltip_parts = [f"Usage: {model.percentage:.1f}%"]

                    # Add used if available for tooltip
                    if model.used is not None:
                        tooltip_parts.append(f"Used: {model.used:,}")

                    usage_item = QTableWidgetItem(usage_text)
                    usage_item.setToolTip("\n".join(tooltip_parts))

                    # Use color-coded status based on usage percentage
                    # Dark green if usage >= 60%, Orange if >= 20% < 60%, Red if < 20%
                    status_color = get_quota_status_color(model.percentage)
                    usage_item.setForeground(status_color)
                    self.quota_table.setItem(row, 3, usage_item)
                else:
                    # Percentage is -1 (unknown/unavailable)
                    # For Gemini CLI, show a more descriptive message
                    if model.name == "gemini-quota":
                        usage_item = QTableWidgetItem("Quota unavailable")
                        usage_item.setForeground(QColor(128, 128, 128))  # Gray
                        usage_item.setToolTip("Gemini CLI doesn't have a public quota API. Account is connected but usage data is not available.")
                    else:
                        usage_item = QTableWidgetItem("N/A")
                    self.quota_table.setItem(row, 3, usage_item)

                # Status column - show connection status, cap, remaining, and reset time
                status_parts = []
                tooltip_parts = []

                if quota_data.models:
                    # Calculate highest usage percentage across all models for status color
                    usage_percentages = [m.percentage for m in quota_data.models if m.percentage >= 0]
                    if usage_percentages:
                        highest_usage = max(usage_percentages)
                        status_color = get_quota_status_color(highest_usage)
                        status_text = "✓ Available"
                        status_parts.append(status_text)
                    else:
                        # All models have percentage < 0 (unknown/unavailable quota)
                        # Check if this is Gemini CLI (which doesn't have a public quota API)
                        has_gemini_quota = any(m.name == "gemini-quota" for m in quota_data.models)
                        if has_gemini_quota:
                            status_text = "Connected (quota unavailable)"
                            status_color = QColor(128, 128, 128)  # Gray - indicates info unavailable
                        else:
                            status_text = "Connected"
                            status_color = QColor(16, 185, 129)  # Dark green - account is connected
                        status_parts.append(status_text)

                    # Add cap (limit) if available for this specific model
                    if model.limit is not None:
                        status_parts.append(f"Cap: {model.limit:,}")
                        tooltip_parts.append(f"Cap: {model.limit:,}")

                    # Add remaining credits if available for this specific model
                    if model.remaining is not None:
                        status_parts.append(f"Remaining: {model.remaining:,}")
                        tooltip_parts.append(f"Remaining: {model.remaining:,}")
                    elif model.used is not None and model.limit is not None:
                        # Calculate remaining if we have used and limit
                        remaining = model.limit - model.used
                        if remaining >= 0:
                            status_parts.append(f"Remaining: {remaining:,}")
                            tooltip_parts.append(f"Remaining: {remaining:,}")

                    # Add reset time if available for this specific model
                    if model.reset_time:
                        # Format the ISO timestamp to local time for display
                        try:
                            from datetime import datetime
                            reset_dt = datetime.fromisoformat(model.reset_time.replace('Z', '+00:00'))
                            reset_local = to_local_dt(reset_dt)
                            reset_formatted = reset_local.strftime("%b %d, %H:%M") if reset_local else model.reset_time
                            status_parts.append(f"Resets: {reset_formatted}")
                            tooltip_parts.append(f"Reset Time: {reset_formatted}")
                        except Exception:
                            # If parsing fails, just show the raw value
                            status_parts.append(f"Resets: {model.reset_time}")
                            tooltip_parts.append(f"Reset Time: {model.reset_time}")

                    # Add subscription cap if available (from plan usage) - only if not already added
                    if not any("Cap:" in part for part in status_parts):
                        for plan_model in quota_data.models:
                            if plan_model.name == "Plan Usage" and plan_model.limit:
                                status_parts.append(f"Cap: {plan_model.limit:,}")
                                tooltip_parts.append(f"Plan Usage Cap: {plan_model.limit:,}")
                                break
                else:
                    status_text = "No data"
                    status_parts.append(status_text)
                    status_color = QColor(128, 128, 128)  # Gray

                # Add subscription info to tooltip
                # Only show if we have valid tier info (not "Unknown")
                if subscription_info:
                    tier_name = subscription_info.tier_display_name
                    # Only add to tooltip if tier name is meaningful
                    if tier_name and tier_name != "Unknown" and tier_name != "unknown":
                        tooltip_parts.append(f"Subscription Tier: {tier_name}")
                        if subscription_info.tier_description:
                            tooltip_parts.append(f"Description: {subscription_info.tier_description}")
                    # Always show project/GCP info if available (these are useful even without tier)
                    if subscription_info.gcp_managed is not None:
                        tooltip_parts.append(f"GCP Managed: {subscription_info.gcp_managed}")
                    if subscription_info.cloudaicompanion_project:
                        tooltip_parts.append(f"Project: {subscription_info.cloudaicompanion_project}")
                if quota_data.plan_type:
                    tooltip_parts.append(f"Plan: {quota_data.plan_type}")
                if quota_data.subscription_status:
                    tooltip_parts.append(f"Status: {quota_data.subscription_status}")

                status_display = " | ".join(status_parts)
                status_item = QTableWidgetItem(status_display)
                status_item.setForeground(status_color)

                if tooltip_parts:
                    status_item.setToolTip("\n".join(tooltip_parts))

                self.quota_table.setItem(row, 4, status_item)
                
                # Favorite star indicator
                model = item_data['model']
                if model:  # Only add favorite key if we have a model
                    favorite_key = self._get_favorite_key(provider, account_key, model.name)
                    is_favorite = favorite_key in self._favorites
                    star_item = QTableWidgetItem("⭐" if is_favorite else "")
                    star_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if is_favorite:
                        star_item.setForeground(QColor(255, 193, 7))  # Gold color
                    self.quota_table.setItem(row, 5, star_item)
                    
                    # Store favorite key in provider item data for context menu
                    provider_item.setData(Qt.ItemDataRole.UserRole, favorite_key)
                else:
                    # No model - empty star column
                    star_item = QTableWidgetItem("")
                    self.quota_table.setItem(row, 5, star_item)

                row += 1

        # Set maximum column widths after populating data
        # This ensures columns fit content but don't get too wide
        if total_rows > 0:
            # Set individual column max widths (in pixels)
            # Provider column: max 150px
            if self.quota_table.columnWidth(0) > 150:
                self.quota_table.setColumnWidth(0, 150)
            # Account column: max 200px
            if self.quota_table.columnWidth(1) > 200:
                self.quota_table.setColumnWidth(1, 200)
            # Model column: max 200px
            if self.quota_table.columnWidth(2) > 200:
                self.quota_table.setColumnWidth(2, 200)
            # Usage column: max 100px (just percentage)
            if self.quota_table.columnWidth(3) > 100:
                self.quota_table.setColumnWidth(3, 100)
            # Status column will stretch to fill remaining space

        if total_rows == 0:
            self.quota_status_label.setText("No quota data matches the current filters.")
            self.quota_status_label.show()
            self.quota_table.hide()

        # Force immediate repaint to ensure UI updates are visible
        # This is critical when updates come from background threads via callbacks
        self.quota_table.viewport().update()
        self.quota_table.update()


    def _load_ignored_models(self) -> None:
        """Load ignored models list from settings."""
        if not self.view_model:
            self._ignored_models = set()
            return

        ignored_models_json = self.view_model.settings.get("ignoredModels", "[]")
        try:
            import json
            ignored_list = json.loads(ignored_models_json)
            self._ignored_models = set(ignored_list)
        except Exception as e:
            print(f"[Dashboard] Error loading ignored models: {e}")
            self._ignored_models = set()

    def _save_ignored_models(self) -> None:
        """Save ignored models list to settings."""
        if not self.view_model:
            return

        try:
            import json
            ignored_list = list(self._ignored_models)
            self.view_model.settings.set("ignoredModels", json.dumps(ignored_list))
        except Exception as e:
            print(f"[Dashboard] Error saving ignored models: {e}")

    def _on_ignore_models_clicked(self) -> None:
        """Open dialog to select models to ignore."""
        if not self.view_model or not self.view_model.provider_quotas:
            return

        # Collect all unique model names
        all_models = set()
        for account_quotas in self.view_model.provider_quotas.values():
            for quota_data in account_quotas.values():
                for model in quota_data.models:
                    all_models.add(model.name)

        if not all_models:
            show_message_box(
                self,
                "No Models",
                "No models available to ignore.",
                QMessageBox.Icon.Information
            )
            return

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Ignore Models")
        dialog.setModal(True)
        dialog.resize(400, 500)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Instructions
        instructions = QLabel("Select models to hide from the quota table:")
        instructions.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(instructions)

        # List widget with checkboxes
        model_list = QListWidget()
        model_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        # Sort models alphabetically
        sorted_models = sorted(all_models)

        for model_name in sorted_models:
            item = QListWidgetItem(model_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Check if model is currently ignored
            if model_name in self._ignored_models:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            model_list.addItem(item)

        layout.addWidget(model_list)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update ignored models set
            self._ignored_models.clear()
            for i in range(model_list.count()):
                item = model_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    self._ignored_models.add(item.text())

            # Save to settings
            self._save_ignored_models()

            # Refresh display
            self._update_quota_display()


    def refresh(self):
        """Refresh the display.

        Note: This method is called by the auto-refresh timer.
        It updates the display with current data from the view model.
        For fresh data, ensure refresh_data() is called in the view model.
        """
        self._update_display()
    
    def _get_favorite_key(self, provider: AIProvider, account: str, model: str) -> str:
        """Generate a unique key for a favorite entry."""
        return f"{provider.value}:{account}:{model}"
    
    def _has_favorite_models(self, provider: AIProvider, account: str) -> bool:
        """Check if an account has any favorite models."""
        if not self.view_model or not self.view_model.provider_quotas:
            return False
        
        if provider not in self.view_model.provider_quotas:
            return False
        
        account_quotas = self.view_model.provider_quotas[provider].get(account)
        if not account_quotas or not account_quotas.models:
            return False
        
        # Check if any model for this account is in favorites
        for model in account_quotas.models:
            favorite_key = self._get_favorite_key(provider, account, model.name)
            if favorite_key in self._favorites:
                return True
        
        return False
    
    def _sort_accounts_with_favorites_first(self, provider: AIProvider, accounts: list[str]) -> list[str]:
        """Sort accounts so that accounts with favorite models appear first."""
        accounts_with_favorites = []
        accounts_without_favorites = []
        
        for account in accounts:
            if self._has_favorite_models(provider, account):
                accounts_with_favorites.append(account)
            else:
                accounts_without_favorites.append(account)
        
        # Sort each group alphabetically
        accounts_with_favorites.sort()
        accounts_without_favorites.sort()
        
        # Return favorites first, then others
        return accounts_with_favorites + accounts_without_favorites
    
    def _load_favorites(self) -> set[str]:
        """Load favorites from settings."""
        if not self.view_model:
            return set()
        favorites = self.view_model.settings.get("quotaFavorites", [])
        favorites_set = set(favorites) if isinstance(favorites, list) else set()
        return favorites_set
    
    def _save_favorites(self):
        """Save favorites to settings."""
        if not self.view_model:
            return
        # Persist favorites to settings immediately
        self.view_model.settings.set("quotaFavorites", list(self._favorites))
    
    def _add_to_favorites(self, favorite_key: str):
        """Add an entry to favorites."""
        self._favorites.add(favorite_key)
        self._save_favorites()
        self._update_quota_display()
        self._update_favorites_display()
    
    def _remove_from_favorites(self, favorite_key: str):
        """Remove an entry from favorites."""
        self._favorites.discard(favorite_key)
        self._save_favorites()
        self._update_quota_display()
        self._update_favorites_display()
    
    def _on_quota_table_context_menu(self, position):
        """Show context menu for the quota table."""
        item = self.quota_table.itemAt(position)
        if not item:
            return
        
        row = item.row()
        provider_item = self.quota_table.item(row, 0)
        if not provider_item:
            return
        
        favorite_key = provider_item.data(Qt.ItemDataRole.UserRole)
        if not favorite_key:
            return
        
        menu = QMenu(self)
        is_favorite = favorite_key in self._favorites
        
        if is_favorite:
            remove_action = QAction("Remove from Favorites", self)
            remove_action.triggered.connect(lambda: self._remove_from_favorites(favorite_key))
            menu.addAction(remove_action)
        else:
            add_action = QAction("Add to Favorites", self)
            add_action.triggered.connect(lambda: self._add_to_favorites(favorite_key))
            menu.addAction(add_action)
        
        menu.exec(self.quota_table.viewport().mapToGlobal(position))
    
    def _on_favorites_table_context_menu(self, position):
        """Show context menu for the favorites table."""
        item = self.favorites_table.itemAt(position)
        if not item:
            return
        
        row = item.row()
        provider_item = self.favorites_table.item(row, 0)
        if not provider_item:
            return
        
        favorite_key = provider_item.data(Qt.ItemDataRole.UserRole)
        if not favorite_key:
            return
        
        menu = QMenu(self)
        remove_action = QAction("Remove from Favorites", self)
        remove_action.triggered.connect(lambda: self._remove_from_favorites(favorite_key))
        menu.addAction(remove_action)
        
        menu.exec(self.favorites_table.viewport().mapToGlobal(position))
    
    def _on_quota_tab_changed(self, index: int):
        """Handle quota tab change."""
        if index == 0:  # Favorites tab (now first)
            self._update_favorites_display()
    
    def _update_favorites_display(self):
        """Update the favorites table."""
        # Clear table
        self.favorites_table.setRowCount(0)
        
        if not self.view_model or not self.view_model.provider_quotas:
            self.favorites_status_label.setText("No quota data available. Click Refresh to load.")
            self.favorites_status_label.show()
            self.favorites_table.hide()
            return
        
        if not self._favorites:
            self.favorites_status_label.setText("No favorites yet. Right-click on a row in the 'All' tab to add to favorites.")
            self.favorites_status_label.show()
            self.favorites_table.hide()
            return
        
        # We have favorites, hide status label and show table
        self.favorites_status_label.hide()
        self.favorites_table.show()
        
        # Collect favorite rows
        favorite_rows = []
        for provider, account_quotas in self.view_model.provider_quotas.items():
            for account_key, quota_data in account_quotas.items():
                for model in quota_data.models:
                    favorite_key = self._get_favorite_key(provider, account_key, model.name)
                    if favorite_key in self._favorites:
                        favorite_rows.append({
                            'provider': provider,
                            'account': account_key,
                            'model': model,
                            'quota_data': quota_data,
                            'favorite_key': favorite_key
                        })
        
        # Sort by provider, then account, then usage, then model (same as main table)
        def sort_key(item_data):
            provider = item_data['provider']
            account_key = item_data['account']
            model = item_data['model']
            
            provider_name = provider.display_name.lower()
            account_name = account_key.lower()
            
            if model and model.percentage is not None and model.percentage >= 0:
                usage_percentage = model.percentage
            else:
                usage_percentage = float('inf')
            
            if model and model.name:
                model_name = model.name.lower()
            else:
                model_name = ""
            
            return (provider_name, account_name, usage_percentage, model_name)
        
        favorite_rows.sort(key=sort_key)
        
        # Populate table
        row = 0
        for item_data in favorite_rows:
            self.favorites_table.insertRow(row)
            
            provider = item_data['provider']
            account_key = item_data['account']
            
            # Check for subscription info
            subscription_info = None
            if provider in self.view_model.subscription_infos:
                subscription_info = self.view_model.subscription_infos[provider].get(account_key)
            
            # Provider
            provider_item = QTableWidgetItem(provider.display_name)
            provider_item.setFont(QFont("", -1, QFont.Weight.Bold))
            provider_item.setData(Qt.ItemDataRole.UserRole, item_data['favorite_key'])
            self.favorites_table.setItem(row, 0, provider_item)
            
            # Account
            account_text = account_key
            subscription_details = []
            if subscription_info:
                tier_name = subscription_info.tier_display_name
                if tier_name and tier_name != "Unknown" and tier_name != "unknown":
                    subscription_details.append(tier_name)
            
            quota_data = item_data['quota_data']
            if quota_data.plan_type:
                subscription_details.append(quota_data.plan_type)
            
            if subscription_details:
                account_text = f"{account_text} ({subscription_details[0]})"
            
            account_item = QTableWidgetItem(account_text)
            if subscription_info and subscription_info.is_paid_tier:
                account_item.setForeground(QColor(0, 128, 0))  # Green for paid tiers
            self.favorites_table.setItem(row, 1, account_item)
            
            # Model
            model = item_data['model']
            model_item = QTableWidgetItem(model.name)
            self.favorites_table.setItem(row, 2, model_item)
            
            # Usage percentage
            if model.percentage >= 0:
                usage_text = f"{model.percentage:.1f}%"
                usage_item = QTableWidgetItem(usage_text)
                status_color = get_quota_status_color(model.percentage)
                usage_item.setForeground(status_color)
            else:
                usage_text = "Unknown"
                usage_item = QTableWidgetItem(usage_text)
                usage_item.setForeground(Qt.GlobalColor.gray)
            self.favorites_table.setItem(row, 3, usage_item)
            
            # Status column - show connection status, cap, remaining, and reset time
            status_parts = []
            tooltip_parts = []
            
            if quota_data.models:
                # Calculate highest usage percentage across all models for status color
                usage_percentages = [m.percentage for m in quota_data.models if m.percentage >= 0]
                if usage_percentages:
                    highest_usage = max(usage_percentages)
                    status_color = get_quota_status_color(highest_usage)
                    status_text = "✓ Available"
                    status_parts.append(status_text)
                else:
                    # All models have percentage < 0 (unknown/unavailable quota)
                    status_text = "✓ Available"
                    status_parts.append(status_text)
                    status_color = QColor(16, 185, 129)  # Dark green
                
                # Add reset time if available for this specific model
                if model.reset_time:
                    try:
                        from datetime import datetime
                        reset_dt = datetime.fromisoformat(model.reset_time.replace('Z', '+00:00'))
                        reset_local = to_local_dt(reset_dt)
                        reset_formatted = reset_local.strftime("%b %d, %H:%M") if reset_local else model.reset_time
                        tooltip_parts.append(f"Reset Time: {reset_formatted}")
                        # Add to status text if space allows
                        if len(status_parts) < 2:
                            status_parts.append(f"Resets: {reset_formatted}")
                    except Exception:
                        # If parsing fails, just add raw reset time
                        tooltip_parts.append(f"Reset Time: {model.reset_time}")
                        status_parts.append(f"Resets: {model.reset_time}")
                
                # Add remaining quota if available
                if model.remaining is not None:
                    tooltip_parts.append(f"Remaining: {model.remaining:,}")
                
                # Add limit if available
                if model.limit is not None:
                    tooltip_parts.append(f"Limit: {model.limit:,}")
                
                # Create status item with combined text
                status_text = " | ".join(status_parts) if status_parts else "✓ Available"
                status_item = QTableWidgetItem(status_text)
                if usage_percentages:
                    status_item.setForeground(status_color)
                else:
                    status_item.setForeground(QColor(16, 185, 129))  # Dark green
                
                # Add tooltip with detailed information
                if tooltip_parts:
                    status_item.setToolTip("\n".join(tooltip_parts))
            else:
                status_text = "No data"
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(Qt.GlobalColor.gray)
            
            self.favorites_table.setItem(row, 4, status_item)
            
            # Favorite star (always shown in favorites tab)
            star_item = QTableWidgetItem("⭐")
            star_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            star_item.setForeground(QColor(255, 193, 7))  # Gold color
            self.favorites_table.setItem(row, 5, star_item)
            
            row += 1
