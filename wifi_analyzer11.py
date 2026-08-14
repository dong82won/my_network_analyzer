#!/usr/bin/env python3
import sys
import re
import time
import subprocess
import statistics
from datetime import datetime
from collections import deque
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QFrame, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QFormLayout,
    QPushButton, QCheckBox
)

import pyqtgraph as pg
from pyqtgraph import PlotWidget, PlotCurveItem, DateAxisItem

# Pylance 모듈 오인을 원천 차단하기 위해 ViewBox 클래스 원본 파일 직접 임포트
from pyqtgraph.graphicsItems.ViewBox.ViewBox import ViewBox

# PyQtGraph 글로벌 다크 테마 및 안티앨리어싱 설정
pg.setConfigOption('background', '#252526')
pg.setConfigOption('foreground', '#CCCCCC')
pg.setConfigOption('antialias', True)

@dataclass
class NetworkMetrics:
    interface: str = "wlan0"
    ssid: str = "Scanning..."
    bssid: str = "--:--:--:--:--:--"
    ip_addr: str = "0.0.0.0"
    gateway: str = "0.0.0.0"
    target_host: str = "192.168.0.1"
    freq_ghz: str = "--"
    link_speed_mbps: str = "--"
    rssi: int = -100
    latency_ms: float = 0.0
    packet_loss_pct: float = 0.0
    jitter_ms: float = 0.0
    score: int = 0
    status_text: str = "POOR"
    wifi_connected: bool = False
    wired_connected: bool = False

class NetworkDataCollector(QThread):
    metrics_updated = Signal(NetworkMetrics)
    event_occurred = Signal(str, str, str, str)

    def __init__(self, target_host="AUTO", interface="wlan0"):
        super().__init__()
        self.target_host = target_host
        self.interface = interface
        self.is_running = True

        # 상태 머신 변수 (이전 주기 상태 저장)
        self.last_bssid = ""
        self.last_wifi_connected = False
        self.last_wired_connected = False
        self.last_spike_logged = False

    def run(self):
        while self.is_running:
            metrics = NetworkMetrics(interface=self.interface)

            self._get_wifi_info(metrics)
            self._get_wired_info(metrics)
            self._get_ip_info(metrics)

            if self.target_host.upper() == "AUTO":
                metrics.target_host = metrics.gateway if metrics.gateway != "0.0.0.0" else "8.8.8.8"
            else:
                metrics.target_host = self.target_host

            self._run_ping_test(metrics)
            self._calculate_health_score(metrics)

            now_str = datetime.now().strftime("%H:%M:%S")

            if metrics.wifi_connected and not self.last_wifi_connected:
                self.event_occurred.emit(now_str, "WIFI_CONN", "INFO", f"Connected to {metrics.ssid} ({metrics.bssid})")
            elif not metrics.wifi_connected and self.last_wifi_connected:
                self.event_occurred.emit(now_str, "WIFI_DISC", "ERROR", "Wi-Fi Link Dropped")

            if metrics.wired_connected and not self.last_wired_connected:
                self.event_occurred.emit(now_str, "ETH_CONN", "INFO", "Ethernet Cable Connected (Link UP)")
            elif not metrics.wired_connected and self.last_wired_connected:
                self.event_occurred.emit(now_str, "ETH_DISC", "WARN", "Ethernet Cable Disconnected (Link DOWN)")

            if (metrics.wifi_connected and self.last_bssid and
                metrics.bssid != "--:--:--:--:--:--" and self.last_bssid != metrics.bssid):
                self.event_occurred.emit(now_str, "AP_ROAMING", "INFO", f"AP Changed: {self.last_bssid} -> {metrics.bssid}")

            if metrics.wifi_connected:
                if metrics.latency_ms > 80.0 and not self.last_spike_logged:
                    self.event_occurred.emit(now_str, "LATENCY_SPIKE", "WARN", f"High Latency Detected: {metrics.latency_ms} ms")
                    self.last_spike_logged = True
                elif metrics.latency_ms <= 80.0:
                    self.last_spike_logged = False

                if metrics.packet_loss_pct > 0.0 and metrics.packet_loss_pct < 100.0:
                    self.event_occurred.emit(now_str, "PACKET_LOSS", "WARN", f"Packet Loss Detected: {metrics.packet_loss_pct} %")

            self.last_wifi_connected = metrics.wifi_connected
            self.last_wired_connected = metrics.wired_connected
            if metrics.bssid != "--:--:--:--:--:--":
                self.last_bssid = metrics.bssid

            self.metrics_updated.emit(metrics)
            self.msleep(1000)

    def stop(self):
        self.is_running = False
        self.wait()

    def _get_wifi_info(self, metrics: NetworkMetrics):
        try:
            cmd = ["nmcli", "-t", "-f", "ACTIVE,DEVICE,SSID,BSSID,SIGNAL,FREQ,RATE", "dev", "wifi"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            for line in res.stdout.strip().split('\n'):
                if line.startswith("yes:"):
                    parts = re.split(r'(?<!\\):', line)
                    if len(parts) >= 7:
                        metrics.interface = parts[1]
                        self.interface = parts[1]

                        metrics.ssid = parts[2].replace(r'\:', ':')
                        metrics.bssid = parts[3].replace(r'\:', ':')

                        try:
                            signal_pct = int(parts[4])
                            metrics.rssi = int((signal_pct / 2) - 100)
                        except ValueError:
                            metrics.rssi = -100

                        metrics.freq_ghz = parts[5].replace(r'\:', ':')
                        metrics.link_speed_mbps = parts[6].replace(r'\:', ':')
                        metrics.wifi_connected = True
                        break
        except Exception:
            metrics.wifi_connected = False

        if metrics.bssid == "--:--:--:--:--:--":
            metrics.wifi_connected = False

    def _get_wired_info(self, metrics: NetworkMetrics):
        try:
            cmd = ["nmcli", "-t", "-f", "TYPE,STATE", "dev"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
            wired_up = False
            for line in res.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 2:
                    dev_type, dev_state = parts[0], parts[1]
                    if dev_type == "ethernet" and dev_state == "connected":
                        wired_up = True
                        break
            metrics.wired_connected = wired_up
        except Exception:
            metrics.wired_connected = False

    def _get_ip_info(self, metrics: NetworkMetrics):
        try:
            if metrics.interface == "wlan0" and self.interface != "wlan0":
                metrics.interface = self.interface

            res_ip = subprocess.run(["ip", "-4", "addr", "show", metrics.interface], capture_output=True, text=True, timeout=2)
            match_ip = re.search(r'inet\s+([\d\.]+)', res_ip.stdout)
            if match_ip:
                metrics.ip_addr = match_ip.group(1)

            res_gw = subprocess.run(["ip", "route", "show", "dev", metrics.interface], capture_output=True, text=True, timeout=2)
            match_gw = re.search(r'default via ([\d\.]+)', res_gw.stdout)
            if match_gw:
                metrics.gateway = match_gw.group(1)
        except Exception:
            pass

    def _run_ping_test(self, metrics: NetworkMetrics):
        if not metrics.wifi_connected or metrics.ip_addr == "0.0.0.0":
            metrics.latency_ms = 0.0
            metrics.jitter_ms = 0.0
            metrics.packet_loss_pct = 100.0
            return

        try:
            cmd = ["ping", "-I", metrics.interface, "-c", "3", "-i", "0.2", "-W", "0.5", metrics.target_host]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                times = [float(t) for t in re.findall(r'time=([\d\.]+)', res.stdout)]
                loss_match = re.search(r'([\d\.]+)%\s+packet loss', res.stdout)
                if times:
                    metrics.latency_ms = round(statistics.mean(times), 1)
                    metrics.jitter_ms = round(statistics.stdev(times), 1) if len(times) > 1 else 0.0
                if loss_match:
                    metrics.packet_loss_pct = float(loss_match.group(1))
            else:
                metrics.latency_ms = 0.0
                metrics.jitter_ms = 0.0
                metrics.packet_loss_pct = 100.0
        except Exception:
            metrics.latency_ms = 0.0
            metrics.jitter_ms = 0.0
            metrics.packet_loss_pct = 100.0

    def _calculate_health_score(self, metrics: NetworkMetrics):
        if not metrics.wifi_connected or metrics.packet_loss_pct == 100.0:
            metrics.score = 0
            metrics.status_text = "BAD"
            return

        s_rssi = max(0, min(100, int((metrics.rssi + 85) * (100 / 35))))
        s_lat = max(0, min(100, int(100 - ((metrics.latency_ms - 10) * (100 / 140))))) if metrics.latency_ms > 0 else 0
        s_loss = max(0, min(100, int(100 - (metrics.packet_loss_pct * 10))))
        s_jit = max(0, min(100, int(100 - ((metrics.jitter_ms - 2) * (100 / 28))))) if metrics.latency_ms > 0 else 0

        total = (s_rssi * 0.25) + (s_lat * 0.25) + (s_loss * 0.30) + (s_jit * 0.20)
        metrics.score = max(0, min(100, int(total)))

        if metrics.score >= 80:
            metrics.status_text = "EXCELLENT"
        elif metrics.score >= 60:
            metrics.status_text = "GOOD"
        elif metrics.score >= 40:
            metrics.status_text = "WARNING"
        else:
            metrics.status_text = "BAD"


class MetricCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setStyleSheet("background-color: #2b2b2b; border-radius: 8px; padding: 8px;")
        layout = QVBoxLayout(self)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")

        val_layout = QHBoxLayout()
        self.val_lbl = QLabel("--")
        self.val_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #00FF66;")

        self.status_lbl = QLabel("GOOD")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #00FF66;")

        val_layout.addWidget(self.val_lbl)
        val_layout.addWidget(self.status_lbl)

        layout.addWidget(self.title_lbl)
        layout.addLayout(val_layout)

    def set_value(self, val_str: str, status_str: str, color: str = "#00FF66"):
        self.val_lbl.setText(val_str)
        self.val_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        self.status_lbl.setText(status_str)
        self.status_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {color};")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robot Network Analyzer (Ubuntu 24.04)")
        self.resize(750, 680)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")

        self.time_history = deque(maxlen=60)
        self.rssi_history = deque(maxlen=60)
        self.lat_history = deque(maxlen=60)
        self.loss_history = deque(maxlen=60)
        self.jit_history = deque(maxlen=60)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333333; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #888888; padding: 8px 16px; font-weight: bold; }
            QTabBar::tab:selected { background: #007acc; color: white; }
        """)
        self.setCentralWidget(self.tabs)

        self._init_corner_status_widget()
        self._init_dashboard_tab()
        self._init_survey_tab()
        self._init_history_tab()
        self._init_settings_tab()

        self.collector = NetworkDataCollector(target_host="AUTO")
        self.collector.metrics_updated.connect(self.update_ui)
        self.collector.event_occurred.connect(self.add_history_event)
        self.collector.start()

    def _init_corner_status_widget(self):
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 12, 0)
        corner_layout.setSpacing(8)

        self.lbl_status_eth = QLabel("ETH: OFF")
        self.lbl_status_eth.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #FF4444; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
        )

        self.lbl_status_wifi = QLabel("WIFI: OFF")
        self.lbl_status_wifi.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #FF4444; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
        )

        corner_layout.addWidget(self.lbl_status_eth)
        corner_layout.addWidget(self.lbl_status_wifi)
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

    def _init_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 1. 상단 네트워크 헤더 박스
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 6px;")
        info_layout = QGridLayout(info_frame)

        self.lbl_iface = QLabel("Interface: --")
        self.lbl_ssid = QLabel("SSID: Scanning...")
        self.lbl_ip = QLabel("IP: 0.0.0.0")
        self.lbl_gw = QLabel("Gateway: 0.0.0.0")
        self.lbl_bssid = QLabel("AP: --:--:--:--:--:--")
        self.lbl_target = QLabel("Target: 192.168.0.1")

        labels = [
            self.lbl_iface, self.lbl_ssid, self.lbl_ip,
            self.lbl_gw, self.lbl_bssid, self.lbl_target
        ]

        for i, lbl in enumerate(labels):
            lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #cccccc;")
            info_layout.addWidget(lbl, i // 3, i % 3)
        layout.addWidget(info_frame)

        # 2. 메트릭 요약 카드 그리드
        grid_cards = QGridLayout()
        self.card_freq = MetricCard("FREQUENCY")
        self.card_rssi = MetricCard("SIGNAL (RSSI)")
        self.card_link = MetricCard("LINK SPEED")

        self.card_lat = MetricCard("LATENCY (PING)")
        self.card_loss = MetricCard("PACKET LOSS")
        self.card_jit = MetricCard("JITTER")

        grid_cards.addWidget(self.card_freq, 0, 0)
        grid_cards.addWidget(self.card_rssi, 0, 1)
        grid_cards.addWidget(self.card_link, 0, 2)

        grid_cards.addWidget(self.card_lat, 1, 0)
        grid_cards.addWidget(self.card_loss, 1, 1)
        grid_cards.addWidget(self.card_jit, 1, 2)
        layout.addLayout(grid_cards)

        # 3. 하단 그래프용 메트릭 선택 체크박스 컨트롤 바
        ctrl_box = QWidget()
        ctrl_layout = QHBoxLayout(ctrl_box)
        ctrl_layout.setContentsMargins(4, 0, 4, 0)

        lbl_ctrl_title = QLabel("BOTTOM GRAPH METRICS:")
        lbl_ctrl_title.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        ctrl_layout.addWidget(lbl_ctrl_title)

        self.cb_lat = QCheckBox("Latency (ms)")
        self.cb_lat.setChecked(True)
        self.cb_lat.setStyleSheet("color: #FFCC00; font-size: 11px; font-weight: bold;")

        self.cb_loss = QCheckBox("Loss (%)")
        self.cb_loss.setChecked(True)
        self.cb_loss.setStyleSheet("color: #FF4444; font-size: 11px; font-weight: bold;")

        self.cb_jit = QCheckBox("Jitter (ms)")
        self.cb_jit.setChecked(True)
        self.cb_jit.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: bold;")

        ctrl_layout.addWidget(self.cb_lat)
        ctrl_layout.addWidget(self.cb_loss)
        ctrl_layout.addWidget(self.cb_jit)
        ctrl_layout.addStretch()

        layout.addWidget(ctrl_box)

        # 4. 상단 Plot (RSSI 단독)
        date_axis_top = DateAxisItem(orientation='bottom')
        self.plot_top = PlotWidget(
            axisItems={'bottom': date_axis_top},
            title='<span style="color: #00FF66; font-size: 10px; font-weight: bold;">SIGNAL HISTORY (RSSI dBm)</span>'
        )
        self.plot_top.setYRange(-100, -30)
        self.plot_top.getAxis('left').setLabel('RSSI', units='dBm', color='#00FF66')
        self.plot_top.showGrid(x=True, y=True, alpha=0.3)
        self.plot_top.setMenuEnabled(False)

        # [핵심] MainWindow 멤버 변수로 vb1 할당 (AttributeError 원천 차단)
        self.vb1: Any = self.plot_top.getViewBox()

        # 5. 하단 Plot (Latency / Loss / Jitter 다중)
        date_axis_bottom = DateAxisItem(orientation='bottom')
        self.plot_bottom = PlotWidget(
            axisItems={'bottom': date_axis_bottom},
            title='<span style="color: #FFCC00; font-size: 10px; font-weight: bold;">QUALITY METRICS (Latency / Loss / Jitter)</span>'
        )
        self.plot_bottom.setYRange(0, 100)
        self.plot_bottom.getAxis('left').setLabel('Quality', units='ms / %', color='#FFCC00')
        self.plot_bottom.showGrid(x=True, y=True, alpha=0.3)
        self.plot_bottom.setMenuEnabled(False)

        # 상/하단 그래프 시간 축(X축) 동기화 바인딩
        self.plot_bottom.setXLink(self.plot_top)

        tick_font = QFont()
        tick_font.setPixelSize(10)
        tick_font.setBold(True)

        for plt in [self.plot_top, self.plot_bottom]:
            for axis in ['left', 'bottom']:
                ax = plt.getAxis(axis)
                ax.setTickFont(tick_font)
                ax.setTextPen('#888888')

        # 커브 객체 생성 및 뷰포트 배치
        self.curve_rssi = self.plot_top.plot(pen=pg.mkPen(color="#00FF66", width=2))
        self.curve_lat = self.plot_bottom.plot(pen=pg.mkPen(color="#FFCC00", width=2))
        self.curve_loss = self.plot_bottom.plot(pen=pg.mkPen(color="#FF4444", width=2))
        self.curve_jit = self.plot_bottom.plot(pen=pg.mkPen(color="#00E5FF", width=2))

        # 체크박스 토글 시그널 바인딩
        self.cb_lat.stateChanged.connect(lambda s: self.curve_lat.setVisible(bool(s)))
        self.cb_loss.stateChanged.connect(lambda s: self.curve_loss.setVisible(bool(s)))
        self.cb_jit.stateChanged.connect(lambda s: self.curve_jit.setVisible(bool(s)))

        # 상/하단 그래프 2단 레이아웃 추가 (상단 40%, 하단 60% 비율)
        layout.addWidget(self.plot_top, stretch=2)
        layout.addWidget(self.plot_bottom, stretch=3)

        # 6. 헬스 스코어 바
        score_frame = QFrame()
        score_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 6px;")
        score_layout = QVBoxLayout(score_frame)

        self.lbl_score_text = QLabel("STATUS: CALCULATING")
        self.lbl_score_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_score_text.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.progress_score = QProgressBar()
        self.progress_score.setRange(0, 100)
        self.progress_score.setFixedHeight(10)
        self.progress_score.setTextVisible(False)

        score_layout.addWidget(self.lbl_score_text)
        score_layout.addWidget(self.progress_score)
        layout.addWidget(score_frame)

        self.tabs.addTab(tab, "Dashboard")

    def _init_survey_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        lbl = QLabel("Spatial Network Heatmap (ROS 2 /odom Integration Target)")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #666666; font-size: 14px; font-weight: bold;")
        layout.addWidget(lbl)
        self.tabs.addTab(tab, "Survey")

    def _init_history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.table_history = QTableWidget(0, 4)
        self.table_history.setHorizontalHeaderLabels(["Timestamp", "Type", "Level", "Details"])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_history.setStyleSheet("background-color: #252526; color: white; gridline-color: #444;")

        layout.addWidget(self.table_history)
        self.tabs.addTab(tab, "History")

    def _init_settings_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.input_host = QLineEdit("AUTO")
        self.input_host.setPlaceholderText("IP 주소 입력 또는 'AUTO' (자동 게이트웨이)")
        self.input_host.setStyleSheet("background-color: #2b2b2b; color: white; padding: 4px;")
        layout.addRow("Ping Target Host / Gateway:", self.input_host)

        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("Apply Settings")
        btn_apply.setStyleSheet("background-color: #007acc; color: white; padding: 6px; font-weight: bold;")
        btn_apply.clicked.connect(self._apply_settings)

        btn_auto = QPushButton("Reset to AUTO")
        btn_auto.setStyleSheet("background-color: #3a3d41; color: white; padding: 6px;")
        btn_auto.clicked.connect(self._set_auto_target)

        btn_layout.addWidget(btn_apply)
        btn_layout.addWidget(btn_auto)
        layout.addRow(btn_layout)

        self.tabs.addTab(tab, "Settings")

    def _apply_settings(self):
        new_target = self.input_host.text().strip()
        if new_target:
            self.collector.target_host = new_target

    def _set_auto_target(self):
        self.input_host.setText("AUTO")
        self.collector.target_host = "AUTO"

    def add_history_event(self, ts: str, event_type: str, level: str, details: str):
        # 최신 이벤트를 항상 최상단 행(인덱스 0)에 삽입
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

        # 메모리 보존을 위해 최대 200개 행 유지
        if self.table_history.rowCount() > 200:
            self.table_history.removeRow(200)

    def update_ui(self, m: NetworkMetrics):
        # 1. 유/무선 연결 상태 배지 업데이트
        if m.wired_connected:
            self.lbl_status_eth.setText("ETH: ON")
            self.lbl_status_eth.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #00FF66; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
            )
        else:
            self.lbl_status_eth.setText("ETH: OFF")
            self.lbl_status_eth.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #FF4444; background: #2b2b2b; padding: 3px 8px; border-radius: 4px;"
            )

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

        # 2. 네트워크 텍스트 정보 레이블 업데이트
        self.lbl_iface.setText(f"Interface: {m.interface}")
        self.lbl_ssid.setText(f"SSID: {m.ssid}")
        self.lbl_ip.setText(f"IP: {m.ip_addr}")
        self.lbl_gw.setText(f"Gateway: {m.gateway}")
        self.lbl_bssid.setText(f"AP: {m.bssid}")
        self.lbl_target.setText(f"Target: {m.target_host}")

        # 3. 메트릭 요약 카드 업데이트
        if m.wifi_connected:
            rssi_status = "GOOD" if m.rssi >= -60 else ("WARN" if m.rssi >= -70 else "BAD")
            rssi_color = "#00FF66" if m.rssi >= -60 else ("#FFCC00" if m.rssi >= -70 else "#FF4444")
            self.card_rssi.set_value(f"{m.rssi} dBm", rssi_status, rssi_color)
        else:
            self.card_rssi.set_value("--", "BAD", "#FF4444")

        lat_status = "GOOD" if m.latency_ms < 30 else ("WARN" if m.latency_ms < 80 else "BAD")
        lat_color = "#00FF66" if m.latency_ms < 30 else ("#FFCC00" if m.latency_ms < 80 else "#FF4444")
        self.card_lat.set_value(f"{m.latency_ms} ms" if m.wifi_connected else "--", lat_status if m.wifi_connected else "BAD", lat_color if m.wifi_connected else "#FF4444")

        loss_status = "GOOD" if m.packet_loss_pct == 0 else "BAD"
        loss_color = "#00FF66" if m.packet_loss_pct == 0 else "#FF4444"
        self.card_loss.set_value(f"{m.packet_loss_pct} %", loss_status, loss_color)

        jit_status = "GOOD" if m.jitter_ms < 5.0 else ("WARN" if m.jitter_ms < 15.0 else "BAD")
        jit_color = "#00FF66" if m.jitter_ms < 5.0 else ("#FFCC00" if m.jitter_ms < 15.0 else "#FF4444")
        self.card_jit.set_value(f"{m.jitter_ms} ms" if m.wifi_connected else "--", jit_status if m.wifi_connected else "BAD", jit_color if m.wifi_connected else "#FF4444")

        link_val = int(match.group()) if (match := re.search(r'\d+', m.link_speed_mbps)) else 0
        link_status = "GOOD" if link_val >= 150 else ("WARN" if link_val >= 54 else "BAD")
        link_color = "#00FF66" if link_val >= 150 else ("#FFCC00" if link_val >= 54 else "#FF4444")
        self.card_link.set_value(m.link_speed_mbps if m.wifi_connected else "--", link_status if m.wifi_connected else "BAD", link_color if m.wifi_connected else "#FF4444")

        freq_val = int(match.group()) if (match := re.search(r'\d+', m.freq_ghz)) else 0
        freq_status = "GOOD" if freq_val >= 4900 else "WARN"
        freq_color = "#00FF66" if freq_val >= 4900 else "#FF4444"
        self.card_freq.set_value(m.freq_ghz if m.wifi_connected else "--", freq_status if m.wifi_connected else "BAD", freq_color if m.wifi_connected else "#FF4444")

        # 4. 히스토리 큐 데이터 기록
        now_ts = time.time()
        self.time_history.append(now_ts)
        self.rssi_history.append(m.rssi if m.wifi_connected else -100)
        self.lat_history.append(m.latency_ms if m.wifi_connected else 0.0)
        self.loss_history.append(m.packet_loss_pct if m.wifi_connected else 100.0)
        self.jit_history.append(m.jitter_ms if m.wifi_connected else 0.0)

        ts_list = list(self.time_history)

        # 5. 상단 RSSI Plot 데이터 및 시간 축 갱신 (self.vb1 활용)
        self.curve_rssi.setData(ts_list, list(self.rssi_history))
        self.vb1.setXRange(now_ts - 60, now_ts, padding=0.0)

        # 6. 하단 Quality Metrics Plot 데이터 갱신 (상/하단 setXLink로 연결됨)
        self.curve_lat.setData(ts_list, list(self.lat_history))
        self.curve_loss.setData(ts_list, list(self.loss_history))
        self.curve_jit.setData(ts_list, list(self.jit_history))

        # 7. 종합 헬스 프로그레스 바 갱신
        self.progress_score.setValue(m.score)
        score_color = "#00FF66" if m.score >= 70 else ("#FFCC00" if m.score >= 40 else "#FF4444")
        self.lbl_score_text.setText(f"{m.status_text} ({m.score} / 100)")
        self.lbl_score_text.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {score_color};")
        self.progress_score.setStyleSheet(f"""
            QProgressBar::chunk {{ background-color: {score_color}; border-radius: 3px; }}
            QProgressBar {{ background-color: #333333; border: none; border-radius: 3px; }}
        """)

    def closeEvent(self, event):
        self.collector.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
