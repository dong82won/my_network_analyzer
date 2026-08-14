#!/usr/bin/env python3
import sys
import re
import subprocess
import statistics
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QFrame, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QFormLayout, QPushButton
)
import pyqtgraph as pg

# PyQtGraph 글로벌 어두운 테마 설정
pg.setConfigOption('background', '#252526')
pg.setConfigOption('foreground', '#CCCCCC')

@dataclass
class NetworkMetrics:
    interface: str = "wlan0"
    ssid: str = "Scanning..."
    bssid: str = "--:--:--:--:--:--"
    ip_addr: str = "0.0.0.0"
    gateway: str = "0.0.0.0"
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

    def __init__(self, target_host="8.8.8.8", interface="wlan0"):
        super().__init__()
        self.target_host = target_host
        self.interface = interface
        self.is_running = True
        self.last_bssid = ""

    def run(self):
        while self.is_running:
            metrics = NetworkMetrics(interface=self.interface)
            self._get_wifi_info(metrics)
            self._get_ip_info(metrics)
            self._run_ping_test(metrics)
            self._calculate_health_score(metrics)

            # AP 로밍 감지 로직
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
            # 1. nmcli를 통해 현재 활성화된 Wi-Fi의 인터페이스 이름 및 AP 정보 수집
            cmd = ["nmcli", "-t", "-f", "ACTIVE,DEVICE,SSID,BSSID,SIGNAL,FREQ,RATE", "dev", "wifi"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            for line in res.stdout.strip().split('\n'):
                if line.startswith("yes:"):
                    parts = line.split(':')
                    if len(parts) >= 7:
                        # 활성화된 실제 무선 인터페이스 이름 자동 업데이트 (예: wlxfc221c5f4173)
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
            # 자동 감지된 인터페이스 이름(self.interface) 기반으로 IP 및 Gateway 조회
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
        try:
            cmd = ["ping", "-c", "3", "-i", "0.2", "-W", "1", self.target_host]
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
        self.val_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #00FF66;")
        self.status_lbl = QLabel("GOOD")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #00FF66;")

        val_layout.addWidget(self.val_lbl)
        val_layout.addWidget(self.status_lbl)

        layout.addWidget(self.title_lbl)
        layout.addLayout(val_layout)

    def set_value(self, val_str: str, status_str: str, color: str = "#00FF66"):
        self.val_lbl.setText(val_str)
        self.val_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")
        self.status_lbl.setText(status_str)
        self.status_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {color};")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robot Network Analyzer (Ubuntu 24.04)")
        self.resize(700, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")

        self.rssi_history = deque(maxlen=60)  # 최근 60초 데이터 버퍼

        # Main Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #333333; background: #1e1e1e; }
            QTabBar::tab { background: #2d2d2d; color: #888888; padding: 8px 16px; font-weight: bold; }
            QTabBar::tab:selected { background: #007acc; color: white; }
        """)
        self.setCentralWidget(self.tabs)

        # Build Tabs
        self._init_dashboard_tab()
        self._init_survey_tab()
        self._init_history_tab()
        self._init_settings_tab()

        # Collector Start
        self.collector = NetworkDataCollector()
        self.collector.metrics_updated.connect(self.update_ui)
        self.collector.start()

    def _init_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 1. Info Header Bar
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 6px;")
        info_layout = QGridLayout(info_frame)

        self.lbl_iface = QLabel("Interface: wlan0")
        self.lbl_ssid = QLabel("SSID: Scanning...")
        self.lbl_ip = QLabel("IP: 0.0.0.0")
        self.lbl_gw = QLabel("Gateway: 0.0.0.0")
        self.lbl_bssid = QLabel("AP: --:--:--:--:--:--")

        for i, lbl in enumerate([self.lbl_iface, self.lbl_ssid, self.lbl_ip, self.lbl_gw, self.lbl_bssid]):
            lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #cccccc;")
            info_layout.addWidget(lbl, i // 3, i % 3)
        layout.addWidget(info_frame)

        # 2. Key Metrics Cards
        cards_layout = QHBoxLayout()
        self.card_rssi = MetricCard("SIGNAL")
        self.card_lat = MetricCard("LATENCY")
        self.card_loss = MetricCard("PACKET LOSS")
        cards_layout.addWidget(self.card_rssi)
        cards_layout.addWidget(self.card_lat)
        cards_layout.addWidget(self.card_loss)
        layout.addLayout(cards_layout)

        # 3. Realtime Signal History Plot (PyQtGraph)
        self.plot_widget = pg.PlotWidget(title="Signal History (RSSI dBm - Last 60s)")
        self.plot_widget.setYRange(-90, -30)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color="#00FF66", width=2))
        layout.addWidget(self.plot_widget)

        # 4. Detailed Link Bar
        self.lbl_detail_bar = QLabel("Ping: -- ms | Jitter: -- ms | Loss: -- % | Link: -- Mbps | Freq: --")
        self.lbl_detail_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_detail_bar.setStyleSheet("background-color: #2b2b2b; padding: 6px; border-radius: 4px; font-weight: bold; color: #aaa;")
        layout.addWidget(self.lbl_detail_bar)

        # 5. Overall Health Gauge
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

    def _init_settings_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.input_host = QLineEdit("8.8.8.8")
        self.input_host.setStyleSheet("background-color: #2b2b2b; color: white; padding: 4px;")
        layout.addRow("Ping Target Host / Gateway:", self.input_host)

        btn_apply = QPushButton("Apply Settings")
        btn_apply.setStyleSheet("background-color: #007acc; color: white; padding: 6px; font-weight: bold;")
        btn_apply.clicked.connect(self._apply_settings)
        layout.addRow(btn_apply)

        self.tabs.addTab(tab, "Settings")

    def _apply_settings(self):
        self.collector.target_host = self.input_host.text().strip()

    def update_ui(self, m: NetworkMetrics):
        # Header Info Update
        self.lbl_iface.setText(f"Interface: {m.interface}")
        self.lbl_ssid.setText(f"SSID: {m.ssid}")
        self.lbl_ip.setText(f"IP: {m.ip_addr}")
        self.lbl_gw.setText(f"Gateway: {m.gateway}")
        self.lbl_bssid.setText(f"AP: {m.bssid}")

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

        # Plot Data Buffer Update
        self.rssi_history.append(m.rssi)
        self.curve.setData(list(self.rssi_history))

        # Detail Bar Update
        self.lbl_detail_bar.setText(
            f"Ping: {m.latency_ms} ms | Jitter: {m.jitter_ms} ms | Loss: {m.packet_loss_pct}% | Link: {m.link_speed_mbps} | Freq: {m.freq_ghz}"
        )

        # Score & Progress Update
        self.progress_score.setValue(m.score)
        score_color = "#00FF66" if m.score >= 70 else ("#FFCC00" if m.score >= 40 else "#FF4444")
        self.lbl_score_text.setText(f"{m.status_text} ({m.score} / 100)")
        self.lbl_score_text.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {score_color};")
        self.progress_score.setStyleSheet(f"""
            QProgressBar::chunk {{ background-color: {score_color}; border-radius: 3px; }}
            QProgressBar {{ background-color: #333333; border: none; border-radius: 3px; }}
        """)

        # Log Roaming Event to History Tab
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
