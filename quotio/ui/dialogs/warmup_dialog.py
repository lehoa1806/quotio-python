"""Warmup (Auto Wake-up) configuration dialog."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QTimeEdit, QScrollArea, QWidget,
    QDialogButtonBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QTime, QTimer
from datetime import datetime
from typing import Optional, List

from ...models.providers import AIProvider
from ...services.warmup_service import WarmupCadence, WarmupScheduleMode


class WarmupDialog(QDialog):
    """Dialog for configuring Auto Wake-up (Warmup) settings."""
    
    def __init__(self, parent=None, view_model=None, provider: AIProvider = None, account_key: str = "", account_email: str = ""):
        """Initialize warmup dialog.
        
        Args:
            parent: Parent widget
            view_model: QuotaViewModel instance
            provider: AI Provider (must be ANTIGRAVITY)
            account_key: Account identifier
            account_email: Account email for display
        """
        super().__init__(parent)
        self.view_model = view_model
        self.provider = provider
        self.account_key = account_key
        self.account_email = account_email
        
        self.setWindowTitle("Auto Wake-up Configuration")
        self.setModal(True)
        self.resize(500, 600)
        
        self._setup_ui()
        self._load_settings()
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("⚡ Auto Wake-up")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        account_label = QLabel(f"Account: {self.account_email}")
        account_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(account_label)
        
        # Description
        desc = QLabel(
            "Schedule automated requests to AI models to consume a small amount of quota "
            "and trigger the reset cycle in advance.\n\n"
            "💡 Multiple Accounts: Each Antigravity account can be configured independently. "
            "The scheduler will run warmup for all enabled accounts according to their individual schedules. "
            "You can enable warmup for multiple accounts, and each will run on its own schedule.\n\n"
            "⚠ Requirements: The proxy must be running. Auth tokens must be valid for the accounts. "
            "Antigravity IDE does not need to be open - warmup works independently through the proxy."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 11px; padding: 10px; background-color: #f5f5f5; border-radius: 4px;")
        layout.addWidget(desc)
        
        # Schedule Mode
        mode_group = QGroupBox("Schedule")
        mode_layout = QFormLayout()
        
        self.schedule_mode_combo = QComboBox()
        self.schedule_mode_combo.addItem("Interval", WarmupScheduleMode.INTERVAL)
        self.schedule_mode_combo.addItem("Daily", WarmupScheduleMode.DAILY)
        self.schedule_mode_combo.currentIndexChanged.connect(self._on_schedule_mode_changed)
        mode_layout.addRow("Mode:", self.schedule_mode_combo)
        
        # Interval cadence (shown when interval mode)
        self.cadence_combo = QComboBox()
        for cadence in WarmupCadence:
            self.cadence_combo.addItem(cadence.display_name, cadence)
        self.cadence_combo.currentIndexChanged.connect(self._on_cadence_changed)
        mode_layout.addRow("Interval:", self.cadence_combo)
        self.cadence_row_index = mode_layout.rowCount() - 1
        
        # Daily time (shown when daily mode)
        self.daily_time_edit = QTimeEdit()
        self.daily_time_edit.setDisplayFormat("HH:mm")
        self.daily_time_edit.setTime(QTime(9, 0))  # Default 9:00 AM
        self.daily_time_edit.timeChanged.connect(self._on_daily_time_changed)
        mode_layout.addRow("Time:", self.daily_time_edit)
        self.daily_time_row_index = mode_layout.rowCount() - 1
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # Model Selection
        models_group = QGroupBox("Models")
        models_layout = QVBoxLayout()
        
        self.models_scroll = QScrollArea()
        self.models_widget = QWidget()
        self.models_widget_layout = QVBoxLayout()
        self.models_widget.setLayout(self.models_widget_layout)
        self.models_scroll.setWidget(self.models_widget)
        self.models_scroll.setWidgetResizable(True)
        self.models_scroll.setMinimumHeight(200)
        models_layout.addWidget(self.models_scroll)
        
        self.loading_label = QLabel("Loading models...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #666; padding: 20px;")
        models_layout.addWidget(self.loading_label)
        
        models_group.setLayout(models_layout)
        layout.addWidget(models_group)
        
        # Status
        status_group = QGroupBox("Status")
        status_layout = QFormLayout()
        
        self.status_label = QLabel("Disabled")
        status_layout.addRow("Status:", self.status_label)
        
        self.last_run_label = QLabel("Never")
        status_layout.addRow("Last Run:", self.last_run_label)
        
        self.next_run_label = QLabel("N/A")
        status_layout.addRow("Next Run:", self.next_run_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        
        # Enable/Disable button
        self.enable_button = QPushButton("Enable")
        self.enable_button.clicked.connect(self._on_enable_clicked)
        button_box.addButton(self.enable_button, QDialogButtonBox.ButtonRole.ActionRole)
        
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Load models asynchronously (this will update enable button when models are loaded)
        self._load_models()
        
        # Initial enable button state (will be updated after models load)
        self._update_enable_button()
        
        # Set up timer to update status periodically
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)  # Update every second
    
    def _load_settings(self):
        """Load current warmup settings."""
        if not self.view_model:
            return
        
        # Load schedule mode
        mode = self.view_model.warmup_settings.warmup_schedule_mode(self.provider, self.account_key)
        index = self.schedule_mode_combo.findData(mode)
        if index >= 0:
            self.schedule_mode_combo.setCurrentIndex(index)
        
        # Load cadence
        cadence = self.view_model.warmup_settings.warmup_cadence(self.provider, self.account_key)
        index = self.cadence_combo.findData(cadence)
        if index >= 0:
            self.cadence_combo.setCurrentIndex(index)
        
        # Load daily time
        daily_time = self.view_model.warmup_settings.warmup_daily_time(self.provider, self.account_key)
        self.daily_time_edit.setTime(QTime(daily_time.hour, daily_time.minute))
        
        # Update visibility
        self._on_schedule_mode_changed()
        
        # Update status
        self._update_status()
    
    async def _load_models_async(self):
        """Load available models asynchronously."""
        if not self.view_model:
            return []
        
        try:
            models = await self.view_model.warmup_available_models(self.provider, self.account_key)
            return models
        except Exception as e:
            print(f"[WarmupDialog] Error loading models: {e}")
            return []
    
    def _load_models(self):
        """Load available models."""
        from ..main_window import run_async_coro
        
        async def load():
            models = await self._load_models_async()
            from ..utils import call_on_main_thread
            call_on_main_thread(lambda: self._populate_models(models))
        
        run_async_coro(load())
    
    def _populate_models(self, models: List[str]):
        """Populate model checkboxes."""
        self.loading_label.hide()
        
        # Clear existing
        while self.models_widget_layout.count():
            item = self.models_widget_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not models:
            no_models_label = QLabel("No models available")
            no_models_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_models_label.setStyleSheet("color: #666; padding: 20px;")
            self.models_widget_layout.addWidget(no_models_label)
            self.model_checkboxes = {}
            return
        
        # Load saved selection
        saved_models = set()
        if self.view_model:
            saved_models = set(self.view_model.warmup_settings.selected_models(self.provider, self.account_key))
        
        # Create checkboxes
        self.model_checkboxes = {}
        for model in sorted(models):
            checkbox = QCheckBox(model)
            checkbox.setChecked(model in saved_models)
            checkbox.stateChanged.connect(self._on_model_selection_changed)
            self.models_widget_layout.addWidget(checkbox)
            self.model_checkboxes[model] = checkbox
        
        self.models_widget_layout.addStretch()
        
        # Update status and enable button after models are loaded
        self._update_status()
        self._update_enable_button()
    
    def _on_schedule_mode_changed(self):
        """Handle schedule mode change."""
        mode = self.schedule_mode_combo.currentData()
        if not mode:
            return
        
        # Find the mode group to get the layout
        mode_group = None
        for child in self.findChildren(QGroupBox):
            if child.title() == "Schedule":
                mode_group = child
                break
        
        if not mode_group:
            return
        
        mode_layout = mode_group.layout()
        if not isinstance(mode_layout, QFormLayout):
            return
        
        if mode == WarmupScheduleMode.INTERVAL:
            # Show interval cadence, hide daily time
            self.cadence_combo.setVisible(True)
            self.daily_time_edit.setVisible(False)
            # Also hide/show the labels
            label_item = mode_layout.itemAt(self.cadence_row_index, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(True)
            label_item = mode_layout.itemAt(self.daily_time_row_index, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)
        else:
            # Show daily time, hide interval cadence
            self.cadence_combo.setVisible(False)
            self.daily_time_edit.setVisible(True)
            # Also hide/show the labels
            label_item = mode_layout.itemAt(self.cadence_row_index, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(False)
            label_item = mode_layout.itemAt(self.daily_time_row_index, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                label_item.widget().setVisible(True)
    
    def _on_cadence_changed(self):
        """Handle cadence change."""
        if not self.view_model:
            return
        cadence = self.cadence_combo.currentData()
        if cadence:
            self.view_model.warmup_settings.set_warmup_cadence(cadence, self.provider, self.account_key)
    
    def _on_daily_time_changed(self, time: QTime):
        """Handle daily time change."""
        if not self.view_model:
            return
        minutes = time.hour() * 60 + time.minute()
        self.view_model.warmup_settings.set_warmup_daily_minutes(minutes, self.provider, self.account_key)
    
    def _on_model_selection_changed(self):
        """Handle model selection change."""
        if not self.view_model:
            return
        selected = [
            model for model, checkbox in self.model_checkboxes.items()
            if checkbox.isChecked()
        ]
        self.view_model.warmup_settings.set_selected_models(selected, self.provider, self.account_key)
        # Update enable button state when selection changes
        self._update_enable_button()
    
    def _update_status(self):
        """Update status display."""
        if not self.view_model:
            return
        
        status = self.view_model.warmup_status(self.provider, self.account_key)
        enabled = self.view_model.is_warmup_enabled(self.provider, self.account_key)
        
        if not enabled:
            self.status_label.setText("Disabled")
        elif not hasattr(self, 'model_checkboxes') or not any(cb.isChecked() for cb in self.model_checkboxes.values()):
            self.status_label.setText("No models selected")
        elif status.is_running:
            self.status_label.setText("Running...")
            if status.progress_total > 0:
                progress_text = f" ({status.progress_completed}/{status.progress_total})"
                self.status_label.setText("Running..." + progress_text)
        elif status.last_error:
            self.status_label.setText(f"Error: {status.last_error[:50]}")
        else:
            self.status_label.setText("Idle")
        
        if status.last_run:
            self.last_run_label.setText(status.last_run.strftime("%Y-%m-%d %H:%M"))
        else:
            self.last_run_label.setText("Never")
        
        next_run = self.view_model.warmup_next_run_date(self.provider, self.account_key)
        if next_run:
            self.next_run_label.setText(next_run.strftime("%Y-%m-%d %H:%M"))
        else:
            self.next_run_label.setText("N/A")
        
        # Update enable button
        self._update_enable_button()
    
    def _update_enable_button(self):
        """Update enable button text and state."""
        if not self.view_model:
            return
        
        enabled = self.view_model.is_warmup_enabled(self.provider, self.account_key)
        # Check if model_checkboxes exists, is not empty, and has at least one checked checkbox
        has_models = bool(
            hasattr(self, 'model_checkboxes') 
            and self.model_checkboxes 
            and any(cb.isChecked() for cb in self.model_checkboxes.values())
        )
        
        if enabled:
            self.enable_button.setText("Disable")
            # Always enable the disable button if warmup is already enabled
            self.enable_button.setEnabled(True)
        else:
            self.enable_button.setText("Enable")
            # Enable button only if models are selected
            self.enable_button.setEnabled(has_models)
    
    def _on_enable_clicked(self):
        """Handle enable/disable button click."""
        if not self.view_model:
            return
        
        enabled = self.view_model.is_warmup_enabled(self.provider, self.account_key)
        self.view_model.set_warmup_enabled(not enabled, self.provider, self.account_key)
        self._update_status()
    
    def _on_accept(self):
        """Handle accept button."""
        # Save schedule mode
        mode = self.schedule_mode_combo.currentData()
        if mode:
            self.view_model.warmup_settings.set_warmup_schedule_mode(mode, self.provider, self.account_key)
        
        # Save cadence
        cadence = self.cadence_combo.currentData()
        if cadence:
            self.view_model.warmup_settings.set_warmup_cadence(cadence, self.provider, self.account_key)
        
        # Save daily time
        daily_time = self.daily_time_edit.time()
        minutes = daily_time.hour() * 60 + daily_time.minute()
        self.view_model.warmup_settings.set_warmup_daily_minutes(minutes, self.provider, self.account_key)
        
        # Save model selection
        if hasattr(self, 'model_checkboxes'):
            selected = [
                model for model, checkbox in self.model_checkboxes.items()
                if checkbox.isChecked()
            ]
            self.view_model.warmup_settings.set_selected_models(selected, self.provider, self.account_key)
        
        self.accept()
