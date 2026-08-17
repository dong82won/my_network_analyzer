#!/usr/bin/env python3
'''
target_changed 시그널이 정의된 SettingsTab 모듈입니다.
'''

from typing import Any
from PySide6.QtCore import Signal  # Signal 임포트
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QLineEdit, QPushButton, QMessageBox
)


class SettingsTab(QWidget):
    # PySide6 커스텀 시그널 Class Attribute 정의
    target_changed = Signal(str)

    def __init__(self, main_window: Any):
        super().__init__()
        self.main_window = main_window
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        group_target = QGroupBox("PING Target Host Settings")
        group_target.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                margin-top: 6px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
            QRadioButton {
                color: #dddddd;
                font-size: 12px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 8px;
                height: 8px;
                border-radius: 4px;
                border: 2px solid #555555;
                background-color: #2b2b2b;
            }
            QRadioButton::indicator:checked {
                background-color: #28a745;
                border: 2px solid #28a745;
            }
            QRadioButton::indicator:hover {
                border: 2px solid #28a745;
            }
        """)

        group_layout = QVBoxLayout(group_target)
        group_layout.setSpacing(12)

        self.radio_auto = QRadioButton("Auto Mode (Default Gateway - Local Wireless Link)")
        self.radio_custom = QRadioButton("Custom Target Host / IP (e.g. Robot Server or WAN)")
        self.radio_auto.setChecked(True)

        input_layout = QHBoxLayout()
        self.input_host = QLineEdit()
        self.input_host.setPlaceholderText("8.8.8.8")
        self.input_host.setText("8.8.8.8")
        self.input_host.setEnabled(False)
        self.input_host.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:disabled {
                background-color: #2b2b2b;
                color: #666666;
            }
        """)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #005999; }
            QPushButton:disabled { background-color: #3a3d41; color: #666666; }
        """)

        input_layout.addWidget(self.input_host)
        input_layout.addWidget(self.btn_apply)

        group_layout.addWidget(self.radio_auto)
        group_layout.addWidget(self.radio_custom)
        group_layout.addLayout(input_layout)

        layout.addWidget(group_target)
        layout.addStretch()

        self.radio_auto.toggled.connect(self._on_target_mode_changed)
        self.btn_apply.clicked.connect(self._on_apply_custom_target)

    def _on_target_mode_changed(self, checked: bool):
        is_custom = not checked
        self.input_host.setEnabled(is_custom)
        self.btn_apply.setEnabled(is_custom)

        if checked:
            self.target_changed.emit("AUTO")
            QMessageBox.information(self, "Target Mode", "PING target switched to Auto Gateway Mode (LAN).")

    def _on_apply_custom_target(self):
        target_ip = self.input_host.text().strip()
        if target_ip:
            self.target_changed.emit(target_ip)
            QMessageBox.information(self, "Target Mode", f"PING target set to Custom Host: {target_ip}")
