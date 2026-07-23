"""필캡쳐 설정 다이얼로그: 모드/저장방식/리사이즈/단축키/영역 프리셋 편집."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from config import ALL_EXTS, RECORD_EXTS, STATIC_EXTS


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("필캡쳐 설정")
        self.setMinimumWidth(420)
        self.cfg = dict(cfg)
        self._build_ui()
        self._load_from_cfg()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        # 모드
        mode_box = QGroupBox("캡쳐 모드")
        mode_layout = QHBoxLayout(mode_box)
        self.rb_mode_drag = QRadioButton("드래그 방식")
        self.rb_mode_region = QRadioButton("영역(고정 박스) 방식")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_mode_drag)
        self.mode_group.addButton(self.rb_mode_region)
        mode_layout.addWidget(self.rb_mode_drag)
        mode_layout.addWidget(self.rb_mode_region)
        root.addWidget(mode_box)

        # 저장 방식
        save_box = QGroupBox("저장 방식")
        save_form = QFormLayout(save_box)

        target_row = QHBoxLayout()
        self.rb_target_clipboard = QRadioButton("클립보드")
        self.rb_target_file = QRadioButton("출력 폴더")
        self.target_group = QButtonGroup(self)
        self.target_group.addButton(self.rb_target_clipboard)
        self.target_group.addButton(self.rb_target_file)
        target_row.addWidget(self.rb_target_clipboard)
        target_row.addWidget(self.rb_target_file)
        save_form.addRow("대상", target_row)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_browse_btn = QPushButton("찾아보기...")
        self.folder_browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(self.folder_browse_btn)
        save_form.addRow("출력 폴더", folder_row)

        self.ext_combo = QComboBox()
        self.ext_combo.addItems(ALL_EXTS)
        self.ext_combo.currentTextChanged.connect(self._on_ext_changed)
        save_form.addRow("확장자", self.ext_combo)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        save_form.addRow("녹화 FPS (동영상/gif만 해당)", self.fps_spin)

        self.record_hint = QLabel(
            "※ 동영상(mp4/avi)·gif는 단축키를 누르면 녹화가 시작되고, 다시 누르면 종료·저장됩니다.\n"
            "   (클립보드 저장은 정지 이미지 포맷에서만 가능합니다)"
        )
        self.record_hint.setWordWrap(True)
        save_form.addRow(self.record_hint)

        root.addWidget(save_box)

        # 리사이즈
        resize_box = QGroupBox("저장 시 리사이즈")
        resize_form = QFormLayout(resize_box)
        self.resize_group = QButtonGroup(self)
        self.rb_resize_off = QRadioButton("사용 안 함")
        self.rb_resize_fixed = QRadioButton("고정 크기 (W x H, 한쪽 비우면 비율 유지)")
        self.rb_resize_percent = QRadioButton("비율 (%)")
        for rb in (self.rb_resize_off, self.rb_resize_fixed, self.rb_resize_percent):
            self.resize_group.addButton(rb)
            resize_form.addRow(rb)

        wh_row = QHBoxLayout()
        self.resize_w_spin = QSpinBox()
        self.resize_w_spin.setRange(0, 10000)
        self.resize_w_spin.setSpecialValueText("(비움)")
        self.resize_h_spin = QSpinBox()
        self.resize_h_spin.setRange(0, 10000)
        self.resize_h_spin.setSpecialValueText("(비움)")
        wh_row.addWidget(QLabel("W"))
        wh_row.addWidget(self.resize_w_spin)
        wh_row.addWidget(QLabel("H"))
        wh_row.addWidget(self.resize_h_spin)
        resize_form.addRow(wh_row)

        self.resize_percent_spin = QSpinBox()
        self.resize_percent_spin.setRange(1, 500)
        self.resize_percent_spin.setSuffix(" %")
        resize_form.addRow(self.resize_percent_spin)

        root.addWidget(resize_box)

        # 단축키
        hotkey_box = QGroupBox("트리거 단축키")
        hotkey_form = QFormLayout(hotkey_box)
        self.hotkey_edit = QKeySequenceEdit()
        hotkey_form.addRow("단축키", self.hotkey_edit)
        hotkey_hint = QLabel("현재 선택된 모드로 캡쳐(또는 녹화 시작/종료)를 실행합니다.")
        hotkey_hint.setWordWrap(True)
        hotkey_form.addRow(hotkey_hint)
        root.addWidget(hotkey_box)

        # 영역 프리셋
        preset_box = QGroupBox("영역 모드 프리셋 (우클릭 메뉴에 표시됨)")
        preset_form = QFormLayout(preset_box)
        self.preset_widgets = []
        for i in range(3):
            name_edit = QLineEdit()
            w_spin = QSpinBox()
            w_spin.setRange(30, 10000)
            h_spin = QSpinBox()
            h_spin.setRange(30, 10000)
            row = QHBoxLayout()
            row.addWidget(QLabel("이름"))
            row.addWidget(name_edit)
            row.addWidget(QLabel("W"))
            row.addWidget(w_spin)
            row.addWidget(QLabel("H"))
            row.addWidget(h_spin)
            preset_form.addRow(f"프리셋 {i + 1}", row)
            self.preset_widgets.append((name_edit, w_spin, h_spin))
        root.addWidget(preset_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------ helpers
    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _on_ext_changed(self, ext: str):
        is_record = ext in RECORD_EXTS
        self.fps_spin.setEnabled(is_record)
        if is_record and self.rb_target_clipboard.isChecked():
            self.rb_target_file.setChecked(True)
        self.rb_target_clipboard.setEnabled(not is_record)

    def _load_from_cfg(self):
        cfg = self.cfg
        (self.rb_mode_drag if cfg["mode"] == "drag" else self.rb_mode_region).setChecked(True)
        (self.rb_target_clipboard if cfg["save_target"] == "clipboard" else self.rb_target_file).setChecked(True)
        self.folder_edit.setText(cfg.get("output_folder", ""))
        idx = self.ext_combo.findText(cfg.get("extension", "png"))
        self.ext_combo.setCurrentIndex(max(0, idx))
        self._on_ext_changed(self.ext_combo.currentText())
        self.fps_spin.setValue(int(cfg.get("fps", 12)))

        resize_mode = cfg.get("resize_mode", "fixed")
        if not cfg.get("resize_enabled"):
            self.rb_resize_off.setChecked(True)
        elif resize_mode == "percent":
            self.rb_resize_percent.setChecked(True)
        else:
            self.rb_resize_fixed.setChecked(True)
        self.resize_w_spin.setValue(int(cfg.get("resize_width") or 0))
        self.resize_h_spin.setValue(int(cfg.get("resize_height") or 0))
        self.resize_percent_spin.setValue(int(cfg.get("resize_percent", 50)))

        if cfg.get("hotkey"):
            self.hotkey_edit.setKeySequence(QKeySequence(cfg["hotkey"], QKeySequence.PortableText))

        presets = cfg.get("region_presets", [])
        for i, (name_edit, w_spin, h_spin) in enumerate(self.preset_widgets):
            if i < len(presets):
                name_edit.setText(presets[i].get("name", f"프리셋{i + 1}"))
                w_spin.setValue(int(presets[i].get("w", 800)))
                h_spin.setValue(int(presets[i].get("h", 600)))

    def _on_accept(self):
        target_is_file = self.rb_target_file.isChecked()
        if target_is_file and not self.folder_edit.text().strip():
            QMessageBox.warning(self, "필캡쳐", "출력 폴더 저장을 선택했다면 폴더 경로를 입력해야 합니다.")
            return

        seq = self.hotkey_edit.keySequence()
        if seq.isEmpty():
            QMessageBox.warning(self, "필캡쳐", "단축키를 지정해 주세요.")
            return

        self.accept()

    def result_config(self) -> dict:
        """OK로 닫힌 뒤 호출: 다이얼로그 입력값을 반영한 새 config dict를 반환."""
        cfg = dict(self.cfg)
        cfg["mode"] = "drag" if self.rb_mode_drag.isChecked() else "region"
        cfg["save_target"] = "clipboard" if self.rb_target_clipboard.isChecked() else "file"
        cfg["output_folder"] = self.folder_edit.text().strip()
        cfg["extension"] = self.ext_combo.currentText()
        cfg["fps"] = self.fps_spin.value()

        if self.rb_resize_off.isChecked():
            cfg["resize_enabled"] = False
        elif self.rb_resize_percent.isChecked():
            cfg["resize_enabled"] = True
            cfg["resize_mode"] = "percent"
            cfg["resize_percent"] = self.resize_percent_spin.value()
        else:
            cfg["resize_enabled"] = True
            cfg["resize_mode"] = "fixed"
            cfg["resize_width"] = self.resize_w_spin.value() or None
            cfg["resize_height"] = self.resize_h_spin.value() or None

        cfg["hotkey"] = self.hotkey_edit.keySequence().toString(QKeySequence.PortableText).lower()

        presets = []
        for i, (name_edit, w_spin, h_spin) in enumerate(self.preset_widgets):
            presets.append(
                {
                    "name": name_edit.text().strip() or f"프리셋{i + 1}",
                    "w": w_spin.value(),
                    "h": h_spin.value(),
                }
            )
        cfg["region_presets"] = presets

        return cfg
