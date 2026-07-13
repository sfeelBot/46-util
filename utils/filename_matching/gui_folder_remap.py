"""그룹폴더 구조 기반 Crop 이미지 재명명 GUI (독립 실행).

GitHub 이슈 #5 대응: 일부 crop 파일명에 박혀있는 저장번호가 실제 셀
위치와 어긋나는 경우가 있어, 파일명 대신 폴더 구조(`{그룹번호}/cropped/`)를
신뢰해서 재명명한다. 계산 로직은 folder_crop_remap.py 참고.

gui.py 의 `ConversionTab`(폴더 스캔/테이블/중복검사/우클릭 탐색기/비동기
변환/되돌리기 공용 워크플로)을 그대로 재사용하고, "행을 어떻게 만드는지"만
이 파일의 `FolderGroupController`가 담당한다 (기존 gui.py 의
BarcodeMaterialController/CropRemapController 와 동일한 패턴).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QFileDialog, QMessageBox,
    QGridLayout,
)

import folder_crop_remap
from gui import ConversionTab

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_AB_MAP = BASE_DIR / "mapping" / "storage_ab_defect_info.csv"


class FolderGroupController:
    """그룹폴더(예: '02') + crop 순서(1~4)로 셀 인덱스를 계산해
    storage_ab_defect_info.csv 에서 올바른 A열 저장번호를 조회, 재명명한다."""

    title = "그룹폴더 기반 Crop 재명명"
    final_col_label = "재명명된 파일명"

    def __init__(self):
        self.ab_map_path = DEFAULT_AB_MAP
        self.ab_map: dict[int, str] = {}

    def is_ready(self) -> bool:
        return bool(self.ab_map)

    def on_tab_ready(self, tab: ConversionTab):
        self._load(tab, initial=True)

    def build_extra_ui(self, tab: ConversionTab, grid: QGridLayout, next_row: int) -> int:
        note = QLabel(
            "폴더 구조가 '{그룹번호}/cropped/{crop파일}' 형태여야 합니다 "
            "(예: A1_매칭(4셀 이미지)/02/cropped/...). "
            "그룹번호 N → 셀 인덱스 [4N-3, 4N], cropped 폴더의 crop 1~4가 오름차순으로 배정됩니다. "
            "베이스 파일명에 박힌 기존 저장번호는 신뢰하지 않고 무시합니다."
        )
        note.setWordWrap(True)
        grid.addWidget(note, next_row, 0, 1, 4)
        next_row += 1

        btn = QPushButton("셀 인덱스↔A열저장번호 매핑 불러오기...")
        lbl = QLabel(str(self.ab_map_path))
        lbl.setWordWrap(True)
        btn.clicked.connect(lambda: self._on_load_map(tab, lbl))
        grid.addWidget(btn, next_row, 0)
        grid.addWidget(lbl, next_row, 1, 1, 3)
        next_row += 1

        tab._extra_lock_widgets.append(btn)
        return next_row

    def _on_load_map(self, tab: ConversionTab, label: QLabel):
        path, _ = QFileDialog.getOpenFileName(
            tab, "셀 인덱스↔A열저장번호 매핑 CSV 선택", str(self.ab_map_path.parent), "CSV (*.csv)"
        )
        if not path:
            return
        self.ab_map_path = Path(path)
        label.setText(path)
        self._load(tab)

    def _load(self, tab: ConversionTab, initial=False):
        try:
            self.ab_map = folder_crop_remap.load_ab_map(self.ab_map_path)
            tab._log(f"매핑 로드 완료: 셀 인덱스↔A열저장번호 {len(self.ab_map)}건")
        except Exception as e:
            self.ab_map = {}
            if not initial:
                QMessageBox.critical(tab, "매핑 로드 실패", str(e))
            tab._log(f"매핑 로드 실패: {e}")

    def build_rows(self, root, extensions, exclude_dir):
        return folder_crop_remap.build_rows(root, extensions, self.ab_map, exclude_dir=exclude_dir)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("그룹폴더 기반 Crop 재명명")
        self.resize(1200, 760)

        self.tab = ConversionTab(FolderGroupController())
        self.setCentralWidget(self.tab)
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
