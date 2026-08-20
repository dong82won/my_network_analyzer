# Network Analyzer (Ubuntu 24.04 LTS)

**Network Analyzer**는 Ubuntu 24.04 LTS Desktop 환경에 최적화된 **실시간 Wi-Fi AP 신호 및 통신 품질(QoS) 모니터링**, 그리고 **2D 무선 현장 조사(Wi-Fi Site Survey) 시각화 플랫폼**입니다.

Linux 인프라의 NetworkManager 및 Wireless Subsystem 텔레메트리 수집 엔진을 기반으로, AP별 신호 세기(RSSI)와 Latency/Jitter/Loss 등의 품질 지표를 30 FPS 시계열 파형으로 관제하며, **전역 역거리 가중 보간(Global IDW)** 기술을 통해 실내 도면 위 부드러운 연속 등고선 히트맵(Continuous Field Heatmap)을 제공합니다.

---

## 1. 주요 기능 (Key Features)

### 📊 실시간 네트워크 텔레메트리 대시보드 (Dashboard)

* **6대 핵심 지표 관제**: Signal Strength (RSSI), Latency (Ping), Jitter, Packet Loss, Link Speed, Frequency 측정.
* **30 FPS 하드웨어 감각 뷰포트**: `pyqtgraph` 기반의 고성능 슬라이딩 윈도우 시계열 파형 그래프 (60초 히스토리).
* **통신 단락 세이프가드 (Link Drop Guard)**:
* Wi-Fi 끊김(`WIFI: OFF`) 시 $0.0\text{ ms}$ 오판을 방지하기 위해 파형에 `NaN` 주입 (파형 왜곡 차단).
* 6개 센서 카드 붉은 경고 테두리 디밍(Red Glow Outline) 및 `POOR` / `N/A` 일괄 전환.
* 단락 지속 시간 카운터(`OFFLINE - Disconnected: 00:15s`) 표출.



### 🗺️ 2D 무선 현장 조사 및 히트맵 생성 엔진 (Site Survey)

* **전역 IDW 보간 엔진 (Global IDW Interpolator)**:
* 인공적 거리 절단(Cutoff)을 제거하여 밀집 구역(#1~#8)을 하나의 매끄러운 연속 등고선 덩어리로 연결.
* 이격 지점(#12)은 실제 수치를 정밀 보존하되, 주변으로 물리적 전파 감쇄 경사면(Gradient) 형성.


* **5m 수동 조사 규격 및 스냅 엔진 (5m Grid & Snap-to-Grid)**:
* 현장 보행 동선에 맞춘 $5\text{m} \times 5\text{m}$ 격자선 및 자석 스냅 지원.
* $10\text{m}$ 전파 감쇄 엔벨로프(Decay Envelope) 적용으로 $5\text{m}$ 조사 지점 간 가짜 음영 구멍 방지.


* **유효 커버리지 면적($\text{m}^2$) 적분 연산**: 서브 픽셀 단위 적분 연산으로 실시간 커버리지 면적 정량화 표출.
* **고대비 이중 윤곽선 마커 (Dual-Stroke Outline Marker)**:
* $4\text{px}$ 흰색 외곽선 + $2\text{px}$ 진한 파란색 코발트 블루(`#0055FF`) 코어 조합으로 녹색/적색 히트맵 배경 위에서 $100\%$ 가시성 확보.



### 💾 프로젝트 및 이력 관리 (Storage & History)

* **JSON 기반 프로젝트 저장/불러오기**: CAD 도면, 메트릭, AP 좌표 및 측점 데이터 완벽 복원.
* **실시간 네트워크 이벤트 로그**: 통신 단락, AP 변경, 측정 저장 이력 트래킹.

---

## 2. 시스템 아키텍처 (System Architecture)

```text
[ Application Layer ]
 ├── DashboardTab (pyqtgraph 30FPS Real-time Plots & Alert Dimming Cards)
 ├── SurveyTab (QGraphicsView 2D Canvas & 5m Grid Engine)
 ├── HistoryTab & SettingsTab
 └── Custom UI Widgets (Dual-Stroke Markers, Legend, Radial Progress)
         │
         │ (Qt Signals / Slots)
         ▼
[ Domain & Analysis Layer ]
 ├── NetworkDataCollector (Background Worker Thread for Telemetry Scanning)
 ├── Spatial Engine (Global IDW Heatmap, 10m Decay Envelope, Area Integrator)
 ├── CoordinateConverter (Pixel <-> Meter Physical Scale Transformation)
 └── ProjectManager (Project Save/Load & JSON Storage Serializer)
         │
         │ (Subprocess / System Calls)
         ▼
[ Linux Infrastructure Layer ]
 ├── Linux Kernel 6.8+ (Network Subsystem / wireless-tools)
 ├── NetworkManager / wpa_supplicant (Wi-Fi Link State Management)
 └── System Utilities (ping, iw, nmcli)

```

---

## 3. 프로젝트 폴더 구조 (Directory Structure)

```text
my_network_analyzer
├── core/                       # 핵심 데이터 수집 및 데이터 모델
│   ├── collector.py            # 백그라운드 네트워크 텔레메트리 수집 스레드
│   └── models.py               # NetworkMetrics, SurveyPoint 등 데이터 dataclass
├── data/                       # 도면 샘플 및 테스트 프로젝트 저장소
│   ├── analyzer_test/          # 기본 테스트 이미지 및 맵 파일
│   └── project_analyzer/       # 분석 프로젝트 도면 예시
├── spatial/                    # 공간 보간 및 좌표계 연산 엔진
│   ├── coordinate.py           # 픽셀-미터(px <-> m) 좌표 변환기
│   └── heatmap_generator.py    # 전역 IDW 보간, 10m 감쇄 엔벨로프, m² 면적 적분기
├── storage/                    # 데이터 영속성 관리
│   └── project_manager.py      # JSON 프로젝트 입출력 및 직렬화
├── ui/                         # Qt 기반 User Interface 계층
│   ├── canvas/                 # 2D 그래픽스 캔버스 요소
│   │   ├── constants.py        # Z-Value, Canvas 타입 정의
│   │   ├── items/              # Dual-Stroke 마커, AP 마커 커스텀 QGraphicsItem
│   │   └── survey_canvas.py    # 2D 캔버스, 5m 격자 렌더링, Snap-to-Grid
│   ├── dialogs/                # AP 선택 및 대화상자 컴포넌트
│   ├── main_window.py          # 메인 윈도우 프레임 및 상단 상태 오버레이
│   ├── tabs/                   # 메인 탭 뷰 (Dashboard, Survey, History, Settings)
│   └── widgets/                # 센서 카운터 카드, 프로그레스 바, 범례 위젯
├── main.py                     # 애플리케이션 진입점 (Application Entry Point)
└── requirements_local.txt      # 개발 및 로컬 테스트 패키지 목록

```

---

## 4. 핵심 공간 보간 알고리즘 (Mathematical Engine)

### 1. 전역 역거리 가중 보간 (Global Inverse Distance Weighting)

도면 상의 모든 연산 격자 픽셀 좌표 $(x, y)$에서 $N$개 측정점의 거리 역수 제곱 가중치를 누적 합산하여 불연속 자름(Cutoff) 없는 연속 전파 필드를 연산합니다.

$$w_i(x, y) = \frac{1}{\left(\sqrt{(x - x_i)^2 + (y - y_i)^2}\right)^2 + \epsilon}$$

$$Z(x, y) = \frac{\sum_{i=1}^{N} w_i(x, y) \cdot Z_i}{\sum_{i=1}^{N} w_i(x, y)}$$

### 2. $10\text{m}$ 소프트 감쇄 엔벨로프 (Decay Envelope)

고립된 지점(#12)이 허공으로 무한히 번지는 현상을 차단하고, $5\text{m}$ 조사 간격 사이의 가짜 구멍을 메우기 위해 이차 곡선 감쇄 마스크를 결합합니다.

$$\text{Envelope}(x, y) = \max\left(0, 1 - \left(\frac{d_{\min}(x, y)}{R_{\text{decay}}}\right)^2\right) \quad (R_{\text{decay}} = 10.0\text{ m})$$

---

## 5. 설치 및 실행 가이드 (Getting Started)

### 사전 요구사항 (Prerequisites)

* **OS**: Ubuntu 24.04 LTS Desktop
* **Python**: Python 3.12+
* **System Utilities**: `iputils-ping`, `wireless-tools`, `network-manager`

### 1. 시스템 패키지 및 가상환경 구축

```bash
# 필수 시스템 패키지 설치
sudo apt update
sudo apt install -y python3-pip python3-venv wireless-tools iputils-ping

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

```

### 2. 의존성 패키지 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt

```

### 3. 애플리케이션 실행

```bash
python3 main.py

```

---

## 6. Linux 인프라 및 네트워크 최적화 (Troubleshooting)

Ubuntu 24.04 환경에서 Wi-Fi 단락 후 재연결 지연을 단축하고 안정적인 텔레메트리 수집을 유지하기 위한 권장 시스템 설정입니다.

### Wi-Fi 절전 모드 비활성화 및 Fast Reconnect

`NetworkManager` 연결 프로필에서 IPv6 DAD 지연 및 2.4GHz 스캔 지연을 제거합니다.

```bash
# 1. Wi-Fi 절전 모드 비활성화
sudo sed -i 's/wifi.powersave = 3/wifi.powersave = 2/' /etc/NetworkManager/conf.d/default-wifi-powersave-on.conf

# 2. 특정 Wi-Fi 접속 프로필(예: Rokey5G) 고속 재연결 설정
nmcli connection modify "Rokey5G" ipv6.method "ignore"
nmcli connection modify "Rokey5G" connection.interface-name ""  # 특정 NIC 바인딩 해제

# 3. NetworkManager 재시작
sudo systemctl restart NetworkManager

```

---

## 7. 기술 스택 (Tech Stack)

| 구분 | 기술 스택 |
| --- | --- |
| **Language** | Python 3.12+ |
| **GUI Framework** | PySide6 (Qt for Python 6.x) |
| **Data Processing** | NumPy (3D Distance Matrix Vectorization) |
| **Plot Engine** | pyqtgraph (Hardware Accelerated Real-time Plotting) |
| **Linux Subsystem** | Linux Kernel 6.8+, NetworkManager, Systemd |

---

## 8. 라이선스 (License)

본 프로젝트는 MIT License에 따라 자유롭게 수정, 배포 및 활용할 수 있습니다.
