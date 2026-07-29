"""화면 픽셀 캡처(mss), 리사이즈, 정지 이미지 저장/클립보드 복사, 타임스탬프 파일명 생성."""
from __future__ import annotations

import datetime
from pathlib import Path

import mss
from PIL import Image

from logger import get_logger

log = get_logger()


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


def excel_col_width_to_px(width_chars: float, mdw: int = 7) -> int:
    """엑셀 열 너비(문자 수, 예: 기본값 8.43)를 픽셀로 변환.

    Calibri 11(엑셀 기본 글꼴, 96 DPI) 기준의 근사식(width_chars*MDW+5)이다.
    기본 열 너비 8.43 -> 64px로, 엑셀에서 흔히 알려진 기본값과 일치한다.
    다른 글꼴/DPI/확대 비율에서는 실제 엑셀 표시와 약간 차이가 날 수 있다.
    """
    return max(1, round(width_chars * mdw + 5))


def excel_row_height_to_px(height_pt: float) -> int:
    """엑셀 행 높이(포인트, 예: 기본값 15)를 픽셀로 변환 (96 DPI 기준, 1pt = 96/72px)."""
    return max(1, round(height_pt * 96 / 72))


def _fit_within(img_w: int, img_h: int, box_w: int, box_h: int) -> tuple[int, int]:
    """원본 비율을 유지한 채 (box_w, box_h) 안에 들어가는 최대 크기를 계산."""
    scale = min(box_w / img_w, box_h / img_h)
    return max(1, round(img_w * scale)), max(1, round(img_h * scale))


def apply_resize(img: Image.Image, cfg: dict) -> Image.Image:
    if not cfg.get("resize_enabled"):
        return img
    mode = cfg.get("resize_mode", "fixed")
    if mode == "percent":
        pct = max(1, int(cfg.get("resize_percent", 100))) / 100.0
        new_w = max(1, round(img.width * pct))
        new_h = max(1, round(img.height * pct))
    elif mode == "excel":
        box_w = excel_col_width_to_px(cfg.get("excel_col_width") or 8.43)
        box_h = excel_row_height_to_px(cfg.get("excel_row_height") or 15.0)
        # 비율을 유지한 채 엑셀 셀 크기 안에 들어가도록 축소/확대 (찌그러짐 없음)
        new_w, new_h = _fit_within(img.width, img.height, box_w, box_h)
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
            log.exception("클립보드 복사 실패")
            return False, f"클립보드 복사 실패: {e}"

    folder = cfg.get("output_folder", "")
    if not folder:
        log.error("정지 이미지 저장 실패: 출력 폴더가 설정되지 않음")
        return False, "출력 폴더가 설정되지 않았습니다."
    try:
        path = make_output_path(folder, ext)
        save_img = img.convert("RGB") if ext in ("jpg", "jpeg") else img
        save_img.save(str(path))
        return True, f"저장됨: {path}"
    except Exception as e:
        log.exception("정지 이미지 저장 실패: folder=%s ext=%s", folder, ext)
        return False, f"저장 실패: {e}"
