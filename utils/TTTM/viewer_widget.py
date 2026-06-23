from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QMouseEvent, QPixmap, QWheelEvent
from PyQt5.QtWidgets import QLabel, QRubberBand, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

logger = logging.getLogger("app")

_MIN_ZOOM = 0.05
_MAX_ZOOM = 8.0
_SMOOTH_DELAY_MS = 180

# 블롭 색상 (RGB 순서, QImage.Format_RGB888 기준)
_COLOR_POS1_FILL      = (50,  100, 220)   # 파랑
_COLOR_POS1_BORDER    = (20,  80,  255)
_COLOR_POS1_LINE      = (0,   220, 220)   # 청록
_COLOR_POS4_FILL      = (30,  200,  60)   # 초록
_COLOR_POS4_BORDER    = (20,  230,  50)
_COLOR_POS4_LINE      = (40,  210,  70)   # 초록
_COLOR_HIGHLIGHT_FILL = (160,  90,  30)   # 갈색 (목록 선택 하이라이트)
_COLOR_HIGHLIGHT_BORD = (200, 120,  40)
_COLOR_UNSEL          = (160, 160, 160)   # 회색 (미선택)
_COLOR_ROI            = (0,   180, 255)   # 파란 하늘색


class ImageLabel(QLabel):
    mouse_pressed  = pyqtSignal(int, int, Qt.MouseButton)
    mouse_moved    = pyqtSignal(int, int)
    mouse_released = pyqtSignal(int, int, Qt.MouseButton)

    def mousePressEvent(self, e: QMouseEvent):
        self.mouse_pressed.emit(e.x(), e.y(), e.button())

    def mouseMoveEvent(self, e: QMouseEvent):
        self.mouse_moved.emit(e.x(), e.y())

    def mouseReleaseEvent(self, e: QMouseEvent):
        self.mouse_released.emit(e.x(), e.y(), e.button())


class ViewerWidget(QWidget):
    """
    이미지 뷰어.
    조작: 휠=줌, 우클릭드래그=팬, 좌클릭=ROI그리기/Blob선택

    성능:
      _overlay_pixmap 캐시 → 이미지·오버레이 변경 시만 재빌드
      휠: FastTransformation 즉시 / 정지 후 SmoothTransformation
    """

    roi_drawn     = pyqtSignal(int, int, int, int)
    clicked_point = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom   = 1.0
        self._np_image: Optional[np.ndarray] = None
        self._overlay_pixmap: Optional[QPixmap] = None
        self._overlays: List[dict] = []
        self._roi_mode = False
        self._rb_origin: Optional[QPoint] = None
        self._rubber_band: Optional[QRubberBand] = None
        self._pan_start: Optional[QPoint] = None
        self._pan_h: int = 0
        self._pan_v: int = 0

        self._smooth_timer = QTimer(self)
        self._smooth_timer.setSingleShot(True)
        self._smooth_timer.setInterval(_SMOOTH_DELAY_MS)
        self._smooth_timer.timeout.connect(self._apply_smooth)

        self._label = ImageLabel()
        self._label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._label.setMouseTracking(True)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._label)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setStyleSheet("background: #1e1e1e;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

        self._label.mouse_pressed.connect(self._on_press)
        self._label.mouse_moved.connect(self._on_move)
        self._label.mouse_released.connect(self._on_release)

    # ------------------------------------------------------------------
    # Public API — 개별 업데이트
    # ------------------------------------------------------------------

    def set_image(self, img: Optional[np.ndarray]):
        """단독 이미지 설정 (오버레이 초기화)."""
        self._np_image = img
        self._overlays = []
        self._rebuild_overlay_pixmap()
        self._apply_smooth()

    def update_display(self, image: np.ndarray, overlays: List[dict]):
        """이미지 + 오버레이 목록을 한 번에 업데이트 (rebuild 1회)."""
        self._np_image = image
        self._overlays = overlays
        self._rebuild_overlay_pixmap()
        self._apply_fast()
        self._smooth_timer.start()

    def set_roi_draw_mode(self, enabled: bool):
        self._roi_mode = enabled
        if not self._pan_start:
            self._label.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

    def zoom_in(self):
        self._set_zoom(min(self._zoom * 1.25, _MAX_ZOOM), smooth=True)

    def zoom_out(self):
        self._set_zoom(max(self._zoom / 1.25, _MIN_ZOOM), smooth=True)

    def zoom_fit(self):
        if self._overlay_pixmap is None:
            return
        sw = self._scroll.viewport().width()
        sh = self._scroll.viewport().height()
        pw, ph = self._overlay_pixmap.width(), self._overlay_pixmap.height()
        if pw == 0 or ph == 0:
            return
        self._set_zoom(min(sw / pw, sh / ph), smooth=True)

    def save_image(self, path: str) -> bool:
        if self._overlay_pixmap is None:
            logger.warning("save_image: 저장할 이미지 없음")
            return False
        ok = self._overlay_pixmap.save(path, "PNG")
        logger.info("이미지 저장 %s: %s", "OK" if ok else "FAIL", path)
        return ok

    # ------------------------------------------------------------------
    # 휠 줌
    # ------------------------------------------------------------------

    def wheelEvent(self, e: QWheelEvent):
        factor = 1.12 if e.angleDelta().y() > 0 else (1 / 1.12)
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        self._apply_fast()
        self._smooth_timer.start()
        e.accept()

    # ------------------------------------------------------------------
    # 마우스 (ROI / 팬 / 클릭)
    # ------------------------------------------------------------------

    def _on_press(self, lx: int, ly: int, btn: Qt.MouseButton):
        if btn == Qt.RightButton:
            self._pan_start = QPoint(lx, ly)
            self._pan_h = self._scroll.horizontalScrollBar().value()
            self._pan_v = self._scroll.verticalScrollBar().value()
            self._label.setCursor(Qt.ClosedHandCursor)
        elif btn == Qt.LeftButton:
            if self._roi_mode:
                self._rb_origin = QPoint(lx, ly)
                if self._rubber_band is None:
                    self._rubber_band = QRubberBand(QRubberBand.Rectangle, self._label)
                self._rubber_band.setGeometry(QRect(self._rb_origin, self._rb_origin))
                self._rubber_band.show()
            else:
                ix, iy = self._label_to_image(lx, ly)
                if ix >= 0 and iy >= 0:
                    self.clicked_point.emit(ix, iy)

    def _on_move(self, lx: int, ly: int):
        if self._pan_start is not None:
            delta = QPoint(lx, ly) - self._pan_start
            self._scroll.horizontalScrollBar().setValue(self._pan_h - delta.x())
            self._scroll.verticalScrollBar().setValue(self._pan_v - delta.y())
        elif self._roi_mode and self._rb_origin is not None and self._rubber_band:
            self._rubber_band.setGeometry(QRect(self._rb_origin, QPoint(lx, ly)).normalized())

    def _on_release(self, lx: int, ly: int, btn: Qt.MouseButton):
        if btn == Qt.RightButton and self._pan_start is not None:
            self._pan_start = None
            self._label.setCursor(Qt.CrossCursor if self._roi_mode else Qt.ArrowCursor)
        elif btn == Qt.LeftButton and self._roi_mode and self._rb_origin is not None:
            if self._rubber_band:
                self._rubber_band.hide()
            rect = QRect(self._rb_origin, QPoint(lx, ly)).normalized()
            x, y = self._label_to_image(rect.x(), rect.y())
            w = int(rect.width()  / self._zoom)
            h = int(rect.height() / self._zoom)
            if w > 0 and h > 0:
                self.roi_drawn.emit(x, y, w, h)
            self._rb_origin = None

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _label_to_image(self, lx: int, ly: int) -> Tuple[int, int]:
        return int(lx / self._zoom), int(ly / self._zoom)

    def _set_zoom(self, z: float, smooth: bool = False):
        self._zoom = z
        if smooth:
            self._apply_smooth()
        else:
            self._apply_fast()
            self._smooth_timer.start()

    def _rebuild_overlay_pixmap(self):
        """이미지 + 오버레이 합성 → _overlay_pixmap 캐시. 줌 변경 시 호출 안 함."""
        if self._np_image is None:
            self._overlay_pixmap = None
            self._label.clear()
            return

        img = self._np_image
        img_rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB) if img.ndim == 2 else img.copy()

        for ov in self._overlays:
            ov_type = ov["type"]

            if ov_type == "roi":
                x, y, w, h = ov["rect"]
                cv2.rectangle(img_rgb, (x, y), (x + w, y + h), _COLOR_ROI, 3)

            elif ov_type == "contours":
                pos1_idx  = ov.get("pos1",      -1)
                pos4_idx  = ov.get("pos4",      -1)
                hi_idx    = ov.get("highlight", -1)
                for i, cnt in enumerate(ov["contours"]):
                    if i == pos1_idx:
                        _draw_filled_contour(img_rgb, cnt, _COLOR_POS1_FILL, _COLOR_POS1_BORDER)
                    elif i == pos4_idx:
                        _draw_filled_contour(img_rgb, cnt, _COLOR_POS4_FILL, _COLOR_POS4_BORDER)
                    elif i == hi_idx:
                        _draw_filled_contour(img_rgb, cnt, _COLOR_HIGHLIGHT_FILL, _COLOR_HIGHLIGHT_BORD)
                    else:
                        cv2.drawContours(img_rgb, [cnt], -1, _COLOR_UNSEL, 2)

            elif ov_type == "measurements":
                ih, iw = img_rgb.shape[:2]
                for pos_name, analysis in ov["data"]:
                    color  = _COLOR_POS1_LINE if pos_name == "pos1" else _COLOR_POS4_LINE
                    y_ref  = analysis.y_at_offset
                    edge_x = analysis.edge_x   # 실제 blob edge x 좌표
                    ref_x  = analysis.ref_x    # 거리값 (표시용 숫자)
                    bar_y  = y_ref

                    # ① 얇은 전폭 Y 수평선 (Y 위치 표시)
                    cv2.line(img_rgb, (0, y_ref), (iw - 1, y_ref), color, 1)

                    if pos_name == "pos1":
                        # pos1: 거리 바 x=0 → edge_x (좌벽 ~ blob 좌측)
                        cv2.line(img_rgb, (0, bar_y), (edge_x, bar_y), color, 5)
                        cv2.line(img_rgb, (0, bar_y - 18), (0, bar_y + 18), color, 4)
                        cv2.line(img_rgb, (edge_x, bar_y - 18), (edge_x, bar_y + 18), color, 4)
                    else:
                        # pos4: 거리 바 edge_x → x=iw-1 (blob 우측 ~ 우벽)
                        cv2.line(img_rgb, (edge_x, bar_y), (iw - 1, bar_y), color, 5)
                        cv2.line(img_rgb, (edge_x, bar_y - 18), (edge_x, bar_y + 18), color, 4)
                        cv2.line(img_rgb, (iw - 1, bar_y - 18), (iw - 1, bar_y + 18), color, 4)

                    # ③ 수직 기준선 (blob edge x 위치)
                    cv2.line(img_rgb, (edge_x, 0), (edge_x, ih - 1), color, 1)

                    # ④ 교차점 원
                    cv2.circle(img_rgb, (edge_x, y_ref), 12, color, 2)

                    # ⑤ 라벨
                    label = f"{pos_name.upper()}  y={y_ref}  x_dist={ref_x}"
                    if pos_name == "pos1":
                        tx = min(edge_x + 16, iw - 360)
                    else:
                        tx = max(edge_x - 460, 4)
                    ty = max(y_ref - 18, 30)
                    cv2.putText(img_rgb, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 5)
                    cv2.putText(img_rgb, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)

        img_rgb = np.ascontiguousarray(img_rgb)
        h, w = img_rgb.shape[:2]
        qimg = QImage(img_rgb.data, w, h, w * 3, QImage.Format_RGB888)
        self._overlay_pixmap = QPixmap.fromImage(qimg)

    def _apply_fast(self):
        if self._overlay_pixmap is None:
            self._label.clear()
            return
        pw, ph = self._overlay_pixmap.width(), self._overlay_pixmap.height()
        scaled = self._overlay_pixmap.scaled(
            max(1, int(pw * self._zoom)), max(1, int(ph * self._zoom)),
            Qt.KeepAspectRatio, Qt.FastTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())

    def _apply_smooth(self):
        if self._overlay_pixmap is None:
            self._label.clear()
            return
        pw, ph = self._overlay_pixmap.width(), self._overlay_pixmap.height()
        scaled = self._overlay_pixmap.scaled(
            max(1, int(pw * self._zoom)), max(1, int(ph * self._zoom)),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------

def _draw_filled_contour(img_rgb: np.ndarray, cnt: np.ndarray,
                          fill_color: tuple, border_color: tuple):
    """bounding rect 범위만 처리하여 반투명 채우기 + 테두리."""
    bx, by, bw, bh = cv2.boundingRect(cnt)
    bx0 = max(0, bx); by0 = max(0, by)
    bx1 = min(img_rgb.shape[1], bx + bw)
    by1 = min(img_rgb.shape[0], by + bh)

    mask_tmp = np.zeros(img_rgb.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask_tmp, [cnt], -1, 255, thickness=cv2.FILLED)

    roi_orig = img_rgb[by0:by1, bx0:bx1]
    roi_col  = roi_orig.copy()
    roi_col[mask_tmp[by0:by1, bx0:bx1] > 0] = fill_color
    img_rgb[by0:by1, bx0:bx1] = cv2.addWeighted(roi_col, 0.4, roi_orig, 0.6, 0)
    cv2.drawContours(img_rgb, [cnt], -1, border_color, 3)
