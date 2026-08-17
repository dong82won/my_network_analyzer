#!/usr/bin/env python3
'''
Phase 1: 네트워크 통신 지표 및 LAN/WAN 타겟 모드 데이터 구조체 모듈입니다.
Phase 2&3: 도면 메타데이터, AP 마커(무선 메타데이터 확장), 수집점(SurveyPoint), 서베이 프로젝트 클래스 정의 모듈입니다.
'''
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class NetworkMetrics:
    timestamp: float = field(default_factory=time.time) # 수집 시점 UNIX 타임스탬프
    interface: str = "wlan0"
    ssid: str = "Scanning..."
    bssid: str = "--:--:--:--:--:--"
    ip_addr: str = "0.0.0.0"
    gateway: str = "0.0.0.0"
    target_host: str = "192.168.0.1"
    target_mode: str = "LAN"
    freq_ghz: str = "--"
    link_speed_mbps: str = "--"
    rssi: int = -100
    latency_ms: float = 0.0
    packet_loss_pct: float = 0.0
    jitter_ms: float = 0.0
    score: int = 0
    status_text: str = "POOR"
    wifi_connected: bool = False
    wired_connected: bool = False


@dataclass
class APMarker:
    bssid: str
    ssid: str
    x_m: float
    y_m: float
    channel_freq: str = "--"    # 예: "5240 MHz"
    channel_num: int = 0         # 예: 48
    wifi_band: str = "--"        # 예: "5GHz"
    security: str = "--"         # 예: "WPA2"
    max_rate: str = "--"         # 예: "270 Mbit/s"
    sequence_id: int = 1


@dataclass
class SurveyPoint:
    x_m: float
    y_m: float
    timestamp: float
    metrics: NetworkMetrics
    sequence_id: int = 1
    scanned_aps: Dict[str, int] = field(default_factory=dict)


@dataclass
class FloorplanMeta:
    image_path: str = ""
    width_px: int = 0
    height_px: int = 0
    meters_per_pixel: float = 0.05


@dataclass
class SurveyProject:
    name: str = "New Survey"
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    floorplan: FloorplanMeta = field(default_factory=FloorplanMeta)
    ap_markers: List[APMarker] = field(default_factory=list)
    survey_points: List[SurveyPoint] = field(default_factory=list)
