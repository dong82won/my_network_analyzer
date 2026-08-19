#!/usr/bin/env python3
'''
이벤트 로그 수집, 레벨별 필터링(ALL/INFO/WARN/ERROR), 셀 읽기 전용 보호,
컬럼 너비 자동 최적화 및 로그 비우기 기능이 보완된 HistoryTab 모듈입니다.
'''

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


class HistoryTab(QWidget):
    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 1. 상단 컨트롤 바 (로그 레벨 필터링 및 비우기)
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)

        lbl_filter = QLabel("FILTER LEVEL:")
        lbl_filter.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: bold;")

        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["ALL", "INFO", "WARN", "ERROR"])
        self.combo_filter.setStyleSheet("""
            QComboBox {
                background-color: #3a3d41;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                border: none;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: white;
                selection-background-color: #007acc;
            }
        """)
        self.combo_filter.currentTextChanged.connect(self._apply_filter)

        self.btn_clear = QPushButton("🗑️ CLEAR LOGS")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #3a3d41;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover { background-color: #555555; }
        """)
        self.btn_clear.clicked.connect(self._clear_logs)

        filter_layout.addWidget(lbl_filter)
        filter_layout.addWidget(self.combo_filter)
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_clear)

        layout.addLayout(filter_layout)

        # 2. 히스토리 로그 테이블 위젯
        self.table_history = QTableWidget(0, 4)
        self.table_history.setHorizontalHeaderLabels(["Timestamp", "Type", "Level", "Details"])

        # 컬럼 너비 정책 설정 (0~2열: 내용에 맞춤, 3열: 나머지 자동 채움)
        header = self.table_history.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.table_history.setStyleSheet("""
            QTableWidget {
                background-color: #252526;
                color: white;
                gridline-color: #333333;
                border: 1px solid #3a3d41;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #1e1e1e;
                color: #aaaaaa;
                font-weight: bold;
                padding: 6px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #007acc;
            }
        """)
        self.table_history.verticalHeader().setVisible(False)

        layout.addWidget(self.table_history)

    def add_event(self, ts: str, event_type: str, level: str, details: str):
        '''신규 이벤트를 최상단(0행)에 추가하고 셀 보호 및 필터 동기화 수행'''
        self.table_history.insertRow(0)

        item_ts = QTableWidgetItem(ts)
        item_type = QTableWidgetItem(event_type)
        item_level = QTableWidgetItem(level)
        item_details = QTableWidgetItem(details)

        # 셀 읽기 전용 플래그 설정 (더블클릭 편집 차단)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        for item in (item_ts, item_type, item_level, item_details):
            item.setFlags(flags)

        # 레벨별 시각 텍스트 색상 구분
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

        # 현재 필터 조건 검사 및 숨김 처리
        current_filter = self.combo_filter.currentText()
        if current_filter != "ALL" and level != current_filter:
            self.table_history.setRowHidden(0, True)

        # 최대 로그 개수 200개 제한
        if self.table_history.rowCount() > 200:
            self.table_history.removeRow(200)

    def _apply_filter(self, filter_text: str):
        '''드롭다운 변경 시 지정된 이벤트 레벨 행만 선택 표출'''
        for row in range(self.table_history.rowCount()):
            item_level = self.table_history.item(row, 2)
            if not item_level:
                continue
            if filter_text == "ALL" or item_level.text() == filter_text:
                self.table_history.setRowHidden(row, False)
            else:
                self.table_history.setRowHidden(row, True)

    def _clear_logs(self):
        '''테이블 로그 전체 초기화'''
        self.table_history.setRowCount(0)
