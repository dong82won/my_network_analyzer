#!/usr/bin/env python3
'''
PySide6 QGraphicsItem 기반 캔버스 결합형 원형 타이머 HUD 모듈입니다.
'''

from typing import Any
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem


class RadialProgressItem(QGraphicsItem):
    def __init__(self, x_px: float, y_px: float, parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self.setPos(x_px, y_px)
        self.progress_ratio = 0.0  # 0.0 ~ 1.0
        self.radius = 28.0

        # Z-Value를 높게 설정하여 최상단에 렌더링
        self.setZValue(100)

    def set_progress(self, ratio: float):
        self.progress_ratio = max(0.0, min(1.0, ratio))
        self.update()

    def boundingRect(self) -> QRectF:
        r = self.radius + 10.0
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 외곽 배경 원
        rect = QRectF(-self.radius, -self.radius, self.radius * 2, self.radius * 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 30, 30, 180)))
        painter.drawEllipse(rect)

        # 2. 프로그레스 링 (Arc)
        pen_ring = QPen(QColor(0, 229, 255, 230), 4)
        pen_ring.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_ring)

        # Qt drawArc는 1/16도 단위를 사용, 12시 방향부터 시계방향 회전
        start_angle = 90 * 16
        span_angle = -int(self.progress_ratio * 360 * 16)
        painter.drawArc(rect, start_angle, span_angle)

        # 3. 중앙 텍스트 (진행률 퍼센트)
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font)
        text = f"{int(self.progress_ratio * 100)}%"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
