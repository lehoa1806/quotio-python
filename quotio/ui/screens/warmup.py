"""Warmup (Auto Wake-up) management screen."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QAbstractItemView, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer
from datetime import datetime
from typing import Optional, List

from ...models.providers import AIProvider
from ...services.warmup_service import WarmupCadence, WarmupScheduleMode, WarmupAccountKey
from ..dialogs.warmup_dialog import WarmupDialog


class WarmupScreen(QDialog):
    """Modal dialog for managing all warmup (Auto Wake-up) configurations."""
    
    def __init__(self, parent=None, view_model=None):
        """Initialize the warmup dialog."""
        super().__init__(parent)
        self.view_model = view_model
        self.setWindowTitle("Auto Warmup Management")
        self.setMinimumSize(1000, 600)
        self._setup_ui()
        self._setup_callbacks()
        
        # Timer to refresh status periodically
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._update_display)
        self.refresh_timer.start(5000)  # Update every 5 seconds
        
        # Initial update
        self._update_display()
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("⚡ Auto Wake-up (Warmup) Management")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Add New button (matching Dashboard style)
        self.add_button = QPushButton("Add New")
        self.add_button.setStyleSheet("""
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
        self.add_button.clicked.connect(self._add_new_warmup)
        header_layout.addWidget(self.add_button)
        
        # Refresh button (reusing Dashboard style)
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
        
        # Description
        desc = QLabel(
            "Manage automated warmup configurations for all Antigravity accounts. "
            "Warmup sends periodic requests to keep your quota cycles active.\n"
            "💡 Each account can be configured independently with its own schedule and models."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 11px; padding: 10px; background-color: #f5f5f5; border-radius: 4px; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        # Table for warmup configurations
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Account",
            "Status",
            "Schedule Mode",
            "Cadence/Time",
            "Models",
            "Last Run",
            "Next Run",
            "Actions"
        ])
        
        # Configure table
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.table)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)
    
    def _setup_callbacks(self):
        """Set up callbacks for view model updates."""
        if not self.view_model:
            return
        
        # Register callback for warmup status updates
        # The view model will call this when warmup status changes
        if hasattr(self.view_model, 'warmup_statuses'):
            # We'll poll the status via timer instead of callbacks
            pass
    
    def _update_display(self):
        """Update the warmup configurations table."""
        if not self.view_model:
            self.table.setRowCount(0)
            self.status_label.setText("No view model available")
            return
        
        # Get all Antigravity accounts
        accounts = self._get_all_antigravity_accounts()
        
        if not accounts:
            self.table.setRowCount(0)
            self.status_label.setText("No Antigravity accounts found. Connect an Antigravity account in the Providers tab.")
            return
        
        # Update table
        self.table.setRowCount(len(accounts))
        
        enabled_count = 0
        for row, (account_key, account_email) in enumerate(accounts):
            # Account
            account_item = QTableWidgetItem(account_email or account_key)
            account_item.setData(Qt.ItemDataRole.UserRole, account_key)
            self.table.setItem(row, 0, account_item)
            
            # Status (Enabled/Disabled)
            is_enabled = self.view_model.is_warmup_enabled(AIProvider.ANTIGRAVITY, account_key)
            status_item = QTableWidgetItem("✅ Enabled" if is_enabled else "❌ Disabled")
            status_item.setData(Qt.ItemDataRole.UserRole, is_enabled)
            if is_enabled:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
                enabled_count += 1
            else:
                status_item.setForeground(Qt.GlobalColor.darkGray)
            self.table.setItem(row, 1, status_item)
            
            # Schedule Mode
            mode = self.view_model.warmup_settings.warmup_schedule_mode(AIProvider.ANTIGRAVITY, account_key)
            mode_item = QTableWidgetItem("Interval" if mode == WarmupScheduleMode.INTERVAL else "Daily")
            self.table.setItem(row, 2, mode_item)
            
            # Cadence/Time
            if mode == WarmupScheduleMode.INTERVAL:
                cadence = self.view_model.warmup_settings.warmup_cadence(AIProvider.ANTIGRAVITY, account_key)
                cadence_item = QTableWidgetItem(cadence.display_name if cadence else "N/A")
            else:  # DAILY
                minutes = self.view_model.warmup_settings.warmup_daily_minutes(AIProvider.ANTIGRAVITY, account_key)
                hours = minutes // 60
                mins = minutes % 60
                time_str = f"{hours:02d}:{mins:02d}"
                cadence_item = QTableWidgetItem(time_str)
            self.table.setItem(row, 3, cadence_item)
            
            # Models (count of selected models)
            account_id = WarmupAccountKey(AIProvider.ANTIGRAVITY, account_key).to_id()
            selected_models = self.view_model.warmup_settings.selected_models(AIProvider.ANTIGRAVITY, account_key)
            model_count = len(selected_models) if selected_models else 0
            models_item = QTableWidgetItem(f"{model_count} model(s)" if model_count > 0 else "No models")
            if model_count == 0:
                models_item.setForeground(Qt.GlobalColor.darkGray)
            self.table.setItem(row, 4, models_item)
            
            # Last Run
            account_id = WarmupAccountKey(AIProvider.ANTIGRAVITY, account_key).to_id()
            status = self.view_model.warmup_statuses.get(account_id)
            if status and status.last_run:
                last_run_str = status.last_run.strftime("%Y-%m-%d %H:%M")
            else:
                last_run_str = "Never"
            last_run_item = QTableWidgetItem(last_run_str)
            self.table.setItem(row, 5, last_run_item)
            
            # Next Run
            if status and status.next_run:
                next_run_str = status.next_run.strftime("%Y-%m-%d %H:%M")
                if status.next_run < datetime.now():
                    next_run_item = QTableWidgetItem("Overdue")
                    next_run_item.setForeground(Qt.GlobalColor.red)
                else:
                    next_run_item = QTableWidgetItem(next_run_str)
            else:
                next_run_item = QTableWidgetItem("N/A")
                next_run_item.setForeground(Qt.GlobalColor.darkGray)
            self.table.setItem(row, 6, next_run_item)
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_widget.setLayout(actions_layout)
            
            # Edit button (matching Dashboard style)
            edit_button = QPushButton("Edit")
            edit_button.setStyleSheet("""
                QPushButton {
                    padding: 6px 12px;
                    font-size: 12px;
                    border-radius: 4px;
                    background-color: #007AFF;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #0051D5;
                }
            """)
            edit_button.clicked.connect(lambda checked, key=account_key, email=account_email: self._edit_config(key, email))
            actions_layout.addWidget(edit_button)
            
            # Enable/Disable button (matching Dashboard style)
            if is_enabled:
                toggle_button = QPushButton("Disable")
                toggle_button.setStyleSheet("""
                    QPushButton {
                        padding: 6px 12px;
                        font-size: 12px;
                        border-radius: 4px;
                        background-color: #FF9500;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #E6850E;
                    }
                """)
                toggle_button.clicked.connect(lambda checked, key=account_key: self._toggle_warmup(key, False))
            else:
                toggle_button = QPushButton("Enable")
                toggle_button.setStyleSheet("""
                    QPushButton {
                        padding: 6px 12px;
                        font-size: 12px;
                        border-radius: 4px;
                        background-color: #34C759;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #2AA84F;
                    }
                """)
                toggle_button.clicked.connect(lambda checked, key=account_key: self._toggle_warmup(key, True))
            actions_layout.addWidget(toggle_button)
            
            # Delete button (darker red style)
            delete_button = QPushButton("Delete")
            delete_button.setStyleSheet("""
                QPushButton {
                    padding: 6px 12px;
                    font-size: 12px;
                    border-radius: 4px;
                    background-color: #8B0000;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #6B0000;
                }
            """)
            delete_button.clicked.connect(lambda checked, key=account_key, email=account_email: self._delete_warmup(key, email))
            actions_layout.addWidget(delete_button)
            
            self.table.setCellWidget(row, 7, actions_widget)
        
        # Update status label
        self.status_label.setText(
            f"Total accounts: {len(accounts)} | "
            f"Enabled: {enabled_count} | "
            f"Disabled: {len(accounts) - enabled_count}"
        )
    
    def _get_all_antigravity_accounts(self, include_excluded: bool = False) -> List[tuple]:
        """Get all Antigravity accounts from auth files.
        
        Args:
            include_excluded: If True, include accounts that were removed from warmup list.
        """
        if not self.view_model:
            return []
        
        accounts = []
        
        # Get accounts from provider quotas
        # provider_quotas[AIProvider.ANTIGRAVITY] is Dict[str, ProviderQuotaData]
        if hasattr(self.view_model, 'provider_quotas'):
            antigravity_quotas = self.view_model.provider_quotas.get(AIProvider.ANTIGRAVITY)
            if antigravity_quotas:
                # antigravity_quotas is already a dict: Dict[str, ProviderQuotaData]
                for account_key, quota_data in antigravity_quotas.items():
                    # Skip excluded accounts unless include_excluded is True
                    if not include_excluded and self.view_model.warmup_settings.is_excluded(AIProvider.ANTIGRAVITY, account_key):
                        continue
                    email = quota_data.account_email if hasattr(quota_data, 'account_email') else account_key
                    accounts.append((account_key, email))
        
        # Also check auth files
        if hasattr(self.view_model, 'auth_files'):
            for auth_file in self.view_model.auth_files:
                if auth_file.provider_type == AIProvider.ANTIGRAVITY:
                    # Use quota_lookup_key which is typically the email
                    account_key = auth_file.quota_lookup_key
                    # Skip excluded accounts unless include_excluded is True
                    if not include_excluded and self.view_model.warmup_settings.is_excluded(AIProvider.ANTIGRAVITY, account_key):
                        continue
                    email = auth_file.email if auth_file.email else account_key
                    # Avoid duplicates
                    if not any(key == account_key for key, _ in accounts):
                        accounts.append((account_key, email))
        
        # Sort by email
        accounts.sort(key=lambda x: x[1] or x[0])
        return accounts
    
    def _edit_config(self, account_key: str, account_email: str):
        """Open edit dialog for warmup configuration."""
        if not self.view_model:
            return
        
        # If account was excluded, include it back when editing
        if self.view_model.warmup_settings.is_excluded(AIProvider.ANTIGRAVITY, account_key):
            self.view_model.warmup_settings.include_account(AIProvider.ANTIGRAVITY, account_key)
        
        dialog = WarmupDialog(
            parent=self,
            view_model=self.view_model,
            provider=AIProvider.ANTIGRAVITY,
            account_key=account_key,
            account_email=account_email
        )
        dialog.exec()
        
        # Refresh display after dialog closes
        self._update_display()
    
    def _on_refresh(self):
        """Handle refresh button click - only refresh warmup list display."""
        # Just refresh the display, don't fetch quotas
        self._update_display()
    
    def _toggle_warmup(self, account_key: str, enable: bool):
        """Toggle warmup for an account."""
        if not self.view_model:
            return
        
        self.view_model.warmup_settings.set_enabled(
            enable,
            AIProvider.ANTIGRAVITY,
            account_key
        )
        
        # Refresh display
        self._update_display()
        
        # Show message
        status = "enabled" if enable else "disabled"
        QMessageBox.information(
            self,
            "Warmup Updated",
            f"Warmup has been {status} for {account_key}."
        )
    
    def _add_new_warmup(self):
        """Add a new warmup configuration."""
        if not self.view_model:
            return
        
        # Get all Antigravity accounts (including excluded ones for re-adding)
        accounts = self._get_all_antigravity_accounts(include_excluded=True)
        
        if not accounts:
            QMessageBox.warning(
                self,
                "No Accounts",
                "No Antigravity accounts found. Please connect an Antigravity account in the Providers tab first."
            )
            return
        
        # Show account selection dialog
        from PyQt6.QtWidgets import QInputDialog
        account_names = [f"{email} ({key})" if email != key else key for key, email in accounts]
        selected_text, ok = QInputDialog.getItem(
            self,
            "Select Account",
            "Select Antigravity account to configure warmup:",
            account_names,
            0,
            False
        )
        
        if ok and selected_text:
            # Extract account key from selection
            # Format: "email (key)" or just "key"
            if " (" in selected_text and selected_text.endswith(")"):
                account_key = selected_text.split(" (")[1][:-1]
                account_email = selected_text.split(" (")[0]
            else:
                # Find matching account
                account_key = None
                account_email = None
                for key, email in accounts:
                    if selected_text == email or selected_text == key:
                        account_key = key
                        account_email = email
                        break
                
                if not account_key:
                    QMessageBox.warning(self, "Error", "Could not find selected account.")
                    return
            
            # Open warmup dialog for the selected account
            self._edit_config(account_key, account_email)
    
    def _delete_warmup(self, account_key: str, account_email: str):
        """Remove account from warmup list (force remove)."""
        if not self.view_model:
            return
        
        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Remove from Warmup List",
            f"Are you sure you want to remove {account_email} from the warmup list?\n\n"
            "This will:\n"
            "- Clear all selected models\n"
            "- Disable warmup for this account\n"
            "- Remove the account from the warmup list",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Clear selected models
            self.view_model.warmup_settings.set_selected_models(
                [],
                AIProvider.ANTIGRAVITY,
                account_key
            )
            
            # Disable warmup
            self.view_model.warmup_settings.set_enabled(
                False,
                AIProvider.ANTIGRAVITY,
                account_key
            )
            
            # Exclude account from warmup list
            self.view_model.warmup_settings.exclude_account(
                AIProvider.ANTIGRAVITY,
                account_key
            )
            
            # Refresh display
            self._update_display()
            
            QMessageBox.information(
                self,
                "Account Removed",
                f"{account_email} has been removed from the warmup list.\n"
                "You can add it back using the 'Add New' button."
            )