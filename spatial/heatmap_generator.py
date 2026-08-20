#!/usr/bin/env python3
'''
5m 수동 조사 규격에 최적화된 전역 공간 보간(Global IDW),
10m 전파 감쇄 엔벨로프 마스킹 및 유효 측정 면적(m²) 적분 수치 연산 모듈입니다.
'''

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap


class HeatmapGenerator:
    @classmethod
    def generate_heatmap_pixmap(
        cls,
        points: list[tuple[float, float, float]],  # [(x_px, y_px, rssi), ...]
        width_px: int,
        height_px: int,
        meters_per_pixel: float = 0.05,
        decay_radius_m: float = 10.0,              # 5m 격자의 2배인 10m 감쇄 반경
        min_rssi: float = -90.0,
        max_rssi: float = -30.0,
        downscale_factor: int = 4,
        alpha_opacity: int = 160
    ) -> QPixmap:
        '''5m 수동 조사 환경 맞춤형 전역 연속 등고선 히트맵 QPixmap 생성'''
        if not points or width_px <= 0 or height_px <= 0:
            return QPixmap()

        # 1. 서브 픽셀 해상도 연산 격자(Meshgrid) 생성
        grid_w = max(1, width_px // downscale_factor)
        grid_h = max(1, height_px // downscale_factor)

        gx, gy = np.meshgrid(
            np.linspace(0, width_px, grid_w),
            np.linspace(0, height_px, grid_h)
        )

        pts = np.array(points)  # Shape: (N, 3) -> [x_px, y_px, rssi]
        px_x = pts[:, 0]
        px_y = pts[:, 1]
        vals = pts[:, 2]

        # 2. 3D Distance Matrix 연산 (grid_h, grid_w, N)
        dx = gx[:, :, np.newaxis] - px_x
        dy = gy[:, :, np.newaxis] - px_y
        dist = np.sqrt(dx * dx + dy * dy)

        # 3. 전역 역거리 가중 보간 (Global IDW - 연속 전파 필드)
        safe_dist = np.maximum(dist, 1e-5)
        weights = 1.0 / (safe_dist ** 2.0)
        weights_sum = np.sum(weights, axis=2)

        z_final = np.sum(weights * vals, axis=2) / weights_sum

        # 4. 10m 감쇄 엔벨로프 (5m 인접 점은 연결, 고립 지점 #12는 10m 이내 소멸)
        min_dist_px = np.min(dist, axis=2)
        radius_px = (decay_radius_m / meters_per_pixel) if meters_per_pixel > 0 else 200.0

        envelope = np.clip(1.0 - (min_dist_px / radius_px) ** 2.0, 0.0, 1.0)
        alpha = (alpha_opacity * envelope).astype(np.uint8)

        # 5. 수신 강도 수치 -> ColorMap (Jet / Rainbow) 변환
        norm = np.clip((z_final - min_rssi) / (max_rssi - min_rssi), 0.0, 1.0)

        r = np.zeros_like(norm, dtype=np.float32)
        g = np.zeros_like(norm, dtype=np.float32)
        b = np.zeros_like(norm, dtype=np.float32)

        # 0.00 ~ 0.25 : Blue -> Cyan
        m1 = (norm < 0.25)
        t1 = norm[m1] / 0.25
        r[m1] = 0
        g[m1] = 255 * t1
        b[m1] = 255

        # 0.25 ~ 0.50 : Cyan -> Green
        m2 = (norm >= 0.25) & (norm < 0.50)
        t2 = (norm[m2] - 0.25) / 0.25
        r[m2] = 0
        g[m2] = 255
        b[m2] = 255 * (1.0 - t2)

        # 0.50 ~ 0.75 : Green -> Yellow
        m3 = (norm >= 0.50) & (norm < 0.75)
        t3 = (norm[m3] - 0.50) / 0.25
        r[m3] = 255 * t3
        g[m3] = 255
        b[m3] = 0

        # 0.75 ~ 1.00 : Yellow -> Red
        m4 = (norm >= 0.75)
        t4 = (norm[m4] - 0.75) / 0.25
        r[m4] = 255
        g[m4] = 255 * (1.0 - t4)
        b[m4] = 0

        rgba_array = np.dstack([
            r.astype(np.uint8),
            g.astype(np.uint8),
            b.astype(np.uint8),
            alpha
        ])

        # 6. QImage 생성 및 원본 도면 해상도로 Smooth 보간 확장
        qimg = QImage(
            rgba_array.data,
            grid_w,
            grid_h,
            grid_w * 4,
            QImage.Format.Format_RGBA8888
        )

        pixmap = QPixmap.fromImage(qimg).scaled(
            width_px,
            height_px,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        return pixmap

    @classmethod
    def calculate_survey_area_m2(
        cls,
        points: list[tuple[float, float, float]],
        width_px: int,
        height_px: int,
        meters_per_pixel: float = 0.05,
        coverage_radius_m: float = 7.5,
        downscale_factor: int = 4
    ) -> float:
        '''[아이디어 ③] 유효 신호 커버리지 실면적(m²) 수치 적분 산출'''
        if not points or width_px <= 0 or height_px <= 0 or meters_per_pixel <= 0:
            return 0.0

        grid_w = max(1, width_px // downscale_factor)
        grid_h = max(1, height_px // downscale_factor)

        gx, gy = np.meshgrid(
            np.linspace(0, width_px, grid_w),
            np.linspace(0, height_px, grid_h)
        )

        pts = np.array(points)
        px_x = pts[:, 0]
        px_y = pts[:, 1]

        dx = gx[:, :, np.newaxis] - px_x
        dy = gy[:, :, np.newaxis] - px_y
        dist = np.sqrt(dx * dx + dy * dy)

        min_dist_px = np.min(dist, axis=2)
        radius_px = coverage_radius_m / meters_per_pixel

        # 유효 범위 내 포함된 격자 셀 개수 적분
        valid_cells = np.sum(min_dist_px <= radius_px)

        # 격자 셀 1개당 실제 면적(m²) 계산
        cell_w_m = (width_px / grid_w) * meters_per_pixel
        cell_h_m = (height_px / grid_h) * meters_per_pixel
        cell_area_m2 = cell_w_m * cell_h_m

        return float(valid_cells * cell_area_m2)
