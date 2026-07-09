"""46util-sync-gui 아이콘(.ico) 생성 스크립트.

순환 화살표(sync) 글리프를 그려 ON(초록)/OFF(회색) 두 버전을 만든다.
색상/모양을 바꾸고 싶으면 이 스크립트를 수정하고 다시 실행하면 된다.

    .venv\\Scripts\\python.exe utils\\github_sync_gui\\assets\\generate_icons.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent

BG_ON = (46, 160, 67, 255)      # 초록 (자동 동기화 ON)
BG_OFF = (110, 118, 129, 255)   # 회색 (자동 동기화 OFF)
FG = (255, 255, 255, 255)       # 화살표(흰색)

SIZE = 256
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _point_on_circle(cx, cy, r, deg):
    rad = math.radians(deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _tangent_dir(deg):
    """PIL의 각도 규약(0=3시 방향, 각도 증가=시계방향)에서, 시계방향 진행 방향의 접선 단위벡터."""
    rad = math.radians(deg)
    return -math.sin(rad), math.cos(rad)


def _draw_arrowhead(draw, cx, cy, r, end_deg, size, color):
    tip_x, tip_y = _point_on_circle(cx, cy, r, end_deg)
    dx, dy = _tangent_dir(end_deg)
    px, py = -dy, dx  # 접선에 수직인 방향 (화살표 폭 방향)

    tip = (tip_x + dx * size * 0.9, tip_y + dy * size * 0.9)
    back_c = (tip_x - dx * size * 0.5, tip_y - dy * size * 0.5)
    left = (back_c[0] + px * size * 0.75, back_c[1] + py * size * 0.75)
    right = (back_c[0] - px * size * 0.75, back_c[1] - py * size * 0.75)
    draw.polygon([tip, left, right], fill=color)


def draw_sync_icon(bg_color) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = SIZE * 0.04
    draw.ellipse([margin, margin, SIZE - margin, SIZE - margin], fill=bg_color)

    cx, cy = SIZE / 2, SIZE / 2
    r = SIZE * 0.27
    stroke = SIZE * 0.10
    bbox = [cx - r, cy - r, cx + r, cy + r]

    # 서로 반대 방향을 향하는 두 개의 원호 (동기화=양방향을 상징)
    start1, end1 = -160, 80
    start2, end2 = 20, 260

    draw.arc(bbox, start=start1, end=end1, fill=FG, width=int(stroke))
    draw.arc(bbox, start=start2, end=end2, fill=FG, width=int(stroke))

    arrow_size = stroke * 1.15
    _draw_arrowhead(draw, cx, cy, r, end1, arrow_size, FG)
    _draw_arrowhead(draw, cx, cy, r, end2, arrow_size, FG)

    return img


def main():
    on_img = draw_sync_icon(BG_ON)
    off_img = draw_sync_icon(BG_OFF)

    on_img.save(OUT_DIR / "icon_on_preview.png")
    off_img.save(OUT_DIR / "icon_off_preview.png")

    on_img.save(OUT_DIR / "icon_on.ico", sizes=ICO_SIZES)
    off_img.save(OUT_DIR / "icon_off.ico", sizes=ICO_SIZES)

    print("생성됨:", OUT_DIR / "icon_on.ico", OUT_DIR / "icon_off.ico")


if __name__ == "__main__":
    main()
