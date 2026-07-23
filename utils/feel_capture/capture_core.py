"""화면 픽셀 캡처(mss), 리사이즈, 정지 이미지 저장/클립보드 복사, 타임스탬프 파일명 생성."""
from __future__ import annotations

import datetime
from pathlib import Path

import mss
from PIL import Image


def grab_virtual_desktop():
    """모든 모니터를 아우르는 가상 데스크톱 전체를 캡처한다.

    Returns:
        (PIL.Image(RGB), offset_x, offset_y) — offset은 가상 데스크톱 좌상단의 스크린 좌표
        (모니터가 기준 모니터의 왼쪽/위에 있으면 음수일 수 있음).
    """
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img, mon["left"], mon["top"]


def grab_region(x: int, y: int, w: int, h: int) -> Image.Image:
    with mss.mss() as sct:
        shot = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def apply_resize(img: Image.Image, cfg: dict) -> Image.Image:
    if not cfg.get("resize_enabled"):
        return img
    mode = cfg.get("resize_mode", "fixed")
    if mode == "percent":
        pct = max(1, int(cfg.get("resize_percent", 100))) / 100.0
        new_w = max(1, round(img.width * pct))
        new_h = max(1, round(img.height * pct))
    else:
        new_w = cfg.get("resize_width") or 0
        new_h = cfg.get("resize_height") or 0
        if not new_w and not new_h:
            return img
        if not new_w:
            new_w = round(img.width * (new_h / img.height))
        if not new_h:
            new_h = round(img.height * (new_w / img.width))
    new_w = max(1, int(new_w))
    new_h = max(1, int(new_h))
    if (new_w, new_h) == (img.width, img.height):
        return img
    return img.resize((new_w, new_h), Image.LANCZOS)


def make_output_path(folder: str, ext: str) -> Path:
    folder_path = Path(folder)
    folder_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = folder_path / f"{ts}.{ext}"
    i = 1
    while candidate.exists():
        candidate = folder_path / f"{ts}_{i}.{ext}"
        i += 1
    return candidate


def copy_to_clipboard(img: Image.Image) -> None:
    from PyQt5.QtGui import QImage
    from PyQt5.QtWidgets import QApplication

    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    QApplication.clipboard().setImage(qimg.copy())


def save_static_image(img: Image.Image, cfg: dict) -> tuple[bool, str]:
    """cfg["save_target"]에 따라 클립보드 복사 또는 파일 저장. (성공여부, 메시지) 반환."""
    img = apply_resize(img, cfg)
    ext = cfg["extension"]

    if cfg["save_target"] == "clipboard":
        try:
            copy_to_clipboard(img)
            return True, "클립보드에 복사했습니다."
        except Exception as e:
            return False, f"클립보드 복사 실패: {e}"

    folder = cfg.get("output_folder", "")
    if not folder:
        return False, "출력 폴더가 설정되지 않았습니다."
    try:
        path = make_output_path(folder, ext)
        save_img = img.convert("RGB") if ext in ("jpg", "jpeg") else img
        save_img.save(str(path))
        return True, f"저장됨: {path}"
    except Exception as e:
        return False, f"저장 실패: {e}"
