"""영역 녹화: mp4/avi(OpenCV)와 애니메이션 gif(Pillow) 녹화 스레드 + 화면 상단의 REC 표시 위젯."""
from __future__ import annotations

import threading
import time

import cv2
import mss
import numpy as np
from PIL import Image
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from capture_core import apply_resize, make_output_path
from logger import get_logger

log = get_logger()


class RecordIndicator(QWidget):
    """녹화 중임을 알리는 작은 빨간 배지 (● REC mm:ss)."""

    def __init__(self, x: int, y: int):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.label = QLabel("● REC 00:00")
        self.label.setStyleSheet(
            "color: white; background-color: rgba(200,0,0,220);"
            " padding: 4px 10px; border-radius: 4px; font-weight: bold;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.move(max(0, x), max(0, y))
        self._start = time.time()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)

    def _tick(self):
        elapsed = int(time.time() - self._start)
        self.label.setText(f"● REC {elapsed // 60:02d}:{elapsed % 60:02d}")


class RecorderThread(QThread):
    """rect(x,y,w,h) 영역을 cfg에 따라 gif/mp4/avi로 녹화한다. request_stop()으로 종료."""

    finished_result = pyqtSignal(bool, str)

    def __init__(self, rect, cfg: dict):
        super().__init__()
        self.x, self.y, self.w, self.h = rect
        self.cfg = cfg
        self._stop_event = threading.Event()

    def request_stop(self):
        self._stop_event.set()

    def run(self):
        ext = self.cfg["extension"]
        fps = max(1, int(self.cfg.get("fps", 12)))
        interval = 1.0 / fps

        folder = self.cfg.get("output_folder", "")
        if not folder:
            log.error("녹화 실패: 출력 폴더가 설정되지 않음")
            self.finished_result.emit(False, "출력 폴더가 설정되지 않았습니다.")
            return

        try:
            out_path = make_output_path(folder, ext)
            if ext in ("gif",):
                self._record_gif(out_path, fps, interval)
            else:
                self._record_video(out_path, ext, fps, interval)
        except Exception as e:
            log.exception("녹화 실패: rect=(%s,%s,%s,%s) ext=%s", self.x, self.y, self.w, self.h, ext)
            self.finished_result.emit(False, f"녹화 실패: {e}")

    def _grab(self, sct) -> Image.Image:
        monitor = {"left": self.x, "top": self.y, "width": self.w, "height": self.h}
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def _record_gif(self, out_path, fps, interval):
        frames = []
        next_t = time.time()
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                img = self._grab(sct)
                img = apply_resize(img, self.cfg)
                frames.append(img)
                next_t += interval
                sleep_t = next_t - time.time()
                if sleep_t > 0:
                    time.sleep(sleep_t)

        if not frames:
            self.finished_result.emit(False, "녹화된 프레임이 없습니다.")
            return

        frames[0].save(
            str(out_path),
            save_all=True,
            append_images=frames[1:],
            duration=max(1, int(1000 / fps)),
            loop=0,
        )
        self.finished_result.emit(True, f"저장됨: {out_path}")

    def _record_video(self, out_path, ext, fps, interval):
        fourcc = cv2.VideoWriter_fourcc(*("mp4v" if ext == "mp4" else "XVID"))
        writer = None
        next_t = time.time()
        frame_count = 0
        try:
            with mss.mss() as sct:
                while not self._stop_event.is_set():
                    img = self._grab(sct)
                    img = apply_resize(img, self.cfg)
                    if writer is None:
                        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (img.width, img.height))
                    frame = np.array(img)[:, :, ::-1]  # RGB -> BGR
                    writer.write(np.ascontiguousarray(frame))
                    frame_count += 1
                    next_t += interval
                    sleep_t = next_t - time.time()
                    if sleep_t > 0:
                        time.sleep(sleep_t)
        finally:
            if writer is not None:
                writer.release()

        if frame_count == 0:
            self.finished_result.emit(False, "녹화된 프레임이 없습니다.")
            return
        self.finished_result.emit(True, f"저장됨: {out_path}")
