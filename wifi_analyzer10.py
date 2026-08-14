#!/usr/bin/env python3
import sys
import re
import time
import subprocess
import statistics
from datetime import datetime
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QFrame, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QFormLayout, QPushButton
)
import pyqtgraph as pg

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

            # 순수 관찰 모드: OS 커널 정보 읽기
            self._get_wifi_info(metrics)
            self._get_wired_info(metrics)
            self._get_ip_info(metrics)

            if self.target_host.upper() == "AUTO":
                metrics.target_host = metrics.gateway if metrics.gateway != "0.0.0.0" else "8.8.8.8"
            else:
                metrics.target_host = self.target_host

            self._run_ping_test(metrics)
            self._calculate_health_score(metrics)

            # 상태 머신 기반 이벤트 검출
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

            # 상태 머신 업데이트
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
            # NetworkManager의 장치 타입(TYPE)과 상태(STATE)를 직접 조회
            # GNOME Quick Settings / OS 네트워크 제어 상태와 100% 동기화
            cmd = ["nmcli", "-t", "-f", "TYPE,STATE", "dev"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1)

            wired_up = False
            for line in res.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 2:
                    dev_type, dev_state = parts[0], parts[1]
                    # 타입이 'ethernet'이고 상태가 'connected'인 경우에만 유선 연결(ON)로 인정
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
        self.resize(750, 650)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")

        self.time_history = deque(maxlen=60)
        self.rssi_history = deque(maxlen=60)

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

        date_axis = pg.DateAxisItem(orientation='bottom')
        title_html = '<span style="color: #888888; font-size: 11px; font-weight: bold;">SIGNAL HISTORY (RSSI dBm - REALTIME)</span>'

        self.plot_widget = pg.PlotWidget(
            axisItems={'bottom': date_axis},
            title=title_html
        )
        view_box = self.plot_widget.getViewBox()
        view_box.setMouseEnabled(x=False, y=False)
        view_box.setMenuEnabled(False)

        tick_font = QFont()
        tick_font.setPixelSize(11)
        tick_font.setBold(True)

        left_axis = self.plot_widget.getAxis('left')
        left_axis.setTickFont(tick_font)
        left_axis.setTextPen('#888888')

        bottom_axis = self.plot_widget.getAxis('bottom')
        bottom_axis.setTickFont(tick_font)
        bottom_axis.setTextPen('#888888')

        self.plot_widget.setYRange(-100, -30)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        self.curve = self.plot_widget.plot(pen=pg.mkPen(color="#00FF66", width=2))
        layout.addWidget(self.plot_widget)

        score_frame = QFrame()
        score_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 8px;")
        score_layout = QVBoxLayout(score_frame)

        self.lbl_score_text = QLabel("STATUS: CALCULATING")
        self.lbl_score_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_score_text.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.progress_score = QProgressBar()
        self.progress_score.setRange(0, 100)
        self.progress_score.setFixedHeight(12)
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
        self.table_history.insertRow(0)

        item_ts = QTableWidgetItem(ts)
        item_type = QTableWidgetItem(event_type)
        item_level = QTableWidgetItem(level)
        item_details = QTableWidgetItem(details)

        if level == "INFO":
            color = QColor("#00FF66")
        elif level == "WARN":
            color = QColor("#FFCC00")
        else: # ERROR
            color = QColor("#FF4444")

        item_type.setForeground(color)
        item_level.setForeground(color)

        self.table_history.setItem(0, 0, item_ts)
        self.table_history.setItem(0, 1, item_type)
        self.table_history.setItem(0, 2, item_level)
        self.table_history.setItem(0, 3, item_details)

        if self.table_history.rowCount() > 200:
            self.table_history.removeRow(200)

    def update_ui(self, m: NetworkMetrics):
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

        self.lbl_iface.setText(f"Interface: {m.interface}")
        self.lbl_ssid.setText(f"SSID: {m.ssid}")
        self.lbl_ip.setText(f"IP: {m.ip_addr}")
        self.lbl_gw.setText(f"Gateway: {m.gateway}")
        self.lbl_bssid.setText(f"AP: {m.bssid}")
        self.lbl_target.setText(f"Target: {m.target_host}")

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

        now_ts = time.time()
        self.time_history.append(now_ts)
        self.rssi_history.append(m.rssi if m.wifi_connected else -100)

        self.curve.setData(list(self.time_history), list(self.rssi_history))
        self.plot_widget.getViewBox().setRange(xRange=(now_ts - 60, now_ts), padding=0.0)

        self.progress_score.setValue(m.score)
        score_color = "#00FF66" if m.score >= 70 else ("#FFCC00" if m.score >= 40 else "#FF4444")
        self.lbl_score_text.setText(f"{m.status_text} ({m.score} / 100)")
        self.lbl_score_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {score_color};")
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
