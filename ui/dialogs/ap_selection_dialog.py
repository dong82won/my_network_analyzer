#!/usr/bin/env python3
'''
Setup Mode에서 도면에 AP 배치 시 주변 스캔된 AP 목록에서 실제 무선 메타데이터를 선택하거나 수동 입력하는 다이얼로그 모듈입니다.
import copy 누락 오류가 수정되었습니다.
'''

import copy  # [핵심 수정] 파이썬 표준 객체 복사 모듈 추가
from typing import Any
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QLineEdit, QGroupBox,
    QHeaderView, QMessageBox
)


class APSelectionDialog(QDialog):
    def __init__(self, scanned_aps_detail: dict[str, dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select AP BSSID for Marker Placement")
        self.resize(680, 420)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: white; }
            QTableWidget { background-color: #252526; color: white; gridline-color: #444; border: 1px solid #333; }
            QHeaderView::section { background-color: #2d2d2d; color: white; padding: 4px; font-weight: bold; border: 1px solid #333; }
            QLineEdit { background-color: #2b2b2b; color: white; border: 1px solid #555; padding: 6px; border-radius: 4px; }
            QPushButton { background-color: #007acc; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px; }
            QPushButton:hover { background-color: #005999; }
        """)

        self.scanned_aps_detail = scanned_aps_detail
        self.selected_ap_info: dict[str, Any] = {}

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. 주변 스캔 AP 선택 테이블
        lbl_title = QLabel("📡 Scanned Wireless Access Points (Select One to Bind):")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00E5FF;")
        layout.addWidget(lbl_title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["SSID", "BSSID (MAC)", "Channel / Band", "Security", "Signal"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        layout.addWidget(self.table)

        # 2. 수동 입력 옵션 그룹
        group_manual = QGroupBox("Custom / Offline AP Manual Input")
        group_manual.setStyleSheet("QGroupBox { font-weight: bold; color: #aaa; border: 1px solid #444; margin-top: 6px; padding-top: 10px; }")
        manual_layout = QHBoxLayout(group_manual)

        self.input_ssid = QLineEdit()
        self.input_ssid.setPlaceholderText("SSID (e.g. Robot_AP_1)")
        self.input_bssid = QLineEdit()
        self.input_bssid.setPlaceholderText("BSSID (e.g. EC:B9:31:39:EB:F3)")

        manual_layout.addWidget(QLabel("SSID:"))
        manual_layout.addWidget(self.input_ssid)
        manual_layout.addWidget(QLabel("BSSID:"))
        manual_layout.addWidget(self.input_bssid)

        layout.addWidget(group_manual)

        # 시그널-슬롯 연결 (데이터 채우기 전에 완료)
        self.table.itemSelectionChanged.connect(self._sync_selection_to_input)
        self.table.cellClicked.connect(lambda row, col: self._sync_row_to_input(row))
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # 데이터 채우기 및 첫 행 자동 선택
        self._populate_table()

        # 3. 하단 버튼
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #555555; color: white;")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Confirm")
        btn_ok.clicked.connect(self._on_confirm)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)

        layout.addLayout(btn_box)

    def _populate_table(self):
        self.table.setRowCount(0)
        for bssid, info in self.scanned_aps_detail.items():
            row = self.table.rowCount()
            self.table.insertRow(row)

            chan_str = f"Ch.{info.get('channel_num', 0)} ({info.get('wifi_band', '--')})"

            item_ssid = QTableWidgetItem(info.get("ssid", "<Unknown>"))
            item_bssid = QTableWidgetItem(bssid)
            item_chan = QTableWidgetItem(chan_str)
            item_sec = QTableWidgetItem(info.get("security", "--"))
            item_rssi = QTableWidgetItem(f"{info.get('rssi', -100)} dBm")

            self.table.setItem(row, 0, item_ssid)
            self.table.setItem(row, 1, item_bssid)
            self.table.setItem(row, 2, item_chan)
            self.table.setItem(row, 3, item_sec)
            self.table.setItem(row, 4, item_rssi)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)
            self._sync_row_to_input(0)

    def _sync_selection_to_input(self):
        row = self.table.currentRow()
        if row >= 0:
            self._sync_row_to_input(row)

    def _sync_row_to_input(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return

        item_ssid = self.table.item(row, 0)
        item_bssid = self.table.item(row, 1)

        if item_ssid is not None and item_bssid is not None:
            self.input_ssid.setText(item_ssid.text())
            self.input_bssid.setText(item_bssid.text())

    def _on_cell_double_clicked(self, row: int, column: int):
        self._sync_row_to_input(row)
        self._on_confirm()

    def _on_confirm(self):
        bssid_text = self.input_bssid.text().strip().upper()
        ssid_text = self.input_ssid.text().strip()

        # 텍스트 박스가 비어있을 경우 현재 선택된 테이블 행에서 직수치 추출 (Fallback)
        if not bssid_text:
            row = self.table.currentRow()
            if row >= 0:
                item_ssid = self.table.item(row, 0)
                item_bssid = self.table.item(row, 1)
                if item_bssid is not None:
                    bssid_text = item_bssid.text().strip().upper()
                if item_ssid is not None:
                    ssid_text = item_ssid.text().strip()

        if not bssid_text:
            QMessageBox.warning(self, "Warning", "Please select an AP from the list or enter a BSSID manually.")
            return

        # 선택된 BSSID에 해당하는 상세 메타데이터를 깊은 복사(deepcopy)하여 격리 생성
        if bssid_text in self.scanned_aps_detail:
            self.selected_ap_info = copy.deepcopy(self.scanned_aps_detail[bssid_text])
            self.selected_ap_info["bssid"] = bssid_text
            self.selected_ap_info["ssid"] = ssid_text
        else:
            # 목록에 없는 수동 입력 AP일 경우 기본값 매핑
            self.selected_ap_info = {
                "bssid": bssid_text,
                "ssid": ssid_text if ssid_text else "Manual AP",
                "channel_freq": "--",
                "channel_num": 0,
                "wifi_band": "--",
                "security": "--",
                "max_rate": "--"
            }

        self.accept()
