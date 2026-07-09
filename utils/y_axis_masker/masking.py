"""y_axis_masker의 핵심 로직: 이미지 로드/마스킹 처리/저장.

GUI(main.py)와 분리하여 서브에이전트 등에서 독립적으로 테스트할 수 있게 한다.
"""
import numpy as np
import cv2
from pathlib import Path
from PIL import Image
from PyQt5.QtGui import QImage, QPixmap

SUPPORTED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.raw'}


def list_images(folder: Path) -> list:
    """폴더 내 지원 포맷 이미지 경로를 이름순으로 반환."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def load_array(path: Path, raw_w: int = 0, raw_h: int = 0) -> np.ndarray:
    """이미지를 원본 dtype 그대로 numpy 배열로 로드.

    Grayscale: (H, W) uint8 또는 uint16
    Color: (H, W, 3) uint8(RGB) 또는 (H, W, 4) uint8(RGBA)
    """
    ext = path.suffix.lower()
    if ext == '.raw':
        if raw_w <= 0 or raw_h <= 0:
            raise ValueError("RAW 파일은 Width/Height를 먼저 입력해야 합니다.")
        data = np.frombuffer(path.read_bytes(), dtype='<u2')
        expected = raw_w * raw_h
        if data.size != expected:
            raise ValueError(
                f"파일 크기({data.size} pixels)가 {raw_w}×{raw_h}={expected}와 맞지 않습니다."
            )
        return data.reshape((raw_h, raw_w)).copy()

    pil = Image.open(str(path))
    if hasattr(pil, 'n_frames') and pil.n_frames > 1:
        pil.seek(0)
    return np.array(pil)


def get_display_range(arr: np.ndarray):
    """16bit/32bit 그레이스케일이면 (min, max)를, 그 외에는 (0, 255)를 반환."""
    if arr.ndim == 2 and arr.dtype in (np.uint16, np.int32):
        lo, hi = float(arr.min()), float(arr.max())
        return lo, hi
    return 0.0, 255.0


def array_to_qpixmap(arr: np.ndarray, mn: float = None, mx: float = None) -> QPixmap:
    """표시용 QPixmap 생성. 16/32bit 그레이스케일은 mn/mx 기준으로 8bit 정규화."""
    if arr.ndim == 2:
        if arr.dtype in (np.uint16, np.int32):
            a = arr.astype(np.float32)
            lo = mn if mn is not None else float(a.min())
            hi = mx if mx is not None else float(a.max())
            if hi > lo:
                arr8 = ((a - lo) / (hi - lo) * 255.0).clip(0, 255).astype(np.uint8)
            else:
                arr8 = np.zeros_like(a, dtype=np.uint8)
        else:
            arr8 = np.ascontiguousarray(arr.astype(np.uint8))
        arr8 = np.ascontiguousarray(arr8)
        h, w = arr8.shape
        qimg = QImage(arr8.data, w, h, w, QImage.Format_Grayscale8)
        return QPixmap.fromImage(qimg.copy())
    elif arr.ndim == 3:
        h, w, c = arr.shape
        arr8 = np.ascontiguousarray(arr if arr.dtype == np.uint8 else arr.astype(np.uint8))
        if c == 3:
            qimg = QImage(arr8.data, w, h, w * 3, QImage.Format_RGB888)
        elif c == 4:
            qimg = QImage(arr8.data, w, h, w * 4, QImage.Format_RGBA8888)
        else:
            raise ValueError(f'지원하지 않는 채널 수: {c}')
        return QPixmap.fromImage(qimg.copy())
    raise ValueError('지원하지 않는 배열 형태')


def _cast_fill(value, dtype: np.dtype) -> np.ndarray:
    arr = np.array(value, dtype=np.float64)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        arr = np.clip(np.round(arr), info.min, info.max)
    return arr.astype(dtype)


def apply_mask(image: np.ndarray, y: int, mode: str, *,
                gaussian_sigma: float = 15.0, fill_value=None) -> np.ndarray:
    """y행(row) 이상(아래) 영역을 mode에 따라 채운 복사본을 반환.

    mode: "black" | "white" | "gaussian" | "constant"
      - "constant"는 fill_value(스칼라 또는 채널별 튜플)가 반드시 필요.
    """
    h = image.shape[0]
    y = max(0, min(h, int(y)))
    out = image.copy()
    if y >= h:
        return out

    if mode == 'black':
        out[y:] = 0
    elif mode == 'white':
        if np.issubdtype(out.dtype, np.integer):
            out[y:] = np.iinfo(out.dtype).max
        else:
            out[y:] = 1.0
    elif mode == 'gaussian':
        sigma = max(0.1, float(gaussian_sigma))
        src = image
        needs_cast = src.dtype not in (np.uint8, np.uint16, np.int16, np.float32, np.float64)
        work = src.astype(np.float32) if needs_cast else src
        blurred = cv2.GaussianBlur(work, (0, 0), sigmaX=sigma, sigmaY=sigma)
        if needs_cast:
            blurred = blurred.astype(src.dtype)
        out[y:] = blurred[y:]
    elif mode == 'constant':
        if fill_value is None:
            raise ValueError('constant 모드는 fill_value가 필요합니다.')
        out[y:] = _cast_fill(fill_value, out.dtype)
    else:
        raise ValueError(f'알 수 없는 mode: {mode}')
    return out


def compute_mean(image: np.ndarray, x: int, y: int, w: int, h: int):
    """ROI(x,y,w,h) 내 평균값. Grayscale은 float, Color는 채널별 float 튜플."""
    region = image[y:y + h, x:x + w]
    if region.size == 0:
        raise ValueError('빈 영역입니다.')
    if image.ndim == 2:
        return float(region.mean())
    return tuple(float(region[..., c].mean()) for c in range(region.shape[-1]))


def sample_pixel(image: np.ndarray, x: int, y: int):
    """(x, y) 픽셀 값. Grayscale은 float, Color는 채널별 float 튜플."""
    if image.ndim == 2:
        return float(image[y, x])
    return tuple(float(v) for v in image[y, x])


def save_masked(src_path: Path, out_array: np.ndarray) -> Path:
    """{원본폴더}/masked/{원본파일명} 으로 저장."""
    out_dir = src_path.parent / 'masked'
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / src_path.name
    ext = src_path.suffix.lower()

    if ext == '.raw':
        out_array.astype('<u2').tofile(str(out_path))
        return out_path

    if out_array.ndim == 2:
        if out_array.dtype == np.uint16:
            img = Image.fromarray(out_array, mode='I;16')
        elif out_array.dtype == np.int32:
            img = Image.fromarray(out_array, mode='I')
        else:
            img = Image.fromarray(out_array.astype(np.uint8), mode='L')
    else:
        c = out_array.shape[-1]
        mode = 'RGB' if c == 3 else 'RGBA'
        img = Image.fromarray(out_array.astype(np.uint8), mode=mode)

    if ext in ('.tif', '.tiff'):
        img.save(str(out_path), compression='tiff_lzw')
    else:
        img.save(str(out_path))
    return out_path
