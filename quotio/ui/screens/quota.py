"""Quota screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QHBoxLayout, QGroupBox, QScrollArea,
    QFrame, QGridLayout, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPen
from ...models.subscription import SubscriptionInfo
import asyncio
from typing import Optional

from ...models.providers import AIProvider
from ..utils import get_quota_status_color, get_agent_status_color

# Import AIProvider for filtering


def run_async_coro(coro):
    """Run an async coroutine, creating task if loop is running."""
    # Import from main_window to use the shared thread-safe function
    from ..main_window import run_async_coro as main_run_async_coro
    return main_run_async_coro(coro)


class QuotaScreen(QWidget):
    """Screen showing quota information."""
    
    def __init__(self, view_model=None, agent_viewmodel=None):
        """Initialize the quota screen."""
        super().__init__()
        self.view_model = view_model
        self.agent_viewmodel = agent_viewmodel
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        self.setLayout(layout)
        
        # Title and refresh button
        header_layout = QHBoxLayout()
        title = QLabel("Quota & Agent Status")
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
        
        layout.addLayout(header_layout)
        
        # Filter controls
        filter_group = QGroupBox("Filters")
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        # Provider filter
        filter_layout.addWidget(QLabel("Provider:"))
        self.provider_filter = QComboBox()
        self.provider_filter.addItem("All Providers")
        self.provider_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.provider_filter)
        
        # Account filter
        filter_layout.addWidget(QLabel("Account:"))
        self.account_filter = QLineEdit()
        self.account_filter.setPlaceholderText("Filter by account...")
        self.account_filter.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.account_filter)
        
        # Model filter
        filter_layout.addWidget(QLabel("Model:"))
        self.model_filter = QLineEdit()
        self.model_filter.setPlaceholderText("Filter by model...")
        self.model_filter.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.model_filter)
        
        # Clear filters button
        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        filter_layout.addWidget(self.clear_filters_button)
        
        filter_layout.addStretch()
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.setSpacing(20)
        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # Quota Section
        quota_group = QGroupBox("Provider Quotas")
        quota_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        quota_layout = QVBoxLayout()
        quota_layout.setSpacing(12)
        
        self.quota_status_label = QLabel("No quota data available")
        self.quota_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quota_layout.addWidget(self.quota_status_label)
        
        # Quota table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Provider", "Account", "Model", "Usage %", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
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
        quota_layout.addWidget(self.table)
        
        quota_group.setLayout(quota_layout)
        scroll_layout.addWidget(quota_group)
        
        scroll_layout.addStretch()
        
        # Filter state
        self._filtered_data = []
        
        # Update display
        self._update_display()
    
    def _update_display(self):
        """Update the quota table and agent status."""
        if not self.view_model:
            return
        
        # Update provider filter dropdown
        self._update_provider_filter()
        
        # Update quota display
        self._update_quota_display()
    
    def _update_provider_filter(self):
        """Update provider filter dropdown with available providers."""
        if not self.view_model:
            return
        
        current_text = self.provider_filter.currentText()
        self.provider_filter.clear()
        self.provider_filter.addItem("All Providers")
        
        # Add all providers that have quota data
        for provider in sorted(self.view_model.provider_quotas.keys(), key=lambda p: p.display_name):
            self.provider_filter.addItem(provider.display_name)
        
        # Restore selection if still available
        index = self.provider_filter.findText(current_text)
        if index >= 0:
            self.provider_filter.setCurrentIndex(index)
    
    def _on_filter_changed(self):
        """Handle filter changes."""
        self._update_quota_display()
    
    def _clear_filters(self):
        """Clear all filters."""
        self.provider_filter.setCurrentIndex(0)  # "All Providers"
        self.account_filter.clear()
        self.model_filter.clear()
        self._update_quota_display()
    
    def _update_quota_display(self):
        """Update the quota table."""
        # Clear table
        self.table.setRowCount(0)
        
        if not self.view_model or not self.view_model.provider_quotas:
            self.quota_status_label.setText("No quota data available. Click Refresh to load.")
            return
        
        # Get filter values
        selected_provider_text = self.provider_filter.currentText()
        account_filter_text = self.account_filter.text().strip().lower()
        model_filter_text = self.model_filter.text().strip().lower()
        
        # Get selected provider
        selected_provider = None
        if selected_provider_text != "All Providers":
            # Find provider by display name
            for provider in self.view_model.provider_quotas.keys():
                if provider.display_name == selected_provider_text:
                    selected_provider = provider
                    break
        
        # Group by provider for better organization
        provider_data = {}
        total_rows = 0
        
        for provider, account_quotas in self.view_model.provider_quotas.items():
            # Apply provider filter
            if selected_provider and provider != selected_provider:
                continue
            
            if not account_quotas:
                continue
            
            provider_rows = []
            for account_key, quota_data in account_quotas.items():
                # Apply account filter
                if account_filter_text and account_filter_text not in account_key.lower():
                    continue
                
                for model in quota_data.models:
                    # Apply model filter
                    if model_filter_text and model_filter_text not in model.name.lower():
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
        
        # Debug: Print what we found
        print(f"[Quota] Displaying {total_rows} rows after filtering")
        if AIProvider.CODEX in self.view_model.provider_quotas:
            codex_quotas = self.view_model.provider_quotas[AIProvider.CODEX]
            print(f"[Quota] Codex has {len(codex_quotas)} account(s) in provider_quotas")
            for account, quota_data in codex_quotas.items():
                print(f"[Quota]   - {account}: {len(quota_data.models)} model(s)")
        
        # Populate table
        row = 0
        for provider in sorted(provider_data.keys(), key=lambda p: p.display_name):
            provider_rows = provider_data[provider]
            
            for item_data in provider_rows:
                self.table.insertRow(row)
                
                provider = item_data['provider']
                account_key = item_data['account']
                
                # Check for subscription info
                subscription_info = None
                if provider in self.view_model.subscription_infos:
                    subscription_info = self.view_model.subscription_infos[provider].get(account_key)
                
                # Provider (with subscription badge if available)
                provider_item = QTableWidgetItem(provider.display_name)
                provider_item.setFont(QFont("", -1, QFont.Weight.Bold))
                self.table.setItem(row, 0, provider_item)
                
                # Account (with subscription badge if available)
                account_text = item_data['account']
                if subscription_info:
                    tier_name = subscription_info.tier_display_name
                    account_text = f"{account_text} ({tier_name})"
                account_item = QTableWidgetItem(account_text)
                if subscription_info and subscription_info.is_paid_tier:
                    account_item.setForeground(QColor(0, 128, 0))  # Green for paid tiers
                self.table.setItem(row, 1, account_item)
                
                # Model
                model_item = QTableWidgetItem(item_data['model'].name)
                self.table.setItem(row, 2, model_item)
                
                # Usage percentage with color-coded status
                model = item_data['model']
                if model.percentage >= 0:
                    usage_text = f"{model.percentage:.1f}%"
                    usage_item = QTableWidgetItem(usage_text)
                    # Use color-coded status based on usage percentage
                    # Dark green if usage >= 60%, Orange if >= 20% < 60%, Red if < 20%
                    status_color = get_quota_status_color(model.percentage)
                    usage_item.setForeground(status_color)
                else:
                    usage_text = "Unknown"
                    usage_item = QTableWidgetItem(usage_text)
                    usage_item.setForeground(Qt.GlobalColor.gray)
                
                self.table.setItem(row, 3, usage_item)
                
                # Status with color-coded indicator (based on highest usage across models)
                quota_data = item_data['quota_data']
                if quota_data.models:
                    # Calculate highest usage percentage across all models for status
                    usage_percentages = [m.percentage for m in quota_data.models if m.percentage >= 0]
                    if usage_percentages:
                        highest_usage = max(usage_percentages)
                        status_color = get_quota_status_color(highest_usage)
                        status_text = "✓ Available"
                        status_item = QTableWidgetItem(status_text)
                        status_item.setForeground(status_color)
                    else:
                        status_text = "✓ Available"
                        status_item = QTableWidgetItem(status_text)
                        status_item.setForeground(QColor(16, 185, 129))  # Dark green
                else:
                    status_text = "No data"
                    status_item = QTableWidgetItem(status_text)
                    status_item.setForeground(Qt.GlobalColor.gray)
                
                self.table.setItem(row, 4, status_item)
                row += 1
        
        # Update status
        if total_rows == 0:
            self.quota_status_label.setText("No quota data available. Click Refresh to load.")
        else:
            provider_count = len(provider_data)
            self.quota_status_label.setText(
                f"Showing {total_rows} quota entries across {provider_count} provider(s)"
            )
    
    def _on_refresh(self):
        """Handle refresh button click."""
        if self.view_model:
            async def refresh():
                try:
                    # Refresh auth files first if proxy is running
                    if self.view_model.proxy_manager.proxy_status.running and self.view_model.api_client:
                        try:
                            self.view_model.auth_files = await self.view_model.api_client.fetch_auth_files()
                            print(f"[Quota] Refreshed {len(self.view_model.auth_files)} auth files")
                        except Exception as e:
                            print(f"[Quota] Error refreshing auth files: {e}")
                    
                    # Refresh quotas
                    await self.view_model.refresh_quotas_unified()
                    
                    # Refresh agent statuses if available
                    
                    # Schedule UI update on main thread to avoid threading issues
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_display)
                except Exception as e:
                    print(f"[Quota] Error refreshing: {e}")
                    import traceback
                    traceback.print_exc()
                    # Schedule UI update on main thread to avoid threading issues
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_display)
            
            run_async_coro(refresh())
    
    def refresh(self):
        """Refresh the display."""
        self._update_display()
