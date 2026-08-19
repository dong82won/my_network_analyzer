#!/usr/bin/env python3
'''
QGraphicsView 뷰포트 우측 하단에 반투명 오버레이로 표출되는
컬러바 범주(HeatmapLegendWidget) 모듈입니다.
'''

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QFont
from PySide6.QtWidgets import QWidget


class HeatmapLegendWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(70, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.min_val = -90
        self.max_val = -30
        self.unit = "dBm"

    def set_range(self, min_val: int, max_val: int, unit: str = "dBm"):
        self.min_val = min_val
        self.max_val = max_val
        self.unit = unit
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 반투명 배경 카트리지 (Dark Frame)
        painter.setBrush(QColor(25, 25, 26, 210))
        painter.setPen(QColor(60, 60, 60, 255))
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1, 6, 6)

        # 2. 수직 수신 강도 컬러 그라데이션 바 (Red -> Yellow -> Green -> Cyan -> Blue)
        bar_x = 12
        bar_y = 28
        bar_w = 14
        bar_h = 138

        gradient = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_h)
        gradient.setColorAt(0.00, QColor(255, 0, 0, 220))       # Red (-30 dBm: Excellent)
        gradient.setColorAt(0.25, QColor(255, 255, 0, 220))     # Yellow
        gradient.setColorAt(0.50, QColor(0, 255, 0, 220))       # Green
        gradient.setColorAt(0.75, QColor(0, 255, 255, 220))     # Cyan
        gradient.setColorAt(1.00, QColor(0, 0, 255, 220))       # Blue (-90 dBm: Poor)

        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        # 3. 타이틀 및 눈금 수치 텍스트 렌더링
        painter.setPen(QColor(220, 220, 220))
        painter.setFont(QFont("Sans", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 6, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.unit)

        painter.setFont(QFont("Sans", 7))
        text_x = bar_x + bar_w + 6

        # 상단 (최상 신호: -30 dBm)
        painter.drawText(text_x, bar_y + 9, f"{self.max_val}")
        # 중간 (보통 신호: -60 dBm)
        painter.drawText(text_x, bar_y + (bar_h // 2) + 3, f"{(self.min_val + self.max_val) // 2}")
        # 하단 (최악 신호: -90 dBm)
        painter.drawText(text_x, bar_y + bar_h - 1, f"{self.min_val}")
