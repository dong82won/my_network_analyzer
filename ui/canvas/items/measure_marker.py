#!/usr/bin/env python3
'''
Wi-Fi 신호 아이콘 형태의 커스텀 측정 마커(MeasureMarkerItem) 모듈입니다.
'''

from typing import Any

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsSimpleTextItem, QGraphicsRectItem
)

from ui.canvas.constants import KEY_ITEM_TYPE, KEY_DATA_OBJ, TYPE_SAMPLE


class MeasureMarkerItem(QGraphicsItem):
    '''Wi-Fi 신호 아이콘 형태의 커스텀 그래픽 마커 아이템'''
    def __init__(self, x_px: float, y_px: float, rssi: int, seq_id: int, point_obj: object = None):
        super().__init__()
        self.setPos(x_px, y_px)
        self.setZValue(30)
        self.seq_id = seq_id
        self.rssi = rssi

        self.primary_color = QColor("#00E5FF")
        self.current_color = QColor("#00E5FF")

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.label_bg = QGraphicsRectItem(self)
        self.label_bg.setBrush(QBrush(QColor(0, 0, 0, 180)))
        self.label_bg.setPen(Qt.PenStyle.NoPen)
        self.label_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.label_txt = QGraphicsSimpleTextItem(f"#{seq_id}", self.label_bg)
        self.label_txt.setFont(QFont("Sans", 8, QFont.Weight.Bold))
        self.label_txt.setBrush(QBrush(self.primary_color))
        self.label_txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        t_rect = self.label_txt.boundingRect()
        padding = 4
        self.label_bg.setRect(0, 0, t_rect.width() + padding * 2, t_rect.height() + padding * 2)
        self.label_txt.setPos(padding, padding)
        self.label_bg.setPos(12, 4)

        self.setData(KEY_ITEM_TYPE, TYPE_SAMPLE)
        self.setData(KEY_DATA_OBJ, point_obj)

        self.full_tooltip = f"Measure Point #{seq_id}\nSignal: {rssi} dBm\nPos: ({x_px:.1f}px, {y_px:.1f}px)"
        self.setToolTip("")
        self.setAcceptHoverEvents(False)

    def set_color(self, color: QColor):
        self.current_color = color
        self.label_txt.setBrush(QBrush(color))
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-16, -16, 32, 32)

    def paint(self, painter: QPainter, option: Any, widget: Any = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(self.current_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # 1. 중앙 원점
        painter.setBrush(QBrush(self.current_color))
        painter.drawEllipse(QRectF(-2.5, 3.5, 5, 5))

        start_angle = 45 * 16
        span_angle = 90 * 16

        # 2. 내측 호
        rect1 = QRectF(-6.5, -2.5, 13, 13)
        painter.drawArc(rect1, start_angle, span_angle)

        # 3. 중간 호
        rect2 = QRectF(-10.5, -6.5, 21, 21)
        painter.drawArc(rect2, start_angle, span_angle)

        # 4. 외측 호
        rect3 = QRectF(-14.5, -10.5, 29, 29)
        painter.drawArc(rect3, start_angle, span_angle)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        '''드래그 이동 시 Snap-to-Grid 연산 및 붉은 점선 가이드선 위치 동기화 (Pylance 타입 검사 보정)'''
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            views = self.scene().views()
            if views:
                canvas: Any = views[0]  # [핵심 1] QGraphicsView 추론을 Any로 캐스팅하여 Pylance 경고 차단
                new_pos: QPointF = value

                # [핵심 2] getattr()를 활용하여 QGraphicsView 커스텀 속성을 안전하게 추출
                show_grid = getattr(canvas, "show_grid", False)
                meters_per_pixel = getattr(canvas, "meters_per_pixel", 0.0)
                grid_offset_x = getattr(canvas, "grid_offset_x", 0.0)
                grid_offset_y = getattr(canvas, "grid_offset_y", 0.0)

                if show_grid and meters_per_pixel > 0:
                    px_per_meter = 1.0 / meters_per_pixel
                    snap_x = round((new_pos.x() - grid_offset_x) / px_per_meter) * px_per_meter + grid_offset_x
                    snap_y = round((new_pos.y() - grid_offset_y) / px_per_meter) * px_per_meter + grid_offset_y
                else:
                    snap_x, snap_y = new_pos.x(), new_pos.y()

                mode = getattr(canvas, "mode", "")
                if mode == "EDIT_PAN" and hasattr(canvas, "update_crosshair_pos"):
                    canvas.update_crosshair_pos(snap_x, snap_y, visible=True)

                return QPointF(snap_x, snap_y)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and scene.views():
            view: Any = scene.views()[0]
            mode = getattr(view, "mode", "")
            if mode == "EDIT_PAN" and hasattr(view, "update_crosshair_pos"):
                view.update_crosshair_pos(0, 0, visible=False)
            if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable and hasattr(view, "marker_moved"):
                view.marker_moved.emit(self.data(KEY_DATA_OBJ), self.scenePos().x(), self.scenePos().y())
