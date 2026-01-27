"""Custom providers screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox, QGroupBox, QDialog
)
from PyQt6.QtCore import Qt

from ..utils import show_message_box, get_main_window, show_question_box
from ..dialogs.custom_provider_dialog import CustomProviderDialog
from ...models.custom_provider import CustomProvider, CustomProviderType


class CustomProvidersScreen(QWidget):
    """Screen for managing custom providers."""

    def __init__(self, view_model=None):
        """Initialize the custom providers screen."""
        super().__init__()
        self.view_model = view_model
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Title
        title = QLabel("Custom Providers")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Manage custom AI providers that are compatible with OpenAI, Claude, Gemini, Codex, or GLM APIs. "
            "These providers will be added to your CLIProxyAPI configuration."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(desc)

        # Provider list
        list_group = QGroupBox("Custom Providers")
        list_layout = QVBoxLayout()

        self.provider_list = QListWidget()
        self.provider_list.itemDoubleClicked.connect(self._on_provider_double_clicked)
        self.provider_list.itemClicked.connect(self._on_provider_selected)
        list_layout.addWidget(self.provider_list)

        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.add_button = QPushButton("Add Provider")
        self.add_button.clicked.connect(self._on_add)
        button_layout.addWidget(self.add_button)

        self.edit_button = QPushButton("Edit Provider")
        self.edit_button.clicked.connect(self._on_edit)
        self.edit_button.setEnabled(False)
        button_layout.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete Provider")
        self.delete_button.clicked.connect(self._on_delete)
        self.delete_button.setEnabled(False)
        button_layout.addWidget(self.delete_button)

        self.toggle_button = QPushButton("Toggle Enable")
        self.toggle_button.clicked.connect(self._on_toggle)
        self.toggle_button.setEnabled(False)
        button_layout.addWidget(self.toggle_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Update display
        self._update_display()

    def _update_display(self):
        """Update the provider list."""
        if not self.view_model:
            return

        self.provider_list.clear()

        # Filter out GLM providers (they're shown in Providers screen)
        for provider in self.view_model.custom_provider_service.providers:
            if provider.type == CustomProviderType.GLM_COMPATIBILITY:
                continue  # Skip GLM providers

            status = "✓" if provider.is_enabled else "✗"
            item_text = f"{status} {provider.name} ({provider.type.display_name})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, provider.id)
            self.provider_list.addItem(item)

    def _on_provider_selected(self, item):
        """Handle provider selection."""
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.toggle_button.setEnabled(True)

    def _on_provider_double_clicked(self, item):
        """Handle provider double-click - open edit dialog."""
        self._on_edit()

    def _on_add(self):
        """Handle add button click."""
        if not self.view_model:
            return

        dialog = CustomProviderDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            provider = dialog.get_provider()
            if provider:
                # Validate using service
                errors = self.view_model.custom_provider_service.validate_provider(provider)
                if errors:
                    show_message_box(
                        self,
                        "Validation Error",
                        "Please fix the following errors:\n\n" + "\n".join(f"• {e}" for e in errors),
                        QMessageBox.Icon.Warning,
                        QMessageBox.StandardButton.Ok,
                        get_main_window(self)
                    )
                    return

                self.view_model.custom_provider_service.add_provider(provider)
                self._sync_to_config()
                self._update_display()

    def _on_edit(self):
        """Handle edit button click."""
        current_item = self.provider_list.currentItem()
        if not current_item or not self.view_model:
            return

        provider_id = current_item.data(Qt.ItemDataRole.UserRole)
        provider = self.view_model.custom_provider_service.get_provider(provider_id)

        if provider:
            dialog = CustomProviderDialog(self, provider=provider)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                updated_provider = dialog.get_provider()
                if updated_provider:
                    # Validate using service
                    errors = self.view_model.custom_provider_service.validate_provider(updated_provider)
                    if errors:
                        show_message_box(
                            self,
                            "Validation Error",
                            "Please fix the following errors:\n\n" + "\n".join(f"• {e}" for e in errors),
                            QMessageBox.Icon.Warning,
                            QMessageBox.StandardButton.Ok,
                            get_main_window(self)
                        )
                        return

                    self.view_model.custom_provider_service.update_provider(updated_provider)
                    self._sync_to_config()
                    self._update_display()

    def _on_delete(self):
        """Handle delete button click."""
        current_item = self.provider_list.currentItem()
        if not current_item or not self.view_model:
            return

        provider_id = current_item.data(Qt.ItemDataRole.UserRole)
        provider = self.view_model.custom_provider_service.get_provider(provider_id)

        if provider:
            main_window = get_main_window(self)
            if show_question_box(
                self,
                "Delete Provider",
                f"Are you sure you want to delete '{provider.name}'?",
                main_window
            ):
                self.view_model.custom_provider_service.delete_provider(provider_id)
                self._sync_to_config()
                self._update_display()
                self.edit_button.setEnabled(False)
                self.delete_button.setEnabled(False)
                self.toggle_button.setEnabled(False)

    def _on_toggle(self):
        """Handle toggle enable button click."""
        current_item = self.provider_list.currentItem()
        if not current_item or not self.view_model:
            return

        provider_id = current_item.data(Qt.ItemDataRole.UserRole)
        self.view_model.custom_provider_service.toggle_provider(provider_id)
        self._sync_to_config()
        self._update_display()

    def _sync_to_config(self):
        """Sync custom providers to CLIProxyAPI config file."""
        if not self.view_model:
            return

        try:
            from pathlib import Path
            config_path = Path.home() / ".cli-proxy-api" / "config.yaml"
            if not config_path.exists():
                # Try alternative location
                config_path = Path.home() / "Library" / "Application Support" / "CLIProxyAPI" / "config.yaml"

            if config_path.exists():
                self.view_model.custom_provider_service.sync_to_config_file(str(config_path))
        except Exception as e:
            print(f"[CustomProviders] Failed to sync to config: {e}")
            # Don't show error to user - this is a background operation

    def refresh(self):
        """Refresh the display."""
        self._update_display()
