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
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QFrame, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QFormLayout, QPushButton
)
import pyqtgraph as pg

# PyQtGraph 글로벌 다크 테마 설정
pg.setConfigOption('background', '#252526')
pg.setConfigOption('foreground', '#CCCCCC')

@dataclass
class NetworkMetrics:
    interface: str = "wlan0"
    ssid: str = "Scanning..."
    bssid: str = "--:--:--:--:--:--"
    ip_addr: str = "0.0.0.0"
    gateway: str = "0.0.0.0"
    target_host: str = "192.168.0.1"  # Ping 대상 IP 추가
    freq_ghz: str = "--"
    link_speed_mbps: str = "--"
    rssi: int = -100
    latency_ms: float = 0.0
    packet_loss_pct: float = 0.0
    jitter_ms: float = 0.0
    score: int = 0
    status_text: str = "POOR"
    roaming_event: str = ""

class NetworkDataCollector(QThread):
    metrics_updated = Signal(NetworkMetrics)

    def __init__(self, target_host="AUTO", interface="wlan0"):
        super().__init__()
        self.target_host = target_host  # 기본값 "AUTO"
        self.interface = interface
        self.is_running = True
        self.last_bssid = ""

    def run(self):
        while self.is_running:
            metrics = NetworkMetrics(interface=self.interface)
            self._get_wifi_info(metrics)
            self._get_ip_info(metrics)

            # [핵심] AUTO 모드일 경우 자동 수집된 Gateway IP를 Ping Target으로 동적 할당
            if self.target_host.upper() == "AUTO":
                metrics.target_host = metrics.gateway if metrics.gateway != "0.0.0.0" else "8.8.8.8"
            else:
                metrics.target_host = self.target_host

            self._run_ping_test(metrics)
            self._calculate_health_score(metrics)

            # AP 로밍 감지
            if self.last_bssid and metrics.bssid != "--:--:--:--:--:--" and self.last_bssid != metrics.bssid:
                metrics.roaming_event = f"AP Changed: {self.last_bssid} -> {metrics.bssid}"
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
                    parts = line.split(':')
                    if len(parts) >= 7:
                        metrics.interface = parts[1]
                        self.interface = parts[1]

                        metrics.ssid = parts[2]
                        raw_bssid = ":".join(parts[3:-3]) if len(parts) > 7 else parts[3]
                        metrics.bssid = raw_bssid.replace('\\', '')

                        signal_pct = int(parts[-3])
                        metrics.rssi = int((signal_pct / 2) - 100)
                        metrics.freq_ghz = parts[-2]
                        metrics.link_speed_mbps = parts[-1]
                        break
        except Exception:
            pass

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

    # def _run_ping_test(self, metrics: NetworkMetrics):
    #     try:
    #         cmd = ["ping", "-c", "3", "-i", "0.2", "-W", "1", self.target_host]
    #         res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    #         if res.returncode == 0:
    #             times = [float(t) for t in re.findall(r'time=([\d\.]+)', res.stdout)]
    #             loss_match = re.search(r'([\d\.]+)%\s+packet loss', res.stdout)
    #             if times:
    #                 metrics.latency_ms = round(statistics.mean(times), 1)
    #                 metrics.jitter_ms = round(statistics.stdev(times), 1) if len(times) > 1 else 0.0
    #             if loss_match:
    #                 metrics.packet_loss_pct = float(loss_match.group(1))
    #         else:
    #             metrics.packet_loss_pct = 100.0
    #     except Exception:
    #         metrics.packet_loss_pct = 100.0

    def _run_ping_test(self, metrics: NetworkMetrics):
            # target_host가 유효하지 않을 경우 예외 처리
            if not metrics.target_host or metrics.target_host == "0.0.0.0":
                metrics.packet_loss_pct = 100.0
                return

            try:
                cmd = ["ping", "-c", "3", "-i", "0.2", "-W", "1", metrics.target_host]
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
                    metrics.packet_loss_pct = 100.0
            except Exception:
                metrics.packet_loss_pct = 100.0

    def _calculate_health_score(self, metrics: NetworkMetrics):
        s_rssi = max(0, min(100, int((metrics.rssi + 85) * (100 / 35))))
        s_lat = max(0, min(100, int(100 - ((metrics.latency_ms - 10) * (100 / 140)))))
        s_loss = max(0, min(100, int(100 - (metrics.packet_loss_pct * 10))))
        s_jit = max(0, min(100, int(100 - ((metrics.jitter_ms - 2) * (100 / 28)))))

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

        self._init_dashboard_tab()
        self._init_survey_tab()
        self._init_history_tab()
        self._init_settings_tab()


        # [핵심] 하드코딩 제거: 기본 Ping 대상을 "AUTO"로 지정하여 스레드 생성
        self.collector = NetworkDataCollector(target_host="AUTO")
        self.collector.metrics_updated.connect(self.update_ui)
        self.collector.start()

    def _init_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 1. Info Header Bar (Ping Target 추가)
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 6px;")
        info_layout = QGridLayout(info_frame)

        self.lbl_iface = QLabel("Interface: --")
        self.lbl_ssid = QLabel("SSID: Scanning...")
        self.lbl_ip = QLabel("IP: 0.0.0.0")
        self.lbl_gw = QLabel("Gateway: 0.0.0.0")
        self.lbl_bssid = QLabel("AP: --:--:--:--:--:--")
        self.lbl_target = QLabel("Target: 192.168.0.1")  # Target IP 라벨 추가

        labels = [
            self.lbl_iface, self.lbl_ssid, self.lbl_ip,
            self.lbl_gw, self.lbl_bssid, self.lbl_target
        ]

        for i, lbl in enumerate(labels):
            lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #cccccc;")
            info_layout.addWidget(lbl, i // 3, i % 3)
        layout.addWidget(info_frame)

        # 2. Key Metrics Grid
        grid_cards = QGridLayout()
        self.card_rssi = MetricCard("SIGNAL (RSSI)")
        self.card_lat = MetricCard("LATENCY (PING)")
        self.card_loss = MetricCard("PACKET LOSS")
        self.card_jit = MetricCard("JITTER")
        self.card_link = MetricCard("LINK SPEED")
        self.card_freq = MetricCard("FREQUENCY")

        grid_cards.addWidget(self.card_rssi, 0, 0)
        grid_cards.addWidget(self.card_lat, 0, 1)
        grid_cards.addWidget(self.card_loss, 0, 2)
        grid_cards.addWidget(self.card_jit, 1, 0)
        grid_cards.addWidget(self.card_link, 1, 1)
        grid_cards.addWidget(self.card_freq, 1, 2)
        layout.addLayout(grid_cards)

        # 3. Realtime Signal History Plot
        date_axis = pg.DateAxisItem(orientation='bottom')
        self.plot_widget = pg.PlotWidget(
            axisItems={'bottom': date_axis},
            title="Signal History (RSSI dBm - Realtime)"
        )
        view_box = self.plot_widget.getViewBox()
        view_box.setMouseEnabled(x=False, y=False)
        view_box.setMenuEnabled(False)

        self.plot_widget.setYRange(-100, -30)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        self.curve = self.plot_widget.plot(pen=pg.mkPen(color="#00FF66", width=2))
        layout.addWidget(self.plot_widget)

        # 4. Overall Health Gauge
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

        self.table_history = QTableWidget(0, 3)
        self.table_history.setHorizontalHeaderLabels(["Timestamp", "Event Type", "Details"])
        self.table_history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_history.setStyleSheet("background-color: #252526; color: white; gridline-color: #444;")

        layout.addWidget(self.table_history)
        self.tabs.addTab(tab, "History")

    # def _init_settings_tab(self):
    #     tab = QWidget()
    #     layout = QFormLayout(tab)

    #     # 기본 설정값: 192.168.0.1 (로컬 게이트웨이)
    #     self.input_host = QLineEdit("192.168.0.1")
    #     self.input_host.setStyleSheet("background-color: #2b2b2b; color: white; padding: 4px;")
    #     layout.addRow("Ping Target Host / Gateway:", self.input_host)

    #     btn_apply = QPushButton("Apply Settings")
    #     btn_apply.setStyleSheet("background-color: #007acc; color: white; padding: 6px; font-weight: bold;")
    #     btn_apply.clicked.connect(self._apply_settings)
    #     layout.addRow(btn_apply)

    #     self.tabs.addTab(tab, "Settings")

    def _init_settings_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        # 입력창 기본값을 "AUTO"로 설정
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

    def update_ui(self, m: NetworkMetrics):
        # Header Info Update (Ping Target 실시간 업데이트)
        self.lbl_iface.setText(f"Interface: {m.interface}")
        self.lbl_ssid.setText(f"SSID: {m.ssid}")
        self.lbl_ip.setText(f"IP: {m.ip_addr}")
        self.lbl_gw.setText(f"Gateway: {m.gateway}")
        self.lbl_bssid.setText(f"AP: {m.bssid}")
        self.lbl_target.setText(f"Target: {m.target_host}")

        # Metric Cards Update
        rssi_status = "GOOD" if m.rssi >= -60 else ("WARN" if m.rssi >= -70 else "BAD")
        rssi_color = "#00FF66" if m.rssi >= -60 else ("#FFCC00" if m.rssi >= -70 else "#FF4444")
        self.card_rssi.set_value(f"{m.rssi} dBm", rssi_status, rssi_color)

        lat_status = "GOOD" if m.latency_ms < 30 else ("WARN" if m.latency_ms < 80 else "BAD")
        lat_color = "#00FF66" if m.latency_ms < 30 else ("#FFCC00" if m.latency_ms < 80 else "#FF4444")
        self.card_lat.set_value(f"{m.latency_ms} ms", lat_status, lat_color)

        loss_status = "GOOD" if m.packet_loss_pct == 0 else "BAD"
        loss_color = "#00FF66" if m.packet_loss_pct == 0 else "#FF4444"
        self.card_loss.set_value(f"{m.packet_loss_pct} %", loss_status, loss_color)

        jit_status = "GOOD" if m.jitter_ms < 5.0 else ("WARN" if m.jitter_ms < 15.0 else "BAD")
        jit_color = "#00FF66" if m.jitter_ms < 5.0 else ("#FFCC00" if m.jitter_ms < 15.0 else "#FF4444")
        self.card_jit.set_value(f"{m.jitter_ms} ms", jit_status, jit_color)

        link_val = int(match.group()) if (match := re.search(r'\d+', m.link_speed_mbps)) else 0
        link_status = "GOOD" if link_val >= 150 else ("WARN" if link_val >= 54 else "BAD")
        link_color = "#00FF66" if link_val >= 150 else ("#FFCC00" if link_val >= 54 else "#FF4444")
        self.card_link.set_value(m.link_speed_mbps, link_status, link_color)

        freq_val = int(match.group()) if (match := re.search(r'\d+', m.freq_ghz)) else 0
        freq_status = "GOOD" if freq_val >= 4900 else "WARN"
        freq_color = "#00FF66" if freq_val >= 4900 else "#FFCC00"
        self.card_freq.set_value(m.freq_ghz, freq_status, freq_color)

        # Plot Data Buffer Update
        now_ts = time.time()
        self.time_history.append(now_ts)
        self.rssi_history.append(m.rssi)

        self.curve.setData(list(self.time_history), list(self.rssi_history))
        self.plot_widget.getViewBox().setRange(xRange=(now_ts - 60, now_ts), padding=0.0)

        # Score & Progress Update
        self.progress_score.setValue(m.score)
        score_color = "#00FF66" if m.score >= 70 else ("#FFCC00" if m.score >= 40 else "#FF4444")
        self.lbl_score_text.setText(f"{m.status_text} ({m.score} / 100)")
        self.lbl_score_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {score_color};")
        self.progress_score.setStyleSheet(f"""
            QProgressBar::chunk {{ background-color: {score_color}; border-radius: 3px; }}
            QProgressBar {{ background-color: #333333; border: none; border-radius: 3px; }}
        """)

        # History 탭 기록
        if m.roaming_event:
            row = self.table_history.rowCount()
            self.table_history.insertRow(row)
            now_str = datetime.now().strftime("%H:%M:%S")
            self.table_history.setItem(row, 0, QTableWidgetItem(now_str))
            self.table_history.setItem(row, 1, QTableWidgetItem("ROAMING"))
            self.table_history.setItem(row, 2, QTableWidgetItem(m.roaming_event))

    def closeEvent(self, event):
        self.collector.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
