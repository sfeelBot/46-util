"""파일명 변환 GUI.

탭 2개로 구성된다:

1. "바코드 → 재료명 변환" — 원본 이미지 파일명을 (바코드 또는 저장번호) → 셀번호 → 재료명
   순으로 재가공한다 (core.py). 매칭에 실패한 파일은 체크 여부와 무관하게 출력 폴더의
   `error/` 하위에 원본 파일명 그대로 함께 복사되어 나중에 확인할 수 있다.
2. "Crop 이미지 재명명" — image_cropper 로 4등분한 crop 이미지들을, 원래 개별 촬영이었다면
   가졌을 저장번호 기반 파일명으로 되돌린다 (crop_remap.py). 결과는 재명명된 파일 자체이며,
   이후 1번 탭에 다시 입력해 바코드→재료명 변환까지 이어갈 수 있다.

두 탭 모두 폴더 재귀 스캔, 확장자 필터, 최종명 미리보기, 중복검사, 우클릭 탐색기 열기,
자유 리사이즈/셀 복사 가능한 테이블, 비동기 일괄 변환(원본 보존, 복사만), 되돌리기(로그
기반)라는 공통 워크플로를 공유하며 `ConversionTab` 하나로 구현되어 있다. 각 탭이 실제
행(목록)을 어떻게 만드는지는 컨트롤러 객체(`BarcodeMaterialController`/`CropRemapController`)
가 담당한다.

로직은 core.py / crop_remap.py 에 GUI 비의존적으로 분리되어 있다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QRadioButton, QButtonGroup,
    QPlainTextEdit, QMenu, QAbstractItemView, QHeaderView, QScrollArea,
    QProgressBar, QShortcut, QTabWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence

import core
import crop_remap

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_BARCODE_MAP = BASE_DIR / "mapping" / "barcode_cell_map.csv"
DEFAULT_CELL_MAP = BASE_DIR / "mapping" / "cell_material_map.csv"
DEFAULT_STORAGE_MAP = BASE_DIR / "mapping" / "storage_cellbarcode_map.csv"

STATUS_COLORS = {
    core.STATUS_OK: None,
    core.STATUS_NO_MATCH: QColor(255, 235, 205),   # 연한 주황: 매칭실패
    core.STATUS_DUPLICATE: QColor(255, 205, 205),  # 연한 빨강: 중복
}

COL_CHECK, COL_NAME, COL_RELDIR, COL_FINAL, COL_STATUS, COL_REASON = range(6)


# ============================================================
# 백그라운드 워커 (두 탭 공용)
# ============================================================
class ScanWorker(QThread):
    """폴더 재귀 스캔 + 변환명 계산을 메인 스레드 밖에서 수행한다."""

    finished_ok = pyqtSignal(list)  # list[core.FileRow]
    failed = pyqtSignal(str)

    def __init__(self, build_fn, parent=None):
        super().__init__(parent)
        self._build_fn = build_fn  # () -> list[core.FileRow]

    def run(self) -> None:
        try:
            rows = self._build_fn()
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(rows)


class ConvertWorker(QThread):
    """실제 파일 복사를 메인 스레드 밖에서 수행한다 (대량 파일 복사가 오래 걸릴 수 있으므로 항상 비동기 실행)."""

    finished_ok = pyqtSignal(dict)  # log
    failed = pyqtSignal(str)
    conflict = pyqtSignal(list)  # conflict dest paths
    progress = pyqtSignal(int, int)  # done, total

    def __init__(self, rows, output_dir, flatten, copy_errors=True, parent=None):
        super().__init__(parent)
        self._rows = rows
        self._output_dir = output_dir
        self._flatten = flatten
        self._copy_errors = copy_errors

    def run(self) -> None:
        try:
            log = core.convert_files(
                self._rows, self._output_dir, self._flatten,
                progress_cb=lambda done, total: self.progress.emit(done, total),
                copy_errors=self._copy_errors,
            )
        except core.ConversionConflictError as e:
            self.conflict.emit(e.conflicts)
            return
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(log)


# ============================================================
# 탭별 컨트롤러: "행을 어떻게 만드는지"만 담당 (탭 UI/워크플로는 ConversionTab 이 공용으로 처리)
# ============================================================
class BarcodeMaterialController:
    """탭 1: (바코드/저장번호) → 셀번호 → 재료명."""

    title = "바코드 → 재료명 변환"
    final_col_label = "최종 변환명"

    def __init__(self):
        self.barcode_map_path = DEFAULT_BARCODE_MAP
        self.cell_map_path = DEFAULT_CELL_MAP
        self.storage_map_path = DEFAULT_STORAGE_MAP
        self.barcode_map: dict[str, str] = {}
        self.cell_map: dict[str, str] = {}
        self.storage_map: dict[str, str] = {}

    def is_ready(self) -> bool:
        return bool(self.barcode_map and self.cell_map)

    def build_rows(self, root, extensions, exclude_dir):
        return core.build_rows(
            root, extensions, self.barcode_map, self.cell_map,
            exclude_dir=exclude_dir, storage_cellbarcode_map=self.storage_map,
        )

    def on_tab_ready(self, tab: "ConversionTab"):
        """탭의 UI(로그 영역 포함)가 완전히 준비된 뒤 최초 1회 호출됨."""
        self.load_mappings(tab, initial=True)

    def build_extra_ui(self, tab: "ConversionTab", grid: QGridLayout, next_row: int) -> int:
        """매핑 3종 선택 UI를 top_grid 에 추가하고, 다음에 쓸 grid row 번호를 반환한다."""
        btn_barcode = QPushButton("바코드↔셀번호 매핑 불러오기...")
        lbl_barcode = QLabel(str(self.barcode_map_path))
        lbl_barcode.setWordWrap(True)
        btn_barcode.clicked.connect(lambda: self._on_load_map(tab, "barcode_map_path", lbl_barcode,
                                                                "바코드↔셀번호 매핑 CSV 선택"))
        grid.addWidget(btn_barcode, next_row, 0)
        grid.addWidget(lbl_barcode, next_row, 1, 1, 3)
        next_row += 1

        btn_cell = QPushButton("셀번호↔재료명 매핑 불러오기...")
        lbl_cell = QLabel(str(self.cell_map_path))
        lbl_cell.setWordWrap(True)
        btn_cell.clicked.connect(lambda: self._on_load_map(tab, "cell_map_path", lbl_cell,
                                                             "셀번호↔재료명 매핑 CSV 선택"))
        grid.addWidget(btn_cell, next_row, 0)
        grid.addWidget(lbl_cell, next_row, 1, 1, 3)
        next_row += 1

        btn_storage = QPushButton("저장번호↔Cell Barcode 매핑 불러오기...")
        lbl_storage = QLabel(str(self.storage_map_path))
        lbl_storage.setWordWrap(True)
        btn_storage.clicked.connect(lambda: self._on_load_map(tab, "storage_map_path", lbl_storage,
                                                                "저장번호↔Cell Barcode 매핑 CSV 선택"))
        grid.addWidget(btn_storage, next_row, 0)
        grid.addWidget(lbl_storage, next_row, 1, 1, 3)
        next_row += 1

        tab._extra_lock_widgets.extend([btn_barcode, btn_cell, btn_storage])
        return next_row

    def _on_load_map(self, tab: "ConversionTab", attr_name: str, label: QLabel, dialog_title: str):
        current = getattr(self, attr_name)
        path, _ = QFileDialog.getOpenFileName(tab, dialog_title, str(current.parent), "CSV (*.csv)")
        if not path:
            return
        setattr(self, attr_name, Path(path))
        label.setText(path)
        self.load_mappings(tab)

    def load_mappings(self, tab: "ConversionTab", initial=False):
        try:
            self.barcode_map = core.load_barcode_cell_map(self.barcode_map_path)
            self.cell_map = core.load_cell_material_map(self.cell_map_path)
            tab._log(
                f"매핑 로드 완료: 바코드↔셀 {len(self.barcode_map)}건, "
                f"셀↔재료 {len(self.cell_map)}건"
            )
        except Exception as e:
            if not initial:
                QMessageBox.critical(tab, "매핑 로드 실패", str(e))
            tab._log(f"매핑 로드 실패: {e}")

        # 저장번호↔Cell Barcode 매핑은 구형 파일명만 쓰는 환경에서는 없어도 되므로
        # 실패해도 barcode/cell 매핑과 별개로 처리 (신형 파일명만 매칭 실패로 표시됨).
        try:
            self.storage_map = core.load_storage_cellbarcode_map(self.storage_map_path)
            tab._log(f"매핑 로드 완료: 저장번호↔Cell Barcode {len(self.storage_map)}건")
        except Exception as e:
            self.storage_map = {}
            if not initial:
                QMessageBox.critical(tab, "매핑 로드 실패", str(e))
            tab._log(f"저장번호↔Cell Barcode 매핑 로드 실패(신형 파일명 매칭 불가): {e}")


class CropRemapController:
    """탭 2: image_cropper 출력(crop 1~4) → 재구성된 개별 저장번호 파일명."""

    title = "Crop 이미지 재명명"
    final_col_label = "재명명된 파일명"

    def is_ready(self) -> bool:
        return True

    def on_tab_ready(self, tab: "ConversionTab"):
        pass

    def build_rows(self, root, extensions, exclude_dir):
        return crop_remap.build_rows(root, extensions, exclude_dir=exclude_dir)

    def build_extra_ui(self, tab: "ConversionTab", grid: QGridLayout, next_row: int) -> int:
        note = QLabel(
            "image_cropper 출력 폴더(cropped/)를 선택하세요. "
            "파일명 규칙: {원본파일명}_{ROI번호}_x{x}y{y}w{w}h{h}{확장자} (ROI번호 1~4)"
        )
        note.setWordWrap(True)
        grid.addWidget(note, next_row, 0, 1, 4)
        return next_row + 1


# ============================================================
# 공용 탭 위젯
# ============================================================
class ConversionTab(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

        self.root_folder: str | None = None
        self.output_folder: str | None = None
        self.rows: list[core.FileRow] = []
        self.ext_checkboxes: dict[str, QCheckBox] = {}
        self.last_log: dict | None = None
        self._extra_lock_widgets: list[QWidget] = []

        self._scan_worker: ScanWorker | None = None
        self._convert_worker: ConvertWorker | None = None

        self._build_ui()
        self.controller.on_tab_ready(self)

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _build_ui(self):
        root_layout = QVBoxLayout(self)

        # --- 폴더 선택 + 탭별 추가 UI(매핑 선택 등) ---
        top_grid = QGridLayout()

        self.btn_select_folder = QPushButton("폴더 선택...")
        self.btn_select_folder.clicked.connect(self.on_select_folder)
        self.lbl_folder = QLabel("(선택 안 됨)")
        self.lbl_folder.setWordWrap(True)
        top_grid.addWidget(self.btn_select_folder, 0, 0)
        top_grid.addWidget(self.lbl_folder, 0, 1, 1, 3)

        self.controller.build_extra_ui(self, top_grid, 1)
        root_layout.addLayout(top_grid)

        # --- 확장자 선택 영역 ---
        ext_box = QGroupBox("불러올 확장자")
        self.ext_layout = QHBoxLayout()
        ext_scroll = QScrollArea()
        ext_scroll.setWidgetResizable(True)
        ext_scroll.setFixedHeight(60)
        ext_inner = QWidget()
        ext_inner.setLayout(self.ext_layout)
        ext_scroll.setWidget(ext_inner)
        ext_box_layout = QVBoxLayout()
        ext_box_layout.addWidget(ext_scroll)
        ext_box.setLayout(ext_box_layout)
        root_layout.addWidget(ext_box)

        btn_row = QHBoxLayout()
        self.btn_load_list = QPushButton("목록 불러오기")
        self.btn_load_list.clicked.connect(self.on_load_list)
        self.btn_load_list.setEnabled(False)
        btn_row.addWidget(self.btn_load_list)

        self.btn_check_dup = QPushButton("중복검사")
        self.btn_check_dup.clicked.connect(self.on_check_duplicates)
        btn_row.addWidget(self.btn_check_dup)
        btn_row.addStretch(1)
        root_layout.addLayout(btn_row)

        # --- 테이블 ---
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["선택", "원본 파일명", "상대 경로", self.controller.final_col_label, "상태", "사유"]
        )
        # 모든 컬럼을 사용자가 드래그로 자유롭게 폭 조절할 수 있게 함 (Stretch 모드는 수동 조절 불가)
        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 셀 단위로 드래그 선택 후 Ctrl+C 로 텍스트 복사 가능 (엑셀과 유사)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_context_menu)

        copy_shortcut = QShortcut(QKeySequence.Copy, self.table)
        copy_shortcut.setContext(Qt.WidgetShortcut)
        copy_shortcut.activated.connect(self._copy_selected_cells)
        self.table.itemChanged.connect(self._on_item_changed)

        root_layout.addWidget(self.table, stretch=1)

        # --- 출력/변환 영역 ---
        out_row = QHBoxLayout()
        self.btn_select_output = QPushButton("출력 폴더 선택...")
        self.btn_select_output.clicked.connect(self.on_select_output)
        self.lbl_output = QLabel("(선택 안 됨)")
        out_row.addWidget(self.btn_select_output)
        out_row.addWidget(self.lbl_output, stretch=1)

        self.radio_flatten = QRadioButton("단일 폴더에 평탄화")
        self.radio_preserve = QRadioButton("원본 하위폴더 구조 유지")
        self.radio_flatten.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.radio_flatten)
        mode_group.addButton(self.radio_preserve)
        out_row.addWidget(self.radio_flatten)
        out_row.addWidget(self.radio_preserve)
        root_layout.addLayout(out_row)

        action_row = QHBoxLayout()
        self.btn_convert_all = QPushButton("모두 변환")
        self.btn_convert_all.clicked.connect(self.on_convert_all)
        action_row.addWidget(self.btn_convert_all)

        self.btn_undo_last = QPushButton("되돌리기 (방금 실행)")
        self.btn_undo_last.clicked.connect(self.on_undo_last)
        self.btn_undo_last.setEnabled(False)
        action_row.addWidget(self.btn_undo_last)

        self.btn_undo_log = QPushButton("로그 불러와서 되돌리기...")
        self.btn_undo_log.clicked.connect(self.on_undo_from_log)
        action_row.addWidget(self.btn_undo_log)
        action_row.addStretch(1)
        root_layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # --- 로그 영역 ---
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(120)
        root_layout.addWidget(self.log_view)

    # ------------------------------------------------------------------
    # 폴더 선택 / 확장자 탐색
    # ------------------------------------------------------------------
    def on_select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not folder:
            return
        self.root_folder = folder
        self.lbl_folder.setText(folder)
        self._populate_extensions(folder)
        self.btn_load_list.setEnabled(True)

    def _populate_extensions(self, folder: str):
        for i in reversed(range(self.ext_layout.count())):
            widget = self.ext_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.ext_checkboxes.clear()

        exts = core.discover_extensions(folder)
        if not exts:
            self.ext_layout.addWidget(QLabel("(파일을 찾을 수 없음)"))
            return

        image_default = {".bmp", ".raw", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
        for ext in exts:
            cb = QCheckBox(ext)
            cb.setChecked(ext in image_default)
            self.ext_layout.addWidget(cb)
            self.ext_checkboxes[ext] = cb
        self.ext_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 목록 불러오기
    # ------------------------------------------------------------------
    def on_load_list(self):
        if not self.root_folder:
            return
        selected_exts = {ext for ext, cb in self.ext_checkboxes.items() if cb.isChecked()}
        if not selected_exts:
            QMessageBox.warning(self, "확장자 선택 필요", "불러올 확장자를 하나 이상 선택하세요.")
            return
        if not self.controller.is_ready():
            QMessageBox.warning(self, "매핑 없음", "매핑 파일이 로드되지 않았습니다.")
            return

        self._set_busy(True, "스캔 중...")
        self._log("스캔 시작...")
        root_folder = self.root_folder
        output_folder = self.output_folder
        build_fn = lambda: self.controller.build_rows(root_folder, selected_exts, output_folder)
        self._scan_worker = ScanWorker(build_fn)
        self._scan_worker.finished_ok.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_finished(self, rows: list):
        self.rows = rows
        self._set_busy(False)
        self._refresh_table()
        ok_count = sum(1 for r in rows if r.status == core.STATUS_OK)
        self._log(f"스캔 완료: 총 {len(rows)}건, 매칭 성공 {ok_count}건")

    def _on_scan_failed(self, message: str):
        self._set_busy(False)
        QMessageBox.critical(self, "스캔 실패", message)
        self._log(f"스캔 실패: {message}")

    # ------------------------------------------------------------------
    # 테이블 렌더링
    # ------------------------------------------------------------------
    def _refresh_table(self):
        self.table.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk_item.setCheckState(Qt.Checked if row.checked else Qt.Unchecked)
            self.table.setItem(i, COL_CHECK, chk_item)

            self.table.setItem(i, COL_NAME, QTableWidgetItem(row.filename))
            self.table.setItem(i, COL_RELDIR, QTableWidgetItem(row.rel_dir))
            self.table.setItem(i, COL_FINAL, QTableWidgetItem(row.final_name or ""))
            self.table.setItem(i, COL_STATUS, QTableWidgetItem(row.status))
            self.table.setItem(i, COL_REASON, QTableWidgetItem(row.reason))

            color = STATUS_COLORS.get(row.status)
            for col in range(self.table.columnCount()):
                item = self.table.item(i, col)
                if item is not None:
                    item.setBackground(color if color else Qt.white)

        self.table.resizeColumnsToContents()  # 초기 폭은 내용에 맞춰 자동 조절, 이후 사용자가 자유롭게 재조절 가능

    def _copy_selected_cells(self):
        """선택된 셀(들)의 텍스트를 엑셀처럼 탭/줄바꿈으로 구분해 클립보드로 복사한다."""
        indexes = self.table.selectionModel().selectedIndexes()
        if not indexes:
            return
        rows = sorted({idx.row() for idx in indexes})
        cols = sorted({idx.column() for idx in indexes})
        cell_text = {(idx.row(), idx.column()): (idx.data() or "") for idx in indexes}
        lines = ["\t".join(cell_text.get((r, c), "") for c in cols) for r in rows]
        QApplication.clipboard().setText("\n".join(lines))

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != COL_CHECK:
            return
        row_idx = item.row()
        if 0 <= row_idx < len(self.rows):
            self.rows[row_idx].checked = item.checkState() == Qt.Checked

    # ------------------------------------------------------------------
    # 우클릭: 탐색기에서 열기
    # ------------------------------------------------------------------
    def on_table_context_menu(self, pos):
        row_idx = self.table.rowAt(pos.y())
        if row_idx < 0 or row_idx >= len(self.rows):
            return
        menu = QMenu(self)
        action = menu.addAction("파일탐색기에서 열기")
        chosen = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if chosen == action:
            self._open_in_explorer(self.rows[row_idx].src_path)

    def _open_in_explorer(self, path: str):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception as e:
            QMessageBox.warning(self, "탐색기 열기 실패", str(e))

    # ------------------------------------------------------------------
    # 중복검사
    # ------------------------------------------------------------------
    def on_check_duplicates(self):
        if not self.rows:
            return
        flatten = self.radio_flatten.isChecked()
        duplicates = core.find_duplicates(self.rows, flatten=flatten)
        self._refresh_table()
        if duplicates:
            total = sum(len(v) for v in duplicates.values())
            self._log(f"중복검사: {len(duplicates)}개 그룹, 총 {total}건 중복 발견")
            QMessageBox.warning(
                self, "중복 발견",
                f"{len(duplicates)}개의 이름에서 중복이 발견되었습니다 (총 {total}건).\n"
                "표에서 빨간색으로 표시된 항목을 확인하세요."
            )
        else:
            self._log("중복검사: 중복 없음")
            QMessageBox.information(self, "중복검사 완료", "중복된 최종 파일명이 없습니다.")

    # ------------------------------------------------------------------
    # 출력 폴더 선택
    # ------------------------------------------------------------------
    def on_select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if not folder:
            return
        self.output_folder = folder
        self.lbl_output.setText(folder)

    # ------------------------------------------------------------------
    # 모두 변환
    # ------------------------------------------------------------------
    def on_convert_all(self):
        if not self.rows:
            QMessageBox.warning(self, "목록 없음", "먼저 목록을 불러오세요.")
            return
        if not self.output_folder:
            QMessageBox.warning(self, "출력 폴더 없음", "출력 폴더를 먼저 선택하세요.")
            return

        checked_ok = [r for r in self.rows if r.checked and r.status == core.STATUS_OK]
        error_rows = [r for r in self.rows if r.status == core.STATUS_NO_MATCH]
        if not checked_ok and not error_rows:
            QMessageBox.warning(self, "변환 대상 없음", "선택되고 매칭에 성공한 파일이 없습니다.")
            return

        flatten = self.radio_flatten.isChecked()
        conflicts = core.check_conflicts(self.rows, self.output_folder, flatten)
        if conflicts:
            preview = "\n".join(conflicts[:20])
            more = f"\n... 외 {len(conflicts) - 20}건" if len(conflicts) > 20 else ""
            QMessageBox.critical(
                self, "변환 불가: 파일명 충돌",
                f"다음 결과 파일명이 서로 충돌하거나 이미 존재합니다.\n"
                f"중복검사를 실행해 체크를 해제하거나 출력 폴더를 변경하세요.\n\n{preview}{more}"
            )
            self._log(f"변환 취소: 충돌 {len(conflicts)}건")
            return

        error_note = f"\n매칭실패 {len(error_rows)}건은 'error' 폴더에 원본 이름으로 함께 복사됩니다." if error_rows else ""
        reply = QMessageBox.question(
            self, "변환 확인",
            f"{len(checked_ok)}건을 '{self.output_folder}' 폴더로 복사합니다.\n"
            f"({'평탄화' if flatten else '하위폴더 구조 유지'}){error_note}\n계속할까요?",
        )
        if reply != QMessageBox.Yes:
            return

        total = len(checked_ok) + len(error_rows)
        self._set_busy(True, f"변환 중... 0/{total}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)

        self._convert_worker = ConvertWorker(self.rows, self.output_folder, flatten, copy_errors=True)
        self._convert_worker.progress.connect(self._on_convert_progress)
        self._convert_worker.finished_ok.connect(self._on_convert_finished)
        self._convert_worker.failed.connect(self._on_convert_failed)
        self._convert_worker.conflict.connect(self._on_convert_conflict)
        self._convert_worker.start()

    def _on_convert_progress(self, done: int, total: int):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.window().statusBar().showMessage(f"변환 중... {done}/{total}")

    def _on_convert_finished(self, log: dict):
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        log_path = core.save_log(log, self.output_folder)
        self.last_log = log
        self.btn_undo_last.setEnabled(True)
        n = len(log["entries"])
        self._log(f"변환 완료: {n}건 복사됨. 로그: {log_path}")
        QMessageBox.information(self, "변환 완료", f"{n}건을 복사했습니다.\n로그: {log_path}")

    def _on_convert_failed(self, message: str):
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "변환 실패", message)
        self._log(f"변환 실패: {message}")

    def _on_convert_conflict(self, conflicts: list):
        self._set_busy(False)
        self.progress_bar.setVisible(False)
        preview = "\n".join(conflicts[:20])
        QMessageBox.critical(self, "변환 불가: 파일명 충돌", preview)
        self._log(f"변환 취소(충돌): {len(conflicts)}건")

    # ------------------------------------------------------------------
    # 되돌리기
    # ------------------------------------------------------------------
    def on_undo_last(self):
        if not self.last_log:
            return
        removed, missing = core.undo_log(self.last_log)
        self._log(f"되돌리기 완료: {removed}건 삭제, {missing}건은 이미 없음 (원본은 그대로)")
        QMessageBox.information(self, "되돌리기 완료", f"{removed}건을 삭제했습니다. (원본은 그대로 유지됨)")
        self.btn_undo_last.setEnabled(False)
        self.last_log = None

    def on_undo_from_log(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "변환 로그(json) 선택", str(self.output_folder or self.root_folder or "."),
            "JSON (*.json)"
        )
        if not path:
            return
        try:
            removed, missing = core.undo_log(path)
        except Exception as e:
            QMessageBox.critical(self, "되돌리기 실패", str(e))
            return
        self._log(f"로그({path})로 되돌리기 완료: {removed}건 삭제, {missing}건은 이미 없음")
        QMessageBox.information(self, "되돌리기 완료", f"{removed}건을 삭제했습니다. (원본은 그대로 유지됨)")

    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, status_message: str = ""):
        """스캔/변환처럼 오래 걸릴 수 있는 작업(QThread) 중에는 충돌 가능한
        조작(폴더/매핑 재선택, 중복 재실행, 되돌리기 등)을 잠가 둔다."""
        for w in (
            [self.btn_select_folder, self.btn_load_list, self.btn_check_dup,
             self.btn_select_output, self.btn_convert_all, self.btn_undo_last,
             self.btn_undo_log, self.radio_flatten, self.radio_preserve]
            + self._extra_lock_widgets
        ):
            w.setEnabled(not busy)
        if busy:
            self.window().statusBar().showMessage(status_message)
        else:
            self.window().statusBar().clearMessage()
            # 되돌리기(방금 실행) 버튼은 last_log 가 있을 때만 다시 활성화
            self.btn_undo_last.setEnabled(self.last_log is not None)

    def _log(self, message: str):
        self.log_view.appendPlainText(message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("파일명 변환기")
        self.resize(1200, 760)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        self.barcode_tab = ConversionTab(BarcodeMaterialController())
        self.crop_tab = ConversionTab(CropRemapController())
        tabs.addTab(self.barcode_tab, BarcodeMaterialController.title)
        tabs.addTab(self.crop_tab, CropRemapController.title)

        self.statusBar()


def main():
    # Windows 콘솔(cp949 등)에서 한글 로그/예외 메시지가 깨져 보이는 것을 방지.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
