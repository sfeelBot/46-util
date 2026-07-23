"""드래그 방식 스크린샷: 화면을 어둡게 덮고, 드래그한 사각형 부분만 밝게 표시."""
from __future__ import annotations

from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget


def pil_to_qpixmap(img) -> QPixmap:
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class DragSelectOverlay(QWidget):
    """가상 데스크톱 전체를 덮는 반투명 오버레이. 완료 시 finished(QRect|None)를 emit한다.

    QRect는 가상 데스크톱(스크린) 좌표계 기준. 취소(ESC) 또는 너무 작은 드래그(5px 미만)면 None.
    """

    finished = pyqtSignal(object)

    MIN_SIZE = 5

    def __init__(self, full_img, offset_x: int, offset_y: int):
        super().__init__()
        self._offset = (offset_x, offset_y)
        self._pixmap = pil_to_qpixmap(full_img)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setGeometry(offset_x, offset_y, full_img.width, full_img.height)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self._origin = None
        self._current = None
        self._done = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._origin and self._current:
            sel = QRect(self._origin, self._current).normalized()
            painter.setClipRect(sel)
            painter.drawPixmap(0, 0, self._pixmap)
            painter.setClipping(False)

            pen = QPen(QColor(255, 60, 60), 2)
            painter.setPen(pen)
            painter.drawRect(sel.adjusted(0, 0, -1, -1))

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(sel.left(), max(12, sel.top() - 6), f"{sel.width()} x {sel.height()}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._origin is not None:
            sel = QRect(self._origin, event.pos()).normalized()
            self._origin = None
            self._current = None
            self._finish(sel if sel.width() >= self.MIN_SIZE and sel.height() >= self.MIN_SIZE else None)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._finish(None)

    def _finish(self, local_rect: QRect | None):
        if self._done:
            return
        self._done = True
        if local_rect is None:
            self.finished.emit(None)
        else:
            ox, oy = self._offset
            global_rect = QRect(local_rect.left() + ox, local_rect.top() + oy, local_rect.width(), local_rect.height())
            self.finished.emit(global_rect)
        self.close()
