#!/usr/bin/env python3
'''
ETH 상단 상태 표시를 제거하고 Wi-Fi 전용 상태 오버레이만 유지하도록 보완된 MainWindow 모듈입니다.
'''

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QLabel, QTabWidget

from core.collector import NetworkDataCollector
from core.models import NetworkMetrics
from ui.tabs.dashboard_tab import DashboardTab
from ui.tabs.survey_tab import SurveyTab
from ui.tabs.history_tab import HistoryTab
from ui.tabs.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Analyzer (Ubuntu 24.04)")
        self.resize(800, 720)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")

        self.current_metrics = NetworkMetrics()

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333333; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #888888; padding: 8px 16px; font-weight: bold; }
            QTabBar::tab:selected { background: #007acc; color: white; }
        """)
        self.setCentralWidget(self.tabs)

        self._init_corner_status_widget()

        self.tab_dashboard = DashboardTab(self)
        self.tab_survey = SurveyTab(self)
        self.tab_history = HistoryTab()
        self.tab_settings = SettingsTab(self)

        self.tabs.addTab(self.tab_dashboard, "Dashboard")
        self.tabs.addTab(self.tab_survey, "Survey")
        self.tabs.addTab(self.tab_history, "History")
        self.tabs.addTab(self.tab_settings, "Settings")

        self.collector = NetworkDataCollector(target_host="AUTO")
        self.collector.metrics_updated.connect(self._on_metrics_updated)
        self.collector.event_occurred.connect(self.tab_history.add_event)

        self.tab_settings.target_changed.connect(self._on_target_changed)
        self.collector.start()

    def _init_corner_status_widget(self):
        '''ETH 상태 라벨을 삭제하고 우측 상단에 Wi-Fi 전용 상태 라벨만 배치'''
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 12, 0)
        corner_layout.setSpacing(8)

        self.lbl_status_wifi = QLabel("WIFI: OFF")
        self.lbl_status_wifi.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #FF4444; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
        )

        corner_layout.addWidget(self.lbl_status_wifi)
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

    def _on_metrics_updated(self, m: NetworkMetrics):
        self.current_metrics = m

        # Wi-Fi 상태 뱃지 업데이트
        if m.wifi_connected:
            self.lbl_status_wifi.setText("WIFI: ON")
            self.lbl_status_wifi.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #00FF66; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
            )
        else:
            self.lbl_status_wifi.setText("WIFI: OFF")
            self.lbl_status_wifi.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #FF4444; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
            )

        if hasattr(self.tab_dashboard, 'update_metrics'):
            self.tab_dashboard.update_metrics(m)

    def _on_target_changed(self, new_target: str):
        self.collector.target_host = new_target

    def closeEvent(self, event):
        self.collector.stop()
        event.accept()
