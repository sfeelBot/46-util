"""
테스트용 16-bit RAW 이미지 생성.

test.png (흰 배경 + 검은 원통 형상) 를 3072x3072로 리사이즈한 후
두 개의 RAW 파일을 생성한다.

  test1.raw : 원본
  test2.raw : 형상을 오른쪽 50px, 아래 20px 이동 + 약간 크기 변형

실행:
    python tests/create_test_images.py
"""

from __future__ import annotations

import os
import sys

import cv2
import numpy as np

TARGET_W = 3072
TARGET_H = 3072
OUT_DIR = os.path.join(os.path.dirname(__file__), "..")   # e:\TTTM


def load_source(png_path: str) -> np.ndarray:
    """PNG 로드 → 그레이스케일 → 3072x3072 리사이즈 → uint16."""
    img = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"PNG 파일을 읽을 수 없음: {png_path}")
    resized = cv2.resize(img, (TARGET_W, TARGET_H), interpolation=cv2.INTER_LINEAR)
    # uint8 (0-255) → uint16 (0-65535)
    img16 = resized.astype(np.uint16) * 257   # 255*257 = 65535
    return img16


def shift_image(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """이미지를 (dx, dy) 픽셀만큼 평행이동. 빈 영역은 배경값(최대값=밝음)으로 채운다."""
    h, w = img.shape
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    # borderValue: 배경(흰색) = 65535
    shifted = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=65535,
    )
    return shifted.astype(np.uint16)


def scale_dark_region(img: np.ndarray, scale: float = 1.05) -> np.ndarray:
    """
    어두운 영역(전경 blob)만 약간 크게 만들기.
    전경 = 픽셀값 < 32768 로 간주.
    """
    h, w = img.shape
    cx, cy = w // 2, h // 2
    M = cv2.getRotationMatrix2D((cx, cy), 0, scale)
    scaled = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=65535,
    )
    # 원본 밝은 영역은 유지, 어두운 영역만 scaled로 교체
    mask_dark = img < 32768
    out = img.copy()
    out[mask_dark] = scaled[mask_dark]
    return out.astype(np.uint16)


def save_raw(img16: np.ndarray, path: str):
    """uint16 → little-endian binary 저장."""
    img16.astype("<u2").tofile(path)
    size_mb = os.path.getsize(path) / 1024 / 1024
    print(f"  저장: {path}  ({size_mb:.1f} MB)")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.abspath(os.path.join(script_dir, ".."))
    png_path = os.path.join(project_dir, "test.png")

    print(f"소스 이미지: {png_path}")
    print(f"출력 디렉토리: {project_dir}")
    print(f"타겟 크기: {TARGET_W}x{TARGET_H}")

    img16 = load_source(png_path)
    print(f"로드 완료: dtype={img16.dtype} shape={img16.shape} min={img16.min()} max={img16.max()}")

    # test1.raw: 원본
    out1 = os.path.join(project_dir, "test1.raw")
    save_raw(img16, out1)

    # test2.raw: 우측 50px + 아래 20px 이동 + 미세 크기 변형
    img2 = shift_image(img16, dx=50, dy=20)
    img2 = scale_dark_region(img2, scale=1.03)
    out2 = os.path.join(project_dir, "test2.raw")
    save_raw(img2, out2)

    print("\n테스트 이미지 생성 완료.")
    print("  test1.raw: 원본")
    print("  test2.raw: +50px right, +20px down, 약 1.03배 크기")


if __name__ == "__main__":
    main()
