#!/usr/bin/env python3
'''
Wi-Fi 단락 시 그래프 파형 그려짐 차단(NaN 처리), 붉은 카드 경고 테두리 디밍,
단락 지속시간 카운터 및 6개 센서 카드 POOR/Red 전환이 반영된 최종 DashboardTab 모듈입니다.
'''

import time
from collections import deque
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar,
    QSizePolicy, QVBoxLayout, QWidget, QCheckBox
)
import pyqtgraph as pg

from core.models import NetworkMetrics


class TimeAxisItem(pg.AxisItem):
    '''UNIX 타임스탬프 수치를 8pt 소형 'HH:MM:SS' 시계열 포맷으로 변환하는 Custom Axis'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyle(tickFont=QFont("SansSerif", 8), tickTextOffset=6)
        self.setTextPen(pg.mkPen('#888888'))

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            try:
                strings.append(time.strftime("%H:%M:%S", time.localtime(v)))
            except (ValueError, OverflowError, OSError):
                strings.append("")
        return strings


class CompactYAxisItem(pg.AxisItem):
    '''Y축 수치 겹침을 방지하고 정갈한 8pt 수치를 제공하는 Custom Y-Axis'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyle(tickFont=QFont("SansSerif", 8), tickTextOffset=4)
        self.setTextPen(pg.mkPen('#888888'))


class MetricCard(QFrame):
    '''단락 시 붉은 경고 테두리 및 어두운 적색 디밍을 지원하는 메트릭 카드'''
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(82)

        self._style_normal = """
            QFrame {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
        """
        self._style_alert = """
            QFrame {
                background-color: #2d1818;
                border: 1px solid #ff4444;
                border-radius: 6px;
            }
        """
        self.setStyleSheet(self._style_normal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setStyleSheet("color: #aaaaaa; font-size: 10px; font-weight: bold; border: none;")

        val_layout = QHBoxLayout()
        val_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_value = QLabel("--")
        self.lbl_value.setStyleSheet("color: #28a745; font-size: 18px; font-weight: bold; border: none;")

        self.lbl_status = QLabel("OFFLINE")
        self.lbl_status.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold; border: none;")

        val_layout.addWidget(self.lbl_value)
        val_layout.addStretch()
        val_layout.addWidget(self.lbl_status)

        layout.addWidget(self.lbl_title)
        layout.addLayout(val_layout)

    def set_alert_mode(self, alert_on: bool):
        '''경고 상태에 따른 테두리 및 배경 디밍 전환'''
        self.setStyleSheet(self._style_alert if alert_on else self._style_normal)

    def update_data(self, value_text: str, value_color: str, status_text: str, status_color: str):
        self.lbl_value.setText(value_text)
        self.lbl_value.setStyleSheet(f"color: {value_color}; font-size: 18px; font-weight: bold; border: none;")
        self.lbl_status.setText(status_text)
        self.lbl_status.setStyleSheet(f"color: {status_color}; font-size: 10px; font-weight: bold; border: none;")


class DashboardTab(QWidget):
    def __init__(self, main_window: Any):
        super().__init__()
        self.main_window = main_window

        # 실시간 파형 데이터 버퍼 (60초 히스토리)
        self.max_points = 60
        self.time_buffer = deque(maxlen=self.max_points)
        self.rssi_buffer = deque(maxlen=self.max_points)
        self.latency_buffer = deque(maxlen=self.max_points)
        self.loss_buffer = deque(maxlen=self.max_points)
        self.jitter_buffer = deque(maxlen=self.max_points)

        # 단락 지속 시간 카운팅용 타임스탬프
        self._disconnect_start_time: float | None = None

        self._init_ui()

        self.render_timer = QTimer(self)
        self.render_timer.setInterval(33)  # 30 FPS
        self.render_timer.timeout.connect(self._update_viewport)
        self.render_timer.start()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. 상단 네트워크 정보 카드
        info_frame = QFrame()
        info_frame.setFixedHeight(62)
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
            }
            QLabel { color: #ffffff; font-size: 12px; font-weight: bold; border: none; }
        """)
        info_layout = QGridLayout(info_frame)
        info_layout.setContentsMargins(16, 6, 16, 6)
        info_layout.setVerticalSpacing(4)

        self.lbl_interface = QLabel("Interface: --")
        self.lbl_ssid = QLabel("SSID: Scanning...")
        self.lbl_ip = QLabel("IP: 0.0.0.0")
        self.lbl_gateway = QLabel("Gateway: 0.0.0.0")
        self.lbl_bssid = QLabel("AP: --:--:--:--:--:--")
        self.lbl_target = QLabel("Target: --")

        info_layout.addWidget(self.lbl_interface, 0, 0)
        info_layout.addWidget(self.lbl_ssid, 0, 1)
        info_layout.addWidget(self.lbl_ip, 0, 2)
        info_layout.addWidget(self.lbl_gateway, 1, 0)
        info_layout.addWidget(self.lbl_bssid, 1, 1)
        info_layout.addWidget(self.lbl_target, 1, 2)

        main_layout.addWidget(info_frame)

        # 2. 종합 평가 점수 바
        score_frame = QFrame()
        score_frame.setFixedHeight(50)
        score_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #383838;
                border-radius: 6px;
            }
        """)
        score_layout = QVBoxLayout(score_frame)
        score_layout.setContentsMargins(12, 6, 12, 6)
        score_layout.setSpacing(4)

        score_text_layout = QHBoxLayout()
        lbl_score_title = QLabel("NETWORK HEALTH EVALUATION:")
        lbl_score_title.setStyleSheet("color: #aaaaaa; font-size: 10px; font-weight: bold; border: none;")

        self.lbl_score_value = QLabel("OFFLINE (0 / 100)")
        self.lbl_score_value.setStyleSheet("color: #ff4d4d; font-size: 12px; font-weight: bold; border: none;")

        score_text_layout.addWidget(lbl_score_title)
        score_text_layout.addStretch()
        score_text_layout.addWidget(self.lbl_score_value)

        self.progress_score = QProgressBar()
        self.progress_score.setFixedHeight(8)
        self.progress_score.setRange(0, 100)
        self.progress_score.setValue(0)
        self.progress_score.setTextVisible(False)
        self.progress_score.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e1e;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #ff4444;
                border-radius: 4px;
            }
        """)

        score_layout.addLayout(score_text_layout)
        score_layout.addWidget(self.progress_score)

        main_layout.addWidget(score_frame)

        # 3. 메트릭 센서 카드 그리드
        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)

        self.card_freq = MetricCard("FREQUENCY")
        self.card_speed = MetricCard("LINK SPEED")
        self.card_rssi = MetricCard("SIGNAL (RSSI)")
        self.card_latency = MetricCard("LATENCY (LAN PING)")
        self.card_jitter = MetricCard("JITTER")
        self.card_loss = MetricCard("PACKET LOSS")

        grid_layout.addWidget(self.card_freq, 0, 0)
        grid_layout.addWidget(self.card_speed, 0, 1)
        grid_layout.addWidget(self.card_rssi, 0, 2)
        grid_layout.addWidget(self.card_latency, 1, 0)
        grid_layout.addWidget(self.card_jitter, 1, 1)
        grid_layout.addWidget(self.card_loss, 1, 2)

        main_layout.addLayout(grid_layout)

        # 4. 파형 그래프 토글 컨트롤 바
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(4, 2, 4, 2)

        lbl_toggle = QLabel("PANEL DISPLAY TOGGLE:")
        lbl_toggle.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        control_layout.addWidget(lbl_toggle)

        self.chk_rssi = QCheckBox("RSSI (dBm)")
        self.chk_rssi.setChecked(True)
        self.chk_rssi.setStyleSheet("color: #00E5FF; font-size: 11px; font-weight: bold;")
        self.chk_rssi.toggled.connect(self._on_toggle_plots)

        self.chk_latency = QCheckBox("Latency (ms)")
        self.chk_latency.setChecked(True)
        self.chk_latency.setStyleSheet("color: #FFD700; font-size: 11px; font-weight: bold;")
        self.chk_latency.toggled.connect(self._on_toggle_plots)

        self.chk_jitter = QCheckBox("Jitter (ms)")
        self.chk_jitter.setChecked(True)
        self.chk_jitter.setStyleSheet("color: #34D399; font-size: 11px; font-weight: bold;")
        self.chk_jitter.toggled.connect(self._on_toggle_plots)

        self.chk_loss = QCheckBox("Loss (%)")
        self.chk_loss.setChecked(True)
        self.chk_loss.setStyleSheet("color: #FF4500; font-size: 11px; font-weight: bold;")
        self.chk_loss.toggled.connect(self._on_toggle_plots)

        control_layout.addWidget(self.chk_rssi)
        control_layout.addWidget(self.chk_latency)
        control_layout.addWidget(self.chk_jitter)
        control_layout.addWidget(self.chk_loss)
        control_layout.addStretch()

        main_layout.addLayout(control_layout)

        # 5. PlotWidgets
        pg.setConfigOption('background', '#181818')
        pg.setConfigOption('foreground', '#888888')

        self.plots_container = QWidget()
        self.plots_layout = QVBoxLayout(self.plots_container)
        self.plots_layout.setContentsMargins(0, 0, 0, 0)
        self.plots_layout.setSpacing(6)

        title_style_html = 'color: #aaaaaa; font-size: 9pt; font-weight: bold;'

        self.pw_rssi = pg.PlotWidget(axisItems={
            'bottom': TimeAxisItem(orientation='bottom'),
            'left': CompactYAxisItem(orientation='left')
        })
        self.pw_rssi.setStyleSheet("border: 1px solid #333333; border-radius: 6px;")
        self.pw_rssi.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.p1: Any = self.pw_rssi.getPlotItem()

        self.p1.setTitle(f'<span style="{title_style_html}">SIGNAL STRENGTH (dBm)</span>', justify='left')
        self.p1.showGrid(x=True, y=True, alpha=0.25)
        self.p1.setYRange(-90, -30, padding=0.05)
        self.p1.getAxis('left').setTicks([[(-80, '-80'), (-60, '-60'), (-40, '-40')]])
        self.curve_rssi = self.p1.plot(pen=pg.mkPen(color='#00E5FF', width=2))

        self.pw_time = pg.PlotWidget(axisItems={
            'bottom': TimeAxisItem(orientation='bottom'),
            'left': CompactYAxisItem(orientation='left')
        })
        self.pw_time.setStyleSheet("border: 1px solid #333333; border-radius: 6px;")
        self.pw_time.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.p2: Any = self.pw_time.getPlotItem()

        self.p2.setTitle(f'<span style="{title_style_html}">TIME METRICS (ms)</span>', justify='left')
        self.p2.showGrid(x=True, y=True, alpha=0.25)
        self.curve_latency = self.p2.plot(pen=pg.mkPen(color='#FFD700', width=2.0), name="Latency")
        self.curve_jitter = self.p2.plot(
            pen=pg.mkPen(color='#34D399', width=1.5, style=Qt.PenStyle.SolidLine),
            name="Jitter"
        )

        self.pw_loss = pg.PlotWidget(axisItems={
            'bottom': TimeAxisItem(orientation='bottom'),
            'left': CompactYAxisItem(orientation='left')
        })
        self.pw_loss.setStyleSheet("border: 1px solid #333333; border-radius: 6px;")
        self.pw_loss.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.p3: Any = self.pw_loss.getPlotItem()

        self.p3.setTitle(f'<span style="{title_style_html}">PACKET LOSS (%)</span>', justify='left')
        self.p3.showGrid(x=True, y=True, alpha=0.25)
        self.p3.setYRange(0, 100, padding=0.05)
        self.p3.getAxis('left').setTicks([[(0, '0'), (50, '50'), (100, '100')]])
        self.curve_loss = self.p3.plot(pen=pg.mkPen(color='#FF4500', width=2))

        for p in (self.p1, self.p2, self.p3):
            p.getAxis('left').setWidth(42)

        self.p2.setXLink(self.p1)
        self.p3.setXLink(self.p1)

        self.plots_layout.addWidget(self.pw_rssi, stretch=1)
        self.plots_layout.addWidget(self.pw_time, stretch=1)
        self.plots_layout.addWidget(self.pw_loss, stretch=1)

        main_layout.addWidget(self.plots_container, stretch=2)

    def _on_toggle_plots(self):
        self.pw_rssi.setVisible(self.chk_rssi.isChecked())
        show_time = self.chk_latency.isChecked() or self.chk_jitter.isChecked()
        self.pw_time.setVisible(show_time)
        self.curve_latency.setVisible(self.chk_latency.isChecked())
        self.curve_jitter.setVisible(self.chk_jitter.isChecked())
        self.pw_loss.setVisible(self.chk_loss.isChecked())

    def update_metrics(self, metrics: NetworkMetrics):
        '''실시간 데이터 수신 시 단락 처리 및 파형 그려짐 차단 실행'''
        if not metrics:
            return

        # -----------------------------------------------------------------
        # [핵심] Wi-Fi 단락(WIFI: OFF) 시 예외 처리 및 파형 차단
        # -----------------------------------------------------------------
        if not metrics.wifi_connected:
            if self._disconnect_start_time is None:
                self._disconnect_start_time = time.time()

            elapsed_sec = int(time.time() - self._disconnect_start_time)
            mins, secs = divmod(elapsed_sec, 60)
            dur_str = f"{mins:02d}:{secs:02d}"

            # 1. 헤더 정보 표시
            self.lbl_interface.setText(f"Interface: {metrics.interface}")
            self.lbl_ssid.setText("SSID: Disconnected")
            self.lbl_ip.setText("IP: 0.0.0.0")
            self.lbl_gateway.setText("Gateway: 0.0.0.0")
            self.lbl_bssid.setText("AP: --:--:--:--:--:--")
            self.lbl_target.setText("Target: OFFLINE")

            # 2. 6개 카드 테두리 경고 디밍(Red Outline) 및 POOR/Red 전환
            for card in (self.card_freq, self.card_speed, self.card_rssi,
                         self.card_latency, self.card_jitter, self.card_loss):
                card.set_alert_mode(True)

            self.card_freq.update_data("--", "#FF4444", "OFFLINE", "#FF4444")
            self.card_speed.update_data("--", "#FF4444", "OFFLINE", "#FF4444")
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#FF4444", "POOR", "#FF4444")
            self.card_latency.update_data("N/A", "#FF4444", "POOR", "#FF4444")
            self.card_jitter.update_data("N/A", "#FF4444", "POOR", "#FF4444")
            self.card_loss.update_data("100.0 %", "#FF4444", "POOR", "#FF4444")

            # 3. 종합 평가 점수 바
            self.progress_score.setValue(0)
            self.progress_score.setStyleSheet("""
                QProgressBar { background-color: #1e1e1e; border: none; border-radius: 4px; }
                QProgressBar::chunk { background-color: #ff4444; border-radius: 4px; }
            """)
            self.lbl_score_value.setText(f"OFFLINE (Disconnected: {dur_str})")
            self.lbl_score_value.setStyleSheet("color: #FF4444; font-size: 12px; font-weight: bold; border: none;")

            # 4. [핵심] 그래프 파형 그려짐 차단 (float('nan') 주입)
            # NaN 주입 시 pyqtgraph는 파형 선을 그리지 않고 구간을 끊어서(Discontinuous) 처리합니다.
            meas_time = getattr(metrics, 'timestamp', time.time())
            self.time_buffer.append(meas_time)
            self.rssi_buffer.append(float('nan'))     # RSSI 파형 끊김
            self.latency_buffer.append(float('nan'))  # Latency 파형 끊김 (0ms 그려짐 방지)
            self.jitter_buffer.append(float('nan'))   # Jitter 파형 끊김
            self.loss_buffer.append(float('nan'))     # Packet Loss 파형 끊김

            if len(self.time_buffer) > 1:
                x_data = list(self.time_buffer)
                self.curve_rssi.setData(x_data, list(self.rssi_buffer))
                self.curve_latency.setData(x_data, list(self.latency_buffer))
                self.curve_jitter.setData(x_data, list(self.jitter_buffer))
                self.curve_loss.setData(x_data, list(self.loss_buffer))

            return

        # -----------------------------------------------------------------
        # 정상 Wi-Fi 연결 복구 시 처리 파이프라인
        # -----------------------------------------------------------------
        self._disconnect_start_time = None
        for card in (self.card_freq, self.card_speed, self.card_rssi,
                     self.card_latency, self.card_jitter, self.card_loss):
            card.set_alert_mode(False)

        # 1. 헤더 정보
        self.lbl_interface.setText(f"Interface: {metrics.interface}")
        self.lbl_ssid.setText(f"SSID: {metrics.ssid}")
        self.lbl_ip.setText(f"IP: {metrics.ip_addr}")
        self.lbl_gateway.setText(f"Gateway: {metrics.gateway}")
        self.lbl_bssid.setText(f"AP: {metrics.bssid}")
        self.lbl_target.setText(f"Target: {metrics.target_host} [{metrics.target_mode}]")

        # 2. 메트릭 평가 및 데이터 업데이트
        self.card_freq.update_data(metrics.freq_ghz, "#00FF66", "GOOD", "#00FF66")
        self.card_speed.update_data(metrics.link_speed_mbps, "#00FF66", "GOOD", "#00FF66")

        if metrics.rssi >= -65:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#00FF66", "EXCELLENT", "#00FF66")
        elif metrics.rssi >= -75:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#00E5FF", "GOOD", "#00E5FF")
        elif metrics.rssi >= -85:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#FFCC00", "WARN", "#FFCC00")
        else:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#FF4444", "POOR", "#FF4444")

        lat_limit = 30.0 if metrics.target_mode == "LAN" else 80.0
        if metrics.latency_ms <= 15.0:
            self.card_latency.update_data(f"{metrics.latency_ms:.1f} ms", "#00FF66", "GOOD", "#00FF66")
        elif metrics.latency_ms <= lat_limit:
            self.card_latency.update_data(f"{metrics.latency_ms:.1f} ms", "#FFCC00", "WARN", "#FFCC00")
        else:
            self.card_latency.update_data(f"{metrics.latency_ms:.1f} ms", "#FF4444", "POOR", "#FF4444")

        if metrics.jitter_ms <= 3.0:
            self.card_jitter.update_data(f"{metrics.jitter_ms:.1f} ms", "#00FF66", "GOOD", "#00FF66")
        elif metrics.jitter_ms <= 10.0:
            self.card_jitter.update_data(f"{metrics.jitter_ms:.1f} ms", "#FFCC00", "WARN", "#FFCC00")
        else:
            self.card_jitter.update_data(f"{metrics.jitter_ms:.1f} ms", "#FF4444", "POOR", "#FF4444")

        if metrics.packet_loss_pct == 0.0:
            self.card_loss.update_data(f"{metrics.packet_loss_pct:.1f} %", "#00FF66", "GOOD", "#00FF66")
        elif metrics.packet_loss_pct <= 5.0:
            self.card_loss.update_data(f"{metrics.packet_loss_pct:.1f} %", "#FFCC00", "WARN", "#FFCC00")
        else:
            self.card_loss.update_data(f"{metrics.packet_loss_pct:.1f} %", "#FF4444", "POOR", "#FF4444")

        # 3. 종합 평가 점수 바
        score_color = "#00FF66" if metrics.score >= 80 else ("#FFCC00" if metrics.score >= 50 else "#FF4444")
        self.lbl_score_value.setText(f"{metrics.status_text} ({metrics.score} / 100)")
        self.lbl_score_value.setStyleSheet(f"color: {score_color}; font-size: 12px; font-weight: bold; border: none;")
        self.progress_score.setValue(metrics.score)
        self.progress_score.setStyleSheet(f"""
            QProgressBar {{ background-color: #1e1e1e; border: none; border-radius: 4px; }}
            QProgressBar::chunk {{ background-color: {score_color}; border-radius: 4px; }}
        """)

        # 4. 정상 실시간 파형 데이터 버퍼 업데이트
        meas_time = getattr(metrics, 'timestamp', time.time())
        self.time_buffer.append(meas_time)
        self.rssi_buffer.append(metrics.rssi)
        self.latency_buffer.append(metrics.latency_ms)
        self.loss_buffer.append(metrics.packet_loss_pct)
        self.jitter_buffer.append(metrics.jitter_ms)

        if len(self.time_buffer) > 1:
            x_data = list(self.time_buffer)
            self.curve_rssi.setData(x_data, list(self.rssi_buffer))
            self.curve_latency.setData(x_data, list(self.latency_buffer))
            self.curve_jitter.setData(x_data, list(self.jitter_buffer))
            self.curve_loss.setData(x_data, list(self.loss_buffer))

    def _update_viewport(self):
        current_time = time.time()

        visible_masters = []
        if self.pw_rssi.isVisible():
            visible_masters.append(self.p1)
        if self.pw_time.isVisible():
            visible_masters.append(self.p2)
        if self.pw_loss.isVisible():
            visible_masters.append(self.p3)

        if visible_masters:
            master_plot = visible_masters[0]
            master_plot.setXRange(current_time - 60.0, current_time, padding=0)
