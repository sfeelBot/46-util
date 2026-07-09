import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QSpinBox, QSlider, QComboBox,
    QFileDialog, QMessageBox, QLineEdit, QGroupBox, QFormLayout,
    QSplitter, QFrame, QProgressDialog, QCheckBox,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import QPen, QColor, QPainter, QIntValidator

import masking


class ZoomPanView(QGraphicsView):
    """휠 줌 + 중간버튼 팬을 지원하는 기본 뷰어."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        self._pixmap_item = None
        self._panning = False
        self._pan_start = None

    def load_pixmap(self, pixmap, fit=True):
        self._scene.clear()
        self._pixmap_item = QGraphicsPixmapItem(pixmap)
        self._scene.addItem(self._pixmap_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        if fit:
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def update_pixmap(self, pixmap):
        """줌/팬 상태를 유지한 채 픽스맵만 교체 (실시간 미리보기용)."""
        if self._pixmap_item is None:
            self.load_pixmap(pixmap)
        else:
            self._pixmap_item.setPixmap(pixmap)

    def image_size(self):
        if self._pixmap_item is None:
            return 0, 0
        pm = self._pixmap_item.pixmap()
        return pm.width(), pm.height()

    def clear(self):
        self._scene.clear()
        self._pixmap_item = None

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            return
        super().mouseReleaseEvent(event)


class BeforeViewer(ZoomPanView):
    """원본 표시 + y 경계선(드래그 가능) + 샘플 ROI 드래그 + 스포이드 클릭."""

    y_changed = pyqtSignal(int)
    roi_sampled = pyqtSignal(int, int, int, int)
    pixel_picked = pyqtSignal(int, int)

    LINE_HIT_MARGIN = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = 'line'  # 'line' | 'sample_roi' | 'eyedropper'
        self._y = 0
        self._line_item = None
        self._dragging_line = False
        self._roi_drawing = False
        self._roi_start = None
        self._temp_roi_item = None
        self._sample_rect_item = None

    def set_mode(self, mode: str):
        self._mode = mode
        self.setCursor(Qt.CrossCursor if mode != 'line' else Qt.ArrowCursor)

    def clear(self):
        super().clear()
        self._line_item = None
        self._sample_rect_item = None
        self._temp_roi_item = None
        self._dragging_line = False
        self._roi_drawing = False

    def load_pixmap(self, pixmap, fit=True):
        super().load_pixmap(pixmap, fit=fit)
        self._sample_rect_item = None
        self._add_line_item()

    def set_y(self, y: int):
        self._y = y
        self._update_line_pos()

    def _add_line_item(self):
        if self._pixmap_item is None:
            return
        w, _ = self.image_size()
        pen = QPen(QColor(255, 40, 40), 2, Qt.SolidLine)
        pen.setCosmetic(True)
        self._line_item = self._scene.addLine(0, self._y, w, self._y, pen)
        self._line_item.setZValue(10)

    def _update_line_pos(self):
        if self._line_item and self._pixmap_item:
            w, _ = self.image_size()
            self._line_item.setLine(0, self._y, w, self._y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton and self._pixmap_item:
            scene_pos = self.mapToScene(event.pos())
            w, h = self.image_size()

            if self._mode == 'eyedropper':
                x, y = int(scene_pos.x()), int(scene_pos.y())
                if 0 <= x < w and 0 <= y < h:
                    self.pixel_picked.emit(x, y)
                self.set_mode('line')
                return

            if self._mode == 'sample_roi':
                self._roi_drawing = True
                self._roi_start = scene_pos
                pen = QPen(QColor(255, 210, 0), 2, Qt.DashLine)
                pen.setCosmetic(True)
                self._temp_roi_item = self._scene.addRect(QRectF(scene_pos, scene_pos), pen)
                return

            # mode == 'line': 선 근처를 클릭했을 때만 드래그 시작
            line_view_y = self.mapFromScene(QPointF(0, self._y)).y()
            if abs(event.pos().y() - line_view_y) <= self.LINE_HIT_MARGIN:
                self._dragging_line = True
                self.setCursor(Qt.SizeVerCursor)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging_line:
            scene_pos = self.mapToScene(event.pos())
            _, h = self.image_size()
            y = int(max(0, min(h, scene_pos.y())))
            self.set_y(y)
            self.y_changed.emit(y)
            return
        if self._roi_drawing and self._roi_start is not None and self._temp_roi_item is not None:
            end = self.mapToScene(event.pos())
            rect = QRectF(self._roi_start, end).normalized()
            self._temp_roi_item.setRect(rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging_line:
            self._dragging_line = False
            self.setCursor(Qt.ArrowCursor)
            return
        if event.button() == Qt.LeftButton and self._roi_drawing:
            self._roi_drawing = False
            end = self.mapToScene(event.pos())
            rect = QRectF(self._roi_start, end).normalized()
            if self._temp_roi_item is not None:
                self._scene.removeItem(self._temp_roi_item)
                self._temp_roi_item = None
            w, h = self.image_size()
            rect = rect.intersected(QRectF(0, 0, w, h))
            if rect.width() >= 2 and rect.height() >= 2:
                rx, ry = int(rect.x()), int(rect.y())
                rw, rh = int(rect.width()), int(rect.height())
                self.roi_sampled.emit(rx, ry, rw, rh)
                self._show_sample_rect(rx, ry, rw, rh)
            self.set_mode('line')
            return
        super().mouseReleaseEvent(event)

    def _show_sample_rect(self, x, y, w, h):
        if self._sample_rect_item is not None:
            self._scene.removeItem(self._sample_rect_item)
        pen = QPen(QColor(255, 210, 0), 2, Qt.SolidLine)
        pen.setCosmetic(True)
        self._sample_rect_item = self._scene.addRect(QRectF(x, y, w, h), pen)
        self._sample_rect_item.setZValue(9)


MODE_LABELS = [
    ('black', '검정'),
    ('white', '흰색'),
    ('gaussian', '가우시안 블러'),
    ('mean', '선택 영역 평균값'),
    ('eyedropper', '스포이드'),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Y-Axis Masker')
        self.resize(1400, 860)

        self._folder: Path = None
        self._image_paths: list = []
        self._current_path: Path = None
        self._current_arr = None
        self._display_mn = 0.0
        self._display_mx = 255.0
        self._raw_w = 0
        self._raw_h = 0

        self._mask_y = 0
        self._mask_mode = 'black'
        self._gaussian_sigma = 25
        self._fill_value = None

        self._syncing = False

        self._build_ui()
        self._update_mode_controls()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 상단 툴바 ────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        btn_folder = QPushButton('📁 폴더 선택')
        btn_folder.setFixedHeight(32)
        btn_folder.clicked.connect(self._on_select_folder)
        toolbar.addWidget(btn_folder)

        self._chk_recursive = QCheckBox('하위 폴더 포함')
        toolbar.addWidget(self._chk_recursive)

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

        # ── 좌측: 파일 목록 | 중앙: 뷰어+컨트롤 ─────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # 파일 목록
        list_frame = QFrame()
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(QLabel('이미지 목록'))

        self._edit_search = QLineEdit()
        self._edit_search.setPlaceholderText('파일명 검색...')
        self._edit_search.textChanged.connect(self._on_search_changed)
        list_layout.addWidget(self._edit_search)

        self._file_list = QListWidget()
        self._file_list.setMinimumWidth(220)
        self._file_list.currentRowChanged.connect(self._on_file_selected)
        list_layout.addWidget(self._file_list, 1)

        chk_row = QHBoxLayout()
        btn_check_all = QPushButton('전체 체크')
        btn_check_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_uncheck_all = QPushButton('전체 해제')
        btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))
        chk_row.addWidget(btn_check_all)
        chk_row.addWidget(btn_uncheck_all)
        list_layout.addLayout(chk_row)

        del_row = QHBoxLayout()
        btn_delete_checked = QPushButton('선택 삭제 (체크된 항목)')
        btn_delete_checked.clicked.connect(self._on_delete_checked)
        btn_delete_all = QPushButton('전체 삭제')
        btn_delete_all.setStyleSheet('color:#b00020;')
        btn_delete_all.clicked.connect(self._on_delete_all)
        del_row.addWidget(btn_delete_checked)
        del_row.addWidget(btn_delete_all)
        list_layout.addLayout(del_row)

        splitter.addWidget(list_frame)

        # 뷰어 + 컨트롤
        center_frame = QFrame()
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(0, 0, 0, 0)

        viewers_row = QHBoxLayout()
        before_col = QVBoxLayout()
        before_col.addWidget(QLabel('Before (원본 + y 경계선, 드래그 가능)'))
        self._before_viewer = BeforeViewer()
        self._before_viewer.y_changed.connect(self._on_line_dragged)
        self._before_viewer.roi_sampled.connect(self._on_roi_sampled)
        self._before_viewer.pixel_picked.connect(self._on_pixel_picked)
        before_col.addWidget(self._before_viewer, 1)
        viewers_row.addLayout(before_col, 1)

        after_col = QVBoxLayout()
        after_col.addWidget(QLabel('After (마스킹 미리보기)'))
        self._after_viewer = ZoomPanView()
        after_col.addWidget(self._after_viewer, 1)
        viewers_row.addLayout(after_col, 1)

        center_layout.addLayout(viewers_row, 1)

        # y 컨트롤
        y_group = QGroupBox('y 경계선 위치')
        y_layout = QHBoxLayout(y_group)
        y_layout.setContentsMargins(6, 4, 6, 4)
        y_layout.addWidget(QLabel('y:'))
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 0)
        self._spin_y.setFixedWidth(80)
        self._spin_y.valueChanged.connect(self._on_y_spin_changed)
        y_layout.addWidget(self._spin_y)
        self._slider_y = QSlider(Qt.Horizontal)
        self._slider_y.setRange(0, 0)
        self._slider_y.valueChanged.connect(self._on_y_slider_changed)
        y_layout.addWidget(self._slider_y, 1)
        center_layout.addWidget(y_group)

        # 마스킹 모드 컨트롤
        mode_group = QGroupBox('마스킹 채우기 방식')
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(6, 4, 6, 4)

        self._combo_mode = QComboBox()
        for key, label in MODE_LABELS:
            self._combo_mode.addItem(label, key)
        self._combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self._combo_mode)

        mode_layout.addWidget(QLabel('가우시안 강도:'))
        self._slider_sigma = QSlider(Qt.Horizontal)
        self._slider_sigma.setRange(1, 150)
        self._slider_sigma.setValue(self._gaussian_sigma)
        self._slider_sigma.valueChanged.connect(self._on_sigma_changed)
        mode_layout.addWidget(self._slider_sigma, 1)
        self._lbl_sigma = QLabel(str(self._gaussian_sigma))
        self._lbl_sigma.setFixedWidth(30)
        mode_layout.addWidget(self._lbl_sigma)

        self._btn_sample_roi = QPushButton('샘플 영역 지정')
        self._btn_sample_roi.clicked.connect(self._on_start_sample_roi)
        mode_layout.addWidget(self._btn_sample_roi)

        self._btn_eyedropper = QPushButton('색상 추출')
        self._btn_eyedropper.clicked.connect(self._on_start_eyedropper)
        mode_layout.addWidget(self._btn_eyedropper)

        self._lbl_fill = QLabel('샘플 값: 미지정')
        mode_layout.addWidget(self._lbl_fill)

        center_layout.addWidget(mode_group)

        # 처리 버튼
        btn_row = QHBoxLayout()
        btn_apply_one = QPushButton('현재 이미지 적용')
        btn_apply_one.setStyleSheet('background:#2a7fcf;color:white;font-weight:bold;')
        btn_apply_one.clicked.connect(lambda: self._on_apply(scope='current'))
        btn_apply_all = QPushButton('폴더 전체 적용')
        btn_apply_all.setStyleSheet('background:#2ca05a;color:white;font-weight:bold;')
        btn_apply_all.clicked.connect(lambda: self._on_apply(scope='all'))
        btn_apply_checked = QPushButton('체크된 이미지만 적용')
        btn_apply_checked.setStyleSheet('background:#c07a1e;color:white;font-weight:bold;')
        btn_apply_checked.clicked.connect(lambda: self._on_apply(scope='checked'))
        btn_row.addStretch()
        btn_row.addWidget(btn_apply_one)
        btn_row.addWidget(btn_apply_all)
        btn_row.addWidget(btn_apply_checked)
        center_layout.addLayout(btn_row)

        splitter.addWidget(center_frame)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 1160])

    # ------------------------------------------------------------------ 폴더/파일 목록

    def _on_select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '폴더 선택', str(self._folder or Path.home()))
        if not folder:
            return
        self._folder = Path(folder)
        recursive = self._chk_recursive.isChecked()
        found = masking.list_images(self._folder, recursive=recursive)

        existing = {p.resolve() for p in self._image_paths}
        added = 0
        for p in found:
            resolved = p.resolve()
            if resolved in existing:
                continue
            existing.add(resolved)
            self._image_paths.append(p)
            item = QListWidgetItem(p.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setToolTip(str(p))
            self._file_list.addItem(item)
            added += 1

        self._lbl_status.setText(f'총 {len(self._image_paths)}개 이미지 (이번에 {added}개 추가됨)')
        if self._file_list.currentRow() < 0 and self._image_paths:
            self._file_list.setCurrentRow(0)

    def _on_delete_checked(self):
        rows = [i for i in range(self._file_list.count())
                if self._file_list.item(i).checkState() == Qt.Checked]
        if not rows:
            QMessageBox.information(self, '알림', '체크된 이미지가 없습니다.')
            return
        self._remove_rows(rows)

    def _on_delete_all(self):
        if not self._image_paths:
            return
        reply = QMessageBox.question(
            self, '전체 삭제',
            f'리스트의 이미지 {len(self._image_paths)}개를 목록에서 모두 제거할까요?\n'
            '(원본 파일은 삭제되지 않습니다)',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._remove_rows(list(range(self._file_list.count())))

    def _remove_rows(self, rows: list):
        """리스트/메모리에서만 제거. 원본 파일은 건드리지 않는다."""
        removed_current = False
        for row in sorted(set(rows), reverse=True):
            path = self._image_paths[row]
            if self._current_path is not None and path == self._current_path:
                removed_current = True
            del self._image_paths[row]
            self._file_list.takeItem(row)

        if removed_current or not self._image_paths:
            self._current_path = None
            self._current_arr = None
            self._before_viewer.clear()
            self._after_viewer.clear()

        self._lbl_status.setText(f'총 {len(self._image_paths)}개 이미지')
        if self._image_paths and self._current_path is None:
            # takeItem() 이후 currentRow가 이미 0으로 맞춰져 있으면 setCurrentRow(0)이
            # currentRowChanged를 emit하지 않아 새 이미지가 로드되지 않을 수 있음.
            # 시그널에 의존하지 않고 직접 로드해 확실하게 갱신한다.
            self._file_list.blockSignals(True)
            self._file_list.setCurrentRow(0)
            self._file_list.blockSignals(False)
            self._current_path = self._image_paths[0]
            self._load_current_image()

    def _on_search_changed(self, text: str):
        text = text.lower().strip()
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _set_all_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def _on_raw_dim_changed(self):
        try:
            self._raw_w = int(self._edit_raw_w.text())
        except ValueError:
            self._raw_w = 0
        try:
            self._raw_h = int(self._edit_raw_h.text())
        except ValueError:
            self._raw_h = 0
        if self._current_path is not None and self._current_path.suffix.lower() == '.raw':
            self._load_current_image()

    def _on_file_selected(self, row: int):
        if row < 0 or row >= len(self._image_paths):
            return
        self._current_path = self._image_paths[row]
        self._load_current_image()

    def _load_current_image(self):
        try:
            arr = masking.load_array(self._current_path, self._raw_w, self._raw_h)
        except Exception as e:
            QMessageBox.warning(self, '로드 오류', str(e))
            return
        self._current_arr = arr
        self._display_mn, self._display_mx = masking.get_display_range(arr)
        h = arr.shape[0]

        self._syncing = True
        self._spin_y.setRange(0, h)
        self._slider_y.setRange(0, h)
        self._mask_y = min(self._mask_y, h)
        self._spin_y.setValue(self._mask_y)
        self._slider_y.setValue(self._mask_y)
        self._syncing = False

        pixmap = masking.array_to_qpixmap(arr, self._display_mn, self._display_mx)
        self._before_viewer.load_pixmap(pixmap)
        self._before_viewer.set_y(self._mask_y)
        self._after_viewer.load_pixmap(pixmap)
        self._lbl_status.setText(self._current_path.name)
        self._update_preview()

    # ------------------------------------------------------------------ y 컨트롤 동기화

    def _set_mask_y(self, y: int):
        if self._syncing:
            return
        self._syncing = True
        self._mask_y = y
        self._spin_y.setValue(y)
        self._slider_y.setValue(y)
        self._before_viewer.set_y(y)
        self._syncing = False
        self._update_preview()

    def _on_y_spin_changed(self, val: int):
        self._set_mask_y(val)

    def _on_y_slider_changed(self, val: int):
        self._set_mask_y(val)

    def _on_line_dragged(self, y: int):
        self._set_mask_y(y)

    # ------------------------------------------------------------------ 마스킹 모드

    def _current_mode_key(self) -> str:
        return self._combo_mode.currentData()

    def _update_mode_controls(self):
        mode = self._current_mode_key()
        self._slider_sigma.setEnabled(mode == 'gaussian')
        self._lbl_sigma.setEnabled(mode == 'gaussian')
        self._btn_sample_roi.setEnabled(mode == 'mean')
        self._btn_eyedropper.setEnabled(mode == 'eyedropper')

    def _on_mode_changed(self):
        self._mask_mode = self._current_mode_key()
        self._fill_value = None
        self._lbl_fill.setText('샘플 값: 미지정')
        self._update_mode_controls()
        self._update_preview()

    def _on_sigma_changed(self, val: int):
        self._gaussian_sigma = val
        self._lbl_sigma.setText(str(val))
        self._update_preview()

    def _on_start_sample_roi(self):
        self._before_viewer.set_mode('sample_roi')

    def _on_start_eyedropper(self):
        self._before_viewer.set_mode('eyedropper')

    def _format_fill(self, value) -> str:
        if isinstance(value, tuple):
            return '(' + ', '.join(f'{v:.1f}' for v in value) + ')'
        return f'{value:.1f}'

    def _on_roi_sampled(self, x: int, y: int, w: int, h: int):
        if self._current_arr is None:
            return
        try:
            self._fill_value = masking.compute_mean(self._current_arr, x, y, w, h)
        except Exception as e:
            QMessageBox.warning(self, '오류', str(e))
            return
        self._lbl_fill.setText(f'샘플 값(평균): {self._format_fill(self._fill_value)}')
        self._update_preview()

    def _on_pixel_picked(self, x: int, y: int):
        if self._current_arr is None:
            return
        self._fill_value = masking.sample_pixel(self._current_arr, x, y)
        self._lbl_fill.setText(f'샘플 값(픽셀): {self._format_fill(self._fill_value)}')
        self._update_preview()

    # ------------------------------------------------------------------ 미리보기/적용

    def _internal_mode_and_fill(self):
        """UI 모드를 masking.apply_mask()의 (mode, fill_value)로 변환."""
        if self._mask_mode in ('black', 'white', 'gaussian'):
            return self._mask_mode, None
        return 'constant', self._fill_value

    def _update_preview(self):
        if self._current_arr is None:
            return
        mode, fill_value = self._internal_mode_and_fill()
        if mode == 'constant' and fill_value is None:
            # 샘플/색상이 아직 지정되지 않음 → 원본 그대로 표시
            pixmap = masking.array_to_qpixmap(self._current_arr, self._display_mn, self._display_mx)
            self._after_viewer.update_pixmap(pixmap)
            return
        try:
            masked = masking.apply_mask(
                self._current_arr, self._mask_y, mode,
                gaussian_sigma=self._gaussian_sigma, fill_value=fill_value,
            )
        except Exception as e:
            QMessageBox.warning(self, '미리보기 오류', str(e))
            return
        pixmap = masking.array_to_qpixmap(masked, self._display_mn, self._display_mx)
        self._after_viewer.update_pixmap(pixmap)

    def _checked_paths(self) -> list:
        result = []
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            if item.checkState() == Qt.Checked:
                result.append(self._image_paths[i])
        return result

    def _on_apply(self, scope: str):
        if self._current_path is None or self._current_arr is None:
            QMessageBox.warning(self, '경고', '이미지를 먼저 선택하세요.')
            return

        mode, fill_value = self._internal_mode_and_fill()
        if mode == 'constant' and fill_value is None:
            QMessageBox.warning(self, '경고', '샘플 영역 또는 스포이드 색상을 먼저 지정하세요.')
            return

        if scope == 'current':
            targets = [self._current_path]
        elif scope == 'all':
            targets = list(self._image_paths)
        else:
            targets = self._checked_paths()
            if not targets:
                QMessageBox.warning(self, '경고', '체크된 이미지가 없습니다.')
                return

        progress = QProgressDialog('마스킹 처리 중...', '취소', 0, len(targets), self)
        progress.setWindowTitle('Y-Axis Masker')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        done = 0
        errors = []
        out_dir = None
        for path in targets:
            if progress.wasCanceled():
                break
            try:
                if path == self._current_path:
                    arr = self._current_arr
                else:
                    arr = masking.load_array(path, self._raw_w, self._raw_h)
                masked = masking.apply_mask(
                    arr, self._mask_y, mode,
                    gaussian_sigma=self._gaussian_sigma, fill_value=fill_value,
                )
                out_dir = masking.save_masked(path, masked).parent
            except Exception as e:
                errors.append(f'{path.name}: {e}')
            done += 1
            progress.setValue(done)

        progress.close()

        scope_label = {'current': '현재 이미지', 'all': '폴더 전체', 'checked': '체크된 이미지'}[scope]
        if errors:
            QMessageBox.warning(self, '완료 (오류 있음)', '완료. 오류:\n' + '\n'.join(errors))
        else:
            QMessageBox.information(self, '완료', f'{scope_label} 마스킹 완료!\n저장 위치: {out_dir}')


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
