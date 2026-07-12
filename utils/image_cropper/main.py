import sys
import os
import re
import struct
import numpy as np
from pathlib import Path
from PIL import Image, ImageSequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QSpinBox, QFileDialog, QMessageBox, QSizePolicy, QLineEdit,
    QGroupBox, QFormLayout, QSplitter, QFrame, QProgressDialog, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPixmap, QImage, QPen, QColor, QBrush, QFont, QIntValidator, QPainter
)

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.raw'}

# Matches the filename suffix produced by save_crop(): "..._{idx}_x{x}y{y}w{w}h{h}"
REFERENCE_NAME_PATTERN = re.compile(r'_(?P<idx>\d+)_x(?P<x>\d+)y(?P<y>\d+)w(?P<w>\d+)h(?P<h>\d+)$')


def parse_reference_filename(path: Path):
    """Parse (idx, x, y, w, h) from a filename following save_crop's naming
    convention. Returns a dict or None if the filename doesn't match."""
    m = REFERENCE_NAME_PATTERN.search(path.stem)
    if not m:
        return None
    return {
        'idx': int(m.group('idx')),
        'x': int(m.group('x')),
        'y': int(m.group('y')),
        'w': int(m.group('w')),
        'h': int(m.group('h')),
    }


def list_images_in_folder(folder: Path, recursive: bool) -> list[Path]:
    """Return sorted image paths under folder. When recursive, walks subfolders
    but skips any 'cropped' subfolder (crop output) to avoid re-processing it."""
    if recursive:
        paths = [
            p for p in folder.rglob('*')
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            and 'cropped' not in p.relative_to(folder).parts[:-1]
        ]
    else:
        paths = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        ]
    return sorted(paths)


def load_image_as_qpixmap(path: Path, raw_w: int = 0, raw_h: int = 0):
    """Return (QPixmap, np_array) for any supported format. np_array is the original pixel data."""
    ext = path.suffix.lower()
    if ext == '.raw':
        if raw_w <= 0 or raw_h <= 0:
            raise ValueError("RAW 파일은 Width/Height를 먼저 입력해야 합니다.")
        data = np.frombuffer(path.read_bytes(), dtype='<u2')
        expected = raw_w * raw_h
        if data.size != expected:
            raise ValueError(
                f"파일 크기({data.size} pixels)가 {raw_w}×{raw_h}={expected}와 맞지 않습니다."
            )
        arr = data.reshape((raw_h, raw_w))
        # Normalize to 8-bit for display
        mn, mx = arr.min(), arr.max()
        if mx > mn:
            arr8 = ((arr.astype(np.float32) - mn) / (mx - mn) * 255).astype(np.uint8)
        else:
            arr8 = np.zeros_like(arr, dtype=np.uint8)
        qimg = QImage(arr8.data, raw_w, raw_h, raw_w, QImage.Format_Grayscale8)
        return QPixmap.fromImage(qimg), arr
    else:
        pil = Image.open(str(path))
        # For multi-frame tiff take first frame
        if hasattr(pil, 'n_frames') and pil.n_frames > 1:
            pil.seek(0)
        mode = pil.mode
        arr = np.array(pil)
        if mode in ('L', 'I;16', 'I;16L'):
            if arr.dtype == np.uint16:
                mn, mx = arr.min(), arr.max()
                if mx > mn:
                    arr8 = ((arr.astype(np.float32) - mn) / (mx - mn) * 255).astype(np.uint8)
                else:
                    arr8 = np.zeros_like(arr, dtype=np.uint8)
                qimg = QImage(arr8.data, arr.shape[1], arr.shape[0], arr.shape[1], QImage.Format_Grayscale8)
            else:
                arr8 = arr.astype(np.uint8)
                qimg = QImage(arr8.data, arr.shape[1], arr.shape[0], arr.shape[1], QImage.Format_Grayscale8)
        elif mode == 'RGB':
            arr8 = arr
            h, w, _ = arr8.shape
            qimg = QImage(arr8.data, w, h, w * 3, QImage.Format_RGB888)
        elif mode == 'RGBA':
            arr8 = arr
            h, w, _ = arr8.shape
            qimg = QImage(arr8.data, w, h, w * 4, QImage.Format_RGBA8888)
        else:
            pil = pil.convert('RGB')
            arr = np.array(pil)
            h, w, _ = arr.shape
            qimg = QImage(arr.data, w, h, w * 3, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg.copy()), np.array(Image.open(str(path)))


def save_crop(src_path: Path, roi_idx: int, x: int, y: int, w: int, h: int,
              np_arr, raw_w: int = 0, raw_h: int = 0):
    """Crop np_arr at (x,y,w,h) and save to cropped/ subfolder."""
    out_dir = src_path.parent / 'cropped'
    out_dir.mkdir(exist_ok=True)

    stem = src_path.stem
    ext = src_path.suffix
    out_name = f"{stem}_{roi_idx}_x{x}y{y}w{w}h{h}{ext}"
    out_path = out_dir / out_name

    ext_lower = ext.lower()
    if ext_lower == '.raw':
        # np_arr is uint16 (H, W)
        crop = np_arr[y:y + h, x:x + w]
        crop.astype('<u2').tofile(str(out_path))
    else:
        pil_orig = Image.open(str(src_path))
        if hasattr(pil_orig, 'n_frames') and pil_orig.n_frames > 1:
            pil_orig.seek(0)
        crop = pil_orig.crop((x, y, x + w, y + h))
        if ext_lower in ('.tif', '.tiff'):
            crop.save(str(out_path), compression='tiff_lzw')
        else:
            crop.save(str(out_path))
    return out_path


class ROIItem(QGraphicsRectItem):
    """A ROI rectangle with a centered index label. Selectable via ImageViewer's click handling."""

    def __init__(self, idx: int, rect: QRectF):
        super().__init__(rect)
        self.idx = idx
        self._normal_pen = QPen(QColor(255, 80, 80), 2, Qt.SolidLine)
        self._normal_pen.setCosmetic(True)
        self._selected_pen = QPen(QColor(255, 230, 0), 3, Qt.SolidLine)
        self._selected_pen.setCosmetic(True)
        self.setPen(self._normal_pen)
        self.setBrush(QBrush(QColor(255, 80, 80, 40)))

        self._label = QGraphicsTextItem(str(idx), self)
        font = QFont('Arial', 18, QFont.Bold)
        self._label.setFont(font)
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        self._update_label()

    def setRect(self, rect: QRectF):
        super().setRect(rect)
        self._update_label()

    def set_idx(self, idx: int):
        self.idx = idx
        self._label.setPlainText(str(idx))
        self._update_label()

    def set_selected_style(self, selected: bool):
        self.setPen(self._selected_pen if selected else self._normal_pen)

    def _update_label(self):
        r = self.rect()
        br = self._label.boundingRect()
        self._label.setPos(
            r.x() + (r.width() - br.width()) / 2,
            r.y() + (r.height() - br.height()) / 2,
        )


class ImageViewer(QGraphicsView):
    """Zoomable/pannable viewer. Emits roi_drawn(idx, QRectF) on each ROI finish,
    and roi_selected(idx, x, y, w, h) when a ROI is clicked (idx=-1 on deselect)."""

    roi_drawn = pyqtSignal(int, QRectF)
    roi_selected = pyqtSignal(int, int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._roi_items: list[ROIItem] = []
        self._roi_count = 1
        self._next_roi_idx = 1
        self._selected_item: ROIItem | None = None

        # drawing state
        self._drawing = False
        self._draw_start: QPointF | None = None
        self._temp_rect: QGraphicsRectItem | None = None

        # panning state
        self._panning = False
        self._pan_start = None

    # ------------------------------------------------------------------ public

    def set_roi_count(self, n: int):
        """Update the target ROI count only. Does NOT clear existing ROIs."""
        self._roi_count = n
        self._recompute_next_idx()

    def clear_rois(self):
        for item in self._roi_items:
            self._scene.removeItem(item)
        self._roi_items.clear()
        self._selected_item = None
        self._next_roi_idx = 1

    def load_pixmap(self, pixmap: QPixmap):
        self._scene.clear()
        self._roi_items.clear()
        self._selected_item = None
        self._next_roi_idx = 1
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def get_rois(self) -> list[tuple[int, int, int, int, int]]:
        """Return list of (idx, x, y, w, h) in image pixel coords."""
        result = []
        for item in self._roi_items:
            r = item.rect()
            x = max(0, int(r.x()))
            y = max(0, int(r.y()))
            w = max(1, int(r.width()))
            h = max(1, int(r.height()))
            result.append((item.idx, x, y, w, h))
        result.sort(key=lambda t: t[0])
        return result

    def has_all_rois(self) -> bool:
        return len(self._roi_items) == self._roi_count

    def find_roi_by_idx(self, idx: int) -> "ROIItem | None":
        for item in self._roi_items:
            if item.idx == idx:
                return item
        return None

    def get_selected_idx(self):
        return self._selected_item.idx if self._selected_item else None

    def select_roi(self, idx: int):
        """Programmatically select (highlight) the ROI at idx, if it exists."""
        self._select_item(self.find_roi_by_idx(idx))

    def set_roi(self, idx: int, x: int, y: int, w: int, h: int) -> bool:
        """Create or replace the ROI at idx with the given pixel-coord rect
        (clamped to image bounds). Returns False if no image loaded or the
        clamped rect collapses to nothing."""
        if self._pixmap_item is None or w <= 0 or h <= 0:
            return False
        rect = self._clamp_rect(QRectF(x, y, w, h))
        if rect.width() < 1 or rect.height() < 1:
            return False

        existing = self.find_roi_by_idx(idx)
        if existing is not None:
            if self._selected_item is existing:
                self._selected_item = None
            self._scene.removeItem(existing)
            self._roi_items.remove(existing)

        roi = ROIItem(idx, rect)
        self._scene.addItem(roi)
        self._roi_items.append(roi)
        self._recompute_next_idx()
        return True

    def remove_roi(self, idx: int) -> bool:
        item = self.find_roi_by_idx(idx)
        if item is None:
            return False
        if self._selected_item is item:
            self._selected_item = None
        self._scene.removeItem(item)
        self._roi_items.remove(item)
        self._recompute_next_idx()
        return True

    # ------------------------------------------------------------------ internal helpers

    def _clamp_rect(self, rect: QRectF) -> QRectF:
        if self._pixmap_item:
            rect = rect.intersected(self._pixmap_item.boundingRect())
        return rect

    def _recompute_next_idx(self):
        used = {item.idx for item in self._roi_items}
        n = 1
        while n in used:
            n += 1
        self._next_roi_idx = n

    def _select_item(self, item: "ROIItem | None"):
        if self._selected_item is item:
            return
        if self._selected_item is not None:
            self._selected_item.set_selected_style(False)
        self._selected_item = item
        if item is not None:
            item.set_selected_style(True)
            r = item.rect()
            self.roi_selected.emit(item.idx, int(r.x()), int(r.y()), int(r.width()), int(r.height()))
        else:
            self.roi_selected.emit(-1, 0, 0, 0, 0)

    # ------------------------------------------------------------------ events

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton and self._pixmap_item:
            scene_pos = self.mapToScene(event.pos())

            # Hit-test existing ROIs (topmost/most-recently-added first) → select, don't draw
            hit = None
            for item in reversed(self._roi_items):
                if item.rect().contains(scene_pos):
                    hit = item
                    break
            if hit is not None:
                self._select_item(hit)
                return

            self._select_item(None)
            if self._next_roi_idx <= self._roi_count:
                self._drawing = True
                self._draw_start = scene_pos
                pen = QPen(QColor(255, 80, 80), 2, Qt.DashLine)
                pen.setCosmetic(True)
                self._temp_rect = QGraphicsRectItem(QRectF(self._draw_start, self._draw_start))
                self._temp_rect.setPen(pen)
                self._scene.addItem(self._temp_rect)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        if self._drawing and self._draw_start and self._temp_rect:
            end = self.mapToScene(event.pos())
            rect = QRectF(self._draw_start, end).normalized()
            self._temp_rect.setRect(rect)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            return
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            end = self.mapToScene(event.pos())
            rect = QRectF(self._draw_start, end).normalized()
            if self._temp_rect:
                self._scene.removeItem(self._temp_rect)
                self._temp_rect = None

            if rect.width() < 2 or rect.height() < 2:
                return

            idx = self._next_roi_idx
            x, y, w, h = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
            if self.set_roi(idx, x, y, w, h):
                item = self.find_roi_by_idx(idx)
                self.roi_drawn.emit(idx, item.rect())
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        # Space + drag → pan (alternative)
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Cropper')
        self.resize(1280, 800)

        self._folder: Path | None = None
        self._image_paths: list[Path] = []
        self._current_path: Path | None = None
        self._current_np = None
        self._raw_w = 0
        self._raw_h = 0
        self._reference_rois: list[dict] = []

        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        # ── Top toolbar ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        root_layout.addLayout(toolbar)

        btn_folder = QPushButton('📁 폴더 선택')
        btn_folder.setFixedHeight(32)
        btn_folder.clicked.connect(self._on_select_folder)
        toolbar.addWidget(btn_folder)

        btn_folder_recursive = QPushButton('📁 폴더 선택 (하위 폴더 포함)')
        btn_folder_recursive.setFixedHeight(32)
        btn_folder_recursive.clicked.connect(self._on_select_folder_recursive)
        toolbar.addWidget(btn_folder_recursive)

        toolbar.addWidget(QLabel('  ROI 개수:'))
        self._spin_roi = QSpinBox()
        self._spin_roi.setRange(1, 999)
        self._spin_roi.setValue(1)
        self._spin_roi.setFixedWidth(60)
        self._spin_roi.valueChanged.connect(self._on_roi_count_changed)
        toolbar.addWidget(self._spin_roi)

        # RAW dimensions group
        raw_group = QGroupBox('RAW 설정')
        raw_form = QFormLayout(raw_group)
        raw_form.setContentsMargins(6, 4, 6, 4)
        raw_form.setSpacing(4)
        self._edit_raw_w = QLineEdit('0')
        self._edit_raw_w.setFixedWidth(70)
        self._edit_raw_w.setValidator(QIntValidator(1, 99999))
        self._edit_raw_h = QLineEdit('0')
        self._edit_raw_h.setFixedWidth(70)
        self._edit_raw_h.setValidator(QIntValidator(1, 99999))
        self._edit_raw_w.textChanged.connect(self._on_raw_dim_changed)
        self._edit_raw_h.textChanged.connect(self._on_raw_dim_changed)
        raw_form.addRow('W:', self._edit_raw_w)
        raw_form.addRow('H:', self._edit_raw_h)
        toolbar.addWidget(raw_group)

        toolbar.addStretch()

        self._lbl_status = QLabel('폴더를 선택하세요.')
        toolbar.addWidget(self._lbl_status)

        # ── Splitter: file list | viewer ─────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        # File list
        list_frame = QFrame()
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(QLabel('이미지 목록 (헤더 클릭 시 정렬)'))
        self._file_table = QTableWidget(0, 2)
        self._file_table.setHorizontalHeaderLabels(['파일명', '폴더'])
        self._file_table.setMinimumWidth(180)
        self._file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._file_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._file_table.verticalHeader().setVisible(False)
        self._file_table.setSortingEnabled(True)
        self._file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._file_table.currentCellChanged.connect(self._on_file_selected)
        list_layout.addWidget(self._file_table, 1)

        # Reference images (parse XYWH from filename → load as ROIs)
        list_layout.addWidget(QLabel('레퍼런스 이미지 (파일명에서 XYWH 파싱)'))
        self._ref_list = QListWidget()
        self._ref_list.setMinimumWidth(180)
        self._ref_list.setMaximumHeight(160)
        self._ref_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._ref_list.setToolTip('선택 없이 "ROI 불러오기"를 누르면 목록 전체가 적용됩니다.')
        list_layout.addWidget(self._ref_list)

        ref_btn_row = QHBoxLayout()
        btn_ref_add = QPushButton('추가')
        btn_ref_add.clicked.connect(self._on_add_reference)
        btn_ref_clear = QPushButton('목록 지우기')
        btn_ref_clear.clicked.connect(self._on_clear_reference)
        ref_btn_row.addWidget(btn_ref_add)
        ref_btn_row.addWidget(btn_ref_clear)
        list_layout.addLayout(ref_btn_row)

        btn_ref_load = QPushButton('ROI 불러오기')
        btn_ref_load.setStyleSheet('background:#8a4fd0;color:white;font-weight:bold;')
        btn_ref_load.clicked.connect(self._on_load_reference_rois)
        list_layout.addWidget(btn_ref_load)

        splitter.addWidget(list_frame)

        # Viewer
        viewer_frame = QFrame()
        viewer_layout = QVBoxLayout(viewer_frame)
        viewer_layout.setContentsMargins(0, 0, 0, 0)

        self._viewer = ImageViewer()
        self._viewer.roi_drawn.connect(self._on_roi_drawn)
        self._viewer.roi_selected.connect(self._on_roi_selected)
        viewer_layout.addWidget(self._viewer, 1)

        # ROI status label
        self._lbl_roi = QLabel('ROI: 0 / 1')
        self._lbl_roi.setAlignment(Qt.AlignCenter)
        viewer_layout.addWidget(self._lbl_roi)

        # ROI 편집: 캔버스에서 ROI를 클릭하면 아래 값이 채워짐. 번호를 바꿔 [적용]하면
        # 그 번호로 재지정(덮어쓰기)되고, XYWH를 바꿔 [적용]하면 좌표가 수정된다.
        roi_edit_group = QGroupBox('ROI 편집 (선택 후 수정 / 숫자로 직접 지정)')
        roi_edit_layout = QHBoxLayout(roi_edit_group)
        roi_edit_layout.setContentsMargins(6, 4, 6, 4)

        def _labeled_spin(label, minv, maxv):
            roi_edit_layout.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(minv, maxv)
            spin.setFixedWidth(70)
            roi_edit_layout.addWidget(spin)
            return spin

        self._spin_edit_idx = _labeled_spin('번호:', 1, 999)
        self._spin_edit_x = _labeled_spin('X:', 0, 999999)
        self._spin_edit_y = _labeled_spin('Y:', 0, 999999)
        self._spin_edit_w = _labeled_spin('W:', 1, 999999)
        self._spin_edit_h = _labeled_spin('H:', 1, 999999)

        btn_apply_roi = QPushButton('적용 (생성/수정)')
        btn_apply_roi.clicked.connect(self._on_apply_manual_roi)
        btn_delete_roi = QPushButton('선택 ROI 삭제')
        btn_delete_roi.clicked.connect(self._on_delete_roi)
        roi_edit_layout.addWidget(btn_apply_roi)
        roi_edit_layout.addWidget(btn_delete_roi)
        roi_edit_layout.addStretch()

        viewer_layout.addWidget(roi_edit_group)

        # Crop buttons
        btn_row = QHBoxLayout()
        btn_clear = QPushButton('ROI 초기화')
        btn_clear.clicked.connect(self._on_clear_roi)
        btn_apply_one = QPushButton('현재 이미지에 적용')
        btn_apply_one.setStyleSheet('background:#2a7fcf;color:white;font-weight:bold;')
        btn_apply_one.clicked.connect(lambda: self._on_crop(all_files=False))
        btn_apply_all = QPushButton('폴더 전체에 적용')
        btn_apply_all.setStyleSheet('background:#2ca05a;color:white;font-weight:bold;')
        btn_apply_all.clicked.connect(lambda: self._on_crop(all_files=True))
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(btn_apply_one)
        btn_row.addWidget(btn_apply_all)
        viewer_layout.addLayout(btn_row)

        splitter.addWidget(viewer_frame)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 1060])

    # ------------------------------------------------------------------ slots

    def _on_select_folder(self):
        self._load_folder(recursive=False)

    def _on_select_folder_recursive(self):
        self._load_folder(recursive=True)

    def _load_folder(self, recursive: bool):
        folder = QFileDialog.getExistingDirectory(self, '폴더 선택', str(self._folder or Path.home()))
        if not folder:
            return
        self._folder = Path(folder)
        self._image_paths = list_images_in_folder(self._folder, recursive)

        self._file_table.setSortingEnabled(False)
        self._file_table.setRowCount(len(self._image_paths))
        for row, p in enumerate(self._image_paths):
            rel_parent = p.relative_to(self._folder).parent
            folder_txt = '' if str(rel_parent) == '.' else str(rel_parent)
            name_item = QTableWidgetItem(p.name)
            name_item.setData(Qt.UserRole, str(p))
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(folder_txt))
        self._file_table.setSortingEnabled(True)

        self._lbl_status.setText(f'{len(self._image_paths)}개 이미지 로드됨')
        if self._image_paths:
            self._file_table.setCurrentCell(0, 0)

    def _on_file_selected(self, row: int, column: int = 0, prev_row: int = -1, prev_column: int = -1):
        if row < 0:
            return
        item = self._file_table.item(row, 0)
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        self._current_path = path
        self._viewer.clear_rois()
        self._update_roi_label()
        try:
            pixmap, np_arr = load_image_as_qpixmap(path, self._raw_w, self._raw_h)
            self._current_np = np_arr
            self._viewer.load_pixmap(pixmap)
            self._lbl_status.setText(path.name)
        except Exception as e:
            QMessageBox.warning(self, '로드 오류', str(e))

    def _on_roi_count_changed(self, val: int):
        self._viewer.set_roi_count(val)
        self._update_roi_label()

    def _on_add_reference(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, '레퍼런스 이미지 선택 (파일명에서 XYWH 파싱)',
            str(self._folder or Path.home()),
            '이미지 파일 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;모든 파일 (*)'
        )
        if not files:
            return
        existing = {e['path'] for e in self._reference_rois}
        for f in files:
            p = Path(f)
            if str(p) in existing:
                continue
            parsed = parse_reference_filename(p)
            entry = {'path': str(p), 'name': p.name, 'valid': parsed is not None}
            if parsed:
                entry.update(parsed)
            self._reference_rois.append(entry)
        self._refresh_reference_list()

    def _refresh_reference_list(self):
        self._ref_list.clear()
        for e in self._reference_rois:
            if e['valid']:
                text = f"[{e['idx']}] {e['name']}  (x{e['x']} y{e['y']} w{e['w']} h{e['h']})"
            else:
                text = f"⚠ 파싱 실패: {e['name']}"
            self._ref_list.addItem(QListWidgetItem(text))

    def _on_clear_reference(self):
        self._reference_rois.clear()
        self._ref_list.clear()

    def _on_load_reference_rois(self):
        if not self._current_path:
            QMessageBox.warning(self, '경고', '이미지를 먼저 선택하세요.')
            return
        if not self._reference_rois:
            QMessageBox.warning(self, '경고', '레퍼런스 이미지를 먼저 추가하세요.')
            return

        selected_rows = {i.row() for i in self._ref_list.selectedIndexes()}
        targets = [self._reference_rois[r] for r in selected_rows] if selected_rows \
            else self._reference_rois
        valid_targets = [e for e in targets if e['valid']]

        if not valid_targets:
            QMessageBox.warning(self, '경고', '불러올 수 있는 레퍼런스 ROI가 없습니다 (파일명 파싱 실패).')
            return

        applied = 0
        max_idx = 0
        for e in valid_targets:
            if self._viewer.set_roi(e['idx'], e['x'], e['y'], e['w'], e['h']):
                applied += 1
                max_idx = max(max_idx, e['idx'])

        if max_idx:
            self._bump_roi_count_if_needed(max_idx)
        self._update_roi_label()

        skipped = len(valid_targets) - applied
        msg = f'{applied}개 ROI를 불러왔습니다.'
        if skipped:
            msg += f'\n({skipped}개는 이미지 범위를 벗어나 제외됨)'
        QMessageBox.information(self, '완료', msg)

    def _on_raw_dim_changed(self):
        try:
            self._raw_w = int(self._edit_raw_w.text())
        except ValueError:
            self._raw_w = 0
        try:
            self._raw_h = int(self._edit_raw_h.text())
        except ValueError:
            self._raw_h = 0

    def _on_roi_drawn(self, idx: int, rect: QRectF):
        self._update_roi_label()

    def _on_clear_roi(self):
        self._viewer.clear_rois()
        self._update_roi_label()

    def _on_roi_selected(self, idx: int, x: int, y: int, w: int, h: int):
        if idx >= 0:
            self._spin_edit_idx.setValue(idx)
            self._spin_edit_x.setValue(x)
            self._spin_edit_y.setValue(y)
            self._spin_edit_w.setValue(w)
            self._spin_edit_h.setValue(h)
        self._update_roi_label()

    def _bump_roi_count_if_needed(self, idx: int):
        """Grow the ROI-count spinbox if idx exceeds it. set_roi_count no longer
        clears existing ROIs, so this is safe to call after adding one."""
        if idx > self._spin_roi.value():
            self._spin_roi.setValue(idx)

    def _on_apply_manual_roi(self):
        if not self._current_path:
            QMessageBox.warning(self, '경고', '이미지를 먼저 선택하세요.')
            return
        idx = self._spin_edit_idx.value()
        x = self._spin_edit_x.value()
        y = self._spin_edit_y.value()
        w = self._spin_edit_w.value()
        h = self._spin_edit_h.value()
        if not self._viewer.set_roi(idx, x, y, w, h):
            QMessageBox.warning(self, '경고', '지정한 좌표가 이미지 범위를 벗어났거나 잘못되었습니다.')
            return
        self._bump_roi_count_if_needed(idx)
        self._viewer.select_roi(idx)
        self._update_roi_label()

    def _on_delete_roi(self):
        idx = self._spin_edit_idx.value()
        if self._viewer.remove_roi(idx):
            self._update_roi_label()
        else:
            QMessageBox.information(self, '알림', f'{idx}번 ROI가 존재하지 않습니다.')

    def _update_roi_label(self):
        n = len(self._viewer._roi_items)
        total = self._spin_roi.value()
        next_idx = self._viewer._next_roi_idx
        next_txt = f'{next_idx}번 드래그' if next_idx <= total else '없음(개수 초과)'
        sel = self._viewer.get_selected_idx()
        sel_txt = f'{sel}번 선택됨' if sel is not None else '선택 없음'
        self._lbl_roi.setText(f'ROI: {n} / {total}   다음: {next_txt}   ({sel_txt})')

    def _on_crop(self, all_files: bool):
        rois = self._viewer.get_rois()
        if not rois:
            QMessageBox.warning(self, '경고', 'ROI를 먼저 선택하세요.')
            return
        if not self._current_path:
            QMessageBox.warning(self, '경고', '이미지를 먼저 선택하세요.')
            return

        targets = self._image_paths if all_files else [self._current_path]

        total_ops = len(targets) * len(rois)
        progress = QProgressDialog('크롭 중...', '취소', 0, total_ops, self)
        progress.setWindowTitle('Image Cropper')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        done = 0
        errors = []
        for img_path in targets:
            if progress.wasCanceled():
                break
            try:
                if img_path.suffix.lower() == '.raw':
                    _, np_arr = load_image_as_qpixmap(img_path, self._raw_w, self._raw_h)
                else:
                    np_arr = None
                for idx, x, y, w, h in rois:
                    if progress.wasCanceled():
                        break
                    try:
                        out = save_crop(img_path, idx, x, y, w, h, np_arr, self._raw_w, self._raw_h)
                    except Exception as e:
                        errors.append(f'{img_path.name}: {e}')
                    done += 1
                    progress.setValue(done)
            except Exception as e:
                errors.append(f'{img_path.name}: {e}')
                done += len(rois)
                progress.setValue(done)

        progress.close()

        out_dir = self._current_path.parent / 'cropped'
        if errors:
            QMessageBox.warning(self, '완료 (오류 있음)',
                                f'완료. 오류:\n' + '\n'.join(errors))
        else:
            scope = '폴더 전체' if all_files else '현재 이미지'
            QMessageBox.information(self, '완료',
                                    f'{scope} 크롭 완료!\n저장 위치: {out_dir}')


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
