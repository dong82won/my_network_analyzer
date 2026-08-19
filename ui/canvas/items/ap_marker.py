#!/usr/bin/env python3
'''
AP 앵커 마커(APMarkerItem) 모듈입니다.
'''

from typing import Any

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsEllipseItem, QGraphicsSimpleTextItem,
    QGraphicsRectItem, QStyle
)

from ui.canvas.constants import KEY_ITEM_TYPE, KEY_DATA_OBJ, TYPE_AP


class APMarkerItem(QGraphicsEllipseItem):
    def __init__(self, x_px: float, y_px: float, seq_id: int, ap_obj: object = None):
        super().__init__(-8, -8, 16, 16)
        self.setPos(x_px, y_px)
        self.setZValue(20)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        ap_color = QColor("#FFCC00")

        self.setBrush(QBrush(ap_color))
        self.setPen(QPen(Qt.GlobalColor.white, 1.5))

        self.label_bg = QGraphicsRectItem(self)
        self.label_bg.setBrush(QBrush(QColor(40, 30, 0, 200)))
        self.label_bg.setPen(Qt.PenStyle.NoPen)
        self.label_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.label_txt = QGraphicsSimpleTextItem(f"AP #{seq_id}", self.label_bg)
        self.label_txt.setFont(QFont("Sans", 8, QFont.Weight.Bold))
        self.label_txt.setBrush(QBrush(ap_color))
        self.label_txt.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        t_rect = self.label_txt.boundingRect()
        padding = 4
        self.label_bg.setRect(0, 0, t_rect.width() + padding * 2, t_rect.height() + padding * 2)
        self.label_txt.setPos(padding, padding)

        self.label_bg.setPos(8, 8)

        self.setData(KEY_ITEM_TYPE, TYPE_AP)
        self.setData(KEY_DATA_OBJ, ap_obj)

        self.full_tooltip = f"AP Marker #{seq_id}\nPos: ({x_px:.1f}px, {y_px:.1f}px)"
        self.setToolTip("")
        self.setAcceptHoverEvents(False)

    def paint(self, painter: QPainter, option: Any, widget: Any = None):
        option.state &= ~QStyle.StateFlag.State_Selected
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, widget)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        '''드래그 이동 시 Snap-to-Grid 연산 및 붉은 점선 가이드선 위치 동기화'''
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            views = self.scene().views()
            if views:
                canvas = views[0]
                new_pos: QPointF = value

                if getattr(canvas, "show_grid", False) and getattr(canvas, "meters_per_pixel", 0) > 0:
                    px_per_meter = 1.0 / canvas.meters_per_pixel
                    snap_x = round((new_pos.x() - canvas.grid_offset_x) / px_per_meter) * px_per_meter + canvas.grid_offset_x
                    snap_y = round((new_pos.y() - canvas.grid_offset_y) / px_per_meter) * px_per_meter + canvas.grid_offset_y
                else:
                    snap_x, snap_y = new_pos.x(), new_pos.y()

                if getattr(canvas, "mode", "") == "EDIT_PAN" and hasattr(canvas, "update_crosshair_pos"):
                    canvas.update_crosshair_pos(snap_x, snap_y, visible=True)

                return QPointF(snap_x, snap_y)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and scene.views():
            view = scene.views()[0]
            if getattr(view, "mode", "") == "EDIT_PAN" and hasattr(view, "update_crosshair_pos"):
                view.update_crosshair_pos(0, 0, visible=False)
            if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable and hasattr(view, "marker_moved"):
                view.marker_moved.emit(self.data(KEY_DATA_OBJ), self.scenePos().x(), self.scenePos().y())
