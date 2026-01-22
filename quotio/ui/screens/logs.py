"""Request logs screen."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QHeaderView, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from datetime import datetime

from ..utils import show_message_box, get_main_window, get_http_status_color


class LogsScreen(QWidget):
    """Screen showing request logs."""
    
    def __init__(self, view_model=None):
        """Initialize the logs screen."""
        super().__init__()
        self.view_model = view_model
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Title
        title = QLabel("Request Logs")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Stats section
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()
        
        self.total_requests_label = QLabel("Total Requests: 0")
        stats_layout.addWidget(self.total_requests_label)
        
        self.success_rate_label = QLabel("Success Rate: —")
        stats_layout.addWidget(self.success_rate_label)
        
        self.avg_duration_label = QLabel("Average Duration: —")
        stats_layout.addWidget(self.avg_duration_label)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Logs table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Time", "Method", "Endpoint", "Provider", "Model",
            "Status", "Duration", "Tokens"
        ])
        
        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh)
        button_layout.addWidget(self.refresh_button)
        
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self._on_clear)
        button_layout.addWidget(self.clear_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Update display
        self._update_display()
    
    def _update_display(self):
        """Update the logs table."""
        if not self.view_model:
            return
        
        # Update stats
        stats = self.view_model.request_tracker.stats
        self.total_requests_label.setText(f"Total Requests: {stats.total_requests}")
        self.success_rate_label.setText(f"Success Rate: {stats.success_rate:.1f}%")
        if stats.average_duration_ms > 0:
            self.avg_duration_label.setText(f"Average Duration: {stats.average_duration_ms:.0f}ms")
        else:
            self.avg_duration_label.setText("Average Duration: —")
        
        # Update table
        self.table.setRowCount(0)
        
        for log in self.view_model.request_tracker.request_history[:1000]:  # Show last 1000
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Time
            time_str = log.timestamp.strftime("%H:%M:%S")
            self.table.setItem(row, 0, QTableWidgetItem(time_str))
            
            # Method
            self.table.setItem(row, 1, QTableWidgetItem(log.method))
            
            # Endpoint
            self.table.setItem(row, 2, QTableWidgetItem(log.endpoint))
            
            # Provider
            provider = log.resolved_provider or log.provider or "—"
            self.table.setItem(row, 3, QTableWidgetItem(provider))
            
            # Model
            model = log.resolved_model or log.model or "—"
            self.table.setItem(row, 4, QTableWidgetItem(model))
            
            # Status with color-coded indicator
            if log.status_code:
                status_item = QTableWidgetItem(str(log.status_code))
                # Use color-coded status (matching original implementation logic)
                status_color = get_http_status_color(log.status_code)
                status_item.setForeground(status_color)
            else:
                status_item = QTableWidgetItem("—")
                status_item.setForeground(QColor(128, 128, 128))  # Gray
            self.table.setItem(row, 5, status_item)
            
            # Duration
            if log.duration_ms:
                duration_item = QTableWidgetItem(f"{log.duration_ms}ms")
            else:
                duration_item = QTableWidgetItem("—")
            self.table.setItem(row, 6, duration_item)
            
            # Tokens
            if log.total_tokens:
                tokens_item = QTableWidgetItem(str(log.total_tokens))
            else:
                tokens_item = QTableWidgetItem("—")
            self.table.setItem(row, 7, tokens_item)
    
    def _on_refresh(self):
        """Handle refresh button click."""
        self._update_display()
    
    def _on_clear(self):
        """Handle clear button click."""
        if not self.view_model:
            return
        
        main_window = get_main_window(self)
        from ..utils import show_question_box
        
        if show_question_box(
            self,
            "Clear History",
            "Are you sure you want to clear all request history?",
            main_window
        ):
            self.view_model.request_tracker.clear_history()
            self._update_display()
    
    def refresh(self):
        """Refresh the display."""
        self._update_display()
