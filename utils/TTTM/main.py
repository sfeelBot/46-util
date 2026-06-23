from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QPlainTextEdit,
    QDialog,
)

from logger_setup import setup_logger
from image_panel import ImagePanel
from image_processor import BlobAnalysis, compute_diff_pair, make_overlay
from overlay_dialog import OverlayDialog

logger = setup_logger("app")

_ROW_LABELS = [
    "pos1  Y 좌표 (offset)",
    "pos1  X 거리 (좌벽→blob)",
    "pos1  픽셀 면적",
    "pos4  Y 좌표 (offset)",
    "pos4  X 거리 (blob→우벽)",
    "pos4  픽셀 면적",
    "X거리 차이 (pos1 - pos4)",
]
_DIFF_KEYS = ["y_at_offset", "ref_x", "area"]


# ---------------------------------------------------------------------------
# Log Viewer Dialog
# ---------------------------------------------------------------------------

class LogViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("로그 보기")
        self.resize(800, 500)
        layout = QVBoxLayout(self)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self._text)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self._load)
        layout.addWidget(btn_refresh)
        self._load()

    def _load(self):
        try:
            with open("app.log", encoding="utf-8") as f:
                self._text.setPlainText(f.read())
            sb = self._text.verticalScrollBar()
            sb.setValue(sb.maximum())
        except FileNotFoundError:
            self._text.setPlainText("(로그 파일 없음)")


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("16-bit RAW 이미지 비교 분석")
        self.resize(1500, 900)

        # (pos1, pos4) 각각 두 이미지 분석 결과
        self._img1_pos1: Optional[BlobAnalysis] = None
        self._img1_pos4: Optional[BlobAnalysis] = None
        self._img2_pos1: Optional[BlobAnalysis] = None
        self._img2_pos4: Optional[BlobAnalysis] = None

        self._build_ui()
        logger.info("MainWindow 초기화 완료")

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        # ── 이미지 패널 (좌우 분할) ─────────────────────────────────────
        self._panel1 = ImagePanel("Image 1", 3072, 3072)
        self._panel2 = ImagePanel("Image 2", 3072, 3072)
        self._panel1.analysis_ready.connect(self._on_analysis1)
        self._panel2.analysis_ready.connect(self._on_analysis2)

        h_splitter = QSplitter(Qt.Horizontal)
        h_splitter.addWidget(self._panel1)
        h_splitter.addWidget(self._panel2)
        h_splitter.setStretchFactor(0, 1)
        h_splitter.setStretchFactor(1, 1)

        # ── 하단 영역 ──────────────────────────────────────────────────
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(4, 4, 4, 4)
        bottom_layout.setSpacing(8)

        # [1] 파라미터 그룹
        param_grp = QGroupBox("파라미터 / 실행")
        param_grp.setFixedWidth(240)
        param_inner = QVBoxLayout(param_grp)
        param_inner.setSpacing(4)

        off_row = QHBoxLayout()
        off_row.addWidget(QLabel("Y Offset:"))
        self._sp_offset = QSpinBox()
        self._sp_offset.setRange(0, 9999)
        self._sp_offset.setValue(30)
        self._sp_offset.setFixedWidth(65)
        self._sp_offset.valueChanged.connect(self._trigger_analysis)
        off_row.addWidget(self._sp_offset)
        off_row.addWidget(QLabel("px"))
        off_row.addStretch()
        param_inner.addLayout(off_row)

        sz_row = QHBoxLayout()
        sz_row.addWidget(QLabel("W:"))
        self._sp_img_w = QSpinBox()
        self._sp_img_w.setRange(1, 99999)
        self._sp_img_w.setValue(3072)
        self._sp_img_w.setFixedWidth(65)
        self._sp_img_w.valueChanged.connect(self._on_size_changed)
        sz_row.addWidget(self._sp_img_w)
        sz_row.addWidget(QLabel("H:"))
        self._sp_img_h = QSpinBox()
        self._sp_img_h.setRange(1, 99999)
        self._sp_img_h.setValue(3072)
        self._sp_img_h.setFixedWidth(65)
        self._sp_img_h.valueChanged.connect(self._on_size_changed)
        sz_row.addWidget(self._sp_img_h)
        param_inner.addLayout(sz_row)

        act_row = QHBoxLayout()
        btn_analyze = QPushButton("비교 분석")
        btn_analyze.clicked.connect(self._trigger_analysis)
        btn_overlay = QPushButton("오버레이")
        btn_overlay.clicked.connect(self._show_overlay)
        btn_log = QPushButton("로그")
        btn_log.clicked.connect(self._show_log)
        act_row.addWidget(btn_analyze)
        act_row.addWidget(btn_overlay)
        act_row.addWidget(btn_log)
        param_inner.addLayout(act_row)

        bottom_layout.addWidget(param_grp)

        # [2] 분석 결과 테이블 (6행 × 3열)
        result_grp = QGroupBox("분석 결과")
        result_layout = QVBoxLayout(result_grp)
        result_layout.setContentsMargins(4, 4, 4, 4)

        self._table = QTableWidget(7, 3)
        self._table.setHorizontalHeaderLabels(["Image 1", "Image 2", "차이 (2-1)"])
        self._table.setVerticalHeaderLabels(_ROW_LABELS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.verticalHeader().setMinimumWidth(160)
        self._table.horizontalHeader().setDefaultSectionSize(90)
        result_layout.addWidget(self._table)
        self._clear_table()

        bottom_layout.addWidget(result_grp, stretch=1)

        # [3] 저장 그룹
        save_grp = QGroupBox("저장")
        save_grp.setFixedWidth(280)
        save_inner = QVBoxLayout(save_grp)
        save_inner.setSpacing(4)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("폴더:"))
        self._le_save_dir = QLineEdit()
        self._le_save_dir.setPlaceholderText("저장 경로 선택...")
        self._le_save_dir.setReadOnly(True)
        folder_row.addWidget(self._le_save_dir)
        btn_browse = QPushButton("찾아보기")
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse_save_dir)
        folder_row.addWidget(btn_browse)
        save_inner.addLayout(folder_row)

        save_row1 = QHBoxLayout()
        btn_save1 = QPushButton("Image 1 저장")
        btn_save1.clicked.connect(lambda: self._save_panel(self._panel1, "image1"))
        btn_save2 = QPushButton("Image 2 저장")
        btn_save2.clicked.connect(lambda: self._save_panel(self._panel2, "image2"))
        save_row1.addWidget(btn_save1)
        save_row1.addWidget(btn_save2)
        save_inner.addLayout(save_row1)

        save_row2 = QHBoxLayout()
        btn_save_ov = QPushButton("오버레이 저장")
        btn_save_ov.clicked.connect(self._save_overlay_image)
        btn_save_all = QPushButton("모두 저장")
        btn_save_all.clicked.connect(self._save_all)
        save_row2.addWidget(btn_save_ov)
        save_row2.addWidget(btn_save_all)
        save_inner.addLayout(save_row2)

        bottom_layout.addWidget(save_grp)

        # ── 수직 스플리터 ────────────────────────────────────────────────
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.addWidget(h_splitter)
        self._v_splitter.addWidget(bottom_widget)
        self._v_splitter.setStretchFactor(0, 3)
        self._v_splitter.setStretchFactor(1, 1)
        bottom_widget.setMinimumHeight(150)
        bottom_widget.setMaximumHeight(230)

        root.addWidget(self._v_splitter)

        # ── 메뉴 ────────────────────────────────────────────────────────
        menu = self.menuBar()
        file_menu = menu.addMenu("파일")
        act_save_all = QAction("모두 저장", self)
        act_save_all.setShortcut("Ctrl+S")
        act_save_all.triggered.connect(self._save_all)
        file_menu.addAction(act_save_all)
        file_menu.addSeparator()
        act_quit = QAction("종료", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        help_menu = menu.addMenu("도움말")
        act_about = QAction("정보", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def showEvent(self, event):
        super().showEvent(event)
        total = self._v_splitter.height()
        if total > 0:
            self._v_splitter.setSizes([int(total * 0.78), int(total * 0.22)])

    # ------------------------------------------------------------------
    # 저장 관련
    # ------------------------------------------------------------------

    def _save_dir(self) -> str:
        return self._le_save_dir.text().strip()

    def _browse_save_dir(self):
        current = self._save_dir() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", current)
        if path:
            self._le_save_dir.setText(path)
            logger.info("저장 폴더 설정: %s", path)

    def _make_save_path(self, prefix: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = self._save_dir() or os.getcwd()
        return os.path.join(folder, f"{prefix}_{ts}.png")

    def _save_panel(self, panel: ImagePanel, prefix: str) -> bool:
        path = self._make_save_path(prefix)
        ok = panel._viewer.save_image(path)
        if ok:
            QMessageBox.information(self, "저장 완료", f"저장됨:\n{path}")
        else:
            QMessageBox.warning(self, "저장 실패", f"저장할 이미지가 없습니다.\n({prefix})")
        return ok

    def _save_overlay_image(self) -> bool:
        """통합 오버레이(pos1+pos4) + 측정선을 파일로 저장."""
        from overlay_dialog import _combine, _avg_bg as _ov_avg, _draw_measurement
        m1p1 = self._panel1.get_pos1_mask()
        m2p1 = self._panel2.get_pos1_mask()
        if m1p1 is None or m2p1 is None:
            QMessageBox.warning(self, "경고", "두 이미지 모두 pos1 blob을 선택해야 합니다.")
            return False

        bg1 = self._panel1.get_normalized_image()
        bg2 = self._panel2.get_normalized_image()
        bg  = _ov_avg(bg1, bg2)

        mask1 = _combine(m1p1, self._panel1.get_pos4_mask())
        mask2 = _combine(m2p1, self._panel2.get_pos4_mask())
        ov_rgb = make_overlay(mask1, mask2, bg)

        for pos_name, analysis, color in _iter_analyses(
            self._img1_pos1, self._img1_pos4,
            self._img2_pos1, self._img2_pos4,
        ):
            _draw_measurement(ov_rgb, analysis, color, pos_name[:4])

        path = self._make_save_path("overlay")
        ok = _save_rgb_array(ov_rgb, path)
        if ok:
            QMessageBox.information(self, "저장 완료", f"저장됨:\n{path}")
        return ok

    def _save_all(self):
        from overlay_dialog import _combine, _avg_bg as _ov_avg, _draw_measurement
        saved, failed = [], []

        for panel, prefix in [(self._panel1, "image1"), (self._panel2, "image2")]:
            path = self._make_save_path(prefix)
            if panel._viewer.save_image(path):
                saved.append(os.path.basename(path))
            else:
                failed.append(f"{prefix} (이미지 없음)")

        m1p1 = self._panel1.get_pos1_mask()
        m2p1 = self._panel2.get_pos1_mask()
        if m1p1 is not None and m2p1 is not None:
            bg1 = self._panel1.get_normalized_image()
            bg2 = self._panel2.get_normalized_image()
            bg  = _ov_avg(bg1, bg2)
            mask1 = _combine(m1p1, self._panel1.get_pos4_mask())
            mask2 = _combine(m2p1, self._panel2.get_pos4_mask())
            ov_rgb = make_overlay(mask1, mask2, bg)
            for pos_name, analysis, color in _iter_analyses(
                self._img1_pos1, self._img1_pos4,
                self._img2_pos1, self._img2_pos4,
            ):
                _draw_measurement(ov_rgb, analysis, color, pos_name[:4])
            path = self._make_save_path("overlay")
            if _save_rgb_array(ov_rgb, path):
                saved.append(os.path.basename(path))
            else:
                failed.append("overlay (저장 실패)")

        msg = ""
        if saved:
            folder = self._save_dir() or os.getcwd()
            msg += f"저장 완료 ({folder}):\n" + "\n".join(f"  · {n}" for n in saved)
        if failed:
            msg += ("\n\n" if msg else "") + "건너뜀:\n" + "\n".join(f"  · {n}" for n in failed)
        QMessageBox.information(self, "모두 저장", msg or "저장할 항목이 없습니다.")

    # ------------------------------------------------------------------
    # 분석 관련
    # ------------------------------------------------------------------

    def _on_size_changed(self):
        self._panel1.set_image_size(self._sp_img_w.value(), self._sp_img_h.value())
        self._panel2.set_image_size(self._sp_img_w.value(), self._sp_img_h.value())

    def _on_analysis1(self, pos1: BlobAnalysis, pos4: BlobAnalysis):
        self._img1_pos1 = pos1
        self._img1_pos4 = pos4
        self._update_table()

    def _on_analysis2(self, pos1: BlobAnalysis, pos4: BlobAnalysis):
        self._img2_pos1 = pos1
        self._img2_pos4 = pos4
        self._update_table()

    def _trigger_analysis(self):
        offset = self._sp_offset.value()
        self._panel1.run_analysis(offset)
        self._panel2.run_analysis(offset)

    def _update_table(self):
        p1_ready = self._img1_pos1 is not None and self._img2_pos1 is not None
        p4_ready = self._img1_pos4 is not None and self._img2_pos4 is not None
        if not p1_ready and not p4_ready:
            return

        if p1_ready:
            diff1 = compute_diff_pair(self._img1_pos1, self._img2_pos1)
            for r, key in enumerate(_DIFF_KEYS):
                v1, v2, d = diff1[key]
                self._table.setItem(r, 0, QTableWidgetItem(str(v1)))
                self._table.setItem(r, 1, QTableWidgetItem(str(v2)))
                item_d = QTableWidgetItem(str(d))
                if d != 0:
                    item_d.setForeground(QColor(200, 50, 50) if d > 0 else QColor(50, 50, 200))
                self._table.setItem(r, 2, item_d)

        if p4_ready:
            diff4 = compute_diff_pair(self._img1_pos4, self._img2_pos4)
            for r, key in enumerate(_DIFF_KEYS):
                v1, v2, d = diff4[key]
                row = r + 3
                self._table.setItem(row, 0, QTableWidgetItem(str(v1)))
                self._table.setItem(row, 1, QTableWidgetItem(str(v2)))
                item_d = QTableWidgetItem(str(d))
                if d != 0:
                    item_d.setForeground(QColor(200, 50, 50) if d > 0 else QColor(50, 50, 200))
                self._table.setItem(row, 2, item_d)

        # 행 6: 각 이미지별 pos1 X거리 - pos4 X거리
        if p1_ready and p4_ready:
            xdiff_img1 = self._img1_pos1.ref_x - self._img1_pos4.ref_x
            xdiff_img2 = self._img2_pos1.ref_x - self._img2_pos4.ref_x
            xdiff_d    = xdiff_img2 - xdiff_img1
            self._table.setItem(6, 0, QTableWidgetItem(str(xdiff_img1)))
            self._table.setItem(6, 1, QTableWidgetItem(str(xdiff_img2)))
            item_xd = QTableWidgetItem(str(xdiff_d))
            if xdiff_d != 0:
                item_xd.setForeground(QColor(200, 50, 50) if xdiff_d > 0 else QColor(50, 50, 200))
            self._table.setItem(6, 2, item_xd)

        logger.info("분석 테이블 업데이트 완료")

    def _clear_table(self):
        for r in range(7):
            for c in range(3):
                self._table.setItem(r, c, QTableWidgetItem("-"))

    def _show_overlay(self):
        m1p1 = self._panel1.get_pos1_mask()
        m2p1 = self._panel2.get_pos1_mask()
        if m1p1 is None or m2p1 is None:
            QMessageBox.warning(self, "경고", "두 이미지 모두 pos1 blob을 선택해야 합니다.")
            return

        bg1 = self._panel1.get_normalized_image()
        bg2 = self._panel2.get_normalized_image()
        dlg = OverlayDialog(
            m1p1, m2p1,
            bg1, bg2,
            mask1_pos4=self._panel1.get_pos4_mask(),
            mask2_pos4=self._panel2.get_pos4_mask(),
            analyses_img1=_build_analyses_list(self._img1_pos1, self._img1_pos4),
            analyses_img2=_build_analyses_list(self._img2_pos1, self._img2_pos4),
            save_dir=self._save_dir(),
            parent=self,
        )
        dlg.exec_()

    def _show_log(self):
        LogViewerDialog(parent=self).exec_()

    def _show_about(self):
        QMessageBox.information(
            self, "정보",
            "16-bit RAW 이미지 비교 분석 프로그램\n\n"
            "조작:\n"
            "  · 휠          : 줌인 / 줌아웃\n"
            "  · 우클릭 드래그: 팬 (이동)\n"
            "  · 좌클릭      : ROI 그리기 / Blob 선택\n\n"
            "· pos1(좌측) + pos4(우측) 각 blob 지정\n"
            "· Y 좌표 / X 거리 / 면적 비교 (6행)\n"
            "· 오버레이 비교 (pos1 쌍 / pos4 쌍)\n"
            "· 이미지 및 오버레이 저장",
        )


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def _build_analyses_list(pos1: Optional[BlobAnalysis], pos4: Optional[BlobAnalysis]) -> list:
    """유효한 분석 결과만 [(pos_name, analysis)] 리스트로 반환."""
    result = []
    if pos1 is not None:
        result.append(("pos1", pos1))
    if pos4 is not None:
        result.append(("pos4", pos4))
    return result


def _iter_analyses(img1_pos1, img1_pos4, img2_pos1, img2_pos4):
    """오버레이 저장용 (pos_name, analysis, color) 이터레이터."""
    from overlay_dialog import _C_IMG1_POS1, _C_IMG1_POS4, _C_IMG2_POS1, _C_IMG2_POS4
    pairs = [
        (img1_pos1, "Img1-", _C_IMG1_POS1),
        (img1_pos4, "Img1-", _C_IMG1_POS4),
        (img2_pos1, "Img2-", _C_IMG2_POS1),
        (img2_pos4, "Img2-", _C_IMG2_POS4),
    ]
    for analysis, label, color in pairs:
        if analysis is not None:
            yield label, analysis, color


def _save_rgb_array(rgb: np.ndarray, path: str) -> bool:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg)
    ok = pixmap.save(path, "PNG")
    if ok:
        logger.info("저장 OK: %s", path)
    else:
        logger.error("저장 실패: %s", path)
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    def handle_exception(exc_type, exc_value, exc_tb):
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        QMessageBox.critical(
            None, "치명적 오류",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

    sys.excepthook = handle_exception

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
