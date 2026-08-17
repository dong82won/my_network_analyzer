#!/usr/bin/env python3
'''
대안 A(고정 윈도우 유지), 대안 B(Y축 가로 타이틀), Jitter 실선 전환 및
데이터/뷰포트 완전 분리(30FPS Timer)가 적용된 최종 DashboardTab 모듈입니다.
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
    '''동적 컬러 수치 및 GOOD/WARN/POOR 우측 라벨을 갖춘 센서 지표 카드'''
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(82)
        self.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
        """)

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

        self._init_ui()

        # [뷰포트 최적화] 데이터 조작 없는 순수 뷰포트 렌더링 전용 타이머 (약 30FPS)
        self.render_timer = QTimer(self)
        self.render_timer.setInterval(33)  # 33ms -> 30 FPS
        self.render_timer.timeout.connect(self._update_viewport)
        self.render_timer.start()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # -----------------------------------------------------------------
        # 1. 상단 네트워크 정보 카드
        # -----------------------------------------------------------------
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

        # -----------------------------------------------------------------
        # 2. 종합 평가 점수 바
        # -----------------------------------------------------------------
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
                background-color: #28a745;
                border-radius: 4px;
            }
        """)

        score_layout.addLayout(score_text_layout)
        score_layout.addWidget(self.progress_score)

        main_layout.addWidget(score_frame)

        # -----------------------------------------------------------------
        # 3. 메트릭 센서 카드 그리드 (2행 3열)
        # -----------------------------------------------------------------
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

        # -----------------------------------------------------------------
        # 4. 실시간 파형 그래프 토글 컨트롤 바
        # -----------------------------------------------------------------
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

        # -----------------------------------------------------------------
        # 5. PySide6 QVBoxLayout + 3개 독립 PlotWidget
        # -----------------------------------------------------------------
        pg.setConfigOption('background', '#181818')
        pg.setConfigOption('foreground', '#888888')

        self.plots_container = QWidget()
        self.plots_layout = QVBoxLayout(self.plots_container)
        self.plots_layout.setContentsMargins(0, 0, 0, 0)
        self.plots_layout.setSpacing(6)

        title_style_html = 'color: #aaaaaa; font-size: 9pt; font-weight: bold;'

        # Plot 1: RSSI
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

        # Plot 2: Time Metrics (Latency & Jitter)
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

        # Plot 3: Packet Loss
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
            left_axis = p.getAxis('left')
            left_axis.setWidth(42)

        self.p2.setXLink(self.p1)
        self.p3.setXLink(self.p1)

        self.plots_layout.addWidget(self.pw_rssi, stretch=1)
        self.plots_layout.addWidget(self.pw_time, stretch=1)
        self.plots_layout.addWidget(self.pw_loss, stretch=1)

        main_layout.addWidget(self.plots_container, stretch=2)

    def _on_toggle_plots(self):
        '''PySide6 Native Widget 가시성 제어로 숨겨진 그래프의 수직 공간 100% 즉시 재배정'''
        self.pw_rssi.setVisible(self.chk_rssi.isChecked())

        show_time = self.chk_latency.isChecked() or self.chk_jitter.isChecked()
        self.pw_time.setVisible(show_time)
        self.curve_latency.setVisible(self.chk_latency.isChecked())
        self.curve_jitter.setVisible(self.chk_jitter.isChecked())

        self.pw_loss.setVisible(self.chk_loss.isChecked())

    def update_metrics(self, metrics: NetworkMetrics):
        '''[Data Layer] 수집 스레드로부터 데이터가 도착할 때만 실행되어 버퍼와 곡선을 업데이트합니다.'''
        if not metrics:
            return

        # 1. 헤더 정보 갱신
        self.lbl_interface.setText(f"Interface: {metrics.interface}")
        self.lbl_ssid.setText(f"SSID: {metrics.ssid}")
        self.lbl_ip.setText(f"IP: {metrics.ip_addr}")
        self.lbl_gateway.setText(f"Gateway: {metrics.gateway}")
        self.lbl_bssid.setText(f"AP: {metrics.bssid}")
        self.lbl_target.setText(f"Target: {metrics.target_host} [{metrics.target_mode}]")

        # 2. 센서 카드 임계값 동적 평가
        self.card_freq.update_data(metrics.freq_ghz, "#28a745", "GOOD", "#28a745")

        if metrics.rssi > -65:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#28a745", "GOOD", "#28a745")
        elif metrics.rssi >= -80:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#FFD700", "WARN", "#FFD700")
        else:
            self.card_rssi.update_data(f"{metrics.rssi} dBm", "#FF4500", "POOR", "#FF4500")

        self.card_speed.update_data(metrics.link_speed_mbps, "#28a745", "GOOD", "#28a745")

        if metrics.latency_ms < 10.0:
            self.card_latency.update_data(f"{metrics.latency_ms} ms", "#28a745", "GOOD", "#28a745")
        elif metrics.latency_ms <= 50.0:
            self.card_latency.update_data(f"{metrics.latency_ms} ms", "#FFD700", "WARN", "#FFD700")
        else:
            self.card_latency.update_data(f"{metrics.latency_ms} ms", "#FF4500", "POOR", "#FF4500")

        if metrics.packet_loss_pct == 0.0:
            self.card_loss.update_data(f"{metrics.packet_loss_pct} %", "#28a745", "GOOD", "#28a745")
        else:
            self.card_loss.update_data(f"{metrics.packet_loss_pct} %", "#FF4500", "POOR", "#FF4500")

        if metrics.jitter_ms < 2.0:
            self.card_jitter.update_data(f"{metrics.jitter_ms} ms", "#28a745", "GOOD", "#28a745")
        elif metrics.jitter_ms <= 10.0:
            self.card_jitter.update_data(f"{metrics.jitter_ms} ms", "#FFD700", "WARN", "#FFD700")
        else:
            self.card_jitter.update_data(f"{metrics.jitter_ms} ms", "#FF4500", "POOR", "#FF4500")

        # 3. 상단 평가 점수 바 갱신
        score_color = "#28a745" if metrics.score >= 80 else ("#FFD700" if metrics.score >= 50 else "#FF4500")
        self.lbl_score_value.setText(f"{metrics.status_text} ({metrics.score} / 100)")
        self.lbl_score_value.setStyleSheet(f"color: {score_color}; font-size: 12px; font-weight: bold; border: none;")
        self.progress_score.setValue(metrics.score)
        self.progress_score.setStyleSheet(f"""
            QProgressBar {{ background-color: #1e1e1e; border: none; border-radius: 4px; }}
            QProgressBar::chunk {{ background-color: {score_color}; border-radius: 4px; }}
        """)

        # 4. 수집기 스레드에서 측정한 정밀 타임스탬프 채록 및 데이터 버퍼 업데이트
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
        '''[View Layer] 30FPS로 동작하며, [현재 시간 - 60초, 현재 시간]의 고정 윈도우(Fixed Sliding Window)를 무조건 유지합니다.'''
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
            # [핵심] 대안 A: 구동 시간과 무관하게 항상 60초 폭을 갖는 하드웨어 오실로스코프 형태의 안정적인 뷰포트 유지
            master_plot.setXRange(current_time - 60.0, current_time, padding=0)
