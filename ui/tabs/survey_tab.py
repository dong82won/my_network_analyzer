#!/usr/bin/env python3
'''
[Edit]과 [Grid] 사이의 구분선(sep3)이 제거되어 연속 배치되고,
setEnabled 기반 레이아웃 고정 및 파일 I/O Safeguard가 반영된 전체 SurveyTab 모듈입니다.
'''

import copy
import statistics
import time
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QDialog, QStackedWidget
)

from core.models import APMarker, NetworkMetrics, SurveyPoint, SurveyProject
from spatial.coordinate import CoordinateConverter
from storage.project_manager import ProjectManager
from ui.dialogs.ap_selection_dialog import APSelectionDialog
from ui.widgets.radial_progress_item import RadialProgressItem
from ui.widgets.survey_canvas import SurveyCanvas


class HubClickableCard(QFrame):
    '''QGraphicsView 오버레이 페인트 충돌을 방지하는 커스텀 카드 위젯'''
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #444444;
                border-radius: 8px;
            }
            QFrame:hover {
                background-color: #007acc;
                border: 1px solid #0099ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff; background: transparent; border: none;")

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet("font-size: 11px; color: #aaaaaa; background: transparent; border: none;")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_sub)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SurveyTab(QWidget):
    def __init__(self, main_window: Any):
        super().__init__()
        self.main_window = main_window
        self.project = SurveyProject()
        self.converter = CoordinateConverter()

        self.workflow_mode = "EMPTY"

        self._sampling_timer: QTimer | None = None
        self._sampling_ticks = 0
        self._sampling_total_ticks = 30
        self._sample_buffer: list[NetworkMetrics] = []
        self._target_px = (0.0, 0.0)
        self._radial_hud: RadialProgressItem | None = None

        self._init_ui()

        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(self._on_spacebar_triggered)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # -----------------------------------------------------------------
        # 1. 상단 동적 툴바 (구분선 sep3 제거로 연속 배치)
        # -----------------------------------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self.active_tools_widget = QWidget()
        active_tools_layout = QHBoxLayout(self.active_tools_widget)
        active_tools_layout.setContentsMargins(0, 0, 0, 0)
        active_tools_layout.setSpacing(8)

        btn_style_common = """
            QPushButton {
                background-color: #3a3d41;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #555555; }
            QPushButton:disabled {
                background-color: #2b2b2b;
                color: #555555;
            }
        """

        # [Group 1] File I/O & Workflow Mode
        self.btn_open_project = QPushButton("📂 Open ")
        self.btn_open_project.setStyleSheet(btn_style_common)
        self.btn_open_project.clicked.connect(self._on_toolbar_open_project)

        self.btn_save_project = QPushButton("💾 Save ")
        self.btn_save_project.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #005999; }
        """)
        self.btn_save_project.clicked.connect(self._on_save_project)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #444444;")

        self.btn_mode_setup = QPushButton("⚙️ SETUP MODE")
        self.btn_mode_setup.setCheckable(True)

        self.btn_mode_survey = QPushButton("📍 SURVEY MODE")
        self.btn_mode_survey.setCheckable(True)

        self.btn_mode_setup.clicked.connect(lambda: self._switch_workflow_mode("SETUP"))
        self.btn_mode_survey.clicked.connect(lambda: self._switch_workflow_mode("LIVE_SURVEY"))

        # [Group 2] Spatial Setup Tools & View Tools 통합
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #444444;")

        self.btn_set_scale = QPushButton("📏 Scale")
        self.btn_set_scale.setStyleSheet(btn_style_common)
        self.btn_set_scale.clicked.connect(self._on_start_scale_calibration)

        self.btn_add_ap = QPushButton("📡 AP")
        self.btn_add_ap.setStyleSheet(btn_style_common)
        self.btn_add_ap.clicked.connect(self._on_start_ap_place_mode)

        self.btn_edit_pan = QPushButton("🖐️ Edit")
        self.btn_edit_pan.setStyleSheet(btn_style_common)
        self.btn_edit_pan.clicked.connect(self._on_start_edit_pan_mode)

        # Viewport Control Tools (sep3 제거로 Edit 직후 바로 배치)
        self.btn_toggle_grid = QPushButton("🌐 Grid ")
        self.btn_toggle_grid.setCheckable(True)
        self.btn_toggle_grid.setStyleSheet(btn_style_common)
        self.btn_toggle_grid.toggled.connect(self._on_toggle_grid)

        self.btn_reset_view = QPushButton("🔍 Reset ")
        self.btn_reset_view.setStyleSheet(btn_style_common)
        self.btn_reset_view.clicked.connect(self._on_reset_view)

        # 레이아웃 순서 배치 ([Edit] | [Grid] 세로선 제거)
        active_tools_layout.addWidget(self.btn_open_project)
        active_tools_layout.addWidget(self.btn_save_project)
        active_tools_layout.addWidget(sep1)
        active_tools_layout.addWidget(self.btn_mode_setup)
        active_tools_layout.addWidget(self.btn_mode_survey)
        active_tools_layout.addWidget(sep2)
        active_tools_layout.addWidget(self.btn_set_scale)
        active_tools_layout.addWidget(self.btn_add_ap)
        active_tools_layout.addWidget(self.btn_edit_pan)
        # sep3 제거 구역
        active_tools_layout.addWidget(self.btn_toggle_grid)
        active_tools_layout.addWidget(self.btn_reset_view)

        top_bar.addWidget(self.active_tools_widget)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        # -----------------------------------------------------------------
        # 2. QStackedWidget 기반 중앙 영역
        # -----------------------------------------------------------------
        self.stacked_widget = QStackedWidget()

        # [Page 0: Start Hub Page]
        self.page_hub = QWidget()
        hub_main_layout = QVBoxLayout(self.page_hub)
        hub_main_layout.setContentsMargins(0, 0, 0, 0)

        hub_center_h = QHBoxLayout()
        hub_center_h.addStretch()

        self.start_hub_card = QFrame()
        self.start_hub_card.setFixedSize(500, 260)
        self.start_hub_card.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 2px solid #007acc;
                border-radius: 12px;
            }
        """)

        card_layout = QVBoxLayout(self.start_hub_card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        lbl_hub_title = QLabel("🚀 Robot Network Analyzer - Survey Hub")
        lbl_hub_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00E5FF; border: none; background: transparent;")
        lbl_hub_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card_new = HubClickableCard("🆕  Start New Survey", "Load floorplan image and create project bundle")
        self.card_open = HubClickableCard("📂  Open Existing Project", "Load recorded survey data from data/ directory")

        self.card_new.clicked.connect(self._on_click_start_new_survey)
        self.card_open.clicked.connect(self._on_open_project)

        card_layout.addWidget(lbl_hub_title)
        card_layout.addWidget(self.card_new)
        card_layout.addWidget(self.card_open)

        hub_center_h.addWidget(self.start_hub_card)
        hub_center_h.addStretch()

        hub_main_layout.addStretch()
        hub_main_layout.addLayout(hub_center_h)
        hub_main_layout.addStretch()

        # [Page 1: Survey Canvas Page]
        self.page_canvas = QWidget()
        canvas_page_layout = QVBoxLayout(self.page_canvas)
        canvas_page_layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = SurveyCanvas()

        self.canvas.point_clicked.connect(self._on_canvas_point_clicked)
        self.canvas.ap_location_clicked.connect(self._on_ap_location_clicked)
        self.canvas.scale_points_selected.connect(self._on_scale_points_selected)

        self.canvas.ap_deleted.connect(self._on_ap_deleted)
        self.canvas.sample_deleted.connect(self._on_sample_deleted)
        self.canvas.scale_deleted.connect(self._on_scale_deleted)
        self.canvas.marker_moved.connect(self._on_marker_moved)
        self.canvas.overlap_detected.connect(self._on_overlap_detected)

        canvas_page_layout.addWidget(self.canvas)

        self.stacked_widget.addWidget(self.page_hub)     # Index 0
        self.stacked_widget.addWidget(self.page_canvas)  # Index 1

        layout.addWidget(self.stacked_widget)

        # -----------------------------------------------------------------
        # 3. 하단 상태 바
        # -----------------------------------------------------------------
        self.lbl_status = QLabel("Status: Ready.")
        self.lbl_status.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_status)

        self._switch_workflow_mode("EMPTY")

    def _on_overlap_detected(self, message: str):
        self.lbl_status.setText(f"⚠️ {message}")

    def _switch_workflow_mode(self, mode: str):
        self.workflow_mode = mode

        style_setup_off = "background-color: #3a3d41; color: #aaa; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        style_setup_on = "background-color: #007acc; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;"
        style_survey_on = "background-color: #007acc; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;"

        if mode == "EMPTY":
            self.active_tools_widget.setVisible(False)
            self.stacked_widget.setCurrentIndex(0)
            self.lbl_status.setText("WELCOME: Select 'Start New Survey' or 'Open Existing Project' to begin.")

        else:
            self.active_tools_widget.setVisible(True)
            self.stacked_widget.setCurrentIndex(1)

            if mode == "SETUP":
                self.btn_mode_setup.setChecked(True)
                self.btn_mode_survey.setChecked(False)
                self.btn_mode_setup.setStyleSheet(style_setup_on)
                self.btn_mode_survey.setStyleSheet(style_setup_off)

                self.btn_set_scale.setEnabled(True)
                self.btn_add_ap.setEnabled(True)
                self.btn_edit_pan.setEnabled(True)

                self._on_start_edit_pan_mode()
                self.lbl_status.setText(f"SETUP MODE [{self.project.name}]: Calibrate scale, place AP markers, or toggle grid.")

            elif mode == "LIVE_SURVEY":
                self.btn_mode_setup.setChecked(False)
                self.btn_mode_survey.setChecked(True)
                self.btn_mode_setup.setStyleSheet(style_setup_off)
                self.btn_mode_survey.setStyleSheet(style_survey_on)

                # Scale과 AP만 비활성화하고 Edit, Grid, Reset은 활성화 유지
                self.btn_set_scale.setEnabled(False)
                self.btn_add_ap.setEnabled(False)
                self.btn_edit_pan.setEnabled(True)

                self._update_canvas_mode("MEASURE")
                self.lbl_status.setText(f"LIVE SURVEY ACTIVE [{self.project.name}]: Click map or press SPACEBAR to sample.")

    def _on_toggle_grid(self, checked: bool):
        self.canvas.toggle_grid(checked)
        style_inactive = "background-color: #3a3d41; color: white; padding: 6px 10px;"
        style_active = "background-color: #007acc; color: white; font-weight: bold; padding: 6px 10px;"
        self.btn_toggle_grid.setStyleSheet(style_active if checked else style_inactive)
        if checked:
            self.lbl_status.setText("Grid Enabled: Hold Shift + Drag mouse on canvas to offset grid.")
        else:
            self.lbl_status.setText("Grid Disabled.")

    def _on_reset_view(self):
        self.canvas.reset_view()
        self.lbl_status.setText("Reset: Fitted canvas to view area.")

    def _check_unsaved_changes_and_proceed(self) -> bool:
        has_data = bool(self.project.survey_points or self.project.ap_markers)
        if not has_data:
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Project Warning",
            f"Current project '{self.project.name}' has recorded points or AP markers.\n\n"
            "Opening a new project will replace your current workspace.\n"
            "Do you want to save your current project before proceeding?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )

        if reply == QMessageBox.StandardButton.Save:
            self._on_save_project()
            return True
        elif reply == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def _on_toolbar_open_project(self):
        if not self._check_unsaved_changes_and_proceed():
            return
        self._on_open_project()

    def _on_click_start_new_survey(self):
        if not self._check_unsaved_changes_and_proceed():
            return

        initial_dir = ProjectManager.get_default_data_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Floorplan Image for New Survey", initial_dir, "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not file_path:
            return

        proj_name, ok = QInputDialog.getText(
            self, "New Survey Project",
            "Enter Project Name (Folder Name):",
            text="project_analyzer"
        )
        if ok and proj_name.strip():
            self.canvas.clear_all_layers()

            raw_name = proj_name.strip()
            self.project = SurveyProject(name=raw_name)
            self.project.floorplan.image_path = file_path

            pixmap = self.canvas.set_floorplan_image(file_path)
            if not pixmap.isNull():
                self.project.floorplan.width_px = pixmap.width()
                self.project.floorplan.height_px = pixmap.height()

            ProjectManager.initialize_project_bundle(self.project, raw_name)

            self._switch_workflow_mode("SETUP")
            self._on_start_scale_calibration()

    def _on_open_project(self):
        initial_dir = ProjectManager.get_default_data_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Survey Project File", initial_dir, "JSON Files (*.json)"
        )
        if file_path:
            loaded_proj = ProjectManager.load_project(file_path)
            if loaded_proj:
                self.canvas.clear_all_layers()

                self.project = loaded_proj
                self.converter.meters_per_pixel = self.project.floorplan.meters_per_pixel

                if self.project.floorplan.image_path:
                    pixmap = self.canvas.set_floorplan_image(self.project.floorplan.image_path)
                    if not pixmap.isNull() and (self.project.floorplan.width_px == 0 or self.project.floorplan.height_px == 0):
                        self.project.floorplan.width_px = pixmap.width()
                        self.project.floorplan.height_px = pixmap.height()

                self.canvas.update_scale(self.converter.meters_per_pixel)

                for ap in self.project.ap_markers:
                    x_px, y_px = self.converter.meter_to_pixel(ap.x_m, ap.y_m)
                    seq_id = getattr(ap, 'sequence_id', 1)
                    self.canvas.draw_ap_marker(x_px, y_px, seq_id, ap)

                for sp in self.project.survey_points:
                    x_px, y_px = self.converter.meter_to_pixel(sp.x_m, sp.y_m)
                    self.canvas.draw_survey_point(x_px, y_px, sp.metrics.rssi, sp.sequence_id, sp)

                self._switch_workflow_mode("LIVE_SURVEY")
            else:
                QMessageBox.critical(self, "Error", "Failed to load project file.")

    def _on_save_project(self):
        if not self.project.name:
            self.project.name = "site_survey"

        success, saved_path = ProjectManager.save_project(self.project, self.project.name)
        if success:
            QMessageBox.information(
                self, "Success",
                f"Project '{self.project.name}' saved successfully!\n\nFile Location:\n{saved_path}"
            )
        else:
            QMessageBox.critical(self, "Error", f"Failed to save project: {saved_path}")

    def _update_canvas_mode(self, canvas_mode: str):
        self.canvas.mode = canvas_mode
        self.canvas.set_markers_movable(canvas_mode == "EDIT_PAN")

        if canvas_mode not in ["MEASURE", "AP_PLACE", "SCALE"]:
            self.canvas.crosshair_v.setVisible(False)
            self.canvas.crosshair_h.setVisible(False)

        if canvas_mode != "MEASURE":
            self.canvas.ghost_measure.setVisible(False)
        if canvas_mode != "AP_PLACE":
            self.canvas.ghost_ap.setVisible(False)

        style_inactive = """
            QPushButton { background-color: #3a3d41; color: white; padding: 6px 10px; border-radius: 4px; }
            QPushButton:hover { background-color: #555555; }
            QPushButton:disabled { background-color: #2b2b2b; color: #555555; }
        """
        style_active = """
            QPushButton { background-color: #007acc; color: white; font-weight: bold; padding: 6px 10px; border-radius: 4px; }
            QPushButton:disabled { background-color: #2b2b2b; color: #555555; }
        """

        self.btn_set_scale.setStyleSheet(style_active if canvas_mode == "SCALE" else style_inactive)
        self.btn_add_ap.setStyleSheet(style_active if canvas_mode == "AP_PLACE" else style_inactive)
        self.btn_edit_pan.setStyleSheet(style_active if canvas_mode == "EDIT_PAN" else style_inactive)

    def _on_start_edit_pan_mode(self):
        self._update_canvas_mode("EDIT_PAN")
        self.lbl_status.setText("Edit Mode: Adjust markers or drag canvas to pan.")

    def _on_start_scale_calibration(self):
        self._update_canvas_mode("SCALE")
        self.lbl_status.setText("[Step 1] Calibrate Scale: Click TWO points on map.")

    def _on_start_ap_place_mode(self):
        self._update_canvas_mode("AP_PLACE")
        self.lbl_status.setText("[Step 2] Add AP Marker: Click anywhere on map to place AP.")

    def _on_spacebar_triggered(self):
        if self.workflow_mode == "LIVE_SURVEY" and self.canvas.mode == "MEASURE":
            line_v = self.canvas.crosshair_v.line()
            line_h = self.canvas.crosshair_h.line()

            x_px = float(line_v.x1())
            y_px = float(line_h.y1())

            self._start_sampling_session(x_px, y_px)

    def _on_canvas_point_clicked(self, x_px: float, y_px: float):
        if self.workflow_mode == "LIVE_SURVEY":
            self._start_sampling_session(x_px, y_px)

    def _start_sampling_session(self, x_px: float, y_px: float):
        current_metrics = self.main_window.current_metrics
        if not current_metrics.wifi_connected:
            QMessageBox.warning(self, "Warning", "Wi-Fi is disconnected! Cannot record measure point.")
            return

        if self._sampling_timer and self._sampling_timer.isActive():
            return

        self._target_px = (x_px, y_px)
        self._sample_buffer.clear()
        self._sampling_ticks = 0

        scene_obj: Any = self.canvas.scene()

        if self._radial_hud and scene_obj:
            scene_obj.removeItem(self._radial_hud)

        self._radial_hud = RadialProgressItem(x_px, y_px)
        if scene_obj:
            scene_obj.addItem(self._radial_hud)

        next_seq_id = len(self.project.survey_points) + 1
        self.lbl_status.setText(f"MEASURING Point #{next_seq_id}... Hold position for 3 seconds.")

        self._sampling_timer = QTimer(self)
        self._sampling_timer.setInterval(100)
        self._sampling_timer.timeout.connect(self._on_sampling_tick)
        self._sampling_timer.start()

    def _on_sampling_tick(self):
        self._sampling_ticks += 1
        live_m = copy.deepcopy(self.main_window.current_metrics)
        self._sample_buffer.append(live_m)

        ratio = self._sampling_ticks / self._sampling_total_ticks
        if self._radial_hud:
            self._radial_hud.set_progress(ratio)

        if self._sampling_ticks >= self._sampling_total_ticks:
            self._stop_sampling_timer()

            QApplication.beep()

            scene_obj: Any = self.canvas.scene()
            if self._radial_hud and scene_obj:
                scene_obj.removeItem(self._radial_hud)
                self._radial_hud = None

            self._aggregate_and_save_point()

    def _stop_sampling_timer(self):
        if self._sampling_timer and self._sampling_timer.isActive():
            self._sampling_timer.stop()
            self._sampling_timer = None

    def _aggregate_and_save_point(self):
        if not self._sample_buffer:
            return

        x_px, y_px = self._target_px
        x_m, y_m = self.converter.pixel_to_meter(x_px, y_px)
        next_seq_id = len(self.project.survey_points) + 1

        rssi_list = [m.rssi for m in self._sample_buffer]
        lat_list = [m.latency_ms for m in self._sample_buffer]
        loss_list = [m.packet_loss_pct for m in self._sample_buffer]
        jit_list = [m.jitter_ms for m in self._sample_buffer]
        score_list = [m.score for m in self._sample_buffer]

        agg_rssi = int(statistics.median(rssi_list))
        agg_lat = round(statistics.mean(lat_list), 1)
        agg_loss = round(statistics.mean(loss_list), 1)
        agg_jit = round(statistics.mean(jit_list), 1)
        agg_score = int(statistics.mean(score_list))

        base_m = copy.deepcopy(self._sample_buffer[-1])
        base_m.rssi = agg_rssi
        base_m.latency_ms = agg_lat
        base_m.packet_loss_pct = agg_loss
        base_m.jitter_ms = agg_jit
        base_m.score = agg_score

        scanned_snapshot: dict[str, int] = {}
        if hasattr(self.main_window, 'collector') and self.main_window.collector:
            scanned_snapshot = self.main_window.collector.get_scanned_aps_snapshot()

        sp = SurveyPoint(
            x_m=x_m,
            y_m=y_m,
            timestamp=time.time(),
            metrics=base_m,
            sequence_id=next_seq_id,
            scanned_aps=scanned_snapshot
        )
        self.project.survey_points.append(sp)
        self.canvas.draw_survey_point(x_px, y_px, agg_rssi, next_seq_id, sp)
        self.lbl_status.setText(
            f"Point #{next_seq_id} SAVED (3s Aggregated, Scanned APs: {len(scanned_snapshot)}) - "
            f"Median RSSI: {agg_rssi} dBm, Avg Latency: {agg_lat} ms"
        )

    def _on_scale_points_selected(self, x1, y1, x2, y2):
        real_dist, ok = QInputDialog.getDouble(self, "Real Distance", "Distance (meters):", 10.0, 0.1, 1000.0, 2)
        if ok:
            scale = self.converter.calibrate_scale((x1, y1), (x2, y2), real_dist)
            self.project.floorplan.meters_per_pixel = scale
            self.canvas.update_scale(scale)
            self._on_start_ap_place_mode()
            self.lbl_status.setText(f"Scale calibrated: 1 px = {scale:.4f}m.")
        else:
            self.canvas.clear_scale_graphics()

    def _on_ap_location_clicked(self, x_px: float, y_px: float):
        scanned_detail = {}
        if hasattr(self.main_window, 'collector') and self.main_window.collector:
            scanned_detail = self.main_window.collector.get_scanned_aps_detail()

        dlg = APSelectionDialog(scanned_detail, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            ap_data: dict[str, Any] = dlg.selected_ap_info

            x_m, y_m = self.converter.pixel_to_meter(x_px, y_px)
            next_seq_id = len(self.project.ap_markers) + 1

            ap = APMarker(
                bssid=ap_data.get("bssid", f"AP-{next_seq_id}"),
                ssid=ap_data.get("ssid", "Auto AP"),
                x_m=x_m,
                y_m=y_m,
                channel_freq=ap_data.get("channel_freq", "--"),
                channel_num=ap_data.get("channel_num", 0),
                wifi_band=ap_data.get("wifi_band", "--"),
                security=ap_data.get("security", "--"),
                max_rate=ap_data.get("max_rate", "--"),
                sequence_id=next_seq_id
            )
            self.project.ap_markers.append(ap)
            self.canvas.draw_ap_marker(x_px, y_px, next_seq_id, ap)
            self.lbl_status.setText(
                f"AP #{next_seq_id} [{ap.ssid} / {ap.bssid} / Ch.{ap.channel_num} ({ap.wifi_band})] placed at ({x_m:.2f}m, {y_m:.2f}m)."
            )

    def _on_marker_moved(self, obj_ref: Any, new_x_px: float, new_y_px: float):
        new_x_m, new_y_m = self.converter.pixel_to_meter(new_x_px, new_y_px)
        if isinstance(obj_ref, APMarker):
            obj_ref.x_m = new_x_m
            obj_ref.y_m = new_y_m
        elif isinstance(obj_ref, SurveyPoint):
            obj_ref.x_m = new_x_m
            obj_ref.y_m = new_y_m

    def _reindex_and_redraw_aps(self):
        self.canvas.clear_ap_graphics()
        for idx, ap in enumerate(self.project.ap_markers, start=1):
            ap.sequence_id = idx
            x_px, y_px = self.converter.meter_to_pixel(ap.x_m, ap.y_m)
            self.canvas.draw_ap_marker(x_px, y_px, ap.sequence_id, ap)

    def _reindex_and_redraw_samples(self):
        self.canvas.clear_sample_graphics()
        for idx, sp in enumerate(self.project.survey_points, start=1):
            sp.sequence_id = idx
            x_px, y_px = self.converter.meter_to_pixel(sp.x_m, sp.y_m)
            self.canvas.draw_survey_point(x_px, y_px, sp.metrics.rssi, sp.sequence_id, sp)

    def _on_ap_deleted(self, ap_obj: Any):
        if ap_obj in self.project.ap_markers:
            self.project.ap_markers.remove(ap_obj)
            self._reindex_and_redraw_aps()

    def _on_sample_deleted(self, sample_obj: Any):
        if sample_obj in self.project.survey_points:
            self.project.survey_points.remove(sample_obj)
            self._reindex_and_redraw_samples()

    def _on_scale_deleted(self):
        self.project.floorplan.meters_per_pixel = 0.05
