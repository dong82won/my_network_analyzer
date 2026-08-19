#!/usr/bin/env python3
'''
NetworkManager 패시브 상태 파싱, 주변 AP 스캔 수집, 사설/공인 IP 대역 판별,
순수 동적 품질 평가(Approach A) 기반 건강 점수 산출 백그라운드 PING 수집기 모듈입니다.
'''

import ipaddress
import re
import statistics
import subprocess
import time
from datetime import datetime
from typing import Any

from PySide6.QtCore import QThread, Signal

from core.models import NetworkMetrics


class NetworkDataCollector(QThread):
    metrics_updated = Signal(NetworkMetrics)
    event_occurred = Signal(str, str, str, str)

    def __init__(self, target_host="AUTO", interface="wlan0"):
        super().__init__()
        self.target_host = target_host
        self.interface = interface
        self.is_running = True

        self.last_bssid = ""
        self.last_wifi_connected = False
        self.last_wired_connected = False
        self.last_spike_logged = False

    def run(self):
        while self.is_running:
            loop_start_time = time.time()
            metrics = NetworkMetrics(interface=self.interface)
            metrics.timestamp = loop_start_time

            self._get_wifi_info(metrics)
            self._get_wired_info(metrics)
            self._get_ip_info(metrics)

            if self.target_host.upper() == "AUTO":
                metrics.target_host = metrics.gateway if metrics.gateway != "0.0.0.0" else "8.8.8.8"
            else:
                metrics.target_host = self.target_host

            self._classify_target_mode(metrics)
            self._run_ping_test(metrics)
            self._calculate_health_score(metrics)

            now_str = datetime.fromtimestamp(metrics.timestamp).strftime("%H:%M:%S")

            # 이벤트 로깅 파이프라인
            if metrics.wifi_connected and not self.last_wifi_connected:
                self.event_occurred.emit(now_str, "WIFI_CONN", "INFO", f"Connected to {metrics.ssid} ({metrics.bssid})")
            elif not metrics.wifi_connected and self.last_wifi_connected:
                self.event_occurred.emit(now_str, "WIFI_DISC", "ERROR", "Wi-Fi Link Dropped")

            if metrics.wired_connected and not self.last_wired_connected:
                self.event_occurred.emit(now_str, "ETH_CONN", "INFO", "Ethernet Cable Connected (Link UP)")
            elif not metrics.wired_connected and self.last_wired_connected:
                self.event_occurred.emit(now_str, "ETH_DISC", "WARN", "Ethernet Cable Disconnected (Link DOWN)")

            if (metrics.wifi_connected and self.last_bssid and
                metrics.bssid != "--:--:--:--:--:--" and self.last_bssid != metrics.bssid):
                self.event_occurred.emit(now_str, "AP_ROAMING", "INFO", f"AP Changed: {self.last_bssid} -> {metrics.bssid}")

            lat_spike_threshold = 30.0 if metrics.target_mode == "LAN" else 80.0
            if metrics.wifi_connected:
                if metrics.latency_ms > lat_spike_threshold and not self.last_spike_logged:
                    self.event_occurred.emit(now_str, "LATENCY_SPIKE", "WARN", f"High Latency ({metrics.target_mode}): {metrics.latency_ms} ms")
                    self.last_spike_logged = True
                elif metrics.latency_ms <= lat_spike_threshold:
                    self.last_spike_logged = False

                if 0.0 < metrics.packet_loss_pct < 100.0:
                    self.event_occurred.emit(now_str, "PACKET_LOSS", "WARN", f"Packet Loss Detected: {metrics.packet_loss_pct} %")

            self.last_wifi_connected = metrics.wifi_connected
            self.last_wired_connected = metrics.wired_connected
            if metrics.bssid != "--:--:--:--:--:--":
                self.last_bssid = metrics.bssid

            self.metrics_updated.emit(metrics)

            # 정밀 1.0초 루프 주기 보정
            elapsed = time.time() - loop_start_time
            sleep_ms = max(50, int((1.0 - elapsed) * 1000))
            self.msleep(sleep_ms)

    def stop(self):
        self.is_running = False
        self.wait()

    def get_scanned_aps_snapshot(self) -> dict[str, int]:
        '''SurveyPoint 수집용 BSSID-RSSI 매핑 스냅샷을 반환합니다.'''
        scanned_dict: dict[str, int] = {}
        try:
            cmd = ["nmcli", "-t", "-f", "BSSID,SIGNAL", "dev", "wifi", "list", "--rescan", "no"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.2)

            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().split('\n'):
                    parts = re.split(r'(?<!\\):', line)
                    if len(parts) >= 2:
                        raw_bssid = parts[0].replace(r'\:', ':').strip().upper()
                        raw_signal = parts[1].strip()
                        if raw_bssid and raw_signal.isdigit():
                            sig_pct = int(raw_signal)
                            rssi_dbm = int((sig_pct / 2) - 100)
                            scanned_dict[raw_bssid] = rssi_dbm
        except Exception:
            pass
        return scanned_dict

    def get_scanned_aps_detail(self) -> dict[str, dict[str, Any]]:
        '''AP 배치 팝업용 BSSID, SSID, RSSI, 주파수, 채널, 대역, 보안규격 상세 스냅샷 수집'''
        scanned_detail: dict[str, dict[str, Any]] = {}
        try:
            cmd = ["nmcli", "-t", "-f", "BSSID,SSID,SIGNAL,FREQ,CHAN,RATE,SECURITY", "dev", "wifi", "list", "--rescan", "no"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.2)

            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().split('\n'):
                    parts = re.split(r'(?<!\\):', line)
                    if len(parts) >= 7:
                        raw_bssid = parts[0].replace(r'\:', ':').strip().upper()
                        raw_ssid = parts[1].replace(r'\:', ':').strip()
                        raw_signal = parts[2].strip()
                        raw_freq = parts[3].replace(r'\:', ':').strip()
                        raw_chan = parts[4].strip()
                        raw_rate = parts[5].replace(r'\:', ':').strip()
                        raw_sec = parts[6].replace(r'\:', ':').strip()

                        if raw_bssid and raw_signal.isdigit():
                            sig_pct = int(raw_signal)
                            rssi_dbm = int((sig_pct / 2) - 100)
                            chan_num = int(raw_chan) if raw_chan.isdigit() else 0

                            freq_match = re.search(r'\d+', raw_freq)
                            freq_val = int(freq_match.group()) if freq_match else 0

                            if freq_val >= 5900:
                                band = "6GHz"
                            elif freq_val >= 4900:
                                band = "5GHz"
                            elif freq_val >= 2400:
                                band = "2.4GHz"
                            else:
                                band = "--"

                            scanned_detail[raw_bssid] = {
                                "ssid": raw_ssid if raw_ssid else "<Hidden SSID>",
                                "rssi": rssi_dbm,
                                "channel_freq": f"{freq_val} MHz" if freq_val > 0 else raw_freq,
                                "channel_num": chan_num,
                                "wifi_band": band,
                                "security": raw_sec if raw_sec else "--",
                                "max_rate": raw_rate if raw_rate else "--"
                            }
        except Exception:
            pass
        return scanned_detail

    def _classify_target_mode(self, metrics: NetworkMetrics):
        try:
            ip_obj = ipaddress.ip_address(metrics.target_host)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                metrics.target_mode = "LAN"
            else:
                metrics.target_mode = "WAN"
        except ValueError:
            metrics.target_mode = "LAN"

    def _get_wifi_info(self, metrics: NetworkMetrics):
        try:
            cmd = ["nmcli", "-t", "-f", "ACTIVE,DEVICE,SSID,BSSID,SIGNAL,FREQ,RATE", "dev", "wifi", "list", "--rescan", "no"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)

            connected_found = False
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().split('\n'):
                    if line.startswith("yes:"):
                        parts = re.split(r'(?<!\\):', line)
                        if len(parts) >= 7:
                            metrics.interface = parts[1]
                            self.interface = parts[1]

                            metrics.ssid = parts[2].replace(r'\:', ':')
                            metrics.bssid = parts[3].replace(r'\:', ':').upper()

                            try:
                                signal_pct = int(parts[4])
                                metrics.rssi = int((signal_pct / 2) - 100)
                            except ValueError:
                                metrics.rssi = -100

                            metrics.freq_ghz = parts[5].replace(r'\:', ':')
                            metrics.link_speed_mbps = parts[6].replace(r'\:', ':')
                            metrics.wifi_connected = True
                            connected_found = True
                            break

            if not connected_found:
                self._get_wifi_info_fallback(metrics)

        except Exception:
            self._get_wifi_info_fallback(metrics)

    def _get_wifi_info_fallback(self, metrics: NetworkMetrics):
        try:
            iface_cmd = ["iw", "dev"]
            iface_res = subprocess.run(iface_cmd, capture_output=True, text=True, timeout=0.8)
            interfaces = re.findall(r'Interface\s+([\w]+)', iface_res.stdout)
            target_iface = self.interface if self.interface in interfaces else (interfaces[0] if interfaces else "wlan0")

            link_cmd = ["iw", "dev", target_iface, "link"]
            link_res = subprocess.run(link_cmd, capture_output=True, text=True, timeout=0.8)

            if "Connected to" in link_res.stdout:
                metrics.interface = target_iface
                self.interface = target_iface
                metrics.wifi_connected = True

                match_bssid = re.search(r'Connected to ([\da-fA-F:]+)', link_res.stdout)
                if match_bssid:
                    metrics.bssid = match_bssid.group(1).upper()

                match_signal = re.search(r'signal:\s*(-?\d+)\s*dBm', link_res.stdout)
                if match_signal:
                    metrics.rssi = int(match_signal.group(1))

                match_freq = re.search(r'freq:\s*(\d+)', link_res.stdout)
                if match_freq:
                    metrics.freq_ghz = f"{match_freq.group(1)} MHz"

                match_ssid = re.search(r'SSID:\s*(.+)', link_res.stdout)
                if match_ssid:
                    metrics.ssid = match_ssid.group(1).strip()
            else:
                metrics.wifi_connected = False
        except Exception:
            metrics.wifi_connected = False

    def _get_wired_info(self, metrics: NetworkMetrics):
        try:
            cmd = ["nmcli", "-t", "-f", "TYPE,STATE", "dev"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=0.8)
            wired_up = False
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().split('\n'):
                    parts = line.split(':')
                    if len(parts) >= 2:
                        dev_type, dev_state = parts[0], parts[1]
                        if dev_type == "ethernet" and dev_state == "connected":
                            wired_up = True
                            break
            metrics.wired_connected = wired_up
        except Exception:
            metrics.wired_connected = False

    def _get_ip_info(self, metrics: NetworkMetrics):
        try:
            if metrics.interface == "wlan0" and self.interface != "wlan0":
                metrics.interface = self.interface

            res_ip = subprocess.run(["ip", "-4", "addr", "show", metrics.interface], capture_output=True, text=True, timeout=0.8)
            match_ip = re.search(r'inet\s+([\d\.]+)', res_ip.stdout)
            if match_ip:
                metrics.ip_addr = match_ip.group(1)

            res_gw = subprocess.run(["ip", "route", "show", "dev", metrics.interface], capture_output=True, text=True, timeout=0.8)
            match_gw = re.search(r'default via ([\d\.]+)', res_gw.stdout)
            if match_gw:
                metrics.gateway = match_gw.group(1)
        except Exception:
            pass

    def _run_ping_test(self, metrics: NetworkMetrics):
        if not metrics.wifi_connected or metrics.ip_addr == "0.0.0.0":
            metrics.latency_ms = 0.0
            metrics.jitter_ms = 0.0
            metrics.packet_loss_pct = 100.0
            return

        try:
            cmd = ["ping", "-I", metrics.interface, "-c", "3", "-i", "0.2", "-W", "0.4", metrics.target_host]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.2)
            if res.returncode == 0 or "packet loss" in res.stdout:
                times = [float(t) for t in re.findall(r'time=([\d\.]+)', res.stdout)]
                loss_match = re.search(r'([\d\.]+)%\s+packet loss', res.stdout)

                if times:
                    metrics.latency_ms = round(statistics.mean(times), 1)
                    metrics.jitter_ms = round(statistics.stdev(times), 1) if len(times) > 1 else 0.0
                else:
                    metrics.latency_ms = 0.0
                    metrics.jitter_ms = 0.0

                if loss_match:
                    metrics.packet_loss_pct = float(loss_match.group(1))
            else:
                metrics.latency_ms = 0.0
                metrics.jitter_ms = 0.0
                metrics.packet_loss_pct = 100.0
        except Exception:
            metrics.latency_ms = 0.0
            metrics.jitter_ms = 0.0
            metrics.packet_loss_pct = 100.0

    def _calculate_health_score(self, metrics: NetworkMetrics):
        '''접근 방식 A: 순수 동적 품질 지표(RSSI, Latency, Loss, Jitter) 중심 0~100점 점수 산출'''
        if not metrics.wifi_connected or metrics.packet_loss_pct == 100.0:
            metrics.score = 0
            metrics.status_text = "BAD"
            return

        # 1. RSSI 점수 (가중치 20%) [-85 dBm -> 0점, -55 dBm -> 100점]
        s_rssi = max(0.0, min(100.0, ((metrics.rssi - (-85.0)) / ((-55.0) - (-85.0))) * 100.0))

        # 2. Latency 점수 (가중치 25%) [LAN: 5ms~100ms, WAN: 20ms~200ms]
        if metrics.target_mode == "LAN":
            min_lat, max_lat = 5.0, 100.0
        else:
            min_lat, max_lat = 20.0, 200.0

        if metrics.latency_ms <= min_lat:
            s_lat = 100.0
        else:
            s_lat = max(0.0, min(100.0, 100.0 - ((metrics.latency_ms - min_lat) / (max_lat - min_lat)) * 100.0))

        # 3. Jitter 점수 (가중치 20%) [1.0ms -> 100점, 30.0ms -> 0점]
        if metrics.jitter_ms <= 1.0:
            s_jit = 100.0
        else:
            s_jit = max(0.0, min(100.0, 100.0 - ((metrics.jitter_ms - 1.0) / (30.0 - 1.0)) * 100.0))

        # 4. Packet Loss 점수 (가중치 35%) [0% -> 100점, 25% 이상 -> 0점]
        s_loss = max(0.0, min(100.0, 100.0 - (metrics.packet_loss_pct * 4.0)))

        # 5. 가중치 합산 (총 1.0)
        total_score = (s_loss * 0.35) + (s_lat * 0.25) + (s_jit * 0.20) + (s_rssi * 0.20)
        final_score = int(round(total_score))
        metrics.score = max(0, min(100, final_score))

        # 6. 상태 텍스트 매핑
        if metrics.score >= 85:
            metrics.status_text = "EXCELLENT"
        elif metrics.score >= 70:
            metrics.status_text = "GOOD"
        elif metrics.score >= 50:
            metrics.status_text = "WARNING"
        else:
            metrics.status_text = "BAD"
