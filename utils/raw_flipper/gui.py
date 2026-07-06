"""raw_flipper PyQt5 GUI.

소스 폴더를 선택하면 내부 이미지 파일을 재귀 탐색해서 목록으로 보여주고,
결과 폴더·RAW 크기·처리 확장자를 설정한 뒤 실행하면 상하반전 결과를
동일한 폴더 구조로 저장한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5 import QtCore, QtWidgets

from flipper import (
    CV2_EXTENSIONS,
    RAW_EXTENSIONS,
    flip_all,
    scan_files,
)

ALL_DEFAULT_EXT = {".raw", ".png", ".bmp"}
EXTRA_EXT = {".tiff", ".tif", ".jpg", ".jpeg"}


class FlipWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, int)
    log_line = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int, int)

    def __init__(self, src_dir, dst_dir, extensions, raw_w, raw_h):
        super().__init__()
        self.src_dir = src_dir
        self.dst_dir = dst_dir
        self.extensions = extensions
        self.raw_w = raw_w
        self.raw_h = raw_h

    def run(self):
        results = flip_all(
            src_dir=self.src_dir,
            dst_dir=self.dst_dir,
            extensions=self.extensions,
            raw_width=self.raw_w,
            raw_height=self.raw_h,
            log=self.log_line.emit,
            progress=self.progress.emit,
        )
        ok = sum(r.success for r in results)
        self.finished.emit(ok, len(results))


class RawFlipperWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RAW Flipper (상하반전)")
        self.resize(780, 640)
        self._src_dir: Path | None = None
        self._dst_dir: Path | None = None
        self._worker: FlipWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(central)

        # 소스 폴더
        src_row = QtWidgets.QHBoxLayout()
        src_row.addWidget(QtWidgets.QLabel("소스 폴더:"))
        self.src_edit = QtWidgets.QLineEdit()
        self.src_edit.setReadOnly(True)
        src_row.addWidget(self.src_edit)
        src_btn = QtWidgets.QPushButton("찾아보기")
        src_btn.clicked.connect(self.on_browse_src)
        src_row.addWidget(src_btn)
        root.addLayout(src_row)

        # 결과 폴더
        dst_row = QtWidgets.QHBoxLayout()
        dst_row.addWidget(QtWidgets.QLabel("결과 폴더:"))
        self.dst_edit = QtWidgets.QLineEdit()
        self.dst_edit.setReadOnly(True)
        dst_row.addWidget(self.dst_edit)
        dst_btn = QtWidgets.QPushButton("찾아보기")
        dst_btn.clicked.connect(self.on_browse_dst)
        dst_row.addWidget(dst_btn)
        root.addLayout(dst_row)

        # 옵션 행
        opt_row = QtWidgets.QGridLayout()

        opt_row.addWidget(QtWidgets.QLabel("RAW 크기 (W×H):"), 0, 0)
        size_box = QtWidgets.QHBoxLayout()
        self.w_spin = QtWidgets.QSpinBox()
        self.w_spin.setRange(1, 99999)
        self.w_spin.setValue(3072)
        self.h_spin = QtWidgets.QSpinBox()
        self.h_spin.setRange(1, 99999)
        self.h_spin.setValue(3072)
        size_box.addWidget(self.w_spin)
        size_box.addWidget(QtWidgets.QLabel("×"))
        size_box.addWidget(self.h_spin)
        opt_row.addLayout(size_box, 0, 1)

        opt_row.addWidget(QtWidgets.QLabel("처리 확장자:"), 1, 0)
        ext_box = QtWidgets.QHBoxLayout()
        self.ext_checks: dict[str, QtWidgets.QCheckBox] = {}
        for ext in [".raw", ".png", ".bmp", ".tiff", ".jpg"]:
            cb = QtWidgets.QCheckBox(ext)
            cb.setChecked(ext in ALL_DEFAULT_EXT)
            cb.stateChanged.connect(self.on_ext_changed)
            self.ext_checks[ext] = cb
            ext_box.addWidget(cb)
        opt_row.addLayout(ext_box, 1, 1)

        root.addLayout(opt_row)

        # 탐색된 파일 목록
        root.addWidget(QtWidgets.QLabel("탐색된 파일 목록:"))
        self.file_list = QtWidgets.QListWidget()
        self.file_list.setMaximumHeight(180)
        root.addWidget(self.file_list)

        # 진행 상황
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)

        # 실행 버튼
        self.run_btn = QtWidgets.QPushButton("실행 (상하반전)")
        self.run_btn.clicked.connect(self.on_run)
        root.addWidget(self.run_btn)

        # 로그
        root.addWidget(QtWidgets.QLabel("결과 / 로그:"))
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        root.addWidget(self.log_box)

        self.setCentralWidget(central)

    def _selected_extensions(self) -> set[str]:
        return {ext for ext, cb in self.ext_checks.items() if cb.isChecked()}

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        if self._src_dir is None:
            return
        exts = self._selected_extensions()
        if not exts:
            return
        files = scan_files(self._src_dir, exts)
        for f in files:
            self.file_list.addItem(str(f.relative_to(self._src_dir)))
        self.log(f"소스 폴더 탐색 완료: {len(files)}개 파일 발견")

    def log(self, text: str) -> None:
        self.log_box.appendPlainText(text)
        print(text)

    def on_browse_src(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "소스 폴더 선택")
        if path:
            self._src_dir = Path(path)
            self.src_edit.setText(path)
            self._refresh_file_list()

    def on_browse_dst(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "결과 폴더 선택")
        if path:
            self._dst_dir = Path(path)
            self.dst_edit.setText(path)

    def on_ext_changed(self) -> None:
        self._refresh_file_list()

    def on_run(self) -> None:
        if self._src_dir is None:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "소스 폴더를 선택하세요.")
            return
        if self._dst_dir is None:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "결과 폴더를 선택하세요.")
            return
        exts = self._selected_extensions()
        if not exts:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "처리할 확장자를 1개 이상 선택하세요.")
            return

        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_box.clear()
        self.log(f"=== 시작: {self._src_dir} → {self._dst_dir} | 확장자: {exts} ===")

        self._worker = FlipWorker(
            src_dir=self._src_dir,
            dst_dir=self._dst_dir,
            extensions=exts,
            raw_w=self.w_spin.value(),
            raw_h=self.h_spin.value(),
        )
        self._worker.log_line.connect(self.log)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_finished(self, ok: int, total: int) -> None:
        self.progress_bar.setValue(100)
        self.run_btn.setEnabled(True)
        self.log(f"=== 완료: {ok}/{total}개 성공 ===")
        QtWidgets.QMessageBox.information(
            self, "완료", f"상하반전 완료\n성공: {ok} / 전체: {total}"
        )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    win = RawFlipperWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
