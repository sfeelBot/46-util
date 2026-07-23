"""필캡쳐(FeelCapture) — 화면 캡쳐/녹화 트레이 상주 앱.

실행:
    .venv\\Scripts\\python.exe utils\\feel_capture\\main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import keyboard as kb
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from capture_core import grab_region, grab_virtual_desktop, save_static_image
from config import RECORD_EXTS, load_config, save_config
from overlay_drag import DragSelectOverlay
from overlay_region import RegionBox
from recorder import RecordIndicator, RecorderThread
from settings_dialog import SettingsDialog


def resource_path(relative: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative)
    return str(Path(__file__).resolve().parent / relative)


class HotkeyBridge(QObject):
    """`keyboard` 라이브러리의 훅 스레드에서 오는 콜백을 Qt 메인 스레드 시그널로 넘겨준다."""

    fired = pyqtSignal()


class HotkeyManager:
    def __init__(self, callback):
        self._callback = callback
        self._registered = None

    def set_hotkey(self, hotkey_str: str):
        self.clear()
        if hotkey_str:
            try:
                kb.add_hotkey(hotkey_str, self._callback)
                self._registered = hotkey_str
            except Exception as e:
                print(f"[필캡쳐] 단축키 등록 실패: {hotkey_str} ({e})")

    def clear(self):
        if self._registered:
            try:
                kb.remove_hotkey(self._registered)
            except Exception:
                pass
            self._registered = None


class TrayApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = load_config()

        self.drag_overlay = None
        self.region_box = None
        self.recorder = None
        self.indicator = None

        self.icon = QIcon(resource_path("assets/icon.ico"))
        self.tray = QSystemTrayIcon(self.icon, app)
        self.tray.setToolTip("필캡쳐 (FeelCapture)")
        self._build_menu()
        self.tray.show()

        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.fired.connect(self.on_hotkey)
        self.hotkey_mgr = HotkeyManager(self.hotkey_bridge.fired.emit)

        self._apply_config()

    # ------------------------------------------------------------- menu
    def _build_menu(self):
        menu = QMenu()

        mode_menu = menu.addMenu("모드")
        self.act_mode_drag = QAction("드래그 방식", self, checkable=True)
        self.act_mode_region = QAction("영역 방식", self, checkable=True)
        group = QActionGroup(self)
        group.addAction(self.act_mode_drag)
        group.addAction(self.act_mode_region)
        self.act_mode_drag.triggered.connect(lambda: self._set_mode("drag"))
        self.act_mode_region.triggered.connect(lambda: self._set_mode("region"))
        mode_menu.addAction(self.act_mode_drag)
        mode_menu.addAction(self.act_mode_region)

        menu.addSeparator()
        settings_act = menu.addAction("설정...")
        settings_act.triggered.connect(self.open_settings)

        menu.addSeparator()
        quit_act = menu.addAction("종료")
        quit_act.triggered.connect(self.quit)

        self.tray.setContextMenu(menu)

    # ------------------------------------------------------------ config
    def _apply_config(self):
        cfg = self.cfg
        self.act_mode_drag.setChecked(cfg["mode"] == "drag")
        self.act_mode_region.setChecked(cfg["mode"] == "region")

        self.hotkey_mgr.set_hotkey(cfg.get("hotkey", ""))

        if cfg["mode"] == "region":
            self._ensure_region_box()
        else:
            self._teardown_region_box()

    def _ensure_region_box(self):
        box_cfg = self.cfg["region_box"]
        if self.region_box is None:
            self.region_box = RegionBox(
                box_cfg["x"],
                box_cfg["y"],
                box_cfg["w"],
                box_cfg["h"],
                locked=box_cfg.get("locked", False),
                presets=self.cfg.get("region_presets", []),
            )
            self.region_box.changed.connect(self._on_region_box_changed)
            self.region_box.openSettingsRequested.connect(self.open_settings)
        else:
            self.region_box.presets = self.cfg.get("region_presets", [])
        self.region_box.show()

    def _teardown_region_box(self):
        if self.region_box is not None:
            self.region_box.hide()

    def _on_region_box_changed(self):
        x, y, w, h = self.region_box.rect_in_screen()
        self.cfg["region_box"] = {"x": x, "y": y, "w": w, "h": h, "locked": self.region_box.locked}
        save_config(self.cfg)

    def _set_mode(self, mode):
        self.cfg["mode"] = mode
        save_config(self.cfg)
        self._apply_config()

    def open_settings(self):
        dlg = SettingsDialog(self.cfg)
        if dlg.exec_():
            self.cfg = dlg.result_config()
            save_config(self.cfg)
            self._apply_config()

    # ----------------------------------------------------------- capture
    def on_hotkey(self):
        if self.recorder is not None:
            self._stop_recording()
            return

        cfg = self.cfg
        is_record_format = cfg["extension"] in RECORD_EXTS

        if cfg["mode"] == "region":
            if self.region_box is None:
                return
            rect = self.region_box.rect_in_screen()
            if is_record_format:
                self._start_recording(rect)
            else:
                img = grab_region(*rect)
                self._finish_static_capture(img)
        else:
            self._start_drag_overlay(for_recording=is_record_format)

    def _start_drag_overlay(self, for_recording: bool):
        if self.drag_overlay is not None:
            return
        full_img, ox, oy = grab_virtual_desktop()
        overlay = DragSelectOverlay(full_img, ox, oy)
        overlay.finished.connect(lambda rect: self._on_drag_finished(rect, for_recording))
        self.drag_overlay = overlay
        overlay.show()
        overlay.activateWindow()

    def _on_drag_finished(self, rect, for_recording: bool):
        self.drag_overlay = None
        if rect is None:
            return
        region = (rect.x(), rect.y(), rect.width(), rect.height())
        if for_recording:
            self._start_recording(region)
        else:
            img = grab_region(*region)
            self._finish_static_capture(img)

    def _finish_static_capture(self, img):
        ok, msg = save_static_image(img, self.cfg)
        self._notify(msg, ok)

    def _start_recording(self, rect):
        self.recorder = RecorderThread(rect, dict(self.cfg))
        self.recorder.finished_result.connect(self._on_recording_finished)
        ix, iy, _iw, _ih = rect
        self.indicator = RecordIndicator(ix + 10, iy + 10)
        self.indicator.show()
        self.recorder.start()

    def _stop_recording(self):
        if self.recorder is not None:
            self.recorder.request_stop()

    def _on_recording_finished(self, ok: bool, msg: str):
        if self.indicator is not None:
            self.indicator.close()
            self.indicator = None
        self.recorder = None
        self._notify(msg, ok)

    def _notify(self, msg: str, ok: bool):
        icon = QSystemTrayIcon.Information if ok else QSystemTrayIcon.Warning
        self.tray.showMessage("필캡쳐", msg, icon, 3000)

    def quit(self):
        self.hotkey_mgr.clear()
        if self.region_box is not None:
            self.region_box.close()
        if self.recorder is not None:
            self.recorder.request_stop()
            self.recorder.wait(3000)
        self.tray.hide()
        self.app.quit()


def main():
    QApplication.setQuitOnLastWindowClosed(False)
    app = QApplication(sys.argv)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "필캡쳐", "이 시스템에서는 시스템 트레이를 사용할 수 없습니다.")
        sys.exit(1)

    tray_app = TrayApp(app)  # noqa: F841 (참조 유지 목적)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
