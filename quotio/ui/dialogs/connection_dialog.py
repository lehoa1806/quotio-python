"""Dialog for creating/editing agent connections."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QFormLayout, QGroupBox, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer

from ...models.agents import CLIAgent
from ...models.agent_connections import NamedAgentConnection
from ...services.agent_connection_storage import AgentConnectionStorage


class ConnectionDialog(QDialog):
    """Dialog for creating or editing an agent connection."""
    
    def __init__(
        self,
        parent,
        installed_agents: list[CLIAgent],
        api_keys: list[str],
        management_key: str = None,
        connection: NamedAgentConnection = None,
        view_model=None
    ):
        """Initialize the dialog.
        
        Args:
            parent: Parent widget
            installed_agents: List of installed agents
            api_keys: List of available API keys
            management_key: Management key (optional)
            connection: Existing connection to edit (None for new connection)
            view_model: QuotaViewModel for adding API keys (optional)
        """
        super().__init__(parent)
        self.connection = connection
        self.installed_agents = installed_agents
        self.api_keys = api_keys
        self.management_key = management_key
        self.view_model = view_model
        self._is_editing = connection is not None
        self._validation_passed = False
        self._needs_validation = False
        self._validation_callback = None  # Will be set by parent
        
        self.setWindowTitle("Edit Connection" if connection else "Add Connection")
        self.setMinimumWidth(600)  # Make modal wider
        # Don't set fixed height - let dialog expand when status message appears
        # Set a reasonable minimum height for the form
        self.setMinimumHeight(280)  # Make modal taller
        
        self._setup_ui()
        
        # If editing, populate fields
        if connection:
            self._populate_fields()
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        
        # Connection name
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Work Account, Personal Account")
        # Fixed height - never resize
        self.name_input.setFixedHeight(self.name_input.sizeHint().height())
        form_layout.addRow("Connection Name:", self.name_input)
        
        # Agent selection
        self.agent_combo = QComboBox()
        for agent in self.installed_agents:
            self.agent_combo.addItem(agent.display_name, agent.value)
        # Fixed height - never resize
        self.agent_combo.setFixedHeight(self.agent_combo.sizeHint().height())
        form_layout.addRow("Agent:", self.agent_combo)
        
        # API Key input (text field) - visible by default
        api_key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter API key...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)  # Visible by default
        # Fixed height - never resize
        self.api_key_input.setFixedHeight(self.api_key_input.sizeHint().height())
        api_key_layout.addWidget(self.api_key_input)
        
        self.api_key_toggle = QPushButton("🙈")
        self.api_key_toggle.setFixedWidth(40)  # Normal size button
        self.api_key_toggle.setFixedHeight(32)  # Normal size button height
        self.api_key_toggle.setCheckable(True)
        self.api_key_toggle.setChecked(True)  # Start with visible (checked = hide)
        self.api_key_toggle.clicked.connect(self._toggle_api_key_visibility)
        api_key_layout.addWidget(self.api_key_toggle)
        
        form_layout.addRow("API Key:", api_key_layout)
        
        layout.addLayout(form_layout)
        
        # Status label for validation feedback
        # This will expand the dialog vertically when shown
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #FF3B30; font-size: 11px; padding: 4px;")
        self.status_label.setWordWrap(True)
        # Allow it to expand vertically - this will make the dialog grow
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_label.setMinimumHeight(0)   # Can collapse to 0 when hidden
        self.status_label.setMaximumHeight(150)  # Max height to prevent excessive growth
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.status_label.hide()
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                font-size: 11px;
                border-radius: 4px;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        # Set button text based on mode (Add vs Update)
        button_text = "Update" if self.connection else "Add"
        self.ok_button = QPushButton(button_text)
        self.ok_button.clicked.connect(self._on_ok)
        self.ok_button.setDefault(True)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    # Removed _update_api_key_combo - no longer using dropdown
    
    def _mask_key(self, key: str) -> str:
        """Mask an API key for display."""
        if not key or len(key) < 8:
            return "****"
        return key[:4] + "..." + key[-4:]
    
    def _toggle_api_key_visibility(self):
        """Toggle API key visibility."""
        is_checked = self.api_key_toggle.isChecked()
        if is_checked:
            # Hide the key
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_toggle.setText("👁")
        else:
            # Show the key
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.api_key_toggle.setText("🙈")
    
    def _populate_fields(self):
        """Populate fields with existing connection data."""
        if not self.connection:
            return
        
        self.name_input.setText(self.connection.name)
        
        # Set agent
        agent_index = self.agent_combo.findData(self.connection.agent.value)
        if agent_index >= 0:
            self.agent_combo.setCurrentIndex(agent_index)
        
        # Set API key in text field
        if self.connection.api_key:
            self.api_key_input.setText(self.connection.api_key)
    
    def _on_ok(self):
        """Handle OK button click."""
        print(f"[ConnectionDialog] _on_ok called, _is_editing={self._is_editing}")
        # Hide previous error messages
        self.status_label.hide()
        
        # Validate inputs
        name = self.name_input.text().strip()
        if not name:
            self._show_error("Please enter a connection name.")
            return
        
        # Get selected agent
        agent_value = self.agent_combo.currentData()
        if not agent_value:
            self._show_error("Please select an agent.")
            return
        
        try:
            agent = CLIAgent(agent_value)
        except ValueError:
            self._show_error("Invalid agent selected.")
            return
        
        # Get API key from text field
        api_key = self.api_key_input.text().strip()
        
        if not api_key:
            self._show_error("Please enter an API key.")
            return
        
        print(f"[ConnectionDialog] Creating connection: name='{name}', agent={agent.display_name}, api_key_length={len(api_key)}")
        
        # Create or update connection object (but don't accept yet)
        if self.connection:
            # Update existing
            self.connection.name = name
            self.connection.agent = agent
            self.connection.api_key = api_key
        else:
            # Create new (ID will be set by caller)
            self.connection = NamedAgentConnection(
                id="",  # Will be set by caller
                name=name,
                agent=agent,
                api_key=api_key
            )
        
        # For new connections, validate API key before accepting
        # For editing existing connections, skip validation (user might be updating other fields)
        if not self._is_editing:
            print(f"[ConnectionDialog] New connection - starting validation, _validation_callback={self._validation_callback is not None}")
            # Mark that validation is needed
            self._needs_validation = True
            # Show validating state
            self.ok_button.setEnabled(False)
            self.ok_button.setText("Validating...")
            self.status_label.setText("Validating API key...")
            self.status_label.setStyleSheet("color: #007AFF; font-size: 11px;")
            self.status_label.show()
            
            # Trigger validation callback if set by parent
            # Don't call accept() - dialog stays open until validation succeeds
            if self._validation_callback:
                print(f"[ConnectionDialog] Calling validation callback with connection: {self.connection.name}")
                self._validation_callback(self.connection)
                print(f"[ConnectionDialog] Validation callback called, waiting for result...")
            else:
                print(f"[ConnectionDialog] ERROR: No validation callback set!")
            # Dialog will stay open - validation callback will call validation_succeeded() or validation_failed()
            return
        
        # If editing existing connection, accept immediately (no validation)
        print(f"[ConnectionDialog] Editing existing connection - accepting immediately")
        self.accept()
    
    def set_validation_callback(self, callback):
        """Set callback to be called when validation is needed."""
        print(f"[ConnectionDialog] set_validation_callback called, callback={callback is not None}")
        self._validation_callback = callback
    
    def _show_error(self, message: str):
        """Show error message in the dialog."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #FF3B30; font-size: 11px;")
        self.status_label.show()
    
    def validation_succeeded(self):
        """Called by parent when validation succeeds - closes the dialog."""
        print(f"[ConnectionDialog] validation_succeeded called")
        self._validation_passed = True
        self._needs_validation = False
        # Call accept() to close the dialog
        print(f"[ConnectionDialog] Calling accept() to close dialog")
        self.accept()
    
    def validation_failed(self, error_message: str):
        """Called by parent when validation fails - shows error and keeps dialog open."""
        print(f"[ConnectionDialog] validation_failed called with error: {error_message}")
        self.ok_button.setEnabled(True)
        self.ok_button.setText("Update" if self._is_editing else "Add")
        self._needs_validation = False  # Reset flag so user can retry
        self._show_error(error_message)
        print(f"[ConnectionDialog] validation_failed completed, dialog remains open")
    
    def get_connection(self) -> NamedAgentConnection:
        """Get the connection from the dialog."""
        return self.connection
