"""crop_locator PyQt5 GUI.

원본 이미지와 crop 이미지(들)를 선택하고, colorspace / top-k / NMS 거리 / dry-run
옵션을 GUI에서 설정해 matcher.locate_crop을 실행하는 화면.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt5 import QtWidgets

from matcher import load_image, locate_crop

IMAGE_FILTER = "Images (*.bmp *.png);;All Files (*)"


class CropLocatorWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Crop Locator")
        self.resize(720, 600)

        self.original_edit = QtWidgets.QLineEdit()
        self.original_edit.setReadOnly(True)
        original_browse_btn = QtWidgets.QPushButton("찾아보기")
        original_browse_btn.clicked.connect(self.on_browse_original)

        self.crop_list = QtWidgets.QListWidget()
        crop_add_btn = QtWidgets.QPushButton("Crop 이미지 추가")
        crop_add_btn.clicked.connect(self.on_add_crops)
        crop_remove_btn = QtWidgets.QPushButton("선택 제거")
        crop_remove_btn.clicked.connect(self.on_remove_selected_crops)

        self.colorspace_combo = QtWidgets.QComboBox()
        self.colorspace_combo.addItems(["gray", "color"])

        self.topk_spin = QtWidgets.QSpinBox()
        self.topk_spin.setRange(1, 50)
        self.topk_spin.setValue(5)

        self.nms_auto_checkbox = QtWidgets.QCheckBox("자동 (템플릿 min(w,h)/2)")
        self.nms_auto_checkbox.setChecked(True)
        self.nms_auto_checkbox.toggled.connect(self.on_nms_auto_toggled)

        self.nms_spin = QtWidgets.QDoubleSpinBox()
        self.nms_spin.setRange(1.0, 10000.0)
        self.nms_spin.setValue(10.0)
        self.nms_spin.setEnabled(False)

        self.dry_run_checkbox = QtWidgets.QCheckBox("Dry run (탐색 과정만 출력, 최종 결과 미확정)")

        self.run_btn = QtWidgets.QPushButton("실행 (Run)")
        self.run_btn.clicked.connect(self.on_run)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)

        self._build_layout(
            original_browse_btn=original_browse_btn,
            crop_add_btn=crop_add_btn,
            crop_remove_btn=crop_remove_btn,
        )

    def _build_layout(
        self,
        original_browse_btn: QtWidgets.QPushButton,
        crop_add_btn: QtWidgets.QPushButton,
        crop_remove_btn: QtWidgets.QPushButton,
    ) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        original_row = QtWidgets.QHBoxLayout()
        original_row.addWidget(QtWidgets.QLabel("원본 이미지:"))
        original_row.addWidget(self.original_edit)
        original_row.addWidget(original_browse_btn)
        layout.addLayout(original_row)

        layout.addWidget(QtWidgets.QLabel("Crop 이미지 목록:"))
        layout.addWidget(self.crop_list)
        crop_btn_row = QtWidgets.QHBoxLayout()
        crop_btn_row.addWidget(crop_add_btn)
        crop_btn_row.addWidget(crop_remove_btn)
        layout.addLayout(crop_btn_row)

        options_grid = QtWidgets.QGridLayout()
        options_grid.addWidget(QtWidgets.QLabel("Colorspace:"), 0, 0)
        options_grid.addWidget(self.colorspace_combo, 0, 1)
        options_grid.addWidget(QtWidgets.QLabel("Top-K:"), 0, 2)
        options_grid.addWidget(self.topk_spin, 0, 3)
        options_grid.addWidget(self.nms_auto_checkbox, 1, 0, 1, 2)
        options_grid.addWidget(QtWidgets.QLabel("NMS 거리:"), 1, 2)
        options_grid.addWidget(self.nms_spin, 1, 3)
        layout.addLayout(options_grid)

        layout.addWidget(self.dry_run_checkbox)
        layout.addWidget(self.run_btn)

        layout.addWidget(QtWidgets.QLabel("결과 / 로그:"))
        layout.addWidget(self.log_box)

        self.setCentralWidget(central)

    def on_nms_auto_toggled(self, checked: bool) -> None:
        self.nms_spin.setEnabled(not checked)

    def on_browse_original(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "원본 이미지 선택", "", IMAGE_FILTER)
        if path:
            self.original_edit.setText(path)

    def on_add_crops(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Crop 이미지 선택", "", IMAGE_FILTER)
        for path in paths:
            self.crop_list.addItem(path)

    def on_remove_selected_crops(self) -> None:
        for item in self.crop_list.selectedItems():
            self.crop_list.takeItem(self.crop_list.row(item))

    def log(self, text: str) -> None:
        self.log_box.appendPlainText(text)
        print(text)

    def on_run(self) -> None:
        original_path_text = self.original_edit.text().strip()
        if not original_path_text:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "원본 이미지를 선택하세요.")
            return
        if self.crop_list.count() == 0:
            QtWidgets.QMessageBox.warning(self, "입력 오류", "Crop 이미지를 1개 이상 추가하세요.")
            return

        colorspace = self.colorspace_combo.currentText()
        topk = self.topk_spin.value()
        nms_dist = None if self.nms_auto_checkbox.isChecked() else self.nms_spin.value()
        dry_run = self.dry_run_checkbox.isChecked()

        original_path = Path(original_path_text)
        try:
            original_img = load_image(original_path, colorspace)
        except FileNotFoundError as exc:
            self.log(f"[ERROR] {exc}")
            return

        self.log_box.clear()
        self.log(f"=== 원본: {original_path.name} | colorspace={colorspace} | topk={topk} "
                  f"| nms_dist={'auto' if nms_dist is None else nms_dist} | dry_run={dry_run} ===")

        for i in range(self.crop_list.count()):
            crop_path = Path(self.crop_list.item(i).text())
            self.log(f"[{crop_path.name}] 후보 탐색 시작")
            try:
                template_img = load_image(crop_path, colorspace)
            except FileNotFoundError as exc:
                self.log(f"[ERROR] {exc}")
                continue

            result = locate_crop(
                original_img,
                template_img,
                crop_path,
                topk=topk,
                nms_dist=nms_dist,
                log=self.log,
            )

            if dry_run:
                self.log(f"[{crop_path.name}] dry-run: 최종 결과 미확정 (탐색 과정만 출력)")
                continue

            if result.found:
                self.log(
                    f"[RESULT] {crop_path.name}: x={result.x} y={result.y} "
                    f"w={result.w} h={result.h} score={result.score:.4f}"
                )
            else:
                self.log(f"[RESULT] {crop_path.name}: 일치하는 위치를 찾지 못했습니다.")


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = CropLocatorWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
