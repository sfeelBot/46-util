from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("app")


# ---------------------------------------------------------------------------
# Image I/O
# ---------------------------------------------------------------------------

def read_raw(path: str, width: int = 3072, height: int = 3072) -> np.ndarray:
    """16-bit little-endian 단채널 RAW 파일을 numpy 배열로 읽기."""
    logger.debug("read_raw: %s  (%dx%d)", path, width, height)
    data = np.fromfile(path, dtype="<u2")
    expected = width * height
    if data.size != expected:
        raise ValueError(
            f"픽셀 수 불일치: 파일={data.size}, 예상={expected} ({width}x{height})"
        )
    return data.reshape(height, width)


def normalize_8bit(img16: np.ndarray) -> np.ndarray:
    """uint16 → uint8 (표시용, 선형 스케일)."""
    return (img16 >> 8).astype(np.uint8)


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def apply_threshold(img16: np.ndarray, thresh: int, invert: bool = False) -> np.ndarray:
    """thresh 미만 픽셀을 전경(255)으로 이진화. invert=True이면 반전."""
    if invert:
        binary = np.where(img16 > thresh, np.uint8(255), np.uint8(0)).astype(np.uint8)
    else:
        binary = np.where(img16 < thresh, np.uint8(255), np.uint8(0)).astype(np.uint8)
    logger.debug("apply_threshold: thresh=%d invert=%s nonzero=%d", thresh, invert, np.count_nonzero(binary))
    return binary


def apply_roi(binary: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """ROI 영역 밖을 0으로 마스킹한 복사본 반환."""
    if w <= 0 or h <= 0:
        return binary.copy()
    out = np.zeros_like(binary)
    img_h, img_w = binary.shape[:2]
    x1 = max(0, x); y1 = max(0, y)
    x2 = min(img_w, x + w); y2 = min(img_h, y + h)
    out[y1:y2, x1:x2] = binary[y1:y2, x1:x2]
    return out


# ---------------------------------------------------------------------------
# Blob detection
# ---------------------------------------------------------------------------

@dataclass
class BlobInfo:
    index: int
    contour: np.ndarray
    area: float
    bbox: Tuple[int, int, int, int]   # x, y, w, h
    mask: np.ndarray                  # uint8


def find_blobs(binary: np.ndarray, min_area: float = 100.0) -> List[BlobInfo]:
    """이진 이미지에서 외부 컨투어 검출 후 면적 내림차순 정렬."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs: List[BlobInfo] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        mask = extract_mask(binary.shape, cnt)
        blobs.append(BlobInfo(index=0, contour=cnt, area=area, bbox=(x, y, w, h), mask=mask))

    blobs.sort(key=lambda b: b.area, reverse=True)
    for i, b in enumerate(blobs):
        b.index = i

    logger.debug("find_blobs: 검출 %d개 (min_area=%.0f)", len(blobs), min_area)
    return blobs


def extract_mask(shape: Tuple[int, ...], contour: np.ndarray) -> np.ndarray:
    mask = np.zeros(shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)
    return mask


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@dataclass
class BlobAnalysis:
    y_at_offset: int   # blob 상단 y + offset_px
    ref_x: int         # 거리값: pos1=xs.min() (좌벽~좌edge), pos4=img_width-xs.max() (우edge~우벽)
    edge_x: int        # 실제 blob edge x좌표: pos1=xs.min(), pos4=xs.max() (뷰어 표시용)
    area: int          # 마스크 픽셀 수
    offset_px: int     # 사용된 offset (참고용)
    pos_type: str      # "pos1" 또는 "pos4"
    img_width: int     # 이미지 너비 (pos4 거리 계산 기준)


def analyze(blob: BlobInfo, offset_px: int, pos_type: str = "pos1",
            img_width: int = 3072) -> BlobAnalysis:
    """
    선택된 blob에서 분석값 계산.

    pos1: ref_x = xs.min()              (x=0 좌벽 ~ blob 좌측 edge 거리)
    pos4: ref_x = img_width - xs.max()  (blob 우측 edge ~ 이미지 우벽 거리)
    """
    x, y, w, h = blob.bbox
    y_at_offset = y + offset_px

    ys, xs = np.where(blob.mask > 0)
    if len(xs) == 0:
        if pos_type == "pos1":
            edge_x, ref_x = x, x
        else:
            edge_x = x + w
            ref_x = img_width - edge_x
        area = 0
    else:
        if pos_type == "pos1":
            edge_x = int(xs.min())
            ref_x  = edge_x
        else:
            edge_x = int(xs.max())
            ref_x  = img_width - edge_x
        area = int(len(xs))

    result = BlobAnalysis(
        y_at_offset=y_at_offset,
        ref_x=ref_x,
        edge_x=edge_x,
        area=area,
        offset_px=offset_px,
        pos_type=pos_type,
        img_width=img_width,
    )
    logger.debug("analyze[%s]: y_at_offset=%d edge_x=%d ref_x=%d area=%d",
                 pos_type, y_at_offset, edge_x, ref_x, area)
    return result


def compute_diff_pair(a1: BlobAnalysis, a2: BlobAnalysis) -> dict:
    """같은 pos_type 두 분석 결과의 차이 계산 (Image2 - Image1)."""
    return {
        "y_at_offset": (a1.y_at_offset, a2.y_at_offset, a2.y_at_offset - a1.y_at_offset),
        "ref_x":       (a1.ref_x,       a2.ref_x,       a2.ref_x - a1.ref_x),
        "area":        (a1.area,         a2.area,         a2.area - a1.area),
    }


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

def make_overlay(mask1: np.ndarray, mask2: np.ndarray, bg: Optional[np.ndarray] = None) -> np.ndarray:
    """mask1(녹색), mask2(빨강), 겹침(노랑) RGB 이미지 반환."""
    h, w = mask1.shape[:2]
    if bg is not None:
        rgb = cv2.cvtColor(bg, cv2.COLOR_GRAY2RGB).copy()
    else:
        rgb = np.full((h, w, 3), 200, dtype=np.uint8)

    m1 = mask1 > 0; m2 = mask2 > 0
    overlap = m1 & m2
    rgb[m1 & ~overlap] = (0, 200, 0)
    rgb[m2 & ~overlap] = (200, 0, 0)
    rgb[overlap]        = (220, 220, 0)

    logger.debug("make_overlay: only1=%d only2=%d overlap=%d", (m1 & ~overlap).sum(), (m2 & ~overlap).sum(), overlap.sum())
    return rgb
