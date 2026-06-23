from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from image_processor import (
    BlobAnalysis,
    BlobInfo,
    analyze,
    apply_roi,
    apply_threshold,
    find_blobs,
    normalize_8bit,
    read_raw,
)
from viewer_widget import ViewerWidget

logger = logging.getLogger("app")

_DISPLAY_MODES = ["Original", "Threshold", "ROI", "Mask"]


def _make_thresh_overlay(img16: np.ndarray, binary: np.ndarray) -> np.ndarray:
    gray8 = (img16 >> 8).astype(np.uint8)
    rgb = np.stack([gray8, gray8, gray8], axis=2)
    if binary is not None:
        rgb[binary > 0] = (220, 50, 50)
    return np.ascontiguousarray(rgb)


class ImagePanel(QGroupBox):
    """
    단일 이미지 패널. 이미지당 pos1(좌측), pos4(우측) blob 2개 선택.

    Signals:
        analysis_ready(BlobAnalysis, BlobAnalysis)
            pos1 분석, pos4 분석 (둘 다 선택된 경우에만 emit)
    """

    analysis_ready = pyqtSignal(object, object)   # (pos1: BlobAnalysis, pos4: BlobAnalysis)

    def __init__(self, title: str, img_width: int = 3072, img_height: int = 3072, parent=None):
        super().__init__(title, parent)
        self._img_w = img_width
        self._img_h = img_height

        self._img16: Optional[np.ndarray] = None
        self._binary: Optional[np.ndarray] = None
        self._roi_binary: Optional[np.ndarray] = None
        self._blobs: List[BlobInfo] = []

        self._pos1_blob: Optional[BlobInfo] = None   # 좌측 blob
        self._pos4_blob: Optional[BlobInfo] = None   # 우측 blob
        self._pos1_analysis: Optional[BlobAnalysis] = None
        self._pos4_analysis: Optional[BlobAnalysis] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(3)
        root.setContentsMargins(4, 6, 4, 4)

        # ── 파일 열기 ────────────────────────────────────────────────
        file_row = QHBoxLayout()
        file_row.setSpacing(4)
        btn_open = QPushButton("파일 열기")
        btn_open.setFixedHeight(26)
        btn_open.clicked.connect(self._on_open)
        self._lbl_file = QLabel("파일 없음")
        self._lbl_file.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        file_row.addWidget(btn_open)
        file_row.addWidget(self._lbl_file)
        root.addLayout(file_row)

        # ── 이미지 뷰어 ─────────────────────────────────────────────
        self._viewer = ViewerWidget()
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._viewer.roi_drawn.connect(self._on_roi_drawn)
        self._viewer.clicked_point.connect(self._on_image_click)
        root.addWidget(self._viewer, stretch=1)

        # ── 표시 모드 + Fit ─────────────────────────────────────────
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        mode_row.addWidget(QLabel("표시:"))
        self._combo_mode = QComboBox()
        self._combo_mode.addItems(_DISPLAY_MODES)
        self._combo_mode.currentIndexChanged.connect(self._refresh_viewer)
        self._combo_mode.setFixedHeight(24)
        mode_row.addWidget(self._combo_mode)
        btn_fit = QPushButton("Fit")
        btn_fit.setFixedSize(36, 24)
        btn_fit.clicked.connect(self._viewer.zoom_fit)
        btn_zin = QPushButton("+")
        btn_zin.setFixedSize(24, 24)
        btn_zin.clicked.connect(self._viewer.zoom_in)
        btn_zout = QPushButton("−")
        btn_zout.setFixedSize(24, 24)
        btn_zout.clicked.connect(self._viewer.zoom_out)
        mode_row.addWidget(btn_zout)
        mode_row.addWidget(btn_fit)
        mode_row.addWidget(btn_zin)
        mode_row.addStretch()
        root.addLayout(mode_row)

        root.addWidget(_hline())

        # ── Threshold ────────────────────────────────────────────────
        thr_row = QHBoxLayout()
        thr_row.setSpacing(4)
        thr_row.addWidget(QLabel("Thresh:"))
        self._sld_thresh = QSlider(Qt.Horizontal)
        self._sld_thresh.setRange(0, 65535)
        self._sld_thresh.setValue(32768)
        self._sld_thresh.valueChanged.connect(self._on_thresh_changed)
        self._lbl_thresh_val = QLabel("32768")
        self._lbl_thresh_val.setFixedWidth(46)
        self._chk_invert = QCheckBox("Inv")
        self._chk_invert.stateChanged.connect(self._on_thresh_changed)
        thr_row.addWidget(self._sld_thresh)
        thr_row.addWidget(self._lbl_thresh_val)
        thr_row.addWidget(self._chk_invert)
        root.addLayout(thr_row)

        # ── ROI ──────────────────────────────────────────────────────
        roi_row = QHBoxLayout()
        roi_row.setSpacing(3)
        for lbl, attr in [("X", "_sp_roi_x"), ("Y", "_sp_roi_y"), ("W", "_sp_roi_w"), ("H", "_sp_roi_h")]:
            roi_row.addWidget(QLabel(lbl + ":"))
            sp = QSpinBox()
            sp.setRange(0, 9999)
            sp.setValue(0)
            sp.setFixedWidth(58)
            sp.setFixedHeight(24)
            sp.valueChanged.connect(self._on_roi_spinbox_changed)
            setattr(self, attr, sp)
            roi_row.addWidget(sp)
        self._btn_draw_roi = QPushButton("ROI 그리기")
        self._btn_draw_roi.setCheckable(True)
        self._btn_draw_roi.setFixedHeight(24)
        self._btn_draw_roi.toggled.connect(self._viewer.set_roi_draw_mode)
        roi_row.addWidget(self._btn_draw_roi)
        root.addLayout(roi_row)

        # ── Blob 탐색 ────────────────────────────────────────────────
        blob_row = QHBoxLayout()
        blob_row.setSpacing(4)
        blob_row.addWidget(QLabel("최소면적:"))
        self._sp_min_area = QSpinBox()
        self._sp_min_area.setRange(1, 999999)
        self._sp_min_area.setValue(500)
        self._sp_min_area.setFixedHeight(24)
        blob_row.addWidget(self._sp_min_area)
        btn_find = QPushButton("Blob 탐색")
        btn_find.setFixedHeight(24)
        btn_find.clicked.connect(self._on_find_blobs)
        blob_row.addWidget(btn_find)
        blob_row.addStretch()
        root.addLayout(blob_row)

        # ── Blob 목록 ────────────────────────────────────────────────
        self._blob_list = QListWidget()
        self._blob_list.setMaximumHeight(80)
        self._blob_list.setMinimumHeight(50)
        self._blob_list.currentRowChanged.connect(self._refresh_viewer)
        root.addWidget(self._blob_list)

        root.addWidget(_hline())

        # ── pos1 / pos4 지정 행 ─────────────────────────────────────
        assign_row = QHBoxLayout()
        assign_row.setSpacing(4)

        self._btn_assign_pos1 = QPushButton("← pos1 지정")
        self._btn_assign_pos1.setFixedHeight(26)
        self._btn_assign_pos1.setStyleSheet("background-color: #2255bb; color: white;")
        self._btn_assign_pos1.clicked.connect(self._on_assign_pos1)
        assign_row.addWidget(self._btn_assign_pos1)

        self._btn_assign_pos4 = QPushButton("pos4 지정 →")
        self._btn_assign_pos4.setFixedHeight(26)
        self._btn_assign_pos4.setStyleSheet("background-color: #cc7700; color: white;")
        self._btn_assign_pos4.clicked.connect(self._on_assign_pos4)
        assign_row.addWidget(self._btn_assign_pos4)

        root.addLayout(assign_row)

        # ── pos1 / pos4 상태 표시 ────────────────────────────────────
        status_row = QHBoxLayout()
        self._lbl_pos1_status = QLabel("pos1: 미지정")
        self._lbl_pos1_status.setStyleSheet("color: #4488ff;")
        self._lbl_pos4_status = QLabel("pos4: 미지정")
        self._lbl_pos4_status.setStyleSheet("color: #ff9900;")
        status_row.addWidget(self._lbl_pos1_status)
        status_row.addStretch()
        status_row.addWidget(self._lbl_pos4_status)
        root.addLayout(status_row)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_image_size(self, w: int, h: int):
        self._img_w = w
        self._img_h = h

    def get_pos1_analysis(self) -> Optional[BlobAnalysis]:
        return self._pos1_analysis

    def get_pos4_analysis(self) -> Optional[BlobAnalysis]:
        return self._pos4_analysis

    def get_pos1_mask(self) -> Optional[np.ndarray]:
        return self._pos1_blob.mask if self._pos1_blob else None

    def get_pos4_mask(self) -> Optional[np.ndarray]:
        return self._pos4_blob.mask if self._pos4_blob else None

    def get_normalized_image(self) -> Optional[np.ndarray]:
        return normalize_8bit(self._img16) if self._img16 is not None else None

    def run_analysis(self, offset_px: int):
        """두 blob 모두 분석 후 시그널 emit. 하나라도 없으면 중단."""
        if self._pos1_blob is None or self._pos4_blob is None:
            return
        try:
            self._pos1_analysis = analyze(self._pos1_blob, offset_px, "pos1", self._img_w)
            self._pos4_analysis = analyze(self._pos4_blob, offset_px, "pos4", self._img_w)
            self.analysis_ready.emit(self._pos1_analysis, self._pos4_analysis)
            self._refresh_viewer()
            logger.info(
                "분석 완료: pos1(y=%d x=%d area=%d) pos4(y=%d x=%d area=%d)",
                self._pos1_analysis.y_at_offset, self._pos1_analysis.ref_x, self._pos1_analysis.area,
                self._pos4_analysis.y_at_offset, self._pos4_analysis.ref_x, self._pos4_analysis.area,
            )
        except Exception as e:
            logger.error("분석 오류: %s", e, exc_info=True)
            QMessageBox.critical(self, "오류", f"분석 실패:\n{e}")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "RAW 파일 열기", "", "RAW Files (*.raw);;All Files (*)"
        )
        if not path:
            return
        try:
            self._img16 = read_raw(path, self._img_w, self._img_h)
            self._binary = None
            self._roi_binary = None
            self._blobs = []
            self._pos1_blob = None
            self._pos4_blob = None
            self._pos1_analysis = None
            self._pos4_analysis = None
            self._blob_list.clear()
            self._lbl_pos1_status.setText("pos1: 미지정")
            self._lbl_pos4_status.setText("pos4: 미지정")
            short_name = path.replace("\\", "/").split("/")[-1]
            self._lbl_file.setText(short_name)
            logger.info("파일 로드: %s", path)
            self._on_thresh_changed()
            QTimer.singleShot(80, self._viewer.zoom_fit)
        except Exception as e:
            logger.error("파일 로드 실패: %s", e, exc_info=True)
            QMessageBox.critical(self, "오류", f"파일 로드 실패:\n{e}")

    def _on_thresh_changed(self):
        if self._img16 is None:
            return
        thresh = self._sld_thresh.value()
        invert = self._chk_invert.isChecked()
        self._lbl_thresh_val.setText(str(thresh))
        try:
            self._binary = apply_threshold(self._img16, thresh, invert)
            self._apply_roi_to_binary()
            self._refresh_viewer()
        except Exception as e:
            logger.error("threshold 처리 오류: %s", e, exc_info=True)

    def _on_roi_spinbox_changed(self):
        self._apply_roi_to_binary()
        self._refresh_viewer()

    def _on_roi_drawn(self, x: int, y: int, w: int, h: int):
        self._sp_roi_x.setValue(x)
        self._sp_roi_y.setValue(y)
        self._sp_roi_w.setValue(w)
        self._sp_roi_h.setValue(h)
        self._btn_draw_roi.setChecked(False)

    def _apply_roi_to_binary(self):
        if self._binary is None:
            return
        x = self._sp_roi_x.value()
        y = self._sp_roi_y.value()
        w = self._sp_roi_w.value()
        h = self._sp_roi_h.value()
        self._roi_binary = apply_roi(self._binary, x, y, w, h) if (w > 0 and h > 0) else self._binary.copy()

    def _on_find_blobs(self):
        src = self._roi_binary if self._roi_binary is not None else self._binary
        if src is None:
            QMessageBox.warning(self, "경고", "이미지를 먼저 로드하세요.")
            return
        try:
            self._blobs = find_blobs(src, float(self._sp_min_area.value()))
            self._blob_list.clear()
            for b in self._blobs:
                x, y, bw, bh = b.bbox
                self._blob_list.addItem(
                    QListWidgetItem(f"Blob {b.index}: 면적={b.area:.0f}  bbox=({x},{y},{bw},{bh})")
                )
            logger.info("blob 탐색 완료: %d개", len(self._blobs))
            self._refresh_viewer()
        except Exception as e:
            logger.error("blob 탐색 오류: %s", e, exc_info=True)
            QMessageBox.critical(self, "오류", f"Blob 탐색 실패:\n{e}")

    def _on_image_click(self, ix: int, iy: int):
        for i, b in enumerate(self._blobs):
            if b.mask[iy, ix] > 0:
                self._blob_list.setCurrentRow(i)
                return

    def _on_assign_pos1(self):
        row = self._blob_list.currentRow()
        if row < 0 or row >= len(self._blobs):
            QMessageBox.warning(self, "경고", "Blob 목록에서 blob을 먼저 선택하세요.")
            return
        self._pos1_blob = self._blobs[row]
        b = self._pos1_blob
        self._lbl_pos1_status.setText(
            f"pos1: Blob{b.index} 면적={b.area:.0f} bbox=({b.bbox[0]},{b.bbox[1]})"
        )
        logger.info("pos1 지정: index=%d area=%.0f", b.index, b.area)
        self._pos1_analysis = None
        self._refresh_viewer()

    def _on_assign_pos4(self):
        row = self._blob_list.currentRow()
        if row < 0 or row >= len(self._blobs):
            QMessageBox.warning(self, "경고", "Blob 목록에서 blob을 먼저 선택하세요.")
            return
        self._pos4_blob = self._blobs[row]
        b = self._pos4_blob
        self._lbl_pos4_status.setText(
            f"pos4: Blob{b.index} 면적={b.area:.0f} bbox=({b.bbox[0]},{b.bbox[1]})"
        )
        logger.info("pos4 지정: index=%d area=%.0f", b.index, b.area)
        self._pos4_analysis = None
        self._refresh_viewer()

    # ------------------------------------------------------------------
    # Viewer refresh
    # ------------------------------------------------------------------

    def _refresh_viewer(self):
        mode = self._combo_mode.currentText()

        # 베이스 이미지 결정
        if mode == "Original":
            base = normalize_8bit(self._img16) if self._img16 is not None else None
        elif mode == "Threshold":
            if self._img16 is not None and self._binary is not None:
                base = _make_thresh_overlay(self._img16, self._binary)
            elif self._img16 is not None:
                base = normalize_8bit(self._img16)
            else:
                base = None
        elif mode == "ROI":
            src = self._roi_binary if self._roi_binary is not None else self._binary
            base = src if src is not None else None
        else:   # Mask
            if self._pos1_blob is not None:
                # pos1 + pos4 마스크 합성
                base = self._pos1_blob.mask.copy()
                if self._pos4_blob is not None:
                    base = np.maximum(base, self._pos4_blob.mask)
            elif self._roi_binary is not None:
                base = self._roi_binary
            else:
                base = None

        if base is None:
            return

        # 오버레이 목록 구성
        overlays = []

        # ROI 사각형
        x = self._sp_roi_x.value()
        y = self._sp_roi_y.value()
        w = self._sp_roi_w.value()
        h = self._sp_roi_h.value()
        if w > 0 and h > 0:
            overlays.append({"type": "roi", "rect": (x, y, w, h)})

        # Blob 컨투어 (pos1, pos4, 현재 선택 하이라이트 인덱스 전달)
        if self._blobs:
            pos1_idx = self._pos1_blob.index if self._pos1_blob else -1
            pos4_idx = self._pos4_blob.index if self._pos4_blob else -1
            hi_row   = self._blob_list.currentRow()
            # 이미 pos1/pos4로 지정된 blob은 갈색 하이라이트 제외
            hi_idx   = hi_row if hi_row >= 0 and hi_row not in (pos1_idx, pos4_idx) else -1
            contours = [b.contour for b in self._blobs]
            overlays.append({
                "type": "contours",
                "contours": contours,
                "pos1": pos1_idx,
                "pos4": pos4_idx,
                "highlight": hi_idx,
            })

        # 측정 결과선 (분석 완료된 경우)
        meas_data = []
        if self._pos1_analysis is not None:
            meas_data.append(("pos1", self._pos1_analysis))
        if self._pos4_analysis is not None:
            meas_data.append(("pos4", self._pos4_analysis))
        if meas_data:
            overlays.append({"type": "measurements", "data": meas_data})

        self._viewer.update_display(base, overlays)


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setFixedHeight(2)
    return line
