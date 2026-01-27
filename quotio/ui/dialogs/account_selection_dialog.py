"""Account selection dialog with status information."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDialogButtonBox, QHeaderView, QWidget
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QColor, QFont, QMouseEvent
from typing import Optional, List, Dict

from ...models.auth import AuthFile
from ...models.providers import AIProvider
from ...models.subscription import SubscriptionInfo


class AccountSelectionDialog(QDialog):
    """Dialog for selecting an account with status information."""

    def __init__(self, parent=None, view_model=None, auth_files: List[AuthFile] = None, provider: AIProvider = None):
        """Initialize account selection dialog.

        Args:
            parent: Parent widget
            view_model: QuotaViewModel instance
            auth_files: List of auth files to choose from
            provider: AI Provider (for context)
        """
        super().__init__(parent)
        self.view_model = view_model
        self.auth_files = auth_files or []
        self.provider = provider
        self.selected_auth_file: Optional[AuthFile] = None
        self.expanded_rows: Dict[int, bool] = {}  # Track which rows are expanded

        self.setWindowTitle(f"Select Account - {provider.display_name if provider else 'Account'}")
        self.setModal(True)
        self.resize(900, 550)  # Increased size to accommodate larger text and better spacing

        self._setup_ui()
        self._populate_accounts()
        # Schedule column width adjustment after dialog is shown
        QTimer.singleShot(100, self._adjust_column_widths)

        # Also refresh when dialog is shown (in case data was already fetched)
        # Use showEvent to refresh when dialog becomes visible
        self._has_been_shown = False

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Header
        header_label = QLabel("Select an account to switch to:")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px;")
        layout.addWidget(header_label)

        # Table for accounts
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Account", "Status", "Subscription", "Quota", "Models"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)

        # Set minimum row height to accommodate multi-line model content
        self.table.verticalHeader().setDefaultSectionSize(100)  # Increased from default ~20px

        # Column widths will be set after populating data
        header = self.table.horizontalHeader()
        # Set all columns to ResizeToContents initially, we'll fix them after populating
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        # Models column will stretch to fill remaining space (set after width calculation)
        # Don't set minimum section size here - it interferes with width calculation

        layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Refresh account information from current data")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        button_layout.addWidget(self.refresh_button)

        button_layout.addStretch()

        # Standard dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

    def _populate_accounts(self):
        """Populate the table with account information."""
        if not self.view_model or not self.auth_files:
            return

        self.table.setRowCount(len(self.auth_files))

        # Get ignored models from settings
        ignored_models = self._get_ignored_models()

        # Get active account email if available
        active_email = None
        if self.view_model.antigravity_switcher and self.view_model.antigravity_switcher.current_active_account:
            active_email = self.view_model.antigravity_switcher.current_active_account.email

        # Get subscription info - read fresh from view model
        subscription_infos = {}
        if self.provider and self.provider in self.view_model.subscription_infos:
            subscription_infos = self.view_model.subscription_infos[self.provider].copy()  # Make a copy to ensure fresh read
            print(f"[AccountSelectionDialog] Loaded {len(subscription_infos)} subscription info(s) for {self.provider}")

        # Get quota data - read fresh from view model
        quota_data = {}
        if self.provider and self.provider in self.view_model.provider_quotas:
            quota_data = self.view_model.provider_quotas[self.provider].copy()  # Make a copy to ensure fresh read
            print(f"[AccountSelectionDialog] Loaded {len(quota_data)} quota data entry/entries for {self.provider}")

        for row, auth_file in enumerate(self.auth_files):
            # Account email/name
            account_display = auth_file.email or auth_file.account or auth_file.name or auth_file.id
            account_item = QTableWidgetItem(account_display)
            account_item.setData(Qt.ItemDataRole.UserRole, auth_file)
            self.table.setItem(row, 0, account_item)

            # Status (Active/Inactive)
            account_key = auth_file.quota_lookup_key
            is_active = False
            if active_email:
                # Compare emails (case-insensitive)
                is_active = (
                    active_email.lower() == account_key.lower() or
                    active_email.lower() == (auth_file.email or "").lower() or
                    active_email.lower() == (auth_file.account or "").lower()
                )

            status_text = "✓ Active" if is_active else "Inactive"
            status_item = QTableWidgetItem(status_text)
            if is_active:
                status_item.setForeground(QColor(0, 128, 0))  # Green
                status_item.setFont(QFont("", -1, QFont.Weight.Bold))
            else:
                status_item.setForeground(QColor(128, 128, 128))  # Gray
            self.table.setItem(row, 1, status_item)

            # Subscription tier
            subscription_info = subscription_infos.get(account_key)
            tier_text = "—"
            if subscription_info:
                tier_name = subscription_info.tier_display_name
                if tier_name and tier_name != "Unknown":
                    tier_text = tier_name
                    if subscription_info.is_paid_tier:
                        tier_text = f"💰 {tier_text}"

            subscription_item = QTableWidgetItem(tier_text)
            if subscription_info and subscription_info.is_paid_tier:
                subscription_item.setForeground(QColor(0, 128, 0))  # Green for paid tiers
            self.table.setItem(row, 2, subscription_item)

            # Quota percentage (if available) - exclude ignored models
            quota_text = "—"
            quota_info = quota_data.get(account_key)
            avg_percentage = None
            if quota_info and quota_info.models:
                # Get the first model's percentage, or average if multiple
                # Exclude ignored models from calculation
                percentages = [
                    m.percentage for m in quota_info.models
                    if m.percentage is not None and m.percentage >= 0 and m.name not in ignored_models
                ]
                if percentages:
                    avg_percentage = sum(percentages) / len(percentages)
                    quota_text = f"{avg_percentage:.1f}%"

                    # Color code based on percentage
                    quota_item = QTableWidgetItem(quota_text)
                    if avg_percentage > 50:
                        quota_item.setForeground(QColor(0, 128, 0))  # Green
                    elif avg_percentage > 20:
                        quota_item.setForeground(QColor(255, 165, 0))  # Orange
                    else:
                        quota_item.setForeground(QColor(255, 0, 0))  # Red
                    self.table.setItem(row, 3, quota_item)
                else:
                    quota_item = QTableWidgetItem(quota_text)
                    quota_item.setForeground(QColor(128, 128, 128))  # Gray
                    self.table.setItem(row, 3, quota_item)
            else:
                quota_item = QTableWidgetItem(quota_text)
                quota_item.setForeground(QColor(128, 128, 128))  # Gray
                self.table.setItem(row, 3, quota_item)

            # Models list (sorted by remaining percentage, ascending) - multi-line display
            # Exclude ignored models
            if quota_info and quota_info.models:
                # Filter models with valid percentage and exclude ignored models, then sort by percentage (ascending - lowest remaining first)
                valid_models = [
                    m for m in quota_info.models
                    if m.percentage is not None and m.percentage >= 0 and m.name not in ignored_models
                ]
                if valid_models:
                    # Sort by percentage ascending (lowest remaining first), then by name ascending
                    sorted_models = sorted(valid_models, key=lambda m: (m.percentage, m.name.lower()))

                    # Check if this row is expanded
                    is_expanded = self.expanded_rows.get(row, False)

                    # Show minimum 3 models, or all if expanded
                    min_models_to_show = 3
                    if is_expanded:
                        models_to_show = sorted_models
                        has_more = False
                    else:
                        models_to_show = sorted_models[:min_models_to_show]
                        has_more = len(sorted_models) > min_models_to_show

                    # Create models widget
                    models_widget = self._create_models_widget(
                        sorted_models, models_to_show, has_more, row, is_expanded
                    )
                    self.table.setCellWidget(row, 4, models_widget)

                    # Adjust row height based on expansion
                    if is_expanded:
                        # Calculate height needed: ~25px per model + padding
                        height_needed = max(100, len(models_to_show) * 25 + 20)
                        self.table.setRowHeight(row, height_needed)
                    else:
                        self.table.setRowHeight(row, 100)  # Default height
                    continue

            # No models available
            no_models_label = QLabel("—")
            no_models_label.setStyleSheet("color: #808080;")
            self.table.setCellWidget(row, 4, no_models_label)

        # Column widths will be adjusted after dialog is shown (via QTimer)

        # Select first row by default
        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def _adjust_column_widths(self):
        """Adjust column widths to fit content. Called after dialog is shown."""
        header = self.table.horizontalHeader()
        font_metrics = self.table.fontMetrics()

        # Calculate maximum width needed for each column by checking all content
        max_widths = [0, 0, 0, 0]  # Account, Status, Subscription, Quota

        # Check header widths first
        header_texts = ["Account", "Status", "Subscription", "Quota"]
        for col, header_text in enumerate(header_texts):
            header_width = font_metrics.horizontalAdvance(header_text) + 40  # Header padding
            max_widths[col] = max(max_widths[col], header_width)

        # Check all row content
        for row in range(self.table.rowCount()):
            # Account column
            account_item = self.table.item(row, 0)
            if account_item:
                text = account_item.text()
                width = font_metrics.horizontalAdvance(text) + 30  # Cell padding
                max_widths[0] = max(max_widths[0], width)

            # Status column
            status_item = self.table.item(row, 1)
            if status_item:
                text = status_item.text()
                width = font_metrics.horizontalAdvance(text) + 30
                max_widths[1] = max(max_widths[1], width)

            # Subscription column
            subscription_item = self.table.item(row, 2)
            if subscription_item:
                text = subscription_item.text()
                width = font_metrics.horizontalAdvance(text) + 30
                max_widths[2] = max(max_widths[2], width)

            # Quota column
            quota_item = self.table.item(row, 3)
            if quota_item:
                text = quota_item.text()
                width = font_metrics.horizontalAdvance(text) + 30
                max_widths[3] = max(max_widths[3], width)

        # Set explicit column widths with maximum limits
        # Account column: calculated width, max 200px
        account_width = min(max(max_widths[0], 100), 200)  # At least 100px, max 200px
        self.table.setColumnWidth(0, account_width)

        # Status column: calculated width, max 100px
        status_width = min(max(max_widths[1], 60), 100)  # At least 60px, max 100px
        self.table.setColumnWidth(1, status_width)

        # Subscription column: calculated width, max 150px
        subscription_width = min(max(max_widths[2], 80), 150)  # At least 80px, max 150px
        self.table.setColumnWidth(2, subscription_width)

        # Quota column: calculated width, max 80px
        quota_width = min(max(max_widths[3], 50), 80)  # At least 50px, max 80px
        self.table.setColumnWidth(3, quota_width)

        # Set resize modes: first 4 columns fixed, Models stretches
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # Account
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Status
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Subscription
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Quota
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Models - gets remaining space

        # Force update
        self.table.viewport().update()

    def _create_models_widget(self, all_models, models_to_show, has_more, row, is_expanded):
        """Create a widget displaying models with proper sizing."""
        models_widget = QWidget()
        models_layout = QVBoxLayout()
        models_layout.setContentsMargins(8, 6, 8, 6)  # Increased padding
        models_layout.setSpacing(4)  # Increased spacing between lines
        models_widget.setLayout(models_layout)

        # Set minimum size for the widget
        models_widget.setMinimumWidth(250)
        models_widget.setMinimumHeight(80 if not is_expanded else len(models_to_show) * 25 + 20)

        # Add model lines
        for model in models_to_show:
            model_name = model.name
            # Don't truncate if expanded, otherwise allow longer names
            if not is_expanded and len(model_name) > 45:
                model_name = model_name[:42] + "..."

            # Color code based on percentage with larger, readable font
            base_style = "font-size: 12px; padding: 2px 0px;"
            model_label = QLabel(f"• {model_name} ({model.percentage:.1f}%)")
            model_label.setWordWrap(False)  # Don't wrap, use ellipsis instead

            if model.percentage > 50:
                model_label.setStyleSheet(f"{base_style} color: #008000;")  # Green
            elif model.percentage > 20:
                model_label.setStyleSheet(f"{base_style} color: #FFA500;")  # Orange
            else:
                model_label.setStyleSheet(f"{base_style} color: #FF0000;")  # Red

            # Set size to fit content
            model_label.setMinimumHeight(20)
            model_label.setSizePolicy(
                model_label.sizePolicy().horizontalPolicy(),
                model_label.sizePolicy().verticalPolicy()
            )
            # Adjust width to fit text
            font_metrics = model_label.fontMetrics()
            text_width = font_metrics.horizontalAdvance(model_label.text())
            model_label.setMinimumWidth(min(text_width + 10, 400))  # Cap at 400px

            models_layout.addWidget(model_label)

        # Add "show more" or "show less" line
        if has_more or is_expanded:
            if is_expanded:
                more_text = "  ... show less"
            else:
                more_text = f"  ... +{len(all_models) - len(models_to_show)} more (click to expand)"

            more_label = QLabel(more_text)
            more_label.setStyleSheet(
                "font-size: 11px; color: #0066CC; font-style: italic; padding: 2px 0px; "
                "text-decoration: underline;"
            )
            more_label.setMinimumHeight(18)
            more_label.setCursor(Qt.CursorShape.PointingHandCursor)  # Set cursor via code, not CSS

            # Make it clickable
            def handle_click(event: QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._toggle_expand(row)

            more_label.mousePressEvent = handle_click
            models_layout.addWidget(more_label)

        models_layout.addStretch()
        return models_widget

    def _toggle_expand(self, row: int):
        """Toggle expansion state for a row and refresh the models widget."""
        # Toggle expansion state
        self.expanded_rows[row] = not self.expanded_rows.get(row, False)

        # Rebuild the models widget for this row
        if not self.view_model or not self.auth_files:
            return

        auth_file = self.auth_files[row]
        account_key = auth_file.quota_lookup_key

        # Get quota data
        quota_data = {}
        if self.provider and self.provider in self.view_model.provider_quotas:
            quota_data = self.view_model.provider_quotas[self.provider]

        quota_info = quota_data.get(account_key)
        if quota_info and quota_info.models:
            # Get ignored models from settings
            ignored_models = self._get_ignored_models()
            # Filter models with valid percentage and exclude ignored models
            valid_models = [
                m for m in quota_info.models
                if m.percentage is not None and m.percentage >= 0 and m.name not in ignored_models
            ]
            if valid_models:
                # Sort by percentage ascending (lowest remaining first), then by name ascending
                sorted_models = sorted(valid_models, key=lambda m: (m.percentage, m.name.lower()))
                is_expanded = self.expanded_rows.get(row, False)

                min_models_to_show = 3
                if is_expanded:
                    models_to_show = sorted_models
                    has_more = False
                else:
                    models_to_show = sorted_models[:min_models_to_show]
                    has_more = len(sorted_models) > min_models_to_show

                # Recreate the widget
                models_widget = self._create_models_widget(
                    sorted_models, models_to_show, has_more, row, is_expanded
                )
                self.table.setCellWidget(row, 4, models_widget)

                # Adjust row height
                if is_expanded:
                    height_needed = max(100, len(models_to_show) * 25 + 20)
                    self.table.setRowHeight(row, height_needed)
                else:
                    self.table.setRowHeight(row, 100)

    def _on_item_double_clicked(self, item):
        """Handle double-click on table item."""
        row = item.row()
        account_item = self.table.item(row, 0)
        if account_item:
            auth_file = account_item.data(Qt.ItemDataRole.UserRole)
            if auth_file:
                self.selected_auth_file = auth_file
                self.accept()

    def _on_accept(self):
        """Handle OK button click."""
        selected_items = self.table.selectedItems()
        if selected_items:
            # Get the account item from the first column
            account_item = self.table.item(selected_items[0].row(), 0)
            if account_item:
                auth_file = account_item.data(Qt.ItemDataRole.UserRole)
                if auth_file:
                    self.selected_auth_file = auth_file
                    self.accept()
                    return

        # If no selection, reject
        self.reject()

    def get_selected_account(self) -> Optional[AuthFile]:
        """Get the selected account."""
        return self.selected_auth_file

    def _on_refresh_clicked(self):
        """Handle refresh button click - refresh account information from current data."""
        print(f"[AccountSelectionDialog] Refresh button clicked")

        # Disable button while refreshing
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing...")

        # Set a timeout to re-enable the button if refresh takes too long (5 seconds)
        def timeout_refresh():
            if not self.refresh_button.isEnabled():
                print(f"[AccountSelectionDialog] Refresh timeout, re-enabling button")
                self.refresh_button.setEnabled(True)
                self.refresh_button.setText("Refresh")
        QTimer.singleShot(5000, timeout_refresh)

        # Refresh active account detection for Antigravity if applicable
        # This only reads the current status, doesn't trigger a new fetch
        if (self.provider == AIProvider.ANTIGRAVITY and
            self.view_model and
            self.view_model.antigravity_switcher):
            # Refresh active account detection asynchronously (reads current status)
            async def refresh_active():
                try:
                    await self.view_model.antigravity_switcher.detect_active_account()
                    print(f"[AccountSelectionDialog] Active account detection completed")
                except Exception as e:
                    print(f"[AccountSelectionDialog] Error refreshing active account: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # Always refresh display - use QTimer to ensure it runs in dialog's event loop
                    # Process events to ensure timer fires even in modal dialog
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                    QTimer.singleShot(50, self._refresh_account_display)

            # Use the same pattern as providers screen
            def run_async_coro(coro):
                from ..main_window import run_async_coro as main_run_async_coro
                return main_run_async_coro(coro)

            run_async_coro(refresh_active())
        else:
            # For other providers, just refresh display with current data immediately
            # Process events first to ensure any pending updates are processed
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            QTimer.singleShot(50, self._refresh_account_display)

    def _refresh_account_display(self):
        """Refresh the account display with current data."""
        print(f"[AccountSelectionDialog] Refreshing account display")

        try:
            if not self.table or not self.view_model or not self.auth_files:
                print(f"[AccountSelectionDialog] Dialog not ready for refresh")
                return

            # Debug: Log current data state
            if self.provider:
                quota_keys = list(self.view_model.provider_quotas.get(self.provider, {}).keys()) if self.provider in self.view_model.provider_quotas else []
                subscription_keys = list(self.view_model.subscription_infos.get(self.provider, {}).keys()) if self.provider in self.view_model.subscription_infos else []
                print(f"[AccountSelectionDialog] Provider: {self.provider}, Quota keys: {quota_keys}, Subscription keys: {subscription_keys}")

            # Save expanded state
            expanded_state = self.expanded_rows.copy()
            selected_row = self.table.currentRow()
            selected_auth_file = None
            if selected_row >= 0 and selected_row < self.table.rowCount():
                account_item = self.table.item(selected_row, 0)
                if account_item:
                    selected_auth_file = account_item.data(Qt.ItemDataRole.UserRole)

            # Clear the table completely to force fresh population
            self.table.setRowCount(0)

            # Remove old widgets
            for row in range(self.table.rowCount()):
                widget = self.table.cellWidget(row, 4)
                if widget:
                    self.table.removeCellWidget(row, 4)

            # Repopulate with fresh data from view model
            self._populate_accounts()

            # Restore expanded state
            self.expanded_rows = expanded_state
            for row, is_expanded in expanded_state.items():
                if is_expanded and row < self.table.rowCount():
                    self._toggle_expand(row)

            # Restore selection
            if selected_auth_file:
                for row in range(self.table.rowCount()):
                    account_item = self.table.item(row, 0)
                    if account_item and account_item.data(Qt.ItemDataRole.UserRole) == selected_auth_file:
                        self.table.selectRow(row)
                        break

            # Re-adjust column widths
            QTimer.singleShot(50, self._adjust_column_widths)

            # Force table update
            self.table.viewport().update()
            self.table.update()

            print(f"[AccountSelectionDialog] Account display refreshed")
        except Exception as e:
            print(f"[AccountSelectionDialog] Error refreshing account display: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Always re-enable refresh button, even if there was an error
            if hasattr(self, 'refresh_button'):
                self.refresh_button.setEnabled(True)
                self.refresh_button.setText("Refresh")

    def reject(self):
        """Handle dialog rejection."""
        super().reject()

    def _get_ignored_models(self) -> set[str]:
        """Get ignored models list from settings."""
        if not self.view_model:
            return set()

        ignored_models_json = self.view_model.settings.get("ignoredModels", "[]")
        try:
            import json
            ignored_list = json.loads(ignored_models_json)
            return set(ignored_list)
        except Exception as e:
            print(f"[AccountSelectionDialog] Error loading ignored models: {e}")
            return set()

    def showEvent(self, event):
        """Handle dialog show event - refresh data if needed."""
        super().showEvent(event)
        if not self._has_been_shown:
            self._has_been_shown = True
            print(f"[AccountSelectionDialog] Dialog shown for first time, refreshing data")
            # Refresh data when dialog is first shown (in case quota data was already fetched)
            # Use a longer delay to ensure dialog is fully rendered
            QTimer.singleShot(300, self._refresh_account_display)
