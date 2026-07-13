"""GitHub 이슈 #5 데이터(storage_ab_defect_info.csv)만으로 동작하는 독립 GUI.

파일명 어딘가에 저장번호(`Test#A..` 또는 `Test#B..`)가 포함되어 있으면,
`storage_ab_defect_info.csv`에서 그 값을 A열_저장번호/B열_저장번호로 찾아
셀번호(cell)와 이물정보(A열_이물정보/B열_이물정보, 매칭된 쪽)를 얻는다.
폴더 구조나 crop 순서는 전혀 보지 않는다 — 오직 파일명 안의 저장번호
문자열과 이 매핑표만으로 매칭한다.

최종 파일명: `{이물정보}_{셀번호}_{원본파일명}`
- cell 값이 "NULL"인 행(바코드가 barcode_cell_map.csv에 없어 셀을 모르는
  경우)도 매칭실패로 치지 않고, 이물정보만 써서 정상 변환한다
  (셀번호 자리에는 문자열 "NULL"이 그대로 들어감).
- 파일명에서 저장번호 패턴 자체를 못 찾거나, 그 값이 매핑표에 아예 없으면
  "매칭실패"로 표시되고 변환 대상에서 제외된다.

gui.py/core.py/crop_remap.py 와는 완전히 독립적인 파일이다 (재사용하지 않음).
변환은 항상 원본을 보존한 채 복사만 수행한다.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QRadioButton, QButtonGroup,
    QPlainTextEdit, QMenu, QAbstractItemView, QHeaderView, QScrollArea,
    QProgressBar, QShortcut,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MAP_PATH = BASE_DIR / "mapping" / "storage_ab_defect_info.csv"

# 파일명 어딘가의 저장번호: Test#A8-0000008 / Test#B8-0000008
STORAGE_RE = re.compile(r"Test#[AB]\d+-\d+")

STATUS_OK = "정상"
STATUS_NO_MATCH = "매칭실패"
STATUS_DUPLICATE = "중복"

COL_CHECK, COL_NAME, COL_RELDIR, COL_FINAL, COL_STATUS, COL_REASON = range(6)

STATUS_COLORS = {
    STATUS_OK: None,
    STATUS_NO_MATCH: QColor(255, 235, 205),
    STATUS_DUPLICATE: QColor(255, 205, 205),
}

_INVALID_FS_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


# ============================================================
# 핵심 로직 (GUI 비의존)
# ============================================================
def load_defect_map(path: str | Path) -> dict[str, tuple[str, str]]:
    """storage_number(A열 또는 B열 값) -> (cell, defect_info) 딕셔너리."""
    mapping: dict[str, tuple[str, str]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cell = (row.get("cell") or "").strip()
            a_storage = (row.get("A열_저장번호") or "").strip()
            a_defect = (row.get("A열_이물정보") or "").strip()
            b_storage = (row.get("B열_저장번호") or "").strip()
            b_defect = (row.get("B열_이물정보") or "").strip()
            if a_storage:
                mapping[a_storage] = (cell, a_defect)
            if b_storage:
                mapping[b_storage] = (cell, b_defect)
    return mapping


def _sanitize(text: str) -> str:
    """이물정보의 '/' 등 파일명에 못 쓰는 문자를 '_'로 치환."""
    return _INVALID_FS_CHARS_RE.sub("_", text)


def compute_final_name(
    filename: str, defect_map: dict[str, tuple[str, str]]
) -> tuple[Optional[str], str, str]:
    match = STORAGE_RE.search(filename)
    if not match:
        return None, STATUS_NO_MATCH, "파일명에서 저장번호(Test#A../Test#B..) 패턴을 찾을 수 없음"

    storage_number = match.group(0)
    entry = defect_map.get(storage_number)
    if entry is None:
        return None, STATUS_NO_MATCH, f"저장번호 {storage_number} 가 매핑표에 없음"

    cell, defect_info = entry
    cell_part = cell if cell else "NULL"
    defect_part = _sanitize(defect_info) if defect_info else "정보없음"
    final_name = f"{defect_part}_{cell_part}_{filename}"
    return final_name, STATUS_OK, ""


@dataclass
class FileRow:
    src_path: str
    rel_dir: str
    filename: str
    final_name: Optional[str]
    status: str
    reason: str
    checked: bool = True


def discover_extensions(root: str | Path) -> list[str]:
    exts: set[str] = set()
    for _dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext:
                exts.add(ext)
    return sorted(exts)


def scan_files(
    root: str | Path, extensions: set[str], exclude_dir: Optional[str | Path] = None
) -> list[tuple[str, str]]:
    root = str(root)
    exclude_abs = os.path.abspath(str(exclude_dir)) if exclude_dir else None
    results: list[tuple[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        abs_dirpath = os.path.abspath(dirpath)
        if exclude_abs and (
            abs_dirpath == exclude_abs or abs_dirpath.startswith(exclude_abs + os.sep)
        ):
            continue
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in extensions:
                results.append((os.path.join(dirpath, name), rel_dir))
    return results


def build_rows(
    root: str | Path,
    extensions: set[str],
    defect_map: dict[str, tuple[str, str]],
    exclude_dir: Optional[str | Path] = None,
) -> list[FileRow]:
    rows: list[FileRow] = []
    for src_path, rel_dir in scan_files(root, extensions, exclude_dir=exclude_dir):
        filename = os.path.basename(src_path)
        final_name, status, reason = compute_final_name(filename, defect_map)
        rows.append(
            FileRow(
                src_path=src_path, rel_dir=rel_dir, filename=filename,
                final_name=final_name, status=status, reason=reason,
                checked=(status == STATUS_OK),
            )
        )
    return rows


def find_duplicates(rows: list[FileRow], flatten: bool) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        if not row.checked or row.status not in (STATUS_OK, STATUS_DUPLICATE):
            continue
        if row.final_name is None:
            continue
        key = row.final_name if flatten else f"{row.rel_dir}/{row.final_name}"
        groups.setdefault(key, []).append(idx)

    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    dup_indices = {i for idxs in duplicates.values() for i in idxs}
    for idx, row in enumerate(rows):
        if row.status == STATUS_DUPLICATE and idx not in dup_indices:
            row.status = STATUS_OK
            row.reason = ""
        if idx in dup_indices:
            row.status = STATUS_DUPLICATE
            row.reason = "동일한 변환 결과 파일명이 여러 개 있음"
    return duplicates


class ConversionConflictError(Exception):
    def __init__(self, conflicts: list[str]):
        super().__init__("변환 대상 파일명이 충돌합니다.")
        self.conflicts = conflicts


def _dest_path(row: FileRow, output_dir: str, flatten: bool) -> str:
    if flatten:
        return os.path.join(output_dir, row.final_name)
    return os.path.join(output_dir, row.rel_dir, row.final_name)


def check_conflicts(rows: list[FileRow], output_dir: str, flatten: bool) -> list[str]:
    targets: dict[str, int] = {}
    conflicts: set[str] = set()
    for row in rows:
        if not row.checked or row.status != STATUS_OK or row.final_name is None:
            continue
        dest = _dest_path(row, output_dir, flatten)
        if dest in targets:
            conflicts.add(dest)
        else:
            targets[dest] = 1
        if os.path.exists(dest):
            conflicts.add(dest)
    return sorted(conflicts)


def convert_files(
    rows: list[FileRow], output_dir: str | Path, flatten: bool, progress_cb=None
) -> dict:
    output_dir = str(output_dir)
    conflicts = check_conflicts(rows, output_dir, flatten)
    if conflicts:
        raise ConversionConflictError(conflicts)

    os.makedirs(output_dir, exist_ok=True)
    targets = [r for r in rows if r.checked and r.status == STATUS_OK and r.final_name]
    total = len(targets)

    entries = []
    for done, row in enumerate(targets, start=1):
        dest = _dest_path(row, output_dir, flatten)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(row.src_path, dest)
        entries.append({"src": row.src_path, "dst": dest})
        if progress_cb is not None:
            progress_cb(done, total)

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": output_dir,
        "flatten": flatten,
        "entries": entries,
    }


def save_log(log: dict, output_dir: str | Path) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(str(output_dir), f"_conversion_log_{ts}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return log_path


def undo_log(log_or_path) -> tuple[int, int]:
    if isinstance(log_or_path, (str, Path)):
        with open(log_or_path, "r", encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = log_or_path

    removed = missing = 0
    for entry in log.get("entries", []):
        dst = entry["dst"]
        if os.path.exists(dst):
            os.remove(dst)
            removed += 1
        else:
            missing += 1
    return removed, missing


# ============================================================
# 백그라운드 워커
# ============================================================
class ScanWorker(QThread):
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, root, extensions, defect_map, exclude_dir, parent=None):
        super().__init__(parent)
        self._root = root
        self._extensions = extensions
        self._defect_map = defect_map
        self._exclude_dir = exclude_dir

    def run(self) -> None:
        try:
            rows = build_rows(self._root, self._extensions, self._defect_map, exclude_dir=self._exclude_dir)
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(rows)


class ConvertWorker(QThread):
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)
    conflict = pyqtSignal(list)
    progress = pyqtSignal(int, int)

    def __init__(self, rows, output_dir, flatten, parent=None):
        super().__init__(parent)
        self._rows = rows
        self._output_dir = output_dir
        self._flatten = flatten

    def run(self) -> None:
        try:
            log = convert_files(
                self._rows, self._output_dir, self._flatten,
                progress_cb=lambda done, total: self.progress.emit(done, total),
            )
        except ConversionConflictError as e:
            self.conflict.emit(e.conflicts)
            return
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(log)


# ============================================================
# GUI
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("이슈#5 매핑표 기반 파일명 재명명")
        self.resize(1200, 760)

        self.root_folder: str | None = None
        self.output_folder: str | None = None
        self.rows: list[FileRow] = []
        self.ext_checkboxes: dict[str, QCheckBox] = {}
        self.last_log: dict | None = None

        self.map_path = DEFAULT_MAP_PATH
        self.defect_map: dict[str, tuple[str, str]] = {}

        self._scan_worker: ScanWorker | None = None
        self._convert_worker: ConvertWorker | None = None

        self._build_ui()
        self._load_map(initial=True)

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        top_grid = QGridLayout()

        self.btn_select_folder = QPushButton("폴더 선택...")
        self.btn_select_folder.clicked.connect(self.on_select_folder)
        self.lbl_folder = QLabel("(선택 안 됨)")
        self.lbl_folder.setWordWrap(True)
        top_grid.addWidget(self.btn_select_folder, 0, 0)
        top_grid.addWidget(self.lbl_folder, 0, 1, 1, 3)

        self.btn_load_map = QPushButton("매핑 CSV 불러오기...")
        self.btn_load_map.clicked.connect(self.on_load_map)
        self.lbl_map = QLabel(str(self.map_path))
        self.lbl_map.setWordWrap(True)
        top_grid.addWidget(self.btn_load_map, 1, 0)
        top_grid.addWidget(self.lbl_map, 1, 1, 1, 3)

        note = QLabel(
            "파일명 어딘가에 저장번호(Test#A../Test#B..)가 있으면 매핑표에서 조회해 "
            "\"{이물정보}_{셀번호}_{원본파일명}\"으로 재명명합니다. "
            "셀번호를 모르는 경우(NULL)도 이물정보만으로 정상 변환됩니다."
        )
        note.setWordWrap(True)
        top_grid.addWidget(note, 2, 0, 1, 4)

        root_layout.addLayout(top_grid)

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

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["선택", "원본 파일명", "상대 경로", "최종 변환명", "상태", "사유"]
        )
        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_context_menu)

        copy_shortcut = QShortcut(QKeySequence.Copy, self.table)
        copy_shortcut.setContext(Qt.WidgetShortcut)
        copy_shortcut.activated.connect(self._copy_selected_cells)
        self.table.itemChanged.connect(self._on_item_changed)

        root_layout.addWidget(self.table, stretch=1)

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

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(120)
        root_layout.addWidget(self.log_view)

        self.statusBar()

    # ------------------------------------------------------------------
    # 매핑 로드
    # ------------------------------------------------------------------
    def _load_map(self, initial=False):
        try:
            self.defect_map = load_defect_map(self.map_path)
            self._log(f"매핑 로드 완료: 저장번호↔셀/이물정보 {len(self.defect_map)}건")
        except Exception as e:
            self.defect_map = {}
            if not initial:
                QMessageBox.critical(self, "매핑 로드 실패", str(e))
            self._log(f"매핑 로드 실패: {e}")

    def on_load_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "매핑 CSV 선택", str(self.map_path.parent), "CSV (*.csv)"
        )
        if not path:
            return
        self.map_path = Path(path)
        self.lbl_map.setText(path)
        self._load_map()

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

        exts = discover_extensions(folder)
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
        if not self.defect_map:
            QMessageBox.warning(self, "매핑 없음", "매핑 파일이 로드되지 않았습니다.")
            return

        self._set_busy(True, "스캔 중...")
        self._log("스캔 시작...")
        self._scan_worker = ScanWorker(
            self.root_folder, selected_exts, self.defect_map, self.output_folder
        )
        self._scan_worker.finished_ok.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_finished(self, rows: list):
        self.rows = rows
        self._set_busy(False)
        self._refresh_table()
        ok_count = sum(1 for r in rows if r.status == STATUS_OK)
        self._log(f"스캔 완료: 총 {len(rows)}건, 매칭 성공 {ok_count}건")

    def _on_scan_failed(self, message: str):
        self._set_busy(False)
        QMessageBox.critical(self, "스캔 실패", message)
        self._log(f"스캔 실패: {message}")

    # ------------------------------------------------------------------
    # 테이블
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

        self.table.resizeColumnsToContents()

    def _copy_selected_cells(self):
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
    def on_check_duplicates(self):
        if not self.rows:
            return
        flatten = self.radio_flatten.isChecked()
        duplicates = find_duplicates(self.rows, flatten=flatten)
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
    def on_select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if not folder:
            return
        self.output_folder = folder
        self.lbl_output.setText(folder)

    # ------------------------------------------------------------------
    def on_convert_all(self):
        if not self.rows:
            QMessageBox.warning(self, "목록 없음", "먼저 목록을 불러오세요.")
            return
        if not self.output_folder:
            QMessageBox.warning(self, "출력 폴더 없음", "출력 폴더를 먼저 선택하세요.")
            return

        checked_ok = [r for r in self.rows if r.checked and r.status == STATUS_OK]
        if not checked_ok:
            QMessageBox.warning(self, "변환 대상 없음", "선택되고 매칭에 성공한 파일이 없습니다.")
            return

        flatten = self.radio_flatten.isChecked()
        conflicts = check_conflicts(self.rows, self.output_folder, flatten)
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
        log_path = save_log(log, self.output_folder)
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
    def on_undo_last(self):
        if not self.last_log:
            return
        removed, missing = undo_log(self.last_log)
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
            removed, missing = undo_log(path)
        except Exception as e:
            QMessageBox.critical(self, "되돌리기 실패", str(e))
            return
        self._log(f"로그({path})로 되돌리기 완료: {removed}건 삭제, {missing}건은 이미 없음")
        QMessageBox.information(self, "되돌리기 완료", f"{removed}건을 삭제했습니다. (원본은 그대로 유지됨)")

    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, status_message: str = ""):
        for w in (
            self.btn_select_folder, self.btn_load_map, self.btn_load_list,
            self.btn_check_dup, self.btn_select_output, self.btn_convert_all,
            self.btn_undo_last, self.btn_undo_log, self.radio_flatten, self.radio_preserve,
        ):
            w.setEnabled(not busy)
        if busy:
            self.statusBar().showMessage(status_message)
        else:
            self.statusBar().clearMessage()
            self.btn_undo_last.setEnabled(self.last_log is not None)

    def _log(self, message: str):
        self.log_view.appendPlainText(message)


def main():
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
