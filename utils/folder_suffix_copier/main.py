# -*- coding: utf-8 -*-
"""folder_suffix_copier — 상위 폴더명 접미어 복사 도구.

지정 폴더를 재귀 탐색하여 파일(bmp/raw 기본, 확장자 선택 가능)을 찾고,
지정 폴더 기준 상대경로의 상위 폴더명들을 `_`로 이어붙인 접미어를
파일명 뒤(확장자 앞)에 붙인 사본을 만든다. 원본은 수정/이동하지 않는다.

예) 대상 폴더 E:\\data, 파일 E:\\data\\LotA\\Cell1\\img.bmp
    → img_LotA_Cell1.bmp

실행:
    .venv\\Scripts\\python.exe utils\\folder_suffix_copier\\main.py
"""

import os
import shutil
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# 스캔 후 기본으로 체크되는 확장자
DEFAULT_CHECKED_EXTS = {".bmp", ".raw"}


def scan_files(root: Path, exclude_dir: Path = None):
    """root 아래 모든 파일을 재귀 수집한다.

    exclude_dir(출력 폴더)가 root 안에 있으면 그 하위는 탐색하지 않는다.
    확장자 없는 파일은 제외한다.
    반환: (파일 Path 리스트, 발견된 소문자 확장자 set)
    """
    exclude_resolved = exclude_dir.resolve() if exclude_dir is not None else None
    files = []
    exts = set()
    for dirpath, dirnames, filenames in os.walk(root):
        if exclude_resolved is not None:
            dirnames[:] = [
                d for d in dirnames
                if (Path(dirpath) / d).resolve() != exclude_resolved
            ]
        for name in filenames:
            p = Path(dirpath) / name
            ext = p.suffix.lower()
            if not ext:
                continue
            files.append(p)
            exts.add(ext)
    files.sort(key=lambda p: str(p).lower())
    return files, exts


def build_plan(root: Path, files, separate_output: bool, out_dir: Path = None):
    """복사 계획을 만든다.

    각 파일에 대해 (원본 Path, 대상 Path, 상대경로 문자열, 번호부여 여부)를 반환.
    - 접미어: root 기준 상대경로의 폴더명들을 '_'로 연결 (root 바로 아래 파일은 접미어 없음)
    - separate_output=True 면 out_dir 한 곳에 모으고, False 면 원본과 같은 폴더에 생성
    - 대상 폴더에 이미 있는 파일명 / 계획 내 중복 이름은 `_2`, `_3` … 번호를 붙인다
      (대소문자 무시 비교. 같은 폴더 모드에서는 원본 자신과의 충돌도 여기서 걸러진다)
    """
    plan = []
    used = {}  # 대상 폴더(소문자 경로) -> 사용 중인 파일명(소문자) set
    for src in files:
        rel = src.relative_to(root)
        parts = rel.parts[:-1]
        stem, ext = os.path.splitext(rel.name)
        suffix = ("_" + "_".join(parts)) if parts else ""
        base = stem + suffix

        dest_dir = out_dir if separate_output else src.parent
        key = str(dest_dir.resolve()).lower()
        if key not in used:
            names = set()
            if dest_dir.is_dir():
                names = {q.name.lower() for q in dest_dir.iterdir() if q.is_file()}
            used[key] = names

        name = base + ext
        n = 1
        while name.lower() in used[key]:
            n += 1
            name = f"{base}_{n}{ext}"
        used[key].add(name.lower())
        plan.append((src, dest_dir / name, str(rel), n > 1))
    return plan


class CopyWorker(QThread):
    """복사 작업 스레드. GUI 멈춤 방지용."""

    progressed = pyqtSignal(int, int, str)   # (완료 수, 전체 수, 로그 한 줄)
    finished_all = pyqtSignal(int, int)      # (성공 수, 실패 수)

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self._plan = plan

    def run(self):
        ok = fail = 0
        total = len(self._plan)
        for i, (src, dest, rel, renumbered) in enumerate(self._plan, 1):
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                ok += 1
                note = "  (이름 충돌 → 번호 부여)" if renumbered else ""
                msg = f"{rel}  →  {dest.name}{note}"
            except Exception as e:  # noqa: BLE001 - 파일 단위로 계속 진행
                fail += 1
                msg = f"[실패] {rel}: {e}"
            self.progressed.emit(i, total, msg)
        self.finished_all.emit(ok, fail)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("folder_suffix_copier — 상위 폴더명 접미어 복사")
        self.resize(900, 700)

        self._all_files = []   # 스캔된 전체 파일
        self._plan = []        # 현재 미리보기 계획
        self._worker = None

        root_layout = QVBoxLayout(self)

        # --- 대상 폴더 ---
        gb_target = QGroupBox("대상 폴더")
        lay = QHBoxLayout(gb_target)
        self.ed_target = QLineEdit()
        btn_browse = QPushButton("찾아보기…")
        btn_browse.clicked.connect(self._browse_target)
        lay.addWidget(self.ed_target)
        lay.addWidget(btn_browse)
        root_layout.addWidget(gb_target)

        # --- 저장 방식 ---
        gb_mode = QGroupBox("저장 방식")
        lay = QVBoxLayout(gb_mode)
        self.rb_separate = QRadioButton("별도 출력 폴더에 모으기")
        self.rb_inplace = QRadioButton("원본과 같은 폴더에 생성")
        self.rb_separate.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.rb_separate)
        grp.addButton(self.rb_inplace)
        lay.addWidget(self.rb_separate)
        row = QHBoxLayout()
        row.addSpacing(24)
        row.addWidget(QLabel("출력 폴더:"))
        self.ed_output = QLineEdit()
        self.btn_browse_out = QPushButton("찾아보기…")
        self.btn_browse_out.clicked.connect(self._browse_output)
        row.addWidget(self.ed_output)
        row.addWidget(self.btn_browse_out)
        lay.addLayout(row)
        lay.addWidget(self.rb_inplace)
        self.rb_separate.toggled.connect(self._on_mode_changed)
        self.rb_separate.toggled.connect(self._rebuild_preview)
        root_layout.addWidget(gb_mode)

        # --- 스캔 ---
        self.btn_scan = QPushButton("스캔 (하위 폴더 재귀 탐색)")
        self.btn_scan.clicked.connect(self._scan)
        root_layout.addWidget(self.btn_scan)

        # --- 확장자 선택 ---
        self.gb_exts = QGroupBox("확장자 선택 (체크된 확장자만 복사)")
        self.lay_exts = QHBoxLayout(self.gb_exts)
        self.lay_exts.addWidget(QLabel("먼저 스캔을 실행하세요."))
        root_layout.addWidget(self.gb_exts)

        # --- 미리보기 테이블 ---
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["상대경로", "변경 전", "변경 후"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 320)
        self.table.setColumnWidth(1, 220)
        root_layout.addWidget(self.table, stretch=3)

        # --- 실행 + 진행률 ---
        row = QHBoxLayout()
        self.btn_run = QPushButton("실행 (복사)")
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self._run_copy)
        self.progress = QProgressBar()
        row.addWidget(self.btn_run)
        row.addWidget(self.progress, stretch=1)
        root_layout.addLayout(row)

        # --- 로그 ---
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root_layout.addWidget(self.log, stretch=2)

    # ---------- UI 핸들러 ----------

    def _browse_target(self):
        d = QFileDialog.getExistingDirectory(self, "대상 폴더 선택")
        if d:
            self.ed_target.setText(d)
            # 출력 폴더 기본값 제안: <대상폴더>_renamed
            root = Path(d)
            self.ed_output.setText(str(root.parent / (root.name + "_renamed")))

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "출력 폴더 선택")
        if d:
            self.ed_output.setText(d)

    def _on_mode_changed(self):
        sep = self.rb_separate.isChecked()
        self.ed_output.setEnabled(sep)
        self.btn_browse_out.setEnabled(sep)

    def _append_log(self, text):
        self.log.appendPlainText(text)

    # ---------- 스캔 / 미리보기 ----------

    def _scan(self):
        target = self.ed_target.text().strip()
        if not target or not Path(target).is_dir():
            QMessageBox.warning(self, "오류", "대상 폴더를 올바르게 지정하세요.")
            return
        root = Path(target)
        exclude = None
        if self.rb_separate.isChecked() and self.ed_output.text().strip():
            exclude = Path(self.ed_output.text().strip())

        self._all_files, exts = scan_files(root, exclude)

        # 확장자 체크박스 재구성 (bmp/raw는 기본 체크)
        while self.lay_exts.count():
            item = self.lay_exts.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._ext_checks = []
        if not exts:
            self.lay_exts.addWidget(QLabel("파일이 없습니다."))
        for ext in sorted(exts):
            cb = QCheckBox(ext)
            cb.setChecked(ext in DEFAULT_CHECKED_EXTS)
            cb.toggled.connect(self._rebuild_preview)
            self.lay_exts.addWidget(cb)
            self._ext_checks.append(cb)
        self.lay_exts.addStretch(1)

        self._append_log(
            f"[스캔] {root} — 파일 {len(self._all_files)}개, "
            f"확장자: {', '.join(sorted(exts)) if exts else '(없음)'}"
        )
        self._rebuild_preview()

    def _checked_exts(self):
        return {cb.text() for cb in getattr(self, "_ext_checks", []) if cb.isChecked()}

    def _rebuild_preview(self):
        target = self.ed_target.text().strip()
        if not target or not Path(target).is_dir() or not self._all_files:
            self.table.setRowCount(0)
            self._plan = []
            self.btn_run.setEnabled(False)
            return
        root = Path(target)
        exts = self._checked_exts()
        files = [f for f in self._all_files if f.suffix.lower() in exts]

        separate = self.rb_separate.isChecked()
        out_dir = Path(self.ed_output.text().strip()) if separate else None
        if separate and not self.ed_output.text().strip():
            self.table.setRowCount(0)
            self._plan = []
            self.btn_run.setEnabled(False)
            return

        self._plan = build_plan(root, files, separate, out_dir)

        self.table.setRowCount(len(self._plan))
        for i, (src, dest, rel, renumbered) in enumerate(self._plan):
            self.table.setItem(i, 0, QTableWidgetItem(rel))
            self.table.setItem(i, 1, QTableWidgetItem(src.name))
            item = QTableWidgetItem(dest.name)
            if renumbered:
                item.setForeground(Qt.red)
            self.table.setItem(i, 2, item)
        self.btn_run.setEnabled(bool(self._plan))

    # ---------- 실행 ----------

    def _run_copy(self):
        if not self._plan:
            return
        # 실행 직전 최신 상태로 계획 재계산 (스캔 이후 파일 변동 대비)
        self._rebuild_preview()
        if not self._plan:
            QMessageBox.information(self, "안내", "복사할 파일이 없습니다.")
            return

        dests = ", ".join(sorted({str(p[1].parent) for p in self._plan})[:3])
        ret = QMessageBox.question(
            self, "실행 확인",
            f"{len(self._plan)}개 파일을 복사합니다.\n대상: {dests} …\n진행할까요?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.progress.setValue(0)
        self.progress.setMaximum(len(self._plan))
        self._append_log(f"[실행] 복사 시작 — {len(self._plan)}개")

        self._worker = CopyWorker(self._plan)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _set_busy(self, busy):
        for w in (self.btn_scan, self.btn_run, self.ed_target,
                  self.rb_separate, self.rb_inplace):
            w.setEnabled(not busy)
        if not busy:
            self._on_mode_changed()
            self.btn_run.setEnabled(bool(self._plan))

    def _on_progress(self, done, total, msg):
        self.progress.setValue(done)
        self._append_log(msg)

    def _on_finished(self, ok, fail):
        self._append_log(f"[완료] 성공 {ok}개, 실패 {fail}개")
        self._set_busy(False)
        QMessageBox.information(self, "완료", f"복사 완료\n성공 {ok}개 / 실패 {fail}개")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
