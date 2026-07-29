"""필캡쳐 로그 설정.

기본 위치(%APPDATA%\\FeelCapture\\logs, 설정에서 변경 가능)에 회전 로그 파일
(feel_capture.log, 2MB 초과 시 feel_capture.log.1/.2/.3으로 순환)을 남긴다.
문제가 생기면 이 로그 파일을 GitHub issue에 붙여넣으면 원인 진단에 활용할 수 있다
— 그래서 각 동작(캡쳐/녹화 시작·종료, 모드/설정 변경, 단축키 등록)과 모든 예외를
전체 traceback과 함께 기록한다.
"""
from __future__ import annotations

import logging
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "feel_capture"
LOG_FILENAME = "feel_capture.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3

_current_handler = None


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def setup_logging(log_folder: str) -> logging.Logger:
    """log_folder에 회전 파일 핸들러를 (재)설정한다.

    log_folder가 빈 문자열이면 파일 핸들러를 붙이지 않아(=로깅 비활성화) INFO 이하
    로그는 조용히 버려진다. 설정에서 로그 폴더를 바꾼 뒤 다시 호출하면 기존 핸들러를
    닫고 새 폴더로 교체한다.
    """
    global _current_handler
    logger = get_logger()
    logger.setLevel(logging.INFO)

    if _current_handler is not None:
        logger.removeHandler(_current_handler)
        _current_handler.close()
        _current_handler = None

    if not log_folder:
        return logger

    folder = Path(log_folder)
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        folder / LOG_FILENAME, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    _current_handler = handler
    return logger


def log_environment_info(logger: logging.Logger, app_version: str) -> None:
    logger.info("=" * 60)
    logger.info("필캡쳐(FeelCapture) 시작 — 버전 %s", app_version)
    logger.info("OS: %s", platform.platform())
    logger.info("Python: %s", sys.version.replace("\n", " "))
    try:
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        logger.info("PyQt5: %s / Qt: %s", PYQT_VERSION_STR, QT_VERSION_STR)
    except Exception:
        logger.info("PyQt5 버전 확인 실패")
    logger.info("실행 모드: %s", "exe (frozen)" if getattr(sys, "frozen", False) else "python 스크립트")


def install_excepthook(logger: logging.Logger) -> None:
    """처리되지 않은 예외를 전체 traceback과 함께 로그에 남긴 뒤 기본 처리로 넘긴다."""

    def _hook(exc_type, exc_value, exc_tb):
        logger.critical("처리되지 않은 예외로 종료됨", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
