#!/usr/bin/env python3
"""Signal/Noise Analyzer — GUI tool for measuring image signal and noise."""

import sys
import csv
import numpy as np
from pathlib import Path
from PIL import Image

try:
    import pyqtgraph as pg
    HAS_PG = True
except ImportError:
    HAS_PG = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabBar, QListWidget, QLabel, QPushButton, QSlider, QSpinBox,
    QDoubleSpinBox, QTreeWidget, QTreeWidgetItem, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsLineItem, QGroupBox,
    QFileDialog, QMessageBox, QShortcut, QButtonGroup, QRadioButton,
    QHeaderView, QAbstractItemView, QFrame,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, QLineF, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QPen, QColor, QPainter, QKeySequence

SUPPORTED_EXTS = {'.bmp', '.png', '.jpg', '.jpeg', '.tif', '.tiff'}
TOOL_RECT   = 'rect'
TOOL_SQUARE = 'square'
TOOL_LINE   = 'line'


# ── helpers ───────────────────────────────────────────────────────────────────

def load_image(path: Path):
    pil = Image.open(str(path))
    if hasattr(pil, 'n_frames') and getattr(pil, 'n_frames', 1) > 1:
        pil.seek(0)
    gray = np.array(pil.convert('L'), dtype=np.uint8)
    rgb  = np.array(pil.convert('RGB'), dtype=np.uint8)
    h, w = gray.shape
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy()), gray


def make_overlay(gray: np.ndarray, roi: QRectF, thr: int):
    h, w = gray.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    x0, y0 = max(0, int(roi.x())),          max(0, int(roi.y()))
    x1, y1 = min(w, x0 + int(roi.width())), min(h, y0 + int(roi.height()))
    if x1 <= x0 or y1 <= y0:
        return None
    crop = gray[y0:y1, x0:x1]
    rgba[y0:y1, x0:x1][crop <  thr] = [255,  50,  50, 140]
    rgba[y0:y1, x0:x1][crop >= thr] = [ 50, 220,  50,  90]
    qimg = QImage(rgba.data, w, h, w * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def compute_metrics(gray: np.ndarray, roi: QRectF, thr: int):
    h, w = gray.shape
    x0, y0 = max(0, int(roi.x())),          max(0, int(roi.y()))
    x1, y1 = min(w, x0 + int(roi.width())), min(h, y0 + int(roi.height()))
    if x1 <= x0 or y1 <= y0:
        return None
    crop   = gray[y0:y1, x0:x1].astype(np.float64)
    sig_px = crop[crop <  thr]
    bg_px  = crop[crop >= thr]
    if sig_px.size == 0 or bg_px.size == 0:
        return None
    bg_mean = bg_px.mean()
    return dict(
        signal=float(bg_mean - sig_px.min()),
        noise1=float(bg_px.std()),
        noise2=float(bg_mean - bg_px.min()),
    )


def line_profile(gray: np.ndarray, p1: QPointF, p2: QPointF) -> np.ndarray:
    h, w   = gray.shape
    length = max(2, int(np.hypot(p2.x() - p1.x(), p2.y() - p1.y())))
    xs = np.clip(np.linspace(p1.x(), p2.x(), length), 0, w - 1).astype(int)
    ys = np.clip(np.linspace(p1.y(), p2.y(), length), 0, h - 1).astype(int)
    return gray[ys, xs].astype(np.float32)


# ── ImageViewer ───────────────────────────────────────────────────────────────

class ImageViewer(QGraphicsView):
    roi_changed  = pyqtSignal(QRectF)
    line_changed = pyqtSignal(QPointF, QPointF)

    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMinimumSize(400, 300)

        self._img_item:     QGraphicsPixmapItem | None = None
        self._overlay_item: QGraphicsPixmapItem | None = None
        self._roi_item:     QGraphicsRectItem   | None = None
        self._line_item:    QGraphicsLineItem   | None = None
        self._temp_item                                = None

        self._tool    = TOOL_RECT
        self._drawing = False
        self._start:  QPointF | None = None
        self._panning = False
        self._pan_pos = None
        self._roi:    QRectF  | None = None

    def set_tool(self, t: str):
        self._tool = t

    def load(self, pixmap: QPixmap):
        self._scene.clear()
        self._img_item     = self._scene.addPixmap(pixmap)
        self._overlay_item = self._scene.addPixmap(QPixmap())
        self._overlay_item.setZValue(1)
        self._roi_item  = None
        self._line_item = None
        self._roi       = None
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._img_item, Qt.KeepAspectRatio)

    def set_overlay(self, pixmap):
        if self._overlay_item:
            self._overlay_item.setPixmap(pixmap if pixmap else QPixmap())

    def show_roi(self, roi: QRectF, color: QColor = None):
        if self._roi_item:
            self._scene.removeItem(self._roi_item)
        pen = QPen(color or QColor(255, 200, 0), 2)
        pen.setCosmetic(True)
        self._roi_item = QGraphicsRectItem(roi)
        self._roi_item.setPen(pen)
        self._roi_item.setZValue(2)
        self._scene.addItem(self._roi_item)
        self._roi = roi

    def current_roi(self) -> QRectF | None:
        return self._roi

    def _cpen(self, color: QColor) -> QPen:
        p = QPen(color, 2)
        p.setCosmetic(True)
        return p

    def _calc_rect(self, cur: QPointF) -> QRectF:
        dx = cur.x() - self._start.x()
        dy = cur.y() - self._start.y()
        if self._tool == TOOL_SQUARE:
            side = min(abs(dx), abs(dy))
            dx = side * (1 if dx >= 0 else -1)
            dy = side * (1 if dy >= 0 else -1)
        return QRectF(self._start, QPointF(self._start.x() + dx, self._start.y() + dy)).normalized()

    def _update_temp(self, cur: QPointF):
        if self._temp_item:
            self._scene.removeItem(self._temp_item)
            self._temp_item = None
        if self._tool in (TOOL_RECT, TOOL_SQUARE):
            item = QGraphicsRectItem(self._calc_rect(cur))
            item.setPen(self._cpen(QColor(255, 80, 80)))
            item.setZValue(3)
            self._scene.addItem(item)
            self._temp_item = item
        elif self._tool == TOOL_LINE:
            item = QGraphicsLineItem(QLineF(self._start, cur))
            item.setPen(self._cpen(QColor(0, 200, 255)))
            item.setZValue(3)
            self._scene.addItem(item)
            self._temp_item = item

    def wheelEvent(self, e):
        self.scale(1.15 if e.angleDelta().y() > 0 else 1 / 1.15,
                   1.15 if e.angleDelta().y() > 0 else 1 / 1.15)

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_pos = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
        elif e.button() == Qt.LeftButton and self._img_item:
            self._drawing = True
            self._start   = self.mapToScene(e.pos())
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning and self._pan_pos is not None:
            d = e.pos() - self._pan_pos
            self._pan_pos = e.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        if self._drawing and self._start:
            cur = self.mapToScene(e.pos())
            self._update_temp(cur)
            if self._tool == TOOL_LINE:
                self.line_changed.emit(self._start, cur)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
        elif e.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            if self._temp_item:
                self._scene.removeItem(self._temp_item)
                self._temp_item = None
            if not self._start or not self._img_item:
                return
            cur   = self.mapToScene(e.pos())
            img_r = self._img_item.boundingRect()
            if self._tool in (TOOL_RECT, TOOL_SQUARE):
                rect = self._calc_rect(cur).intersected(img_r)
                if rect.width() >= 2 and rect.height() >= 2:
                    self.show_roi(rect, QColor(255, 80, 80))
                    self.roi_changed.emit(rect)
            elif self._tool == TOOL_LINE:
                p2 = QPointF(
                    max(img_r.left(), min(img_r.right(),  cur.x())),
                    max(img_r.top(),  min(img_r.bottom(), cur.y())),
                )
                if self._line_item:
                    self._scene.removeItem(self._line_item)
                self._line_item = QGraphicsLineItem(QLineF(self._start, p2))
                self._line_item.setPen(self._cpen(QColor(0, 200, 255)))
                self._line_item.setZValue(3)
                self._scene.addItem(self._line_item)
                self.line_changed.emit(self._start, p2)
        super().mouseReleaseEvent(e)


# ── FolderData ────────────────────────────────────────────────────────────────

class FolderData:
    def __init__(self, folder: Path):
        self.folder = folder
        self.images: list[Path] = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        )


# ── MainWindow ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Signal / Noise Analyzer')
        self.resize(1440, 900)

        self._gray:       np.ndarray | None = None
        self._cur_path:   Path        | None = None
        self._threshold:  int               = 128
        self._pixel_size: float             = 1.0
        self._folders:    list[FolderData]  = []
        self._results:    list[dict]        = []

        self._build_ui()
        self._connect()

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_v = QVBoxLayout(central)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # ── TOP BAR: folder tabs ───────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setFixedHeight(42)
        top_bar.setStyleSheet(
            'QFrame { background:#2d2d2d; border-bottom:2px solid #1a1a1a; }'
        )
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(8, 4, 8, 4)
        tb.setSpacing(6)

        lbl = QLabel('폴더')
        lbl.setStyleSheet('color:#aaa; font-size:11px; font-weight:bold;')
        tb.addWidget(lbl)

        self._tab_bar = QTabBar()
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setMovable(True)
        self._tab_bar.setStyleSheet('''
            QTabBar::tab {
                background:#3c3c3c; color:#ccc;
                padding:4px 16px; min-width:90px;
                border:1px solid #555; border-bottom:none;
                border-radius:4px 4px 0 0; margin-right:2px;
            }
            QTabBar::tab:selected { background:#555; color:#fff; font-weight:bold; }
            QTabBar::tab:hover    { background:#4a4a4a; }
            QTabBar::close-button { subcontrol-position:right; }
        ''')
        tb.addWidget(self._tab_bar, 1)

        add_btn = QPushButton('＋  폴더 추가')
        add_btn.setFixedHeight(30)
        add_btn.setStyleSheet(
            'QPushButton { background:#2a7fcf; color:white; font-weight:bold;'
            ' border-radius:4px; padding:0 12px; }'
            'QPushButton:hover { background:#3a8fdf; }'
        )
        add_btn.clicked.connect(lambda: self._add_folder())
        tb.addWidget(add_btn)

        root_v.addWidget(top_bar)

        # ── MAIN SPLITTER ──────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        root_v.addWidget(splitter, 1)

        # ── LEFT: image list ───────────────────────────────────────────────
        left = QWidget()
        left.setMinimumWidth(160)
        left.setMaximumWidth(240)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 6, 4, 4)
        lv.setSpacing(2)
        self._lbl_folder = QLabel('이미지 없음')
        self._lbl_folder.setStyleSheet('color:#888; font-size:11px;')
        lv.addWidget(self._lbl_folder)
        self._img_list = QListWidget()
        self._img_list.currentRowChanged.connect(self._on_img_row_changed)
        lv.addWidget(self._img_list, 1)
        splitter.addWidget(left)

        # ── CENTER: viewer ─────────────────────────────────────────────────
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(2)
        self._viewer = ImageViewer()
        cv.addWidget(self._viewer, 1)
        self._lbl_status = QLabel('＋ 폴더 추가 버튼으로 시작하세요.')
        self._lbl_status.setStyleSheet('padding:3px; color:#888; font-size:11px;')
        cv.addWidget(self._lbl_status)
        splitter.addWidget(center)

        # ── RIGHT: controls ────────────────────────────────────────────────
        right = QWidget()
        right.setMinimumWidth(330)
        right.setMaximumWidth(450)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 6, 4, 4)
        rv.setSpacing(6)

        # Tool buttons
        tool_box = QGroupBox('도구')
        tl = QHBoxLayout(tool_box)
        tl.setSpacing(4)
        self._bg_tool = QButtonGroup(self)
        for label, tip, tool in [
            ('사각형 ROI',  '자유 사각형 드래그', TOOL_RECT),
            ('정사각형 ROI', '정사각형 드래그',   TOOL_SQUARE),
            ('선 프로파일', '라인 프로파일',      TOOL_LINE),
        ]:
            rb = QRadioButton(label)
            rb.setToolTip(tip)
            rb.setProperty('tool', tool)
            self._bg_tool.addButton(rb)
            tl.addWidget(rb)
        self._bg_tool.buttons()[0].setChecked(True)
        rv.addWidget(tool_box)

        # Threshold
        thr_box = QGroupBox('이진화 Threshold  (0 – 255)')
        thr_lay = QHBoxLayout(thr_box)
        self._thr_slider = QSlider(Qt.Horizontal)
        self._thr_slider.setRange(0, 255)
        self._thr_slider.setValue(self._threshold)
        self._thr_spin = QSpinBox()
        self._thr_spin.setRange(0, 255)
        self._thr_spin.setValue(self._threshold)
        self._thr_spin.setFixedWidth(62)
        thr_lay.addWidget(self._thr_slider, 1)
        thr_lay.addWidget(self._thr_spin)
        rv.addWidget(thr_box)

        # Metrics + pixel size
        met_box = QGroupBox('측정값')
        ml = QVBoxLayout(met_box)
        ml.setSpacing(4)

        px_row = QHBoxLayout()
        px_row.addWidget(QLabel('Pixel Size:'))
        self._spin_px = QDoubleSpinBox()
        self._spin_px.setRange(0.001, 100000.0)
        self._spin_px.setValue(1.0)
        self._spin_px.setDecimals(3)
        self._spin_px.setSingleStep(0.1)
        self._spin_px.setFixedWidth(100)
        self._spin_px.setSuffix('  µm/px')
        px_row.addWidget(self._spin_px)
        px_row.addStretch()
        ml.addLayout(px_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet('color:#ccc;')
        ml.addWidget(sep)

        self._lbl_signal = QLabel('Signal             :  —')
        self._lbl_noise1 = QLabel('Noise1  (σ_bg)     :  —')
        self._lbl_noise2 = QLabel('Noise2  (mean−min) :  —')
        for lbl in (self._lbl_signal, self._lbl_noise1, self._lbl_noise2):
            lbl.setStyleSheet('font-family:monospace; font-size:12px;')
            ml.addWidget(lbl)

        hint = QLabel('  ↵ Enter  →  현재 측정값 저장')
        hint.setStyleSheet('color:#888; font-size:11px; margin-top:4px;')
        ml.addWidget(hint)
        rv.addWidget(met_box)

        # Line profile chart
        chart_box = QGroupBox('라인 프로파일')
        cl = QVBoxLayout(chart_box)
        cl.setContentsMargins(2, 2, 2, 2)
        if HAS_PG:
            self._plot = pg.PlotWidget(background='#111827')
            ax_pen   = pg.mkPen('#4b5563')
            ax_style = {'color': '#9ca3af', 'font-size': '9pt'}
            for axis in ('left', 'bottom'):
                self._plot.getAxis(axis).setPen(ax_pen)
                self._plot.getAxis(axis).setTextPen(pg.mkPen('#9ca3af'))
            self._plot.setLabel('left',   '밝기 (0–255)', **ax_style)
            self._plot.setLabel('bottom', '픽셀 위치',     **ax_style)
            self._plot.setYRange(0, 255)
            self._plot.showGrid(x=True, y=True, alpha=0.15)
            self._curve = self._plot.plot(
                pen=pg.mkPen(color='#00e5ff', width=2.5)
            )
            self._thr_line = pg.InfiniteLine(
                pos=self._threshold, angle=0,
                pen=pg.mkPen(color='#ff6b6b', width=1.5, style=Qt.DashLine),
                label='Thr={value:.0f}',
                labelOpts={'color': '#ff6b6b', 'position': 0.08, 'fill': '#1f2937'},
            )
            self._plot.addItem(self._thr_line)
            self._plot.setFixedHeight(190)
            cl.addWidget(self._plot)
        else:
            no_pg = QLabel('pyqtgraph 미설치\npip install pyqtgraph')
            no_pg.setAlignment(Qt.AlignCenter)
            no_pg.setFixedHeight(80)
            cl.addWidget(no_pg)
        rv.addWidget(chart_box)

        # Results tree
        tree_box = QGroupBox('저장된 측정값')
        trl = QVBoxLayout(tree_box)
        trl.setContentsMargins(2, 2, 2, 2)
        trl.setSpacing(3)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(10)
        self._tree.setHeaderLabels([
            '이미지 / #', 'X', 'Y', 'W', 'H', 'Thr', 'Px(µm)',
            'Signal', 'Noise1', 'Noise2',
        ])
        self._tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        hdr = self._tree.header()
        for i in range(10):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemClicked.connect(self._on_tree_click)
        trl.addWidget(self._tree, 1)

        btn_row = QHBoxLayout()
        btn_del = QPushButton('선택 삭제  (Del)')
        btn_del.clicked.connect(self._delete_selected)

        btn_save_sel = QPushButton('선택 저장 (CSV)')
        btn_save_sel.setStyleSheet(
            'QPushButton{background:#2a7fcf;color:white;font-weight:bold;}'
            'QPushButton:hover{background:#3a8fdf;}'
        )
        btn_save_sel.clicked.connect(self._save_selected_csv)

        btn_save_all = QPushButton('전체 저장 (CSV)')
        btn_save_all.setStyleSheet(
            'QPushButton{background:#2ca05a;color:white;font-weight:bold;}'
            'QPushButton:hover{background:#3cb06a;}'
        )
        btn_save_all.clicked.connect(self._save_all_csv)

        btn_clear = QPushButton('전체 초기화')
        btn_clear.clicked.connect(self._clear_results)

        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_save_sel)
        btn_row.addWidget(btn_save_all)
        btn_row.addWidget(btn_clear)
        trl.addLayout(btn_row)

        rv.addWidget(tree_box, 1)
        splitter.addWidget(right)
        splitter.setSizes([190, 890, 390])

    # ── connect ───────────────────────────────────────────────────────────────

    def _connect(self):
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_tab_closed)

        self._viewer.roi_changed.connect(self._on_roi_changed)
        self._viewer.line_changed.connect(self._on_line_changed)

        self._thr_slider.valueChanged.connect(self._on_thr_slider)
        self._thr_spin.valueChanged.connect(self._on_thr_spin)
        self._spin_px.valueChanged.connect(lambda v: setattr(self, '_pixel_size', v))

        for btn in self._bg_tool.buttons():
            btn.toggled.connect(
                lambda checked, b=btn: self._viewer.set_tool(b.property('tool')) if checked else None
            )

        for key in (Qt.Key_Return, Qt.Key_Enter):
            QShortcut(QKeySequence(key), self).activated.connect(self._save_measurement)
        QShortcut(QKeySequence(Qt.Key_Delete), self._tree).activated.connect(self._delete_selected)

    # ── folder / tab management ───────────────────────────────────────────────

    def _add_folder(self, folder_str: str = None):
        if folder_str is None:
            folder_str = QFileDialog.getExistingDirectory(
                self, '폴더 선택', str(Path.home())
            )
        if not folder_str:
            return
        fd = FolderData(Path(folder_str))
        self._folders.append(fd)
        self._tab_bar.addTab(fd.folder.name)
        self._tab_bar.setCurrentIndex(len(self._folders) - 1)

    def _on_tab_changed(self, idx: int):
        if idx < 0 or idx >= len(self._folders):
            self._img_list.clear()
            self._lbl_folder.setText('이미지 없음')
            return
        fd = self._folders[idx]
        self._img_list.blockSignals(True)
        self._img_list.clear()
        for p in fd.images:
            self._img_list.addItem(p.name)
        self._img_list.blockSignals(False)
        self._lbl_folder.setText(f'{len(fd.images)}개 이미지')
        if fd.images:
            self._img_list.setCurrentRow(0)
            self._load_image(fd.images[0])

    def _on_tab_closed(self, idx: int):
        if 0 <= idx < len(self._folders):
            self._folders.pop(idx)
        self._tab_bar.removeTab(idx)

    # ── image loading ─────────────────────────────────────────────────────────

    def _on_img_row_changed(self, row: int):
        idx = self._tab_bar.currentIndex()
        if idx < 0 or idx >= len(self._folders):
            return
        fd = self._folders[idx]
        if 0 <= row < len(fd.images):
            self._load_image(fd.images[row])

    def _load_image(self, path: Path):
        self._cur_path = path
        try:
            pixmap, gray = load_image(path)
            self._gray = gray
            self._viewer.load(pixmap)
            self._lbl_status.setText(str(path.name))
            self._clear_metrics_display()
        except Exception as exc:
            QMessageBox.warning(self, '로드 오류', str(exc))

    # ── threshold ─────────────────────────────────────────────────────────────

    def _on_thr_slider(self, val: int):
        self._thr_spin.blockSignals(True)
        self._thr_spin.setValue(val)
        self._thr_spin.blockSignals(False)
        self._threshold = val
        if HAS_PG:
            self._thr_line.setValue(val)
        roi = self._viewer.current_roi()
        if roi:
            self._refresh_overlay_and_metrics(roi)

    def _on_thr_spin(self, val: int):
        self._thr_slider.blockSignals(True)
        self._thr_slider.setValue(val)
        self._thr_slider.blockSignals(False)
        self._threshold = val
        if HAS_PG:
            self._thr_line.setValue(val)
        roi = self._viewer.current_roi()
        if roi:
            self._refresh_overlay_and_metrics(roi)

    # ── ROI / line ────────────────────────────────────────────────────────────

    def _on_roi_changed(self, roi: QRectF):
        self._refresh_overlay_and_metrics(roi)

    def _on_line_changed(self, p1: QPointF, p2: QPointF):
        if self._gray is None or not HAS_PG:
            return
        self._curve.setData(line_profile(self._gray, p1, p2))

    def _refresh_overlay_and_metrics(self, roi: QRectF):
        if self._gray is None:
            return
        self._viewer.set_overlay(make_overlay(self._gray, roi, self._threshold))
        m = compute_metrics(self._gray, roi, self._threshold)
        if m:
            self._lbl_signal.setText(f'Signal             :  {m["signal"]:>9.3f}')
            self._lbl_noise1.setText(f'Noise1  (σ_bg)     :  {m["noise1"]:>9.3f}')
            self._lbl_noise2.setText(f'Noise2  (mean−min) :  {m["noise2"]:>9.3f}')
        else:
            self._clear_metrics_display()
            self._lbl_status.setText('⚠ 신호/배경 픽셀 없음 — threshold 조정 필요')

    def _clear_metrics_display(self):
        self._lbl_signal.setText('Signal             :  —')
        self._lbl_noise1.setText('Noise1  (σ_bg)     :  —')
        self._lbl_noise2.setText('Noise2  (mean−min) :  —')

    # ── save measurement ──────────────────────────────────────────────────────

    def _save_measurement(self):
        roi = self._viewer.current_roi()
        if roi is None or self._gray is None or self._cur_path is None:
            self._lbl_status.setText('⚠ ROI를 먼저 그려주세요.')
            return
        m = compute_metrics(self._gray, roi, self._threshold)
        if m is None:
            self._lbl_status.setText('⚠ 이진화 결과 없음 — threshold를 조정하세요.')
            return

        x, y, w, h = int(roi.x()), int(roi.y()), int(roi.width()), int(roi.height())
        rec = dict(
            img_path=self._cur_path,
            img_name=self._cur_path.name,
            x=x, y=y, w=w, h=h,
            threshold=self._threshold,
            pixel_size=self._pixel_size,
            **m,
        )
        self._results.append(rec)
        self._add_tree_row(rec)
        self._lbl_status.setText(
            f'저장됨 ✓  {self._cur_path.name}  ROI=({x},{y},{w},{h})'
            f'  Signal={m["signal"]:.2f}  N1={m["noise1"]:.2f}  N2={m["noise2"]:.2f}'
        )

    def _add_tree_row(self, rec: dict):
        name = rec['img_name']
        parent = None
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.text(0) == name:
                parent = item
                break
        if parent is None:
            parent = QTreeWidgetItem([name])
            parent.setExpanded(True)
            self._tree.addTopLevelItem(parent)

        n = parent.childCount() + 1
        child = QTreeWidgetItem([
            f'#{n}',
            str(rec['x']), str(rec['y']), str(rec['w']), str(rec['h']),
            str(rec['threshold']),
            f'{rec["pixel_size"]:.3f}',
            f'{rec["signal"]:.3f}',
            f'{rec["noise1"]:.3f}',
            f'{rec["noise2"]:.3f}',
        ])
        child.setData(0, Qt.UserRole, rec)
        parent.addChild(child)
        self._tree.scrollToItem(child)

    # ── tree click ────────────────────────────────────────────────────────────

    def _on_tree_click(self, item: QTreeWidgetItem, _col: int):
        rec: dict = item.data(0, Qt.UserRole)
        if rec is None:
            return
        path: Path = rec['img_path']

        for i, fd in enumerate(self._folders):
            if fd.folder == path.parent:
                self._tab_bar.blockSignals(True)
                self._tab_bar.setCurrentIndex(i)
                self._tab_bar.blockSignals(False)
                # Refresh list content for this folder
                self._img_list.blockSignals(True)
                self._img_list.clear()
                for img in fd.images:
                    self._img_list.addItem(img.name)
                for j, p in enumerate(fd.images):
                    if p == path:
                        self._img_list.setCurrentRow(j)
                        break
                self._img_list.blockSignals(False)
                self._lbl_folder.setText(f'{len(fd.images)}개 이미지')
                break

        if path != self._cur_path:
            self._load_image(path)

        roi = QRectF(rec['x'], rec['y'], rec['w'], rec['h'])
        self._viewer.show_roi(roi, QColor(255, 200, 0))

        self._threshold  = rec['threshold']
        self._pixel_size = rec['pixel_size']
        for w in (self._thr_slider, self._thr_spin):
            w.blockSignals(True)
        self._thr_slider.setValue(self._threshold)
        self._thr_spin.setValue(self._threshold)
        for w in (self._thr_slider, self._thr_spin):
            w.blockSignals(False)
        self._spin_px.blockSignals(True)
        self._spin_px.setValue(self._pixel_size)
        self._spin_px.blockSignals(False)
        if HAS_PG:
            self._thr_line.setValue(self._threshold)

        if self._gray is not None:
            self._viewer.set_overlay(make_overlay(self._gray, roi, self._threshold))
            m = compute_metrics(self._gray, roi, self._threshold)
            if m:
                self._lbl_signal.setText(f'Signal             :  {m["signal"]:>9.3f}')
                self._lbl_noise1.setText(f'Noise1  (σ_bg)     :  {m["noise1"]:>9.3f}')
                self._lbl_noise2.setText(f'Noise2  (mean−min) :  {m["noise2"]:>9.3f}')

    # ── delete / save CSV ─────────────────────────────────────────────────────

    def _delete_selected(self):
        to_del = [item for item in self._tree.selectedItems()
                  if item.data(0, Qt.UserRole) is not None]
        if not to_del:
            return
        for item in to_del:
            rec = item.data(0, Qt.UserRole)
            if rec in self._results:
                self._results.remove(rec)
            parent = item.parent()
            parent.removeChild(item)
            if parent.childCount() == 0:
                self._tree.takeTopLevelItem(self._tree.indexOfTopLevelItem(parent))
        self._renumber_all()
        self._lbl_status.setText(f'{len(to_del)}개 항목 삭제됨.')

    def _renumber_all(self):
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            for j in range(parent.childCount()):
                parent.child(j).setText(0, f'#{j + 1}')

    def _write_csv(self, path: str, recs: list[dict]):
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['이미지명', 'X', 'Y', 'W', 'H', 'Threshold',
                        'Pixel Size(µm/px)', 'Signal', 'Noise1', 'Noise2'])
            for rec in recs:
                w.writerow([
                    rec['img_name'], rec['x'], rec['y'], rec['w'], rec['h'],
                    rec['threshold'], f'{rec["pixel_size"]:.3f}',
                    f'{rec["signal"]:.3f}', f'{rec["noise1"]:.3f}', f'{rec["noise2"]:.3f}',
                ])

    def _save_selected_csv(self):
        recs = [item.data(0, Qt.UserRole) for item in self._tree.selectedItems()
                if item.data(0, Qt.UserRole) is not None]
        if not recs:
            QMessageBox.warning(self, '선택 없음', '저장할 항목을 먼저 선택하세요.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '선택 항목 저장', 'results.csv', 'CSV (*.csv)'
        )
        if not path:
            return
        self._write_csv(path, recs)
        self._lbl_status.setText(f'선택 저장 완료: {len(recs)}개 → {Path(path).name}')

    def _save_all_csv(self):
        if not self._results:
            QMessageBox.warning(self, '저장 없음', '저장된 측정값이 없습니다.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '전체 저장', 'results_all.csv', 'CSV (*.csv)'
        )
        if not path:
            return
        self._write_csv(path, self._results)
        self._lbl_status.setText(f'전체 저장 완료: {len(self._results)}개 → {Path(path).name}')

    def _clear_results(self):
        self._results.clear()
        self._tree.clear()
        self._lbl_status.setText('결과 초기화됨.')


# ── entry ─────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
