"""파일명 변환 GUI (바코드 -> 셀번호 -> 재료명 파이프라인 통합).

폴더를 선택하면 하위 폴더까지 재귀 스캔해서 지정한 확장자의 파일을 모두
불러오고, 최종 변환명을 미리보기로 보여준다. 중복검사, 목록 우클릭으로
탐색기 열기, 체크된 항목만 골라서 일괄 변환(원본은 항상 보존, 복사만
수행), 방금 실행한 변환(또는 이전 로그)을 되돌리는 기능을 제공한다.

로직은 core.py 에 GUI 비의존적으로 분리되어 있다.
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
    QProgressBar, QShortcut,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence

import core

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


class ScanWorker(QThread):
    """폴더 재귀 스캔 + 변환명 계산을 메인 스레드 밖에서 수행한다."""

    finished_ok = pyqtSignal(list)  # list[core.FileRow]
    failed = pyqtSignal(str)

    def __init__(self, root, extensions, barcode_map, cell_map, exclude_dir, storage_map, parent=None):
        super().__init__(parent)
        self._root = root
        self._extensions = extensions
        self._barcode_map = barcode_map
        self._cell_map = cell_map
        self._exclude_dir = exclude_dir
        self._storage_map = storage_map

    def run(self) -> None:
        try:
            rows = core.build_rows(
                self._root, self._extensions, self._barcode_map, self._cell_map,
                exclude_dir=self._exclude_dir, storage_cellbarcode_map=self._storage_map,
            )
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

    def __init__(self, rows, output_dir, flatten, parent=None):
        super().__init__(parent)
        self._rows = rows
        self._output_dir = output_dir
        self._flatten = flatten

    def run(self) -> None:
        try:
            log = core.convert_files(
                self._rows, self._output_dir, self._flatten,
                progress_cb=lambda done, total: self.progress.emit(done, total),
            )
        except core.ConversionConflictError as e:
            self.conflict.emit(e.conflicts)
            return
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(log)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("파일명 변환기 (바코드 → 셀번호 → 재료명)")
        self.resize(1200, 720)

        self.root_folder: str | None = None
        self.output_folder: str | None = None
        self.rows: list[core.FileRow] = []
        self.ext_checkboxes: dict[str, QCheckBox] = {}
        self.last_log: dict | None = None

        self.barcode_map_path = DEFAULT_BARCODE_MAP
        self.cell_map_path = DEFAULT_CELL_MAP
        self.storage_map_path = DEFAULT_STORAGE_MAP
        self.barcode_map: dict[str, str] = {}
        self.cell_map: dict[str, str] = {}
        self.storage_map: dict[str, str] = {}

        self._scan_worker: ScanWorker | None = None
        self._convert_worker: ConvertWorker | None = None

        self._build_ui()
        self._load_mappings(initial=True)

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # --- 폴더/매핑 선택 영역 ---
        top_grid = QGridLayout()

        self.btn_select_folder = QPushButton("폴더 선택...")
        self.btn_select_folder.clicked.connect(self.on_select_folder)
        self.lbl_folder = QLabel("(선택 안 됨)")
        self.lbl_folder.setWordWrap(True)
        top_grid.addWidget(self.btn_select_folder, 0, 0)
        top_grid.addWidget(self.lbl_folder, 0, 1, 1, 3)

        self.btn_load_barcode_map = QPushButton("바코드↔셀번호 매핑 불러오기...")
        self.btn_load_barcode_map.clicked.connect(self.on_load_barcode_map)
        self.lbl_barcode_map = QLabel(str(self.barcode_map_path))
        self.lbl_barcode_map.setWordWrap(True)
        top_grid.addWidget(self.btn_load_barcode_map, 1, 0)
        top_grid.addWidget(self.lbl_barcode_map, 1, 1, 1, 3)

        self.btn_load_cell_map = QPushButton("셀번호↔재료명 매핑 불러오기...")
        self.btn_load_cell_map.clicked.connect(self.on_load_cell_map)
        self.lbl_cell_map = QLabel(str(self.cell_map_path))
        self.lbl_cell_map.setWordWrap(True)
        top_grid.addWidget(self.btn_load_cell_map, 2, 0)
        top_grid.addWidget(self.lbl_cell_map, 2, 1, 1, 3)

        self.btn_load_storage_map = QPushButton("저장번호↔Cell Barcode 매핑 불러오기...")
        self.btn_load_storage_map.clicked.connect(self.on_load_storage_map)
        self.lbl_storage_map = QLabel(str(self.storage_map_path))
        self.lbl_storage_map.setWordWrap(True)
        top_grid.addWidget(self.btn_load_storage_map, 3, 0)
        top_grid.addWidget(self.lbl_storage_map, 3, 1, 1, 3)

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
            ["선택", "원본 파일명", "상대 경로", "최종 변환명", "상태", "사유"]
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
    # 매핑 로드
    # ------------------------------------------------------------------
    def _load_mappings(self, initial=False):
        try:
            self.barcode_map = core.load_barcode_cell_map(self.barcode_map_path)
            self.cell_map = core.load_cell_material_map(self.cell_map_path)
            self._log(
                f"매핑 로드 완료: 바코드↔셀 {len(self.barcode_map)}건, "
                f"셀↔재료 {len(self.cell_map)}건"
            )
        except Exception as e:
            if not initial:
                QMessageBox.critical(self, "매핑 로드 실패", str(e))
            self._log(f"매핑 로드 실패: {e}")

        # 저장번호↔Cell Barcode 매핑은 구형 파일명만 쓰는 환경에서는 없어도 되므로
        # 실패해도 barcode/cell 매핑과 별개로 처리 (신형 파일명만 매칭 실패로 표시됨).
        try:
            self.storage_map = core.load_storage_cellbarcode_map(self.storage_map_path)
            self._log(f"매핑 로드 완료: 저장번호↔Cell Barcode {len(self.storage_map)}건")
        except Exception as e:
            self.storage_map = {}
            if not initial:
                QMessageBox.critical(self, "매핑 로드 실패", str(e))
            self._log(f"저장번호↔Cell Barcode 매핑 로드 실패(신형 파일명 매칭 불가): {e}")

    def on_load_barcode_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "바코드↔셀번호 매핑 CSV 선택", str(self.barcode_map_path.parent), "CSV (*.csv)"
        )
        if not path:
            return
        self.barcode_map_path = Path(path)
        self.lbl_barcode_map.setText(path)
        self._load_mappings()

    def on_load_cell_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "셀번호↔재료명 매핑 CSV 선택", str(self.cell_map_path.parent), "CSV (*.csv)"
        )
        if not path:
            return
        self.cell_map_path = Path(path)
        self.lbl_cell_map.setText(path)
        self._load_mappings()

    def on_load_storage_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "저장번호↔Cell Barcode 매핑 CSV 선택", str(self.storage_map_path.parent), "CSV (*.csv)"
        )
        if not path:
            return
        self.storage_map_path = Path(path)
        self.lbl_storage_map.setText(path)
        self._load_mappings()

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
        if not self.barcode_map or not self.cell_map:
            QMessageBox.warning(self, "매핑 없음", "매핑 파일이 로드되지 않았습니다.")
            return

        self._set_busy(True, "스캔 중...")
        self._log("스캔 시작...")
        self._scan_worker = ScanWorker(
            self.root_folder, selected_exts, self.barcode_map, self.cell_map,
            exclude_dir=self.output_folder, storage_map=self.storage_map,
        )
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
        if not checked_ok:
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

        reply = QMessageBox.question(
            self, "변환 확인",
            f"{len(checked_ok)}건을 '{self.output_folder}' 폴더로 복사합니다.\n"
            f"({'평탄화' if flatten else '하위폴더 구조 유지'})\n계속할까요?",
        )
        if reply != QMessageBox.Yes:
            return

        self._set_busy(True, f"변환 중... 0/{len(checked_ok)}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(checked_ok))
        self.progress_bar.setValue(0)

        self._convert_worker = ConvertWorker(self.rows, self.output_folder, flatten)
        self._convert_worker.progress.connect(self._on_convert_progress)
        self._convert_worker.finished_ok.connect(self._on_convert_finished)
        self._convert_worker.failed.connect(self._on_convert_failed)
        self._convert_worker.conflict.connect(self._on_convert_conflict)
        self._convert_worker.start()

    def _on_convert_progress(self, done: int, total: int):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.statusBar().showMessage(f"변환 중... {done}/{total}")

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
            self.btn_select_folder, self.btn_load_barcode_map, self.btn_load_cell_map,
            self.btn_load_storage_map, self.btn_load_list, self.btn_check_dup,
            self.btn_select_output, self.btn_convert_all, self.btn_undo_last,
            self.btn_undo_log, self.radio_flatten, self.radio_preserve,
        ):
            w.setEnabled(not busy)
        if busy:
            self.statusBar().showMessage(status_message)
        else:
            self.statusBar().clearMessage()
            # 되돌리기(방금 실행) 버튼은 last_log 가 있을 때만 다시 활성화
            self.btn_undo_last.setEnabled(self.last_log is not None)

    def _log(self, message: str):
        self.log_view.appendPlainText(message)


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
