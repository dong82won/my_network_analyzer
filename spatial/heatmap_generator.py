#!/usr/bin/env python3
'''
실측 데이터 기반 전역 공간 보간(Global IDW) 및 부드러운 연속 등고선 필드를
생성하는 HeatmapGenerator 모듈입니다.
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
        min_rssi: float = -90.0,
        max_rssi: float = -30.0,
        downscale_factor: int = 4,
        alpha_opacity: int = 160
    ) -> QPixmap:
        '''
        전역 데이터 기반 연속 등고선 히트맵 QPixmap 생성
        '''
        if not points or width_px <= 0 or height_px <= 0:
            return QPixmap()

        # 1. 저해상도 연산 격자(Meshgrid) 생성 (NumPy 백터화)
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

        # 3. 전역 역거리 가중 보간 (Global IDW - 6개 지점 가중치 제한 없는 누적 합성)
        safe_dist = np.maximum(dist, 1e-5)
        weights = 1.0 / (safe_dist ** 2.0)
        weights_sum = np.sum(weights, axis=2)

        z_final = np.sum(weights * vals, axis=2) / weights_sum

        # 4. 소프트 경계 알파 엔벨로프 (측정점 집합 외곽 부드러운 투명도 처리)
        min_dist_px = np.min(dist, axis=2)
        effective_radius_px = (15.0 / meters_per_pixel) if meters_per_pixel > 0 else 300.0

        envelope = np.clip(1.0 - (min_dist_px / effective_radius_px) ** 2.0, 0.0, 1.0)
        alpha = (alpha_opacity * (0.25 + 0.75 * envelope)).astype(np.uint8)

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
