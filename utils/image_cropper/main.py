import sys
import os
import struct
import numpy as np
from pathlib import Path
from PIL import Image, ImageSequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QSpinBox, QFileDialog, QMessageBox, QSizePolicy, QLineEdit,
    QGroupBox, QFormLayout, QSplitter, QFrame, QProgressDialog
)
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPixmap, QImage, QPen, QColor, QBrush, QFont, QIntValidator, QPainter
)

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.raw'}


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
    """A draggable ROI rectangle with a centered index label."""

    def __init__(self, idx: int, rect: QRectF):
        super().__init__(rect)
        pen = QPen(QColor(255, 80, 80), 2, Qt.SolidLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(255, 80, 80, 40)))

        self._label = QGraphicsTextItem(str(idx), self)
        font = QFont('Arial', 18, QFont.Bold)
        self._label.setFont(font)
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        self._update_label()

    def setRect(self, rect: QRectF):
        super().setRect(rect)
        self._update_label()

    def _update_label(self):
        r = self.rect()
        br = self._label.boundingRect()
        self._label.setPos(
            r.x() + (r.width() - br.width()) / 2,
            r.y() + (r.height() - br.height()) / 2,
        )


class ImageViewer(QGraphicsView):
    """Zoomable/pannable viewer. Emits roi_drawn(idx, QRectF) on each ROI finish."""

    roi_drawn = pyqtSignal(int, QRectF)

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

        # drawing state
        self._drawing = False
        self._draw_start: QPointF | None = None
        self._temp_rect: QGraphicsRectItem | None = None

        # panning state
        self._panning = False
        self._pan_start = None

    # ------------------------------------------------------------------ public

    def set_roi_count(self, n: int):
        self._roi_count = n
        self.clear_rois()

    def clear_rois(self):
        for item in self._roi_items:
            self._scene.removeItem(item)
        self._roi_items.clear()
        self._next_roi_idx = 1

    def load_pixmap(self, pixmap: QPixmap):
        self._scene.clear()
        self._roi_items.clear()
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
            idx = int(item._label.toPlainText())
            x = max(0, int(r.x()))
            y = max(0, int(r.y()))
            w = max(1, int(r.width()))
            h = max(1, int(r.height()))
            result.append((idx, x, y, w, h))
        result.sort(key=lambda t: t[0])
        return result

    def has_all_rois(self) -> bool:
        return len(self._roi_items) == self._roi_count

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
            if self._next_roi_idx <= self._roi_count:
                self._drawing = True
                self._draw_start = self.mapToScene(event.pos())
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

            # Clamp to image bounds
            if self._pixmap_item:
                img_rect = self._pixmap_item.boundingRect()
                rect = rect.intersected(img_rect)

            idx = self._next_roi_idx

            # Replace existing ROI with same index if present
            existing = [i for i, item in enumerate(self._roi_items)
                        if int(item._label.toPlainText()) == idx]
            for i in reversed(existing):
                self._scene.removeItem(self._roi_items[i])
                self._roi_items.pop(i)

            roi = ROIItem(idx, rect)
            self._scene.addItem(roi)
            self._roi_items.append(roi)
            self._next_roi_idx = idx + 1
            self.roi_drawn.emit(idx, rect)
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

        toolbar.addWidget(QLabel('  ROI 개수:'))
        self._spin_roi = QSpinBox()
        self._spin_roi.setRange(1, 20)
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
        list_layout.addWidget(QLabel('이미지 목록'))
        self._file_list = QListWidget()
        self._file_list.setMinimumWidth(180)
        self._file_list.currentRowChanged.connect(self._on_file_selected)
        list_layout.addWidget(self._file_list)
        splitter.addWidget(list_frame)

        # Viewer
        viewer_frame = QFrame()
        viewer_layout = QVBoxLayout(viewer_frame)
        viewer_layout.setContentsMargins(0, 0, 0, 0)

        self._viewer = ImageViewer()
        self._viewer.roi_drawn.connect(self._on_roi_drawn)
        viewer_layout.addWidget(self._viewer, 1)

        # ROI status label
        self._lbl_roi = QLabel('ROI: 0 / 1')
        self._lbl_roi.setAlignment(Qt.AlignCenter)
        viewer_layout.addWidget(self._lbl_roi)

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
        folder = QFileDialog.getExistingDirectory(self, '폴더 선택', str(self._folder or Path.home()))
        if not folder:
            return
        self._folder = Path(folder)
        self._image_paths = sorted(
            p for p in self._folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        )
        self._file_list.clear()
        for p in self._image_paths:
            self._file_list.addItem(p.name)
        self._lbl_status.setText(f'{len(self._image_paths)}개 이미지 로드됨')
        if self._image_paths:
            self._file_list.setCurrentRow(0)

    def _on_file_selected(self, row: int):
        if row < 0 or row >= len(self._image_paths):
            return
        path = self._image_paths[row]
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

    def _update_roi_label(self):
        n = len(self._viewer._roi_items)
        total = self._spin_roi.value()
        self._lbl_roi.setText(f'ROI: {n} / {total}  (다음: {min(n+1, total)}번 드래그)')

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
