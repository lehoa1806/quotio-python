"""Providers screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer
import asyncio
from typing import Optional

from ...models.providers import AIProvider
from ...models.auth import AuthFile
from ..utils import show_question_box, get_main_window


def run_async_coro(coro):
    """Run an async coroutine, creating task if loop is running."""
    # Import from main_window to use the shared thread-safe function
    from ..main_window import run_async_coro as main_run_async_coro
    return main_run_async_coro(coro)


class ProvidersScreen(QWidget):
    """Screen for managing AI providers."""
    
    def __init__(self, view_model=None):
        """Initialize the providers screen."""
        super().__init__()
        self.view_model = view_model
        self._setup_ui()
        
        # Register for quota update notifications
        if self.view_model:
            self.view_model.register_quota_update_callback(self._update_display)
            self._quota_callback_registered = True
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Title
        title = QLabel("Providers")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Provider list
        self.provider_list = QListWidget()
        self.provider_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.provider_list.itemClicked.connect(self._on_item_clicked)
        # Also listen to selection changes for immediate button visibility updates
        self.provider_list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.provider_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        button_layout.addWidget(self.refresh_button)
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect)
        button_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._on_disconnect)
        button_layout.addWidget(self.disconnect_button)
        
        # Switch Account button (only for Antigravity)
        self.switch_account_button = QPushButton("Switch Account")
        self.switch_account_button.clicked.connect(self._on_switch_account)
        self.switch_account_button.setVisible(False)  # Hidden by default
        button_layout.addWidget(self.switch_account_button)
        
        # Warmup (Auto Wake-up) button (only for Antigravity)
        self.warmup_button = QPushButton("Auto Warmup")
        self.warmup_button.clicked.connect(self._on_warmup_clicked)
        self.warmup_button.setVisible(False)  # Hidden by default
        button_layout.addWidget(self.warmup_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        # Message area for non-blocking feedback
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                border-radius: 4px;
                background-color: #f0f0f0;
                color: #333;
                min-height: 20px;
            }
        """)
        self.message_label.hide()  # Hidden by default
        layout.addWidget(self.message_label)
        
        # Update display
        self._update_display()
    
    def _update_display(self):
        """Update the provider list."""
        print(f"[Providers] _update_display() called (from callback)")
        if not self.view_model:
            print(f"[Providers] No view_model, returning early")
            return
        
        # Save current selection before clearing
        selected_provider = None
        current_item = self.provider_list.currentItem()
        if current_item:
            selected_provider = current_item.data(Qt.ItemDataRole.UserRole)
        
        self.provider_list.clear()
        
        # Show connected providers
        # Use both provider string and provider_type enum for matching
        connected_provider_strings = set()
        connected_provider_enums = set()
        
        # First, try to get from auth_files
        if self.view_model.auth_files:
            for f in self.view_model.auth_files:
                # Add provider string
                if f.provider:
                    connected_provider_strings.add(f.provider)
                
                # Add provider enum if available
                provider_type = f.provider_type
                if provider_type:
                    connected_provider_enums.add(provider_type)
                elif f.provider:
                    # Try to convert provider string to enum
                    try:
                        # Handle aliases
                        provider_str = f.provider
                        if provider_str == "copilot":
                            provider_str = "github-copilot"
                        provider_enum = AIProvider(provider_str)
                        connected_provider_enums.add(provider_enum)
                    except ValueError:
                        pass  # Provider string doesn't match any enum
        
        # Always merge providers from quota data (works in all modes)
        # This ensures we show providers even if auth_files haven't loaded yet
        # Access provider_quotas directly like Quota screen does
        # This is especially important for auto-detected providers like Cursor and Trae
        if self.view_model.provider_quotas:
            quota_providers = set(self.view_model.provider_quotas.keys())
            print(f"[Providers] Found {len(quota_providers)} providers in provider_quotas: {[p.value for p in quota_providers]}")
            # Add all providers that have quota data (including Cursor, Trae)
            for provider in quota_providers:
                connected_provider_enums.add(provider)
                connected_provider_strings.add(provider.value)
                # Debug: Check if Cursor/Trae are in the list
                if provider in [AIProvider.CURSOR, AIProvider.TRAE]:
                    quota_count = len(self.view_model.provider_quotas[provider])
                    print(f"[Providers] Found {quota_count} {provider.display_name} account(s) in provider_quotas")
            print(f"[Providers] Merged {len(quota_providers)} providers from quota data")
        else:
            print(f"[Providers] provider_quotas is empty or None")
        
        # Fallback: If still no providers found, try to use quota data as primary source
        if not connected_provider_enums and not connected_provider_strings and self.view_model.provider_quotas:
            # Use providers from quota data as fallback
            connected_provider_enums = set(self.view_model.provider_quotas.keys())
            # Convert to strings for matching
            connected_provider_strings = {p.value for p in connected_provider_enums}
            print(f"[Providers] Using provider_quotas as primary source: {[p.value for p in connected_provider_enums]}")
        
        print(f"[Providers] Found {len(self.view_model.auth_files)} auth files")
        print(f"[Providers] Provider quotas has {len(self.view_model.provider_quotas)} providers")
        if self.view_model.provider_quotas:
            print(f"[Providers] Provider quotas keys: {[p.value for p in self.view_model.provider_quotas.keys()]}")
        print(f"[Providers] Connected providers (strings): {connected_provider_strings}")
        print(f"[Providers] Connected providers (enums): {[p.value for p in connected_provider_enums]}")
        print(f"[Providers] Will mark {len(connected_provider_enums)} providers as connected in UI")
        
        selected_item = None
        connected_count = 0
        for provider in AIProvider:
            item = QListWidgetItem(provider.display_name)
            
            # Store provider enum in item data for easy retrieval
            item.setData(Qt.ItemDataRole.UserRole, provider)
            
            # Mark connected providers - check both string value and enum
            # Also handle various provider name variations
            is_connected = (
                provider.value in connected_provider_strings or
                provider in connected_provider_enums or
                # Handle aliases
                (provider == AIProvider.COPILOT and ("copilot" in connected_provider_strings or "github-copilot" in connected_provider_strings)) or
                # Handle case-insensitive matching
                any(provider.value.lower() == p.lower() for p in connected_provider_strings)
            )
            
            if is_connected:
                connected_count += 1
                print(f"[Providers] Marking {provider.value} ({provider.display_name}) as connected")
                item.setForeground(Qt.GlobalColor.green)
                
                # For auto-detected providers (Cursor, Trae), show account count
                if not provider.supports_manual_auth and provider in self.view_model.provider_quotas:
                    account_count = len(self.view_model.provider_quotas[provider])
                    if account_count > 0:
                        item.setText(f"✓ {provider.display_name} ({account_count} account{'s' if account_count > 1 else ''})")
                    else:
                        item.setText(f"✓ {provider.display_name}")
                else:
                    item.setText(f"✓ {provider.display_name}")
                
                # For Antigravity, check if account switching is available and show subscription status
                if provider == AIProvider.ANTIGRAVITY:
                    status_parts = []
                    
                    # Check if this is the active account
                    if self.view_model and self.view_model.antigravity_switcher.current_active_account:
                        active_email = self.view_model.antigravity_switcher.current_active_account.email
                        # Find matching auth file
                        matching_file = next(
                            (f for f in self.view_model.auth_files 
                             if f.provider_type == provider and (f.email == active_email or f.account == active_email)),
                            None
                        )
                        if matching_file:
                            status_parts.append("Active")
                    
                    # Check subscription status
                    if provider in self.view_model.subscription_infos:
                        # Get first account's subscription info (or check all accounts)
                        for account_email, sub_info in self.view_model.subscription_infos[provider].items():
                            if sub_info:
                                tier_name = sub_info.tier_display_name
                                if tier_name and tier_name != "Unknown":
                                    status_parts.append(tier_name)
                                break
                    
                    if status_parts:
                        status_text = " | ".join(status_parts)
                        item.setText(f"✓ {provider.display_name} ({status_text})")
                        # Add tooltip with full subscription details
                        tooltip_parts = [f"Provider: {provider.display_name}"]
                        if provider in self.view_model.subscription_infos:
                            for account_email, sub_info in self.view_model.subscription_infos[provider].items():
                                if sub_info:
                                    tooltip_parts.append(f"\nAccount: {account_email}")
                                    tooltip_parts.append(f"Tier: {sub_info.tier_display_name}")
                                    if sub_info.tier_description:
                                        tooltip_parts.append(f"Description: {sub_info.tier_description}")
                                    if sub_info.gcp_managed is not None:
                                        tooltip_parts.append(f"GCP Managed: {sub_info.gcp_managed}")
                                    if sub_info.cloudaicompanion_project:
                                        tooltip_parts.append(f"Project: {sub_info.cloudaicompanion_project}")
                        item.setToolTip("\n".join(tooltip_parts))
            
            # Disable providers that don't support manual auth (but keep checkmark if connected)
            if not provider.supports_manual_auth:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                # Only set "Auto-detect only" text if not already marked as connected
                if not is_connected:
                    item.setText(f"{provider.display_name} (Auto-detect only)")
            
            self.provider_list.addItem(item)
            
            # Restore selection if this was the previously selected provider
            if selected_provider and provider == selected_provider:
                selected_item = item
        
        # Restore selection (block signals to prevent recursive updates)
        if selected_item and (selected_item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self.provider_list.blockSignals(True)
            self.provider_list.setCurrentItem(selected_item)
            self.provider_list.blockSignals(False)
        
        # Force widget repaint to ensure UI updates are visible
        self.update()
        self.provider_list.update()
        self.provider_list.viewport().update()
        
        # Update button visibility based on selection
        self._update_button_visibility()
        
        # Update status - use the larger count to be accurate
        # Deduplicate by using enums (more accurate) but fall back to strings
        if connected_provider_enums:
            count = len(connected_provider_enums)
        elif connected_provider_strings:
            # Count unique provider strings
            count = len(connected_provider_strings)
        else:
            count = 0
        
        # Debug output
        if count == 0:
            print(f"[Providers] WARNING: No connected providers detected!")
            print(f"[Providers]   - auth_files count: {len(self.view_model.auth_files)}")
            print(f"[Providers]   - provider_quotas count: {len(self.view_model.provider_quotas)}")
            if self.view_model.auth_files:
                print(f"[Providers]   - auth_file providers: {[f.provider for f in self.view_model.auth_files]}")
            if self.view_model.provider_quotas:
                print(f"[Providers]   - quota providers: {[p.value for p in self.view_model.provider_quotas.keys()]}")
        
        self.status_label.setText(f"{count} provider(s) connected")
    
    def _update_button_visibility(self):
        """Update button visibility based on selected provider.
        
        This is called immediately when selection changes for instant feedback.
        """
        # Check if button exists (might not be created yet during initialization)
        if not hasattr(self, 'switch_account_button'):
            return
        
        current_item = self.provider_list.currentItem()
        if not current_item:
            self.switch_account_button.setVisible(False)
            return
        
        provider = current_item.data(Qt.ItemDataRole.UserRole)
        if not provider:
            self.switch_account_button.setVisible(False)
            return
        
        if provider == AIProvider.ANTIGRAVITY:
            # Show switch account button for Antigravity
            # Check both auth_files and direct_auth_files for immediate response
            has_auth_files = False
            if self.view_model:
                # Check auth_files (from proxy API)
                has_auth_files = any(
                    f.provider_type == AIProvider.ANTIGRAVITY 
                    for f in self.view_model.auth_files
                )
                # Also check direct_auth_files (from filesystem scan)
                if not has_auth_files and hasattr(self.view_model, 'direct_auth_files'):
                    has_auth_files = any(
                        f.provider == AIProvider.ANTIGRAVITY
                        for f in self.view_model.direct_auth_files
                    )
                # Also check provider_quotas as fallback
                if not has_auth_files and AIProvider.ANTIGRAVITY in self.view_model.provider_quotas:
                    has_auth_files = len(self.view_model.provider_quotas[AIProvider.ANTIGRAVITY]) > 0
            
            self.switch_account_button.setVisible(has_auth_files)
            self.warmup_button.setVisible(has_auth_files)
        else:
            self.switch_account_button.setVisible(False)
            self.warmup_button.setVisible(False)
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click - ensure it's selected."""
        # Only allow selection of enabled items
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            # Block signals temporarily to prevent recursive updates
            self.provider_list.blockSignals(True)
            self.provider_list.setCurrentItem(item)
            self.provider_list.blockSignals(False)
            # Update button visibility immediately
            self._update_button_visibility()
    
    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle selection change - update button visibility immediately."""
        # Update button visibility immediately when selection changes
        self._update_button_visibility()
    
    def _on_connect(self):
        """Handle connect button click."""
        # Try to get current item, or first selected item
        current_item = self.provider_list.currentItem()
        if not current_item:
            # Try selected items
            selected = self.provider_list.selectedItems()
            if selected:
                current_item = selected[0]
        
        if not current_item:
            self._show_message("Please click on a provider in the list to select it, then click Connect.", "info")
            return
        
        # Check if item is disabled
        if not (current_item.flags() & Qt.ItemFlag.ItemIsEnabled):
            self._show_message("This provider does not support manual connection. It will be auto-detected when available.", "info")
            return
        
        # Get provider from item data (stored in UserRole)
        provider = current_item.data(Qt.ItemDataRole.UserRole)
        if not provider:
            # Fallback: try to extract from text
            provider_name = current_item.text().replace("✓ ", "").split(" (")[0]
            provider = None
            for p in AIProvider:
                if p.display_name == provider_name:
                    provider = p
                    break
        
        if not provider or not self.view_model:
            self._show_message("Error: Could not identify provider.", "error")
            return
        
        # Check if proxy is running (required for most OAuth flows)
        if provider not in [AIProvider.COPILOT, AIProvider.KIRO]:
            if not self.view_model.proxy_manager.proxy_status.running:
                # Use non-blocking question dialog
                main_window = get_main_window(self)
                reply = show_question_box(
                    self,
                    "Proxy Not Running",
                    "The proxy server needs to be running to connect this provider.\n\n"
                    "Would you like to start it now?",
                    main_window
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # Start proxy asynchronously
                    async def start_and_connect():
                        try:
                            await self.view_model.start_proxy()
                            # Wait a moment for proxy to be ready
                            await asyncio.sleep(1)
                            # Now start OAuth
                            await self._do_start_oauth(provider)
                        except Exception as e:
                            from ..utils import show_message_box
                            from PyQt6.QtWidgets import QMessageBox as QMB
                            main_window = get_main_window(self)
                            show_message_box(
                                self,
                                "Error",
                                f"Failed to start proxy: {str(e)}",
                                QMB.Icon.Warning,
                                QMB.StandardButton.Ok,
                                main_window
                            )
                    run_async_coro(start_and_connect())
                return
            else:
                # Proxy is running, start OAuth
                run_async_coro(self._do_start_oauth(provider))
        else:
            # Copilot/Kiro don't need proxy
            run_async_coro(self._do_start_oauth(provider))
    
    async def _do_start_oauth(self, provider: AIProvider, auth_method: Optional[str] = None):
        """Internal method to start OAuth flow."""
        try:
            # Ensure proxy is set up if needed
            if provider not in [AIProvider.COPILOT, AIProvider.KIRO]:
                if not self.view_model.proxy_manager.proxy_status.running:
                    # This should have been handled in _on_connect before calling this
                    # But if we get here, just return
                    return
                
                # Ensure API client is set up
                if not self.view_model.api_client:
                    self.view_model._setup_api_client()
            
            # Start OAuth
            if provider == AIProvider.KIRO:
                method = auth_method or "kiro-google-login"
                await self.view_model.start_oauth(provider, auth_method=method)
            else:
                await self.view_model.start_oauth(provider)
            
            # Check OAuth state after a short delay
            await asyncio.sleep(0.5)
            
            # Show result message on main thread
            if self.view_model.oauth_state:
                status = self.view_model.oauth_state.status
                # Handle both enum and string status
                status_str = status.value if hasattr(status, 'value') else str(status)
                
                if status_str == "error":
                    error_msg = self.view_model.oauth_state.error or 'Unknown error'
                    error_text = f"Failed to start OAuth: {error_msg}"
                    self._show_message(error_text, "error")
                elif status_str in ["polling", "waiting"]:
                    # Check if there's a URL in the error message (browser didn't open)
                    error_msg = self.view_model.oauth_state.error or ""
                    if "Please visit:" in error_msg:
                        # Extract URL from error message
                        url = error_msg.split("Please visit:")[-1].strip()
                        msg_text = f"OAuth flow started for {provider.display_name}. Browser did not open automatically. Please visit: {url}"
                        self._show_message(msg_text, "info")
                    else:
                        msg_text = f"OAuth flow started for {provider.display_name}. Please complete authentication in your browser."
                        self._show_message(msg_text, "success")
                else:
                    msg_text = f"OAuth flow started for {provider.display_name}. Please complete authentication in your browser."
                    self._show_message(msg_text, "success")
            else:
                self._show_message("OAuth state not set. The proxy may not be running or there was an error.", "error")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"OAuth error: {error_details}")  # Debug output
            error_text = f"Failed to start OAuth: {str(e)}. Check console for details."
            self._show_message(error_text, "error")
    
    def _on_disconnect(self):
        """Handle disconnect button click."""
        # Try to get current item, or first selected item
        current_item = self.provider_list.currentItem()
        if not current_item:
            # Try selected items
            selected = self.provider_list.selectedItems()
            if selected:
                current_item = selected[0]
        
        if not current_item:
            self._show_message("Please click on a provider in the list to select it, then click Disconnect.", "info")
            return
        
        # Get provider from item data
        provider = current_item.data(Qt.ItemDataRole.UserRole)
        if not provider:
            # Fallback: try to extract from text
            provider_name = current_item.text().replace("✓ ", "").split(" (")[0]
            provider = None
            for p in AIProvider:
                if p.display_name == provider_name:
                    provider = p
                    break
        
        if not provider or not self.view_model:
            return
        
        # Find auth files for this provider
        files_to_delete = [
            f for f in self.view_model.auth_files
            if f.provider_type == provider
        ]
        
        if not files_to_delete:
            self._show_message(f"No active connection for {provider.display_name}.", "info")
            return
        
        # Show account selection dialog
        selected_file = self._show_account_selection_dialog(provider, files_to_delete)
        if selected_file:
            # Confirm deletion
            reply = show_question_box(
                self,
                "Confirm Disconnect",
                f"Are you sure you want to disconnect {selected_file.email or selected_file.account or selected_file.name}?",
                get_main_window(self)
            )
            if reply == QMessageBox.StandardButton.Yes:
                run_async_coro(self.view_model.delete_auth_file(selected_file))
                # Update display after a short delay to allow deletion to complete
                QTimer.singleShot(500, self._update_display)
                self._show_message(f"Disconnected {selected_file.email or selected_file.account or selected_file.name}", "success")
    
    def _on_switch_account(self):
        """Handle Switch Account button click for Antigravity."""
        current_item = self.provider_list.currentItem()
        if not current_item:
            return
        
        provider = current_item.data(Qt.ItemDataRole.UserRole)
        if provider != AIProvider.ANTIGRAVITY:
            return
        
        if not self.view_model:
            return
        
        # Find auth files for Antigravity
        files_to_switch = [
            f for f in self.view_model.auth_files
            if f.provider_type == AIProvider.ANTIGRAVITY
        ]
        
        if not files_to_switch:
            self._show_message("No Antigravity accounts found.", "info")
            return
        
        # Handle account switching
        self._handle_antigravity_switch(files_to_switch)
    
    def _handle_antigravity_switch(self, auth_files):
        """Handle Antigravity account switching."""
        if not self.view_model or not auth_files:
            return
        
        from ..utils import show_question_box
        main_window = get_main_window(self)
        
        # Check if IDE is running
        if self.view_model.antigravity_switcher.is_ide_running():
            reply = show_question_box(
                self,
                "Antigravity IDE Running",
                "Antigravity IDE is currently running. To switch accounts, the IDE will need to be restarted.\n\n"
                "Do you want to continue?",
                main_window
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Show account selection
        if len(auth_files) == 1:
            # Only one account, switch to it
            auth_file = auth_files[0]
            self._execute_antigravity_switch(auth_file)
        else:
            # Multiple accounts - show selection dialog
            from PyQt6.QtWidgets import QInputDialog
            account_names = [f.email or f.account or f.name or f.id for f in auth_files]
            if account_names:
                account, ok = QInputDialog.getItem(
                    self,
                    "Select Account",
                    "Choose account to switch to:",
                    account_names,
                    0,
                    False
                )
                if ok and account:
                    selected_file = next((f for f in auth_files if (f.email or f.account or f.name or f.id) == account), None)
                    if selected_file:
                        self._execute_antigravity_switch(selected_file)
    
    def _execute_antigravity_switch(self, auth_file):
        """Execute Antigravity account switch."""
        if not self.view_model:
            return
        
        async def switch_account():
            try:
                # Find auth file path
                from pathlib import Path
                auth_dir = Path.home() / ".cli-proxy-api"
                auth_file_path = auth_dir / auth_file.name
                
                if not auth_file_path.exists():
                    self._show_message(f"Auth file not found: {auth_file.name}", "error")
                    return
                
                self._show_message("Switching Antigravity account...", "info")
                await self.view_model.antigravity_switcher.execute_switch(
                    str(auth_file_path),
                    should_restart_ide=True
                )
                
                # Check switch state
                switch_state = self.view_model.antigravity_switcher.switch_state
                print(f"[Providers] Switch state after execution: {switch_state}")
                
                if switch_state == "success":
                    self._show_message("Account switched successfully! Please restart Antigravity IDE if it's running.", "success")
                    # Refresh active account detection
                    await self.view_model.antigravity_switcher.detect_active_account()
                    # Refresh quotas
                    await self.view_model.refresh_quotas_unified()
                    # Refresh auth files to update the list
                    if self.view_model.api_client:
                        try:
                            self.view_model.auth_files = await self.view_model.api_client.fetch_auth_files()
                        except Exception:
                            pass  # Ignore errors, just try to refresh
                    # Update display and button visibility
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_display)
                    call_on_main_thread(self._update_button_visibility)
                else:
                    error_msg = f"Account switch failed (state: {switch_state}). Check console for details."
                    self._show_message(error_msg, "error")
                    print(f"[Providers] Account switch failed. State: {switch_state}")
            except Exception as e:
                self._show_message(f"Error switching account: {str(e)}", "error")
                import traceback
                traceback.print_exc()
        
        run_async_coro(switch_account())
    
    def _show_account_selection_dialog(self, provider: AIProvider, auth_files) -> Optional[AuthFile]:
        """Show a dialog to select which account to disconnect.
        
        Returns the selected AuthFile or None if cancelled.
        """
        if not auth_files:
            return None
        
        # If only one account, return it directly (caller can show confirmation)
        if len(auth_files) == 1:
            return auth_files[0]
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Select Account to Disconnect - {provider.display_name}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(300)
        
        layout = QVBoxLayout(dialog)
        
        # Label
        label = QLabel(f"Select which {provider.display_name} account to disconnect:")
        layout.addWidget(label)
        
        # List widget for accounts
        account_list = QListWidget()
        account_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        
        # Add accounts to list
        for auth_file in auth_files:
            # Create display text
            display_text = auth_file.email or auth_file.account or auth_file.name or auth_file.id
            if auth_file.status:
                display_text += f" ({auth_file.status})"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, auth_file)
            account_list.addItem(item)
        
        # Select first item by default
        if account_list.count() > 0:
            account_list.setCurrentRow(0)
        
        layout.addWidget(account_list)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            current_item = account_list.currentItem()
            if current_item:
                return current_item.data(Qt.ItemDataRole.UserRole)
        
        return None
    
    def _show_message(self, message: str, message_type: str = "info"):
        """Show a non-blocking message in the message area."""
        self.message_label.setText(message)
        
        # Set color based on message type
        if message_type == "error":
            self.message_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    background-color: #fee;
                    color: #c33;
                    min-height: 20px;
                    border: 1px solid #fcc;
                }
            """)
        elif message_type == "success":
            self.message_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    background-color: #efe;
                    color: #3c3;
                    min-height: 20px;
                    border: 1px solid #cfc;
                }
            """)
        else:  # info
            self.message_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    background-color: #eef;
                    color: #33c;
                    min-height: 20px;
                    border: 1px solid #ccf;
                }
            """)
        
        self.message_label.show()
        
        # Auto-hide after 5 seconds for info/success messages
        if message_type in ["info", "success"]:
            QTimer.singleShot(5000, self.message_label.hide)
    
    def _on_refresh_clicked(self):
        """Handle refresh button click."""
        self.refresh()
    
    def refresh(self):
        """Refresh the display."""
        # Always update display first (uses cached data)
        self._update_display()
        
        # Prevent concurrent refreshes
        if hasattr(self, '_refreshing') and self._refreshing:
            return
        
        if not self.view_model:
            return
        
        # Refresh quotas if available (works in all modes)
        async def refresh_all():
            try:
                # Refresh quotas (works in monitor mode too)
                await self.view_model.refresh_quotas_unified()
                # Update display after quotas are refreshed
                from ..utils import call_on_main_thread
                call_on_main_thread(self._update_display)
            except Exception as e:
                print(f"[Providers] Error refreshing quotas: {e}")
        
        run_async_coro(refresh_all())
        
        # Refresh Antigravity active account detection
        if self.view_model:
            async def detect_active():
                await self.view_model.antigravity_switcher.detect_active_account()
                # Update display after detection
                from ..utils import call_on_main_thread
                call_on_main_thread(self._update_display)
            run_async_coro(detect_active())
    
    def _on_warmup_clicked(self):
        """Handle warmup (Auto Wake-up) button click - open warmup management modal."""
        current_item = self.provider_list.currentItem()
        if not current_item:
            return
        
        provider = current_item.data(Qt.ItemDataRole.UserRole)
        
        if provider != AIProvider.ANTIGRAVITY:
            return
        
        if not self.view_model:
            return
        
        # Open warmup management modal dialog
        from ..screens.warmup import WarmupScreen
        dialog = WarmupScreen(parent=self, view_model=self.view_model)
        dialog.exec()
        
        # Refresh display after dialog closes
        self._update_display()
        
        # Refresh auth files if proxy is running
        if self.view_model and self.view_model.mode_manager.is_proxy_mode and self.view_model.api_client:
            async def refresh_auth_files():
                self._refreshing = True
                try:
                    if self.view_model.api_client:
                        # Add timeout to prevent hanging
                        import asyncio
                        try:
                            self.view_model.auth_files = await asyncio.wait_for(
                                self.view_model.api_client.fetch_auth_files(),
                                timeout=5.0  # 5 second timeout
                            )
                            print(f"[Providers] Refreshed {len(self.view_model.auth_files)} auth files")
                        except asyncio.TimeoutError:
                            print(f"[Providers] Timeout refreshing auth files (proxy may be slow)")
                        except Exception as e:
                            print(f"[Providers] Error refreshing auth files: {e}")
                            # Don't print full traceback for connection errors to reduce spam
                            if "Connection error" not in str(e):
                                import traceback
                                traceback.print_exc()
                    # Schedule UI update on main thread to avoid threading issues
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_display)
                    call_on_main_thread(self._update_button_visibility)
                except Exception as e:
                    print(f"[Providers] Error in refresh_auth_files: {e}")
                    # Schedule UI update on main thread to avoid threading issues
                    from ..utils import call_on_main_thread
                    call_on_main_thread(self._update_display)  # Update display anyway
                    call_on_main_thread(self._update_button_visibility)
                finally:
                    self._refreshing = False
            
            run_async_coro(refresh_auth_files())
        else:
            # Not in proxy mode - still update display (will use provider_quotas as fallback)
            # Also try to refresh quotas if available
            if hasattr(self.view_model, 'provider_quotas') and not self.view_model.provider_quotas:
                # No quota data yet, try to refresh it
                async def refresh_quotas():
                    try:
                        await self.view_model.refresh_quotas_unified()
                        from ..utils import call_on_main_thread
                        call_on_main_thread(self._update_display)
                    except Exception as e:
                        print(f"[Providers] Error refreshing quotas: {e}")
                        from ..utils import call_on_main_thread
                        call_on_main_thread(self._update_display)
                
                run_async_coro(refresh_quotas())
            else:
                self._update_display()
