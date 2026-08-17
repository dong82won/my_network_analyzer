#!/usr/bin/env python3
'''
Phase 2&3: Pixel 좌표와 Meter 좌표 간의 상호 변환 및 축척 보정 기능을 전담합니다.
'''
import math
from typing import Tuple

class CoordinateConverter:
    def __init__(self, meters_per_pixel: float = 0.05):
        self.meters_per_pixel = meters_per_pixel

    def calibrate_scale(self, p1_px: Tuple[float, float], p2_px: Tuple[float, float], real_distance_m: float) -> float:
        """도면 상의 두 픽셀 점과 실제 거리를 입력받아 m/px 축척 비율을 계산합니다."""
        dx = p2_px[0] - p1_px[0]
        dy = p2_px[1] - p1_px[1]
        pixel_distance = math.sqrt(dx * dx + dy * dy)

        if pixel_distance > 0 and real_distance_m > 0:
            self.meters_per_pixel = real_distance_m / pixel_distance
        return self.meters_per_pixel

    def pixel_to_meter(self, x_px: float, y_px: float) -> Tuple[float, float]:
        return x_px * self.meters_per_pixel, y_px * self.meters_per_pixel

    def meter_to_pixel(self, x_m: float, y_m: float) -> Tuple[float, float]:
        if self.meters_per_pixel == 0:
            return 0.0, 0.0
        return x_m / self.meters_per_pixel, y_m / self.meters_per_pixel
