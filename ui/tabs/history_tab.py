#!/usr/bin/env python3
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView

class HistoryTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.table_history = QTableWidget(0, 4)
        self.table_history.setHorizontalHeaderLabels(["Timestamp", "Type", "Level", "Details"])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_history.setStyleSheet("background-color: #252526; color: white; gridline-color: #444;")

        layout.addWidget(self.table_history)

    def add_event(self, ts: str, event_type: str, level: str, details: str):
        self.table_history.insertRow(0)

        item_ts = QTableWidgetItem(ts)
        item_type = QTableWidgetItem(event_type)
        item_level = QTableWidgetItem(level)
        item_details = QTableWidgetItem(details)

        if level == "INFO":
            color = QColor("#00FF66")
        elif level == "WARN":
            color = QColor("#FFCC00")
        else:
            color = QColor("#FF4444")

        item_type.setForeground(color)
        item_level.setForeground(color)

        self.table_history.setItem(0, 0, item_ts)
        self.table_history.setItem(0, 1, item_type)
        self.table_history.setItem(0, 2, item_level)
        self.table_history.setItem(0, 3, item_details)

        if self.table_history.rowCount() > 200:
            self.table_history.removeRow(200)
