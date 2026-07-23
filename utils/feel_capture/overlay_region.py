"""영역 스크린샷: 화면에 항상 떠 있는 빨간 박스. 드래그로 이동/리사이즈, 우클릭으로 프리셋/설정."""
from __future__ import annotations

from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMenu,
    QSpinBox,
    QWidget,
)

EDGE_MARGIN = 8
MIN_SIZE = 30


class RegionBox(QWidget):
    """빨간 테두리 리사이즈/이동 가능한 프레임리스 위젯.

    changed: 위치/크기/잠금 상태가 바뀔 때마다 emit (호출측에서 config에 반영)
    openSettingsRequested: 우클릭 메뉴의 "설정 열기" 선택 시 emit
    """

    changed = pyqtSignal()
    openSettingsRequested = pyqtSignal()

    def __init__(self, x: int, y: int, w: int, h: int, locked: bool = False, presets=None):
        super().__init__()
        self.locked = locked
        self.presets = presets or []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(x, y, max(MIN_SIZE, w), max(MIN_SIZE, h))
        self.setMouseTracking(True)
        self._drag_mode = None
        self._drag_start_global = None
        self._drag_start_geom = None

    def rect_in_screen(self):
        g = self.geometry()
        return g.x(), g.y(), g.width(), g.height()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(255, 0, 0), 3)
        painter.setPen(pen)
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)

    def _hit_test(self, pos):
        if self.locked:
            return None
        w, h = self.width(), self.height()
        left = pos.x() <= EDGE_MARGIN
        right = pos.x() >= w - EDGE_MARGIN
        top = pos.y() <= EDGE_MARGIN
        bottom = pos.y() >= h - EDGE_MARGIN
        if top and left:
            return "nw"
        if top and right:
            return "ne"
        if bottom and left:
            return "sw"
        if bottom and right:
            return "se"
        if top:
            return "n"
        if bottom:
            return "s"
        if left:
            return "w"
        if right:
            return "e"
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._hit_test(event.pos())
            self._drag_mode = edge or "move"
            self._drag_start_global = event.globalPos()
            self._drag_start_geom = QRect(self.geometry())

    def mouseMoveEvent(self, event):
        if self._drag_start_global is None:
            edge = self._hit_test(event.pos())
            cursor_map = {
                "n": Qt.SizeVerCursor,
                "s": Qt.SizeVerCursor,
                "e": Qt.SizeHorCursor,
                "w": Qt.SizeHorCursor,
                "ne": Qt.SizeBDiagCursor,
                "sw": Qt.SizeBDiagCursor,
                "nw": Qt.SizeFDiagCursor,
                "se": Qt.SizeFDiagCursor,
            }
            self.setCursor(cursor_map.get(edge, Qt.SizeAllCursor))
            return

        delta = event.globalPos() - self._drag_start_global
        start = self._drag_start_geom
        geom = QRect(start)
        if self._drag_mode == "move":
            geom.moveTopLeft(start.topLeft() + delta)
        else:
            # 반대쪽(고정되어야 할) 경계를 앵커로 두고 새 좌표 자체를 클램프한다.
            # setWidth()/setHeight()로 사후 클램프하면 반대쪽 경계를 이미 넘어간
            # 좌표가 앵커가 되어버려 박스가 커서 위치로 순간이동하는 문제가 있었다.
            if "w" in self._drag_mode:
                geom.setLeft(min(start.left() + delta.x(), start.right() - MIN_SIZE + 1))
            if "e" in self._drag_mode:
                geom.setRight(max(start.right() + delta.x(), start.left() + MIN_SIZE - 1))
            if "n" in self._drag_mode:
                geom.setTop(min(start.top() + delta.y(), start.bottom() - MIN_SIZE + 1))
            if "s" in self._drag_mode:
                geom.setBottom(max(start.bottom() + delta.y(), start.top() + MIN_SIZE - 1))
        self.setGeometry(geom)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start_global is not None:
            self._drag_start_global = None
            self._drag_start_geom = None
            self.changed.emit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        preset_menu = menu.addMenu("프리셋 크기")
        for p in self.presets:
            act = preset_menu.addAction(f'{p["name"]} ({p["w"]}x{p["h"]})')
            act.triggered.connect(lambda checked=False, pp=p: self._apply_preset(pp))

        custom_act = menu.addAction("사용자 지정 크기...")
        custom_act.triggered.connect(self._open_custom_dialog)

        lock_act = menu.addAction("고정 크기 해제" if self.locked else "현재 크기로 고정")
        lock_act.triggered.connect(self._toggle_lock)

        menu.addSeparator()
        settings_act = menu.addAction("설정 열기...")
        settings_act.triggered.connect(self.openSettingsRequested.emit)

        menu.exec_(event.globalPos())

    def _apply_preset(self, preset):
        geom = self.geometry()
        self.setGeometry(geom.x(), geom.y(), preset["w"], preset["h"])
        self.locked = True
        self.changed.emit()

    def _toggle_lock(self):
        self.locked = not self.locked
        self.changed.emit()

    def _open_custom_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("사용자 지정 크기")
        layout = QFormLayout(dlg)
        w_spin = QSpinBox()
        w_spin.setRange(MIN_SIZE, 10000)
        w_spin.setValue(self.width())
        h_spin = QSpinBox()
        h_spin.setRange(MIN_SIZE, 10000)
        h_spin.setValue(self.height())
        lock_chk = QCheckBox("고정 크기로 사용")
        lock_chk.setChecked(True)
        layout.addRow("너비", w_spin)
        layout.addRow("높이", h_spin)
        layout.addRow(lock_chk)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addRow(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            geom = self.geometry()
            self.setGeometry(geom.x(), geom.y(), w_spin.value(), h_spin.value())
            self.locked = lock_chk.isChecked()
            self.changed.emit()
