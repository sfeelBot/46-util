from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox,
)

from image_processor import BlobAnalysis, make_overlay
from viewer_widget import ViewerWidget

logger = logging.getLogger("app")

# 측정선 색상 (RGB) ― overlay 위에 겹쳐 그릴 때 구분이 잘 되는 색
_C_IMG1_POS1 = (0,   220, 220)   # 청록  — Image1 pos1
_C_IMG1_POS4 = (80,  230, 100)   # 연초록 — Image1 pos4
_C_IMG2_POS1 = (255, 240,  70)   # 노랑  — Image2 pos1
_C_IMG2_POS4 = (255, 130,  50)   # 주황  — Image2 pos4


class OverlayDialog(QDialog):
    """
    pos1+pos4 통합 마스크 비교 + 양쪽 이미지 측정선 표시.
    탭 없이 단일 뷰어로 표시.
    """

    def __init__(
        self,
        mask1_pos1: Optional[np.ndarray],
        mask2_pos1: Optional[np.ndarray],
        bg1: Optional[np.ndarray] = None,
        bg2: Optional[np.ndarray] = None,
        mask1_pos4: Optional[np.ndarray] = None,
        mask2_pos4: Optional[np.ndarray] = None,
        analyses_img1: Optional[List[Tuple[str, BlobAnalysis]]] = None,
        analyses_img2: Optional[List[Tuple[str, BlobAnalysis]]] = None,
        save_dir: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("마스크 오버레이 비교")
        self.resize(960, 780)
        self._save_dir = save_dir

        # ── 마스크 합산 (pos1 OR pos4) ──────────────────────────────
        mask1 = _combine(mask1_pos1, mask1_pos4)
        mask2 = _combine(mask2_pos1, mask2_pos4)

        # ── 배경 ────────────────────────────────────────────────────
        bg = _avg_bg(bg1, bg2)

        # ── 오버레이 이미지 생성 ─────────────────────────────────────
        overlay_rgb = make_overlay(mask1, mask2, bg)

        # ── 측정선 그리기 ───────────────────────────────────────────
        iw = overlay_rgb.shape[1]
        for pos_name, analysis in (analyses_img1 or []):
            c = _C_IMG1_POS1 if pos_name == "pos1" else _C_IMG1_POS4
            _draw_measurement(overlay_rgb, analysis, c, "Img1-")

        for pos_name, analysis in (analyses_img2 or []):
            c = _C_IMG2_POS1 if pos_name == "pos1" else _C_IMG2_POS4
            _draw_measurement(overlay_rgb, analysis, c, "Img2-")

        logger.info("OverlayDialog 생성: %s", overlay_rgb.shape)

        # ── UI ──────────────────────────────────────────────────────
        layout = QVBoxLayout(self)

        # 범례
        legend_row = QHBoxLayout()
        for color_hex, text in [
            ("#00c800", "Image1 단독 (녹)"),
            ("#c80000", "Image2 단독 (적)"),
            ("#dcdc00", "겹침 (황)"),
            ("#00dcdc", "Img1 pos1 측정선"),
            ("#50e664", "Img1 pos4 측정선"),
            ("#fff046", "Img2 pos1 측정선"),
            ("#ff8232", "Img2 pos4 측정선"),
        ]:
            lbl = QLabel(
                f"<span style='background:{color_hex}; color:black; padding:1px 6px;'>"
                f"&nbsp;</span>&nbsp;{text}&nbsp;&nbsp;"
            )
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        # 뷰어
        self._viewer = ViewerWidget()
        self._viewer.set_image(overlay_rgb)
        layout.addWidget(self._viewer)

        # 버튼
        btn_row = QHBoxLayout()
        btn_fit   = QPushButton("Fit")
        btn_fit.clicked.connect(self._viewer.zoom_fit)
        btn_save  = QPushButton("저장 PNG")
        btn_save.clicked.connect(self._save)
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_fit)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _save(self):
        default = (self._save_dir + "/overlay.png") if self._save_dir else "overlay.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "오버레이 저장", default, "PNG (*.png);;All Files (*)"
        )
        if not path:
            return
        if self._viewer.save_image(path):
            QMessageBox.information(self, "저장 완료", f"저장됨:\n{path}")
        else:
            QMessageBox.warning(self, "저장 실패", "이미지 저장에 실패했습니다.")


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------

def _combine(m1: Optional[np.ndarray], m2: Optional[np.ndarray]) -> np.ndarray:
    """두 마스크를 OR 합산. 둘 다 None이면 빈 배열 반환."""
    if m1 is not None and m2 is not None:
        return np.maximum(m1, m2)
    if m1 is not None:
        return m1.copy()
    if m2 is not None:
        return m2.copy()
    return np.zeros((1, 1), dtype=np.uint8)


def _avg_bg(bg1: Optional[np.ndarray], bg2: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if bg1 is not None and bg2 is not None:
        return ((bg1.astype(np.uint16) + bg2.astype(np.uint16)) // 2).astype(np.uint8)
    return bg1 if bg1 is not None else bg2


def _draw_measurement(img_rgb: np.ndarray, analysis: BlobAnalysis,
                      color: tuple, label_prefix: str):
    """오버레이 이미지에 측정선 + 라벨 그리기."""
    ih, iw = img_rgb.shape[:2]
    y_ref  = analysis.y_at_offset
    edge_x = analysis.edge_x
    ref_x  = analysis.ref_x
    bar_y  = y_ref

    # Y 수평 가이드선 (전폭, 얇게)
    cv2.line(img_rgb, (0, y_ref), (iw - 1, y_ref), color, 1)

    if analysis.pos_type == "pos1":
        # X 거리 바: 좌벽(0) → blob 좌측 edge
        cv2.line(img_rgb, (0, bar_y), (edge_x, bar_y), color, 4)
        cv2.line(img_rgb, (0,      bar_y - 14), (0,      bar_y + 14), color, 3)
        cv2.line(img_rgb, (edge_x, bar_y - 14), (edge_x, bar_y + 14), color, 3)
        tx = min(edge_x + 12, iw - 400)
    else:
        # X 거리 바: blob 우측 edge → 우벽(iw-1)
        cv2.line(img_rgb, (edge_x, bar_y), (iw - 1, bar_y), color, 4)
        cv2.line(img_rgb, (edge_x, bar_y - 14), (edge_x, bar_y + 14), color, 3)
        cv2.line(img_rgb, (iw - 1, bar_y - 14), (iw - 1, bar_y + 14), color, 3)
        tx = max(edge_x - 480, 4)

    # edge 수직선
    cv2.line(img_rgb, (edge_x, 0), (edge_x, ih - 1), color, 1)

    # 교차점 원
    cv2.circle(img_rgb, (edge_x, y_ref), 10, color, 2)

    # 라벨
    label = f"{label_prefix}{analysis.pos_type.upper()} y={y_ref} x={ref_x}"
    ty = max(y_ref - 12, 28)
    cv2.putText(img_rgb, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
    cv2.putText(img_rgb, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
