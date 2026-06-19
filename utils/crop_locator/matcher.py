"""원본 이미지 안에서 crop 이미지의 위치(x, y, w, h)를 찾는 핵심 로직.

알고리즘:
1. crop 이미지의 shape에서 w, h를 가져온다.
2. cv2.matchTemplate으로 score map을 구한다.
3. score가 가장 높은 지점을 고르고, 그 주변(템플릿 크기 기반 반경)을 억제(NMS)하는
   과정을 top-k번 반복해 서로 겹치지 않는 상위 후보를 뽑는다.
4. score가 높은 후보부터 순서대로 원본에서 동일 크기로 잘라 pixel-by-pixel로
   완전히 동일한지 검사한다. 완전히 동일한 첫 후보를 결과로 확정한다.
5. 모든 후보가 불일치하면 결과 없음으로 처리한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np


@dataclass
class Candidate:
    x: int
    y: int
    w: int
    h: int
    score: float
    pixel_match: Optional[bool] = None  # 검사 전이면 None


@dataclass
class MatchResult:
    crop_path: Path
    found: bool
    x: Optional[int] = None
    y: Optional[int] = None
    w: Optional[int] = None
    h: Optional[int] = None
    score: Optional[float] = None
    candidates: list[Candidate] = field(default_factory=list)


def load_image(path: Path, colorspace: str) -> np.ndarray:
    """colorspace: 'gray' 또는 'color'. color는 BGR, 알파채널은 무시."""
    flag = cv2.IMREAD_GRAYSCALE if colorspace == "gray" else cv2.IMREAD_COLOR
    img = cv2.imread(str(path), flag)
    if img is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {path}")
    return img


def find_top_candidates(
    original: np.ndarray, template: np.ndarray, topk: int, nms_dist: float
) -> list[Candidate]:
    h, w = template.shape[:2]
    result = cv2.matchTemplate(original, template, cv2.TM_CCOEFF_NORMED).astype(np.float64)

    candidates: list[Candidate] = []
    radius = max(1, int(round(nms_dist)))
    for _ in range(topk):
        y, x = np.unravel_index(np.argmax(result), result.shape)
        score = float(result[y, x])
        if not np.isfinite(score):
            break
        candidates.append(Candidate(x=int(x), y=int(y), w=w, h=h, score=score))

        y0, y1 = max(0, y - radius), min(result.shape[0], y + radius + 1)
        x0, x1 = max(0, x - radius), min(result.shape[1], x + radius + 1)
        result[y0:y1, x0:x1] = -np.inf
    return candidates


def pixel_match(original: np.ndarray, template: np.ndarray, x: int, y: int) -> bool:
    h, w = template.shape[:2]
    region = original[y : y + h, x : x + w]
    if region.shape != template.shape:
        return False
    return bool(np.array_equal(region, template))


def locate_crop(
    original: np.ndarray,
    template: np.ndarray,
    crop_path: Path,
    topk: int = 5,
    nms_dist: Optional[float] = None,
    log: Optional[Callable[[str], None]] = None,
) -> MatchResult:
    h, w = template.shape[:2]
    if nms_dist is None:
        nms_dist = max(1.0, min(w, h) / 2)

    candidates = find_top_candidates(original, template, topk, nms_dist)

    for rank, cand in enumerate(candidates, start=1):
        cand.pixel_match = pixel_match(original, template, cand.x, cand.y)
        if log:
            log(
                f"  [{rank}/{len(candidates)}] score={cand.score:.4f} "
                f"x={cand.x} y={cand.y} w={cand.w} h={cand.h} -> pixel_match={cand.pixel_match}"
            )
        if cand.pixel_match:
            return MatchResult(
                crop_path=crop_path,
                found=True,
                x=cand.x,
                y=cand.y,
                w=cand.w,
                h=cand.h,
                score=cand.score,
                candidates=candidates[:rank],
            )

    return MatchResult(crop_path=crop_path, found=False, candidates=candidates)
