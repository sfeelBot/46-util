"""필캡쳐(FeelCapture) 설정 스키마 및 로드/저장.

설정 파일 위치: %APPDATA%\\FeelCapture\\config.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "FeelCapture"

CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"

# 정지 이미지 포맷 (즉시 1장 캡쳐)
STATIC_EXTS = ["png", "jpg", "bmp", "webp", "tiff"]
# 녹화 포맷 (단축키가 녹화 시작/종료 토글로 동작)
ANIMATED_EXTS = ["gif"]
VIDEO_EXTS = ["mp4", "avi"]
RECORD_EXTS = ANIMATED_EXTS + VIDEO_EXTS
ALL_EXTS = STATIC_EXTS + RECORD_EXTS

DEFAULT_CONFIG = {
    "mode": "drag",  # "drag" | "region"
    "save_target": "file",  # "clipboard" | "file" (녹화 포맷은 항상 file)
    "output_folder": str(Path.home() / "Pictures" / "FeelCapture"),
    "extension": "png",
    "resize_enabled": False,
    "resize_mode": "fixed",  # "fixed" | "percent"
    "resize_width": 1280,
    "resize_height": 720,
    "resize_percent": 50,
    "hotkey": "ctrl+shift+s",
    "fps": 12,
    "region_box": {"x": 200, "y": 200, "w": 500, "h": 350, "locked": False},
    "region_presets": [
        {"name": "1920x1080", "w": 1920, "h": 1080},
        {"name": "1280x720", "w": 1280, "h": 720},
        {"name": "800x600", "w": 800, "h": 600},
    ],
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update(data)
            if "region_box" in data and isinstance(data["region_box"], dict):
                cfg["region_box"] = {**DEFAULT_CONFIG["region_box"], **data["region_box"]}
            if not cfg.get("region_presets"):
                cfg["region_presets"] = json.loads(json.dumps(DEFAULT_CONFIG["region_presets"]))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
