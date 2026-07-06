"""이미지 파일 상하반전(vertical flip) 핵심 로직.

지원 형식:
- .raw : 16-bit little-endian unsigned (np.uint16), W×H는 외부에서 지정
- .png / .bmp / .tiff / .tif / .jpg / .jpeg 등: cv2.IMREAD_UNCHANGED로 읽어
  비트심도(8/16-bit)·채널 수 그대로 유지하며 저장

처리 방식: np.flipud (상하반전).
결과 파일: 원본 파일명/확장자 그대로, result 폴더에 원본 상대경로 복제.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

RAW_EXTENSIONS = {".raw"}
CV2_EXTENSIONS = {".png", ".bmp", ".tiff", ".tif", ".jpg", ".jpeg"}


@dataclass
class FlipResult:
    src: Path
    dst: Path
    success: bool
    error: str = ""


def scan_files(src_dir: Path, extensions: set[str]) -> list[Path]:
    """src_dir 하위를 재귀 탐색하여 지정 확장자의 파일 목록 반환."""
    found: list[Path] = []
    for ext in extensions:
        found.extend(src_dir.rglob(f"*{ext}"))
        found.extend(src_dir.rglob(f"*{ext.upper()}"))
    return sorted(set(found))


def _dst_path(src: Path, src_dir: Path, dst_dir: Path) -> Path:
    """src의 src_dir 기준 상대경로를 dst_dir 아래에 복제."""
    return dst_dir / src.relative_to(src_dir)


def flip_raw(src: Path, dst: Path, width: int, height: int) -> None:
    data = np.fromfile(str(src), dtype="<u2")
    img = data.reshape(height, width)
    flipped = np.flipud(img)
    dst.parent.mkdir(parents=True, exist_ok=True)
    flipped.astype("<u2").tofile(str(dst))


def flip_image(src: Path, dst: Path) -> None:
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cv2.imread 실패: {src}")
    flipped = np.flipud(img)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), flipped)


def flip_all(
    src_dir: Path,
    dst_dir: Path,
    extensions: set[str],
    raw_width: int,
    raw_height: int,
    log: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> list[FlipResult]:
    files = scan_files(src_dir, extensions)
    results: list[FlipResult] = []
    total = len(files)

    for i, src in enumerate(files, start=1):
        dst = _dst_path(src, src_dir, dst_dir)
        ext = src.suffix.lower()
        try:
            if ext in RAW_EXTENSIONS:
                flip_raw(src, dst, raw_width, raw_height)
            else:
                flip_image(src, dst)
            results.append(FlipResult(src=src, dst=dst, success=True))
            if log:
                log(f"[OK] {src.name} → {dst}")
        except Exception as exc:
            results.append(FlipResult(src=src, dst=dst, success=False, error=str(exc)))
            if log:
                log(f"[ERROR] {src.name}: {exc}")
        if progress:
            progress(i, total)

    return results
