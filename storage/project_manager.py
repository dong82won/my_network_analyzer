#!/usr/bin/env python3
'''
data/<project_name>/ 폴더 번들링 초기화 및 저장 기능을 분리한 ProjectManager 모듈입니다.
'''

import os
import re
import json
import time
import shutil
from pathlib import Path
from dataclasses import asdict
from typing import Optional, Tuple

from core.models import SurveyProject, FloorplanMeta, APMarker, SurveyPoint, NetworkMetrics


class ProjectManager:
    _MODULE_DIR = Path(__file__).resolve().parent
    _ROOT_DIR = _MODULE_DIR.parent
    DATA_DIR = _ROOT_DIR / "data"

    @classmethod
    def ensure_data_dir_exists(cls) -> None:
        '''data/ 최상위 디렉터리가 없으면 자동 생성'''
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_default_data_dir(cls) -> str:
        '''기본 data/ 디렉터리 경로 반환'''
        cls.ensure_data_dir_exists()
        return str(cls.DATA_DIR)

    @classmethod
    def sanitize_folder_name(cls, name: str) -> str:
        '''폴더 및 파일명으로 안전한 문자열 변환'''
        safe_name = re.sub(r'[^\w\-]', '_', name.strip())
        return safe_name if safe_name else "survey_project"

    @classmethod
    def initialize_project_bundle(cls, project: SurveyProject, project_name: str) -> bool:
        '''
        [신규] 프로젝트 번들 초기화:
        JSON 파일은 생성하지 않고 data/<project_name>/ 디렉터리 생성 및 도면 이미지 복사만 수행합니다.
        '''
        try:
            cls.ensure_data_dir_exists()
            safe_name = cls.sanitize_folder_name(project_name)
            project_dir = cls.DATA_DIR / safe_name
            project_dir.mkdir(parents=True, exist_ok=True)

            project.name = project_name

            # 도면 이미지 파일 복사 처리 (JSON 파일은 작성하지 않음)
            src_image_input = project.floorplan.image_path
            if src_image_input and os.path.exists(src_image_input):
                src_path = Path(src_image_input)
                dest_image_name = f"{safe_name}{src_path.suffix}"
                dest_image_path = project_dir / dest_image_name

                if src_path.resolve() != dest_image_path.resolve():
                    if not dest_image_path.exists():
                        shutil.copy2(src_path, dest_image_path)

                project.floorplan.image_path = dest_image_name

            return True
        except Exception as e:
            print(f"[ProjectManager Error] Bundle initialization failed: {e}")
            return False

    @classmethod
    def save_project(cls, project: SurveyProject, project_name: str) -> Tuple[bool, str]:
        '''
        사용자가 'Save Project' 버튼을 클릭했을 때만 타임스탬프 JSON 파일을 실제로 생성합니다.
        '''
        try:
            cls.ensure_data_dir_exists()
            safe_name = cls.sanitize_folder_name(project_name)
            project_dir = cls.DATA_DIR / safe_name
            project_dir.mkdir(parents=True, exist_ok=True)

            project.name = project_name

            # 도면 사본 안전 검사
            src_image_input = project.floorplan.image_path
            rel_image_name = ""

            if src_image_input and os.path.exists(src_image_input):
                src_path = Path(src_image_input)
                dest_image_name = f"{safe_name}{src_path.suffix}"
                dest_image_path = project_dir / dest_image_name

                if src_path.resolve() != dest_image_path.resolve():
                    if not dest_image_path.exists():
                        shutil.copy2(src_path, dest_image_path)

                rel_image_name = dest_image_name
            else:
                for ext in ['.png', '.jpg', '.jpeg', '.bmp']:
                    candidate = project_dir / f"{safe_name}{ext}"
                    if candidate.exists():
                        rel_image_name = candidate.name
                        break

            project.floorplan.image_path = rel_image_name

            # 단 1개의 유효한 타임스탬프 JSON 생성
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            json_filename = f"{safe_name}_{timestamp_str}.json"
            json_file_path = project_dir / json_filename

            data = asdict(project)
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            return True, str(json_file_path)
        except Exception as e:
            print(f"[ProjectManager Error] Save failed: {e}")
            return False, str(e)

    @classmethod
    def load_project(cls, json_file_path: str) -> Optional[SurveyProject]:
        '''JSON 프로젝트 로드 및 동일 프로젝트 폴더 내 도면 이미지 자가 복원'''
        try:
            json_path = Path(json_file_path).resolve()
            if not json_path.exists():
                print(f"[ProjectManager Error] File not found: {json_path}")
                return None

            project_dir = json_path.parent
            project_folder_name = project_dir.name

            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            floorplan_data = data.get("floorplan", {})
            rel_image_name = floorplan_data.get("image_path", "")

            abs_image_path = ""
            if rel_image_name:
                candidate = project_dir / rel_image_name
                if candidate.exists():
                    abs_image_path = str(candidate)

            if not abs_image_path:
                for ext in ['.png', '.jpg', '.jpeg', '.bmp']:
                    candidate = project_dir / f"{project_folder_name}{ext}"
                    if candidate.exists():
                        abs_image_path = str(candidate)
                        break

            if not abs_image_path:
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.bmp']:
                    found = list(project_dir.glob(ext))
                    if found:
                        abs_image_path = str(found[0])
                        break

            floorplan = FloorplanMeta(
                image_path=abs_image_path,
                width_px=floorplan_data.get("width_px", 0),
                height_px=floorplan_data.get("height_px", 0),
                meters_per_pixel=floorplan_data.get("meters_per_pixel", 0.05)
            )

            ap_markers = []
            for ap in data.get("ap_markers", []):
                ap_markers.append(
                    APMarker(
                        bssid=ap.get("bssid", "--"),
                        ssid=ap.get("ssid", "--"),
                        x_m=ap.get("x_m", 0.0),
                        y_m=ap.get("y_m", 0.0),
                        channel_freq=ap.get("channel_freq", "--"),
                        channel_num=ap.get("channel_num", 0),
                        wifi_band=ap.get("wifi_band", "--"),
                        security=ap.get("security", "--"),
                        max_rate=ap.get("max_rate", "--"),
                        sequence_id=ap.get("sequence_id", 1)
                    )
                )

            survey_points = []
            for sp in data.get("survey_points", []):
                metrics = NetworkMetrics(**sp["metrics"])
                survey_points.append(
                    SurveyPoint(
                        x_m=sp["x_m"],
                        y_m=sp["y_m"],
                        timestamp=sp["timestamp"],
                        metrics=metrics,
                        sequence_id=sp.get("sequence_id", 1),
                        scanned_aps=sp.get("scanned_aps", {})
                    )
                )

            return SurveyProject(
                name=data.get("name", project_folder_name),
                created_at=data.get("created_at", ""),
                floorplan=floorplan,
                ap_markers=ap_markers,
                survey_points=survey_points
            )
        except Exception as e:
            print(f"[ProjectManager Error] Load failed: {e}")
            return None
