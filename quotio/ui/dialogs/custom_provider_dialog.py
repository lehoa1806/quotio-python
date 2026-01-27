"""Custom Provider Dialog - Modal dialog for adding/editing custom providers."""

from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTextEdit, QCheckBox, QFormLayout,
    QGroupBox, QScrollArea, QWidget, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List

from ...models.custom_provider import (
    CustomProvider, CustomProviderType, CustomAPIKeyEntry,
    ModelMapping, CustomHeader
)
from ..utils import show_message_box, get_main_window


class APIKeyRow(QWidget):
    """Widget for editing a single API key entry."""

    removed = pyqtSignal()

    def __init__(self, key_entry: Optional[CustomAPIKeyEntry] = None, can_remove: bool = True):
        super().__init__()
        self.key_entry = key_entry or CustomAPIKeyEntry()
        self.can_remove = can_remove
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        header_layout = QHBoxLayout()
        label = QLabel(f"API Key #{self.key_entry.id[:8]}")
        label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(label)
        header_layout.addStretch()

        if self.can_remove:
            remove_btn = QPushButton("Remove")
            remove_btn.setStyleSheet("color: red;")
            remove_btn.clicked.connect(self.removed.emit)
            header_layout.addWidget(remove_btn)

        layout.addLayout(header_layout)

        # API Key field
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter API key")
        if self.key_entry.api_key:
            self.api_key_input.setText(self.key_entry.api_key)
        layout.addWidget(QLabel("API Key:"))
        layout.addWidget(self.api_key_input)

        # Proxy URL field
        self.proxy_url_input = QLineEdit()
        self.proxy_url_input.setPlaceholderText("Optional: Proxy URL for this key")
        if self.key_entry.proxy_url:
            self.proxy_url_input.setText(self.key_entry.proxy_url)
        layout.addWidget(QLabel("Proxy URL (optional):"))
        layout.addWidget(self.proxy_url_input)

    def get_key_entry(self) -> CustomAPIKeyEntry:
        """Get the API key entry from inputs."""
        return CustomAPIKeyEntry(
            id=self.key_entry.id,
            api_key=self.api_key_input.text().strip(),
            proxy_url=self.proxy_url_input.text().strip() or None
        )


class ModelMappingRow(QWidget):
    """Widget for editing a single model mapping."""

    removed = pyqtSignal()

    def __init__(self, mapping: Optional[ModelMapping] = None):
        super().__init__()
        self.mapping = mapping or ModelMapping()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Model name and alias
        row_layout = QHBoxLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Upstream model name")
        if self.mapping.name:
            self.name_input.setText(self.mapping.name)
        row_layout.addWidget(QLabel("Model:"))
        row_layout.addWidget(self.name_input)

        row_layout.addWidget(QLabel("→"))

        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText("Local alias")
        if self.mapping.alias:
            self.alias_input.setText(self.mapping.alias)
        row_layout.addWidget(QLabel("Alias:"))
        row_layout.addWidget(self.alias_input)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet("color: red;")
        remove_btn.clicked.connect(self.removed.emit)
        row_layout.addWidget(remove_btn)

        layout.addLayout(row_layout)

        # Thinking budget
        budget_layout = QHBoxLayout()
        self.budget_input = QLineEdit()
        self.budget_input.setPlaceholderText("Optional: Thinking budget")
        if self.mapping.thinking_budget:
            self.budget_input.setText(self.mapping.thinking_budget)
        budget_layout.addWidget(QLabel("Thinking Budget:"))
        budget_layout.addWidget(self.budget_input)
        budget_layout.addStretch()
        layout.addLayout(budget_layout)

    def get_mapping(self) -> ModelMapping:
        """Get the model mapping from inputs."""
        return ModelMapping(
            id=self.mapping.id,
            name=self.name_input.text().strip(),
            alias=self.alias_input.text().strip(),
            thinking_budget=self.budget_input.text().strip() or None
        )


class CustomHeaderRow(QWidget):
    """Widget for editing a single custom header."""

    removed = pyqtSignal()

    def __init__(self, header: Optional[CustomHeader] = None):
        super().__init__()
        self.header = header or CustomHeader()
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Header name")
        if self.header.key:
            self.key_input.setText(self.header.key)
        layout.addWidget(self.key_input)

        layout.addWidget(QLabel(":"))

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Header value")
        if self.header.value:
            self.value_input.setText(self.header.value)
        layout.addWidget(self.value_input)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet("color: red;")
        remove_btn.clicked.connect(self.removed.emit)
        layout.addWidget(remove_btn)

    def get_header(self) -> CustomHeader:
        """Get the custom header from inputs."""
        return CustomHeader(
            id=self.header.id,
            key=self.key_input.text().strip(),
            value=self.value_input.text().strip()
        )


class CustomProviderDialog(QDialog):
    """Dialog for adding/editing custom providers."""

    def __init__(self, parent=None, provider: Optional[CustomProvider] = None):
        super().__init__(parent)
        self.provider = provider
        self.saved_provider: Optional[CustomProvider] = None
        self._setup_ui()
        if provider:
            self._load_provider_data()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add Custom Provider" if not self.provider else "Edit Custom Provider")
        self.setMinimumSize(600, 700)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Header
        header = QLabel(self.windowTitle())
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_content.setLayout(scroll_layout)

        # Basic Info Section
        basic_group = QGroupBox("Basic Information")
        basic_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., OpenRouter, Ollama Local")
        basic_layout.addRow("Provider Name:", self.name_input)

        self.type_combo = QComboBox()
        for provider_type in CustomProviderType:
            self.type_combo.addItem(provider_type.display_name, provider_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        basic_layout.addRow("Provider Type:", self.type_combo)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.example.com")
        basic_layout.addRow("Base URL:", self.base_url_input)

        basic_group.setLayout(basic_layout)
        scroll_layout.addWidget(basic_group)

        # API Keys Section
        api_keys_group = QGroupBox("API Keys")
        api_keys_layout = QVBoxLayout()

        self.api_keys_container = QWidget()
        self.api_keys_layout = QVBoxLayout()
        self.api_keys_container.setLayout(self.api_keys_layout)

        # Add initial API key row
        self.api_key_rows: List[APIKeyRow] = []
        self._add_api_key_row()

        add_key_btn = QPushButton("Add API Key")
        add_key_btn.clicked.connect(self._add_api_key_row)
        api_keys_layout.addWidget(self.api_keys_container)
        api_keys_layout.addWidget(add_key_btn)

        api_keys_group.setLayout(api_keys_layout)
        scroll_layout.addWidget(api_keys_group)

        # Model Mapping Section (conditional)
        self.model_mapping_group = QGroupBox("Model Mapping")
        self.model_mapping_layout = QVBoxLayout()

        self.models_container = QWidget()
        self.models_layout = QVBoxLayout()
        self.models_container.setLayout(self.models_layout)

        self.model_rows: List[ModelMappingRow] = []

        add_model_btn = QPushButton("Add Model Mapping")
        add_model_btn.clicked.connect(self._add_model_row)
        self.model_mapping_layout.addWidget(QLabel("Map upstream model names to local aliases:"))
        self.model_mapping_layout.addWidget(self.models_container)
        self.model_mapping_layout.addWidget(add_model_btn)

        self.model_mapping_group.setLayout(self.model_mapping_layout)
        self.model_mapping_group.setVisible(False)  # Hidden by default
        scroll_layout.addWidget(self.model_mapping_group)

        # Custom Headers Section (conditional)
        self.headers_group = QGroupBox("Custom Headers")
        self.headers_layout = QVBoxLayout()

        self.headers_container = QWidget()
        self.headers_layout_inner = QVBoxLayout()
        self.headers_container.setLayout(self.headers_layout_inner)

        self.header_rows: List[CustomHeaderRow] = []

        add_header_btn = QPushButton("Add Header")
        add_header_btn.clicked.connect(self._add_header_row)
        self.headers_layout.addWidget(QLabel("Custom HTTP headers (for Gemini-compatible providers):"))
        self.headers_layout.addWidget(self.headers_container)
        self.headers_layout.addWidget(add_header_btn)

        self.headers_group.setLayout(self.headers_layout)
        self.headers_group.setVisible(False)  # Hidden by default
        scroll_layout.addWidget(self.headers_group)

        # Enabled Section
        enabled_group = QGroupBox()
        enabled_layout = QHBoxLayout()
        self.enabled_checkbox = QCheckBox("Enable Provider")
        self.enabled_checkbox.setChecked(True)
        enabled_layout.addWidget(self.enabled_checkbox)
        enabled_layout.addStretch()
        enabled_group.setLayout(enabled_layout)
        scroll_layout.addWidget(enabled_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save" if self.provider else "Add Provider")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _on_type_changed(self):
        """Handle provider type change."""
        provider_type = self.type_combo.currentData()

        # Update base URL placeholder/default
        if provider_type.default_base_url:
            self.base_url_input.setPlaceholderText(f"Default: {provider_type.default_base_url}")
            if not self.base_url_input.text():
                self.base_url_input.setText(provider_type.default_base_url)
        else:
            self.base_url_input.setPlaceholderText("https://api.example.com")

        # Show/hide model mapping section
        self.model_mapping_group.setVisible(provider_type.supports_model_mapping)

        # Show/hide custom headers section
        self.headers_group.setVisible(provider_type.supports_custom_headers)

    def _add_api_key_row(self, key_entry: Optional[CustomAPIKeyEntry] = None):
        """Add an API key row."""
        row = APIKeyRow(key_entry, can_remove=len(self.api_key_rows) > 0)
        row.removed.connect(lambda: self._remove_api_key_row(row))
        self.api_key_rows.append(row)
        self.api_keys_layout.addWidget(row)

    def _remove_api_key_row(self, row: APIKeyRow):
        """Remove an API key row."""
        if len(self.api_key_rows) <= 1:
            show_message_box(
                self,
                "Cannot Remove",
                "At least one API key is required.",
                QMessageBox.Icon.Warning,
                QMessageBox.StandardButton.Ok,
                get_main_window(self)
            )
            return

        self.api_key_rows.remove(row)
        row.setParent(None)
        row.deleteLater()

        # Update remove buttons
        for i, r in enumerate(self.api_key_rows):
            r.can_remove = len(self.api_key_rows) > 1

    def _add_model_row(self, mapping: Optional[ModelMapping] = None):
        """Add a model mapping row."""
        row = ModelMappingRow(mapping)
        row.removed.connect(lambda: self._remove_model_row(row))
        self.model_rows.append(row)
        self.models_layout.addWidget(row)

    def _remove_model_row(self, row: ModelMappingRow):
        """Remove a model mapping row."""
        self.model_rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _add_header_row(self, header: Optional[CustomHeader] = None):
        """Add a custom header row."""
        row = CustomHeaderRow(header)
        row.removed.connect(lambda: self._remove_header_row(row))
        self.header_rows.append(row)
        self.headers_layout_inner.addWidget(row)

    def _remove_header_row(self, row: CustomHeaderRow):
        """Remove a custom header row."""
        self.header_rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _load_provider_data(self):
        """Load provider data into the form."""
        if not self.provider:
            return

        self.name_input.setText(self.provider.name)
        index = self.type_combo.findData(self.provider.type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.base_url_input.setText(self.provider.base_url)
        self.enabled_checkbox.setChecked(self.provider.is_enabled)

        # Load API keys
        self.api_key_rows.clear()
        if self.provider.api_keys:
            for key in self.provider.api_keys:
                self._add_api_key_row(key)
        else:
            self._add_api_key_row()

        # Load model mappings
        self.model_rows.clear()
        for mapping in self.provider.models:
            self._add_model_row(mapping)

        # Load headers
        self.header_rows.clear()
        for header in self.provider.headers:
            self._add_header_row(header)

        # Update visibility based on type
        self._on_type_changed()

    def _on_save(self):
        """Handle save button click."""
        # Collect data
        name = self.name_input.text().strip()
        provider_type = self.type_combo.currentData()
        base_url = self.base_url_input.text().strip()

        # Collect API keys
        api_keys = [row.get_key_entry() for row in self.api_key_rows]
        api_keys = [k for k in api_keys if k.api_key.strip()]

        # Collect model mappings
        models = [row.get_mapping() for row in self.model_rows]
        models = [m for m in models if m.name.strip() and m.alias.strip()]

        # Collect headers
        headers = [row.get_header() for row in self.header_rows]
        headers = [h for h in headers if h.key.strip() and h.value.strip()]

        # Create provider
        if self.provider:
            provider = CustomProvider(
                id=self.provider.id,
                name=name,
                type=provider_type,
                base_url=base_url,
                api_keys=api_keys,
                models=models,
                headers=headers,
                is_enabled=self.enabled_checkbox.isChecked(),
                created_at=self.provider.created_at,
                updated_at=datetime.now()
            )
        else:
            provider = CustomProvider.create(
                name=name,
                type=provider_type,
                base_url=base_url,
                api_keys=api_keys,
                models=models,
                headers=headers,
                is_enabled=self.enabled_checkbox.isChecked()
            )

        # Validate
        errors = provider.validate()
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

        self.saved_provider = provider
        self.accept()

    def get_provider(self) -> Optional[CustomProvider]:
        """Get the saved provider."""
        return self.saved_provider
