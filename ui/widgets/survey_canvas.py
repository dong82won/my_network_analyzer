#!/ural/bin/env python3
'''
마커 드래그 이동 시 붉은 점선 가이드선(Crosshair) 실시간 동기화,
Snap-to-Grid, 점선 테두리 억제 및 typing.Any 지원이 적용된 SurveyCanvas 모듈입니다.
'''

import math
from typing import Any

from PySide6.QtCore import Qt, Signal, QRectF, QPoint, QPointF
from PySide6.QtGui import QPixmap, QPen, QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsItem, QGraphicsLineItem, QGraphicsEllipseItem,
    QGraphicsSimpleTextItem, QGraphicsItemGroup, QGraphicsRectItem,
    QStyle
)


KEY_ITEM_TYPE = 0
KEY_DATA_OBJ = 1

TYPE_SCALE = "SCALE"
TYPE_AP = "AP"
TYPE_SAMPLE = "SAMPLE"


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
        '''드래그 이동 시 Snap-to-Grid 연산 및 붉은 점선 가이드선 위치 동기화'''
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            views = self.scene().views()
            if views and isinstance(views[0], SurveyCanvas):
                canvas = views[0]
                new_pos: QPointF = value

                if canvas.show_grid and canvas.meters_per_pixel > 0:
                    px_per_meter = 1.0 / canvas.meters_per_pixel
                    snap_x = round((new_pos.x() - canvas.grid_offset_x) / px_per_meter) * px_per_meter + canvas.grid_offset_x
                    snap_y = round((new_pos.y() - canvas.grid_offset_y) / px_per_meter) * px_per_meter + canvas.grid_offset_y
                else:
                    snap_x, snap_y = new_pos.x(), new_pos.y()

                # EDIT_PAN 모드에서 드래그 중 가이드선 표시 및 위치 업데이트
                if canvas.mode == "EDIT_PAN":
                    canvas.update_crosshair_pos(snap_x, snap_y, visible=True)

                return QPointF(snap_x, snap_y)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and scene.views():
            view = scene.views()[0]
            if isinstance(view, SurveyCanvas):
                if view.mode == "EDIT_PAN":
                    view.update_crosshair_pos(0, 0, visible=False)
                if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
                    view.marker_moved.emit(self.data(KEY_DATA_OBJ), self.scenePos().x(), self.scenePos().y())


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
            if views and isinstance(views[0], SurveyCanvas):
                canvas = views[0]
                new_pos: QPointF = value

                if canvas.show_grid and canvas.meters_per_pixel > 0:
                    px_per_meter = 1.0 / canvas.meters_per_pixel
                    snap_x = round((new_pos.x() - canvas.grid_offset_x) / px_per_meter) * px_per_meter + canvas.grid_offset_x
                    snap_y = round((new_pos.y() - canvas.grid_offset_y) / px_per_meter) * px_per_meter + canvas.grid_offset_y
                else:
                    snap_x, snap_y = new_pos.x(), new_pos.y()

                # EDIT_PAN 모드에서 드래그 중 가이드선 표시 및 위치 업데이트
                if canvas.mode == "EDIT_PAN":
                    canvas.update_crosshair_pos(snap_x, snap_y, visible=True)

                return QPointF(snap_x, snap_y)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if scene and scene.views():
            view = scene.views()[0]
            if isinstance(view, SurveyCanvas):
                if view.mode == "EDIT_PAN":
                    view.update_crosshair_pos(0, 0, visible=False)
                if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
                    view.marker_moved.emit(self.data(KEY_DATA_OBJ), self.scenePos().x(), self.scenePos().y())


class SurveyCanvas(QGraphicsView):
    point_clicked = Signal(float, float)
    ap_location_clicked = Signal(float, float)
    scale_points_selected = Signal(float, float, float, float)
    marker_moved = Signal(object, float, float)
    ap_deleted = Signal(object)
    sample_deleted = Signal(object)
    scale_deleted = Signal()
    overlap_detected = Signal(str)
    

    def __init__(self):
        super().__init__()
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)

        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.mode = "NONE"

        self.scale_temp_points = []
        self.scale_preview_line: QGraphicsLineItem | None = None
        self.scale_items = []
        self.marker_items = []

        self.meters_per_pixel = 0.05
        self.min_marker_dist_px = 15.0
        self.show_grid = False
        self.grid_group: QGraphicsItemGroup | None = None

        self.grid_offset_x = 0.0
        self.grid_offset_y = 0.0
        self._is_dragging_grid = False
        self._grid_drag_start = QPoint()

        crosshair_pen = QPen(QColor(255, 68, 68, 200), 1.5, Qt.PenStyle.DashLine)
        self.crosshair_v = self.scene_obj.addLine(0, 0, 0, 0, crosshair_pen)
        self.crosshair_h = self.scene_obj.addLine(0, 0, 0, 0, crosshair_pen)
        self.crosshair_v.setZValue(100)
        self.crosshair_h.setZValue(100)
        self.crosshair_v.setVisible(False)
        self.crosshair_h.setVisible(False)

        self.ghost_measure = MeasureMarkerItem(0, 0, -50, 0)
        self.ghost_measure.setOpacity(0.6)
        self.ghost_measure.setZValue(90)
        self.ghost_measure.setVisible(False)
        self.scene_obj.addItem(self.ghost_measure)

        self.ghost_ap = APMarkerItem(0, 0, 0)
        self.ghost_ap.setOpacity(0.5)
        self.ghost_ap.setZValue(90)
        self.ghost_ap.setVisible(False)
        self.scene_obj.addItem(self.ghost_ap)

        self.current_zoom = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 10.0
        self._is_panning = False
        self._pan_start_pos = QPoint()

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(self.renderHints().Antialiasing)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #1a1a1a; border: 1px solid #333333;")

    def update_crosshair_pos(self, x_px: float, y_px: float, visible: bool = True):
        '''가이드선(Crosshair) 위치 및 가시성을 외부 마커 이벤트에서 직접 제어하는 슬롯'''
        if not self.pixmap_item:
            return
        rect = self.pixmap_item.boundingRect()
        self.crosshair_v.setVisible(visible)
        self.crosshair_h.setVisible(visible)
        if visible:
            self.crosshair_v.setLine(x_px, 0, x_px, rect.height())
            self.crosshair_h.setLine(0, y_px, rect.width(), y_px)

    def is_position_overlapping(self, x_px: float, y_px: float) -> bool:
        for item in self.marker_items:
            pos = item.scenePos()
            dx = x_px - pos.x()
            dy = y_px - pos.y()
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < self.min_marker_dist_px:
                return True
        return False

    def set_floorplan_image(self, image_path: str) -> QPixmap:
        self.clear_all_layers()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.pixmap_item = self.scene_obj.addPixmap(pixmap)
            self.pixmap_item.setZValue(-100)
            self.scene_obj.setSceneRect(QRectF(pixmap.rect()))
            self.reset_view()
            self.draw_virtual_grid()
        return pixmap

    def reset_view(self):
        if self.pixmap_item:
            self.resetTransform()
            self.current_zoom = 1.0
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def update_scale(self, scale: float):
        self.meters_per_pixel = scale
        self.draw_virtual_grid()

    def toggle_grid(self, state: bool):
        self.show_grid = state
        if self.grid_group:
            self.grid_group.setVisible(self.show_grid)

    def draw_virtual_grid(self):
        if self.grid_group:
            self.scene_obj.removeItem(self.grid_group)
            self.grid_group = None

        if not self.pixmap_item or self.meters_per_pixel <= 0:
            return

        self.grid_group = QGraphicsItemGroup()
        self.grid_group.setZValue(-50)

        grid_pen = QPen(QColor(128, 128, 128, 180), 1, Qt.PenStyle.DashLine)
        px_per_meter = 1.0 / self.meters_per_pixel

        rect = self.pixmap_item.boundingRect()
        width, height = rect.width(), rect.height()

        start_x = self.grid_offset_x % px_per_meter
        start_y = self.grid_offset_y % px_per_meter

        x = start_x
        while x <= width:
            line = QGraphicsLineItem(x, 0, x, height)
            line.setPen(grid_pen)
            self.grid_group.addToGroup(line)
            x += px_per_meter

        y = start_y
        while y <= height:
            line = QGraphicsLineItem(0, y, width, y)
            line.setPen(grid_pen)
            self.grid_group.addToGroup(line)
            y += px_per_meter

        self.scene_obj.addItem(self.grid_group)
        self.grid_group.setVisible(self.show_grid)

    def set_markers_movable(self, movable: bool):
        for item in self.marker_items:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, movable)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, movable)
            item.setAcceptHoverEvents(movable)
            if hasattr(item, 'full_tooltip'):
                item.setToolTip(item.full_tooltip if movable else "")

    def clear_all_layers(self):
        self.scene_obj.clear()
        self.pixmap_item = None
        self.scale_temp_points.clear()
        self.scale_preview_line = None
        self.scale_items.clear()
        self.marker_items.clear()
        self.grid_group = None
        self.grid_offset_x = 0.0
        self.grid_offset_y = 0.0

        crosshair_pen = QPen(QColor(255, 68, 68, 200), 1.5, Qt.PenStyle.DashLine)
        self.crosshair_v = self.scene_obj.addLine(0, 0, 0, 0, crosshair_pen)
        self.crosshair_h = self.scene_obj.addLine(0, 0, 0, 0, crosshair_pen)
        self.crosshair_v.setZValue(100)
        self.crosshair_h.setZValue(100)
        self.crosshair_v.setVisible(False)
        self.crosshair_h.setVisible(False)

        self.ghost_measure = MeasureMarkerItem(0, 0, -50, 0)
        self.ghost_measure.setOpacity(0.6)
        self.ghost_measure.setZValue(90)
        self.ghost_measure.setVisible(False)
        self.scene_obj.addItem(self.ghost_measure)

        self.ghost_ap = APMarkerItem(0, 0, 0)
        self.ghost_ap.setOpacity(0.5)
        self.ghost_ap.setZValue(90)
        self.ghost_ap.setVisible(False)
        self.scene_obj.addItem(self.ghost_ap)

    def clear_scale_graphics(self):
        for item in self.scale_items:
            self.scene_obj.removeItem(item)
        self.scale_items.clear()
        if self.scale_preview_line:
            self.scene_obj.removeItem(self.scale_preview_line)
            self.scale_preview_line = None

    def clear_sample_graphics(self):
        items_to_remove = [item for item in self.marker_items if item.data(KEY_ITEM_TYPE) == TYPE_SAMPLE]
        for item in items_to_remove:
            self.scene_obj.removeItem(item)
            self.marker_items.remove(item)

    def clear_ap_graphics(self):
        items_to_remove = [item for item in self.marker_items if item.data(KEY_ITEM_TYPE) == TYPE_AP]
        for item in items_to_remove:
            self.scene_obj.removeItem(item)
            self.marker_items.remove(item)

    def wheelEvent(self, event):
        if not self.pixmap_item:
            super().wheelEvent(event)
            return
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        zoom_factor = zoom_in_factor if event.angleDelta().y() > 0 else zoom_out_factor
        new_zoom = self.current_zoom * zoom_factor
        if self.min_zoom <= new_zoom <= self.max_zoom:
            self.current_zoom = new_zoom
            self.scale(zoom_factor, zoom_factor)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._is_dragging_grid:
            prev_scene_pos = self.mapToScene(self._grid_drag_start)
            curr_scene_pos = self.mapToScene(event.pos())

            self.grid_offset_x += (curr_scene_pos.x() - prev_scene_pos.x())
            self.grid_offset_y += (curr_scene_pos.y() - prev_scene_pos.y())

            self._grid_drag_start = event.pos()
            self.draw_virtual_grid()
            event.accept()
            return

        if not self.pixmap_item:
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.pos())
        x_px, y_px = scene_pos.x(), scene_pos.y()
        rect = self.pixmap_item.boundingRect()

        if self.show_grid and self.meters_per_pixel > 0:
            px_per_meter = 1.0 / self.meters_per_pixel
            snap_x = round((x_px - self.grid_offset_x) / px_per_meter) * px_per_meter + self.grid_offset_x
            snap_y = round((y_px - self.grid_offset_y) / px_per_meter) * px_per_meter + self.grid_offset_y
        else:
            snap_x, snap_y = x_px, y_px

        if self.mode in ["MEASURE", "AP_PLACE", "SCALE"]:
            self.crosshair_v.setVisible(True)
            self.crosshair_h.setVisible(True)
            self.crosshair_v.setLine(snap_x, 0, snap_x, rect.height())
            self.crosshair_h.setLine(0, snap_y, rect.width(), snap_y)

            is_overlap = self.is_position_overlapping(snap_x, snap_y)
            warn_color = QColor("#FF4444")
            normal_crosshair = QColor(255, 68, 68, 200)

            ch_pen = QPen(warn_color if is_overlap else normal_crosshair, 1.5, Qt.PenStyle.DashLine)
            self.crosshair_v.setPen(ch_pen)
            self.crosshair_h.setPen(ch_pen)

            if self.mode == "MEASURE":
                self.ghost_measure.setVisible(True)
                self.ghost_ap.setVisible(False)
                self.ghost_measure.setPos(snap_x, snap_y)
                self.ghost_measure.set_color(warn_color if is_overlap else QColor("#00E5FF"))
            elif self.mode == "AP_PLACE":
                self.ghost_ap.setVisible(True)
                self.ghost_measure.setVisible(False)
                self.ghost_ap.setPos(snap_x, snap_y)
                self.ghost_ap.setBrush(QBrush(warn_color if is_overlap else QColor("#FFCC00")))
            elif self.mode == "SCALE":
                self.ghost_measure.setVisible(False)
                self.ghost_ap.setVisible(False)
        else:
            self.crosshair_v.setVisible(False)
            self.crosshair_h.setVisible(False)
            self.ghost_measure.setVisible(False)
            self.ghost_ap.setVisible(False)

        if self.mode == "SCALE" and len(self.scale_temp_points) == 1:
            p1 = self.scale_temp_points[0]
            if not self.scale_preview_line:
                self.scale_preview_line = self.scene_obj.addLine(
                    p1[0], p1[1], snap_x, snap_y,
                    QPen(QColor("#FFCC00"), 1.5, Qt.PenStyle.DashLine)
                )
                self.scale_preview_line.setZValue(10)
            else:
                self.scale_preview_line.setLine(p1[0], p1[1], snap_x, snap_y)

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if not self.pixmap_item:
            super().mousePressEvent(event)
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and event.button() == Qt.MouseButton.LeftButton:
            if self.show_grid:
                self._is_dragging_grid = True
                self._grid_drag_start = event.pos()
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                event.accept()
                return

        scene_pos = self.mapToScene(event.pos())
        x_px, y_px = scene_pos.x(), scene_pos.y()

        if self.show_grid and self.meters_per_pixel > 0:
            px_per_meter = 1.0 / self.meters_per_pixel
            x_px = round((x_px - self.grid_offset_x) / px_per_meter) * px_per_meter + self.grid_offset_x
            y_px = round((y_px - self.grid_offset_y) / px_per_meter) * px_per_meter + self.grid_offset_y

        if self.mode == "EDIT_PAN" and event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item == self.pixmap_item or item is None:
                self._is_panning = True
                self._pan_start_pos = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode in ["MEASURE", "AP_PLACE"]:
                if self.is_position_overlapping(x_px, y_px):
                    self.overlap_detected.emit("Marker placement failed: Position overlaps with an existing marker!")
                    return

            if self.mode == "MEASURE":
                self.point_clicked.emit(x_px, y_px)

            elif self.mode == "AP_PLACE":
                self.ap_location_clicked.emit(x_px, y_px)

            elif self.mode == "SCALE":
                self.scale_temp_points.append((x_px, y_px))
                if len(self.scale_temp_points) == 1:
                    pt_item = self.scene_obj.addEllipse(x_px - 5, y_px - 5, 10, 10, QPen(QColor("#FFCC00"), 2), QBrush(QColor("#FFCC00")))
                    pt_item.setZValue(10)
                    self.scale_items.append(pt_item)

                elif len(self.scale_temp_points) == 2:
                    if self.scale_preview_line:
                        self.scene_obj.removeItem(self.scale_preview_line)
                        self.scale_preview_line = None

                    self.clear_scale_graphics()
                    p1, p2 = self.scale_temp_points[0], self.scale_temp_points[1]

                    line_item = self.scene_obj.addLine(p1[0], p1[1], p2[0], p2[1], QPen(QColor("#FF4444"), 2, Qt.PenStyle.SolidLine))
                    line_item.setZValue(10)
                    line_item.setData(KEY_ITEM_TYPE, TYPE_SCALE)

                    pt1 = self.scene_obj.addEllipse(p1[0] - 4, p1[1] - 4, 8, 8, QPen(QColor("#FF4444")), QBrush(QColor("#FF4444")))
                    pt2 = self.scene_obj.addEllipse(p2[0] - 4, p2[1] - 4, 8, 8, QPen(QColor("#FF4444")), QBrush(QColor("#FF4444")))
                    pt1.setZValue(10)
                    pt2.setZValue(10)

                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    dist_px = math.sqrt(dx * dx + dy * dy)

                    mid_x = (p1[0] + p2[0]) / 2
                    mid_y = (p1[1] + p2[1]) / 2

                    txt_group = QGraphicsItemGroup()
                    txt_item = QGraphicsSimpleTextItem(f"{dist_px:.1f} px")
                    txt_item.setFont(QFont("Sans", 11, QFont.Weight.Bold))
                    txt_item.setBrush(QBrush(QColor("#FF4444")))

                    bg_rect = QGraphicsRectItem(txt_item.boundingRect())
                    bg_rect.setBrush(QBrush(QColor(240, 240, 240, 220)))
                    bg_rect.setPen(Qt.PenStyle.NoPen)

                    txt_group.addToGroup(bg_rect)
                    txt_group.addToGroup(txt_item)

                    t_rect = txt_group.boundingRect()
                    txt_group.setPos(mid_x - (t_rect.width() / 2), mid_y - (t_rect.height() / 2))
                    txt_group.setZValue(15)

                    self.scale_items.extend([line_item, pt1, pt2, txt_group])
                    self.scene_obj.addItem(txt_group)

                    self.scale_points_selected.emit(p1[0], p1[1], p2[0], p2[1])
                    self.scale_temp_points.clear()

        elif event.button() == Qt.MouseButton.RightButton:
            if self.mode == "SCALE" and len(self.scale_temp_points) == 1:
                self.scale_temp_points.clear()
                if self.scale_preview_line:
                    self.scene_obj.removeItem(self.scale_preview_line)
                    self.scale_preview_line = None
                return

            if self.mode == "EDIT_PAN":
                item = self.itemAt(event.pos())
                if item and item != self.pixmap_item:
                    target_item = item
                    while target_item.parentItem():
                        target_item = target_item.parentItem()

                    item_type = target_item.data(KEY_ITEM_TYPE)
                    obj_ref = target_item.data(KEY_DATA_OBJ)

                    if item_type == TYPE_AP:
                        self.scene_obj.removeItem(target_item)
                        if target_item in self.marker_items:
                            self.marker_items.remove(target_item)
                        self.ap_deleted.emit(obj_ref)

                    elif item_type == TYPE_SAMPLE:
                        self.scene_obj.removeItem(target_item)
                        if target_item in self.marker_items:
                            self.marker_items.remove(target_item)
                        self.sample_deleted.emit(obj_ref)

                    elif item_type == TYPE_SCALE:
                        self.clear_scale_graphics()
                        self.scale_deleted.emit()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning and (event.button() in [Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton]):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if self._is_dragging_grid and event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging_grid = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def draw_survey_point(self, x_px: float, y_px: float, rssi: int, seq_id: int, point_obj: object = None) -> MeasureMarkerItem:
        item = MeasureMarkerItem(x_px, y_px, rssi, seq_id, point_obj)
        self.scene_obj.addItem(item)
        self.marker_items.append(item)

        is_edit_pan = (self.mode == "EDIT_PAN")
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_edit_pan)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, is_edit_pan)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, is_edit_pan)
        item.setAcceptHoverEvents(is_edit_pan)
        if hasattr(item, 'full_tooltip'):
            item.setToolTip(item.full_tooltip if is_edit_pan else "")

        return item

    def draw_ap_marker(self, x_px: float, y_px: float, seq_id: int, ap_obj: object = None) -> APMarkerItem:
        item = APMarkerItem(x_px, y_px, seq_id, ap_obj)
        self.scene_obj.addItem(item)
        self.marker_items.append(item)

        is_edit_pan = (self.mode == "EDIT_PAN")
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_edit_pan)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, is_edit_pan)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, is_edit_pan)
        item.setAcceptHoverEvents(is_edit_pan)
        if hasattr(item, 'full_tooltip'):
            item.setToolTip(item.full_tooltip if is_edit_pan else "")

        return item
