"""IDE scan screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QGroupBox, QCheckBox, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
import asyncio
import json
from datetime import datetime
from typing import Optional

from ..utils import show_message_box, get_main_window, call_on_main_thread, log_with_timestamp
from ...services.ide_scan_service import IDEScanOptions, IDEScanResult
from ..main_window import run_async_coro


class IDEScanScreen(QWidget):
    """Screen for IDE scanning."""

    def __init__(self, view_model=None):
        """Initialize the IDE scan screen."""
        super().__init__()
        self.view_model = view_model
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Title
        title = QLabel("IDE Scan")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Scan for installed IDEs and CLI tools to automatically detect "
            "and configure quota tracking."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Scan options
        options_group = QGroupBox("Scan Options")
        options_layout = QVBoxLayout()

        self.scan_cursor_checkbox = QCheckBox("Cursor")
        self.scan_cursor_checkbox.setToolTip("Scan Cursor's database for auth/quota info")
        self.scan_cursor_checkbox.stateChanged.connect(self._on_options_changed)
        options_layout.addWidget(self.scan_cursor_checkbox)

        self.scan_trae_checkbox = QCheckBox("Trae")
        self.scan_trae_checkbox.setToolTip("Scan Trae's storage for auth/quota info")
        self.scan_trae_checkbox.stateChanged.connect(self._on_options_changed)
        options_layout.addWidget(self.scan_trae_checkbox)

        self.scan_cli_checkbox = QCheckBox("CLI Tools")
        self.scan_cli_checkbox.setToolTip("Scan for installed CLI tools (claude, codex, gemini, etc.)")
        self.scan_cli_checkbox.stateChanged.connect(self._on_options_changed)
        options_layout.addWidget(self.scan_cli_checkbox)

        # Auto scan at startup
        self.auto_scan_checkbox = QCheckBox("Enable auto scan at startup")
        self.auto_scan_checkbox.setToolTip("Automatically scan when the app starts")
        self.auto_scan_checkbox.stateChanged.connect(self._on_auto_scan_changed)
        options_layout.addWidget(self.auto_scan_checkbox)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Results
        results_group = QGroupBox("Scan Results")
        results_layout = QVBoxLayout()

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("Click 'Scan' to start scanning...")
        results_layout.addWidget(self.results_text)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.scan_button = QPushButton("Scan")
        self.scan_button.clicked.connect(self._on_scan)
        button_layout.addWidget(self.scan_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self._on_reset)
        self.reset_button.setVisible(False)  # Only show when results exist
        button_layout.addWidget(self.reset_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Load persisted scan options
        self._load_persisted_options()

        # Load persisted scan results
        self._load_persisted_results()

        # Update display
        self._update_display()

    def _load_persisted_options(self):
        """Load persisted scan options from settings."""
        if not self.view_model:
            return

        # Load persisted options
        options_json = self.view_model.settings.get("ideScanOptions", None)
        if options_json:
            try:
                data = json.loads(options_json)
                self.scan_cursor_checkbox.setChecked(data.get("scan_cursor", False))
                self.scan_trae_checkbox.setChecked(data.get("scan_trae", False))
                self.scan_cli_checkbox.setChecked(data.get("scan_cli_tools", True))
            except Exception as e:
                log_with_timestamp(f"Error loading persisted options: {e}", "[IDEScan]")
                # Use defaults
                self.scan_cursor_checkbox.setChecked(False)
                self.scan_trae_checkbox.setChecked(False)
                self.scan_cli_checkbox.setChecked(True)
        else:
            # Use defaults
            self.scan_cursor_checkbox.setChecked(False)
            self.scan_trae_checkbox.setChecked(False)
            self.scan_cli_checkbox.setChecked(True)

        # Load auto-scan setting
        auto_scan = self.view_model.settings.get("ideAutoScanAtStartup", False)
        self.auto_scan_checkbox.setChecked(auto_scan)

    def _save_persisted_options(self):
        """Save scan options to settings."""
        if not self.view_model:
            return

        try:
            options = {
                "scan_cursor": self.scan_cursor_checkbox.isChecked(),
                "scan_trae": self.scan_trae_checkbox.isChecked(),
                "scan_cli_tools": self.scan_cli_checkbox.isChecked(),
            }
            self.view_model.settings.set("ideScanOptions", json.dumps(options))
            log_with_timestamp("Saved scan options to settings", "[IDEScan]")
        except Exception as e:
            log_with_timestamp(f"Error saving persisted options: {e}", "[IDEScan]")

    def _on_options_changed(self):
        """Handle scan options checkbox changes."""
        self._save_persisted_options()

    def _on_auto_scan_changed(self):
        """Handle auto-scan checkbox change."""
        if not self.view_model:
            return

        auto_scan = self.auto_scan_checkbox.isChecked()
        self.view_model.settings.set("ideAutoScanAtStartup", auto_scan)
        # Also update the old setting for backward compatibility
        self.view_model.settings.set("ideScanAutoScanMode", "always" if auto_scan else "never")
        self.view_model.settings.set("ideScanAutoScan", auto_scan)
        log_with_timestamp(f"Auto-scan at startup: {auto_scan}", "[IDEScan]")

    def _load_persisted_results(self):
        """Load persisted scan results from settings."""
        if not self.view_model:
            return

        # Load persisted results
        persisted_json = self.view_model.settings.get("ideScanResult", None)
        has_results = False

        if persisted_json:
            try:
                data = json.loads(persisted_json)
                result = IDEScanResult()
                result.cursor_found = data.get("cursor_found", False)
                result.cursor_email = data.get("cursor_email")
                result.trae_found = data.get("trae_found", False)
                result.trae_email = data.get("trae_email")
                result.cli_tools_found = data.get("cli_tools_found", [])
                if data.get("timestamp"):
                    result.timestamp = datetime.fromisoformat(data["timestamp"])
                else:
                    result.timestamp = datetime.now()

                self.view_model.ide_scan_result = result
                has_results = True
                log_with_timestamp("Loaded persisted scan results", "[IDEScan]")
            except Exception as e:
                log_with_timestamp(f"Error loading persisted results: {e}", "[IDEScan]")
                import traceback
                traceback.print_exc()

        # Check auto-scan at startup setting
        auto_scan_at_startup = self.view_model.settings.get("ideAutoScanAtStartup", False)
        # Backward compatibility: check old settings
        if not auto_scan_at_startup:
            auto_scan_mode = self.view_model.settings.get("ideScanAutoScanMode", "never")
            if auto_scan_mode == "never":
                old_setting = self.view_model.settings.get("ideScanAutoScan", False)
                if old_setting:
                    auto_scan_at_startup = True

        if auto_scan_at_startup:
            log_with_timestamp("Auto-scan at startup enabled - will perform scan", "[IDEScan]")

            # Use persisted options or current checkbox states
            options_json = self.view_model.settings.get("ideScanOptions", None)
            if options_json:
                try:
                    data = json.loads(options_json)
                    options = IDEScanOptions(
                        scan_cursor=data.get("scan_cursor", False),
                        scan_trae=data.get("scan_trae", False),
                        scan_cli_tools=data.get("scan_cli_tools", True),
                    )
                except Exception:
                    # Fallback to current checkbox states
                    options = IDEScanOptions(
                        scan_cursor=self.scan_cursor_checkbox.isChecked(),
                        scan_trae=self.scan_trae_checkbox.isChecked(),
                        scan_cli_tools=self.scan_cli_checkbox.isChecked(),
                    )
            else:
                # Use current checkbox states
                options = IDEScanOptions(
                    scan_cursor=self.scan_cursor_checkbox.isChecked(),
                    scan_trae=self.scan_trae_checkbox.isChecked(),
                    scan_cli_tools=self.scan_cli_checkbox.isChecked(),
                )

            # Only scan if at least one option is enabled
            if options.has_any_scan_enabled:
                # Schedule auto-scan after a short delay to allow UI to initialize
                # Use call_on_main_thread to ensure QTimer is called from the correct thread
                def schedule_scan():
                    from PyQt6.QtCore import QTimer
                    # Use call_on_main_thread to ensure QTimer is called from main thread
                    def schedule_scan_timer():
                        QTimer.singleShot(2000, lambda: self._perform_scan(options))
                    call_on_main_thread(schedule_scan_timer)
                call_on_main_thread(schedule_scan)
            else:
                log_with_timestamp("Auto-scan at startup enabled but no options selected - skipping scan", "[IDEScan]")
        else:
            log_with_timestamp("Auto-scan at startup disabled - skipping auto-scan", "[IDEScan]")

    def _save_persisted_results(self, result: IDEScanResult, options: IDEScanOptions):
        """Save scan results to settings for persistence."""
        if not self.view_model:
            return

        try:
            data = {
                "cursor_found": result.cursor_found,
                "cursor_email": result.cursor_email,
                "trae_found": result.trae_found,
                "trae_email": result.trae_email,
                "cli_tools_found": result.cli_tools_found,
                "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                "scan_cursor": options.scan_cursor,
                "scan_trae": options.scan_trae,
                "scan_cli_tools": options.scan_cli_tools,
            }
            self.view_model.settings.set("ideScanResult", json.dumps(data))
            log_with_timestamp("Saved scan results to settings", "[IDEScan]")
        except Exception as e:
            log_with_timestamp(f"Error saving persisted results: {e}", "[IDEScan]")

    def _update_display(self):
        """Update the display."""
        if not self.view_model:
            self.results_text.setPlainText("No view model available.")
            return

        if not self.view_model.ide_scan_result:
            # No scan result yet, show placeholder
            self.results_text.setPlainText("No scan results yet. Click 'Scan' to start scanning...")
            self.scan_button.setText("Scan")
            self.reset_button.setVisible(False)
            return

        result = self.view_model.ide_scan_result
        lines = []

        lines.append("=== IDE Scan Results ===\n")

        # Only show results for options that were scanned
        # For now, show all results if they exist
        if hasattr(result, 'cursor_found'):
            if result.cursor_found:
                lines.append(f"✓ Cursor IDE found")
                if result.cursor_email:
                    lines.append(f"  Email: {result.cursor_email}")
            else:
                lines.append("✗ Cursor IDE not found")
        else:
            lines.append("— Cursor IDE: Not scanned")

        lines.append("")

        if hasattr(result, 'trae_found'):
            if result.trae_found:
                lines.append(f"✓ Trae IDE found")
                if result.trae_email:
                    lines.append(f"  Email: {result.trae_email}")
            else:
                lines.append("✗ Trae IDE not found")
        else:
            lines.append("— Trae IDE: Not scanned")

        lines.append("")

        if hasattr(result, 'cli_tools_found') and result.cli_tools_found:
            lines.append(f"✓ CLI Tools found: {', '.join(result.cli_tools_found)}")
        else:
            lines.append("✗ No CLI tools found")

        if hasattr(result, 'timestamp') and result.timestamp:
            lines.append(f"\nScanned at: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

        self.results_text.setPlainText("\n".join(lines))

        # Update button text and visibility
        self.scan_button.setText("Rescan")
        self.reset_button.setVisible(True)

    def _on_scan(self):
        """Handle scan/rescan button click."""
        if not self.view_model:
            log_with_timestamp("No view model available", "[IDEScan]")
            return

        # Save options before scanning
        self._save_persisted_options()

        options = IDEScanOptions(
            scan_cursor=self.scan_cursor_checkbox.isChecked(),
            scan_trae=self.scan_trae_checkbox.isChecked(),
            scan_cli_tools=self.scan_cli_checkbox.isChecked(),
        )

        if not options.has_any_scan_enabled:
            show_message_box(
                self,
                "No Options Selected",
                "Please select at least one scan option.",
                QMessageBox.Icon.Information,
                QMessageBox.StandardButton.Ok,
                get_main_window(self)
            )
            return

        self._perform_scan(options)

    def _perform_scan(self, options: IDEScanOptions):
        """Perform the actual scan operation."""
        # Show scanning status
        def show_scanning():
            self.results_text.setPlainText("Scanning... Please wait...")
            self.scan_button.setEnabled(False)
            self.scan_button.setText("Scanning...")
            self.reset_button.setEnabled(False)

        call_on_main_thread(show_scanning)

        async def scan():
            try:
                log_with_timestamp(f"Starting scan with options: cursor={options.scan_cursor}, trae={options.scan_trae}, cli={options.scan_cli_tools}", "[IDEScan]")
                await self.view_model.scan_ides(options)
                result = self.view_model.ide_scan_result
                log_with_timestamp(f"Scan completed, result: {result}", "[IDEScan]")

                # Save results for persistence
                if result:
                    self._save_persisted_results(result, options)

                # Schedule UI update on main thread to avoid threading issues
                # No need for sleep delay - quota update callbacks are already scheduled via QTimer
                # and will execute asynchronously on the main thread
                def update_ui():
                    try:
                        # Update IDE scan screen UI first (lightweight)
                        self._update_display()
                        self.scan_button.setEnabled(True)
                        self.reset_button.setEnabled(True)

                        # Ensure auto-refresh timer is running after scan
                        from ..utils import get_main_window
                        main_window = get_main_window(self)
                        if main_window and hasattr(main_window, '_update_auto_refresh_timer'):
                            # Restart auto-refresh timer to ensure background jobs continue
                            main_window._update_auto_refresh_timer()
                            log_with_timestamp("Restarted auto-refresh timer after scan", "[IDEScan]")

                        # Don't manually refresh other screens - let the quota update callbacks handle it
                        # The callbacks are already registered and will be called automatically
                        # This prevents blocking the UI with heavy refresh operations
                        log_with_timestamp("IDE scan UI updated, quota callbacks will handle other screen updates", "[IDEScan]")
                    except Exception as e:
                        log_with_timestamp(f"Error in update_ui: {e}", "[IDEScan]")
                        import traceback
                        traceback.print_exc()
                call_on_main_thread(update_ui)
            except Exception as e:
                error_msg = str(e)
                log_with_timestamp(f"Error during scan: {error_msg}", "[IDEScan]")
                import traceback
                traceback.print_exc()
                # Schedule message box and UI reset on main thread
                def show_error():
                    show_message_box(
                        self,
                        "Scan Error",
                        f"Error during scan: {error_msg}\n\nCheck console for details.",
                        QMessageBox.Icon.Warning,
                        QMessageBox.StandardButton.Ok,
                        get_main_window(self)
                    )
                    self.scan_button.setEnabled(True)
                    self.scan_button.setText("Rescan" if self.view_model.ide_scan_result else "Scan")
                    self.reset_button.setEnabled(True)
                    self.results_text.setPlainText("Scan failed. Check console for details.")
                call_on_main_thread(show_error)

        log_with_timestamp("Scheduling scan coroutine...", "[IDEScan]")
        result = run_async_coro(scan())
        if result is None:
            log_with_timestamp("Warning: Could not schedule scan coroutine", "[IDEScan]")
            def reset_ui():
                self.scan_button.setEnabled(True)
                self.scan_button.setText("Rescan" if self.view_model.ide_scan_result else "Scan")
                self.reset_button.setEnabled(True)
                self.results_text.setPlainText("Error: Could not start scan. Check console for details.")
            call_on_main_thread(reset_ui)

    def _on_reset(self):
        """Handle reset button click."""
        if not self.view_model:
            return

        reply = show_message_box(
            self,
            "Reset Scan Results",
            "Are you sure you want to clear the scan results?",
            QMessageBox.Icon.Question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            get_main_window(self)
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.view_model.ide_scan_result = None
            self.view_model.settings.set("ideScanResult", None)
            self._update_display()
            log_with_timestamp("Scan results reset", "[IDEScan]")

    def refresh(self):
        """Refresh the display."""
        self._update_display()
