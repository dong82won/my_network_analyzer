#!/usr/bin/env python3
import sys
import re
import subprocess
import statistics
from dataclasses import dataclass
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QFrame, QGridLayout
)

@dataclass
class NetworkMetrics:
    interface: str = "wlan0"
    ssid: str = "Scanning..."
    bssid: str = "--:--:--:--:--:--"
    ip_addr: str = "0.0.0.0"
    rssi: int = -100
    latency_ms: float = 0.0
    packet_loss_pct: float = 0.0
    jitter_ms: float = 0.0
    score: int = 0
    status_text: str = "POOR"

class NetworkDataCollector(QThread):
    metrics_updated = Signal(NetworkMetrics)

    def __init__(self, target_host="8.8.8.8", interface="wlan0"):
        super().__init__()
        self.target_host = target_host
        self.interface = interface
        self.is_running = True

    def run(self):
        while self.is_running:
            metrics = NetworkMetrics(interface=self.interface)
            self._get_wifi_info(metrics)
            self._get_ip_info(metrics)
            self._run_ping_test(metrics)
            self._calculate_health_score(metrics)

            self.metrics_updated.emit(metrics)
            self.msleep(1000)

    def stop(self):
        self.is_running = False
        self.wait()

    def _get_wifi_info(self, metrics: NetworkMetrics):
        try:
            cmd = ["nmcli", "-t", "-f", "ACTIVE,SSID,BSSID,SIGNAL", "dev", "wifi"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            for line in res.stdout.strip().split('\n'):
                if line.startswith("yes:"):
                    parts = line.split(':')
                    if len(parts) >= 4:
                        metrics.ssid = parts[1]
                        metrics.bssid = ":".join(parts[2:-1]) if len(parts) > 4 else parts[2]
                        signal_pct = int(parts[-1])
                        metrics.rssi = int((signal_pct / 2) - 100)
                        break
        except Exception:
            pass

    def _get_ip_info(self, metrics: NetworkMetrics):
        try:
            cmd = ["ip", "-4", "addr", "show", self.interface]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            match = re.search(r'inet\s+([\d\.]+)', res.stdout)
            if match:
                metrics.ip_addr = match.group(1)
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
        self.setStyleSheet("background-color: #2b2b2b; border-radius: 8px; padding: 10px;")
        layout = QVBoxLayout(self)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        self.val_lbl = QLabel("--")
        self.val_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #00FF66;")
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.val_lbl)

    def set_value(self, val_str: str, color: str = "#00FF66"):
        self.val_lbl.setText(val_str)
        self.val_lbl.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Portable Wi-Fi Analyzer")
        self.resize(550, 400)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Info Bar
        info_layout = QHBoxLayout()
        self.lbl_ssid = QLabel("SSID: --")
        self.lbl_bssid = QLabel("BSSID: --")
        self.lbl_ip = QLabel("IP: --")
        for lbl in (self.lbl_ssid, self.lbl_bssid, self.lbl_ip):
            lbl.setStyleSheet("font-weight: bold; color: #cccccc; font-size: 12px;")
            info_layout.addWidget(lbl)
        main_layout.addLayout(info_layout)

        # Cards Grid
        grid_layout = QGridLayout()
        self.card_rssi = MetricCard("SIGNAL (RSSI)")
        self.card_lat = MetricCard("LATENCY")
        self.card_loss = MetricCard("PACKET LOSS")
        self.card_jit = MetricCard("JITTER")

        grid_layout.addWidget(self.card_rssi, 0, 0)
        grid_layout.addWidget(self.card_lat, 0, 1)
        grid_layout.addWidget(self.card_loss, 1, 0)
        grid_layout.addWidget(self.card_jit, 1, 1)
        main_layout.addLayout(grid_layout)

        # Health Gauge
        score_frame = QFrame()
        score_frame.setStyleSheet("background-color: #252526; border-radius: 8px; padding: 10px;")
        score_layout = QVBoxLayout(score_frame)

        self.lbl_score_text = QLabel("STATUS: CALCULATING")
        self.lbl_score_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_score_text.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.progress_score = QProgressBar()
        self.progress_score.setRange(0, 100)
        self.progress_score.setFixedHeight(16)
        self.progress_score.setTextVisible(False)

        score_layout.addWidget(self.lbl_score_text)
        score_layout.addWidget(self.progress_score)
        main_layout.addWidget(score_frame)

        # Background Thread Start
        self.collector = NetworkDataCollector()
        self.collector.metrics_updated.connect(self.update_ui)
        self.collector.start()

    def update_ui(self, m: NetworkMetrics):
        self.lbl_ssid.setText(f"SSID: {m.ssid}")
        self.lbl_bssid.setText(f"BSSID: {m.bssid}")
        self.lbl_ip.setText(f"IP: {m.ip_addr}")

        self.card_rssi.set_value(f"{m.rssi} dBm", "#00FF66" if m.rssi >= -60 else ("#FFCC00" if m.rssi >= -70 else "#FF4444"))
        self.card_lat.set_value(f"{m.latency_ms} ms", "#00FF66" if m.latency_ms < 30 else "#FFCC00")
        self.card_loss.set_value(f"{m.packet_loss_pct} %", "#00FF66" if m.packet_loss_pct == 0 else "#FF4444")
        self.card_jit.set_value(f"{m.jitter_ms} ms", "#00FF66" if m.jitter_ms < 10 else "#FFCC00")

        self.progress_score.setValue(m.score)
        color = "#00FF66" if m.score >= 70 else ("#FFCC00" if m.score >= 40 else "#FF4444")
        self.lbl_score_text.setText(f"{m.status_text} ({m.score} / 100)")
        self.lbl_score_text.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        self.progress_score.setStyleSheet(f"""
            QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
            QProgressBar {{ background-color: #333333; border: none; border-radius: 4px; }}
        """)

    def closeEvent(self, event):
        self.collector.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
