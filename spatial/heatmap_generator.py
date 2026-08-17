#!/usr/bin/env python3
'''
NumPy 기반 역거리 가중법(IDW) 공간 보간 및
RGBA QImage 변환을 수행하는 HeatmapGenerator 모듈입니다.
'''

import numpy as np
from PySide6.QtGui import QImage, QPixmap, QColor

class HeatmapGenerator:
    @staticmethod
    def rssi_to_rgba(rssi_val: float, min_rssi: float = -90.0, max_rssi: float = -30.0) -> tuple[int, int, int, int]:
        '''RSSI 범위(-90 dBm ~ -30 dBm)를 Rainbow/Jet 컬러맵 및 알파 투명도로 매핑'''
        if np.isnan(rssi_val):
            return (0, 0, 0, 0)

        # 0.0 (최악: -90dBm 이하) ~ 1.0 (최상: -30dBm 이상) 정규화
        norm = float(np.clip((rssi_val - min_rssi) / (max_rssi - min_rssi), 0.0, 1.0))

        # Blue (0.0) -> Cyan (0.25) -> Green (0.5) -> Yellow (0.75) -> Red (1.0)
        if norm < 0.25:
            t = norm / 0.25
            r, g, b = 0, int(255 * t), 255
        elif norm < 0.5:
            t = (norm - 0.25) / 0.25
            r, g, b = 0, 255, int(255 * (1.0 - t))
        elif norm < 0.75:
            t = (norm - 0.5) / 0.25
            r, g, b = int(255 * t), 255, 0
        else:
            t = (norm - 0.75) / 0.25
            r, g, b = 255, int(255 * (1.0 - t)), 0

        # 반투명 알파 채널 적용 (140 / 255)
        alpha = 140
        return (r, g, b, alpha)

    @classmethod
    def generate_heatmap_pixmap(
        cls,
        points: list[tuple[float, float, float]],  # [(x_px, y_px, rssi), ...]
        width_px: int,
        height_px: int,
        downscale_factor: int = 4,
        power: float = 2.0
    ) -> QPixmap:
        '''Vectorized IDW 공간 보간 연산 수행 후 QPixmap 반환'''
        if not points or width_px <= 0 or height_px <= 0:
            return QPixmap()

        # 1. Downscaling 해상도 격자 정의 (성능 최적화)
        grid_w = max(1, width_px // downscale_factor)
        grid_h = max(1, height_px // downscale_factor)

        grid_x, grid_y = np.meshgrid(
            np.linspace(0, width_px, grid_w),
            np.linspace(0, height_px, grid_h)
        )

        pts = np.array(points)  # Shape: (N, 3) [x, y, rssi]
        px_x = pts[:, 0]
        px_y = pts[:, 1]
        vals = pts[:, 2]

        # 2. Vectorized IDW Distance Matrix 계산
        # grid_x/y: (grid_h, grid_w) -> (grid_h, grid_w, 1)
        dx = grid_x[:, :, np.newaxis] - px_x
        dy = grid_y[:, :, np.newaxis] - px_y
        dist = np.sqrt(dx * dx + dy * dy)

        # Division by zero 방지용 미소값
        dist = np.maximum(dist, 1e-5)

        # Weight 산출: w = 1 / (d ^ power)
        weights = 1.0 / (dist ** power)
        weights_sum = np.sum(weights, axis=2)

        # 보간 행렬 생성 (grid_h, grid_w)
        interpolated_grid = np.sum(weights * vals, axis=2) / weights_sum

        # 3. RGBA QImage 데이터 버퍼 바인딩
        img_buffer = np.zeros((grid_h, grid_w, 4), dtype=np.uint8)

        for y in range(grid_h):
            for x in range(grid_w):
                v = interpolated_grid[y, x]
                img_buffer[y, x] = cls.rssi_to_rgba(v)

        # QImage 생성 (Format_RGBA8888)
        qimg = QImage(
            img_buffer.data,
            grid_w,
            grid_h,
            grid_w * 4,
            QImage.Format.Format_RGBA8888
        )

        # 원본 도면 크기로 Bilinear 확대 변환
        pixmap = QPixmap.fromImage(qimg).scaled(
            width_px,
            height_px,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        return pixmap
