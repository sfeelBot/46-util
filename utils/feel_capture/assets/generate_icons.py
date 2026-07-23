"""필캡쳐(FeelCapture) 아이콘(.ico) 생성 스크립트.

보라색 둥근 사각형 배경 위에 흰색 카메라(렌즈) 글리프를 그린다.
색상/모양을 바꾸고 싶으면 이 스크립트를 수정하고 다시 실행하면 된다.

    .venv\\Scripts\\python.exe utils\\feel_capture\\assets\\generate_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent

BG = (108, 71, 237, 255)   # 보라색 배경
FG = (255, 255, 255, 255)  # 흰색 글리프

SIZE = 256
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def draw_camera_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = SIZE * 0.04
    radius = SIZE * 0.22
    draw.rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin], radius=radius, fill=BG)

    # 카메라 상단 뷰파인더 돌기
    bump_w, bump_h = SIZE * 0.22, SIZE * 0.09
    bump_x0 = SIZE * 0.5 - bump_w / 2
    bump_y0 = SIZE * 0.30
    draw.rounded_rectangle(
        [bump_x0, bump_y0, bump_x0 + bump_w, bump_y0 + bump_h], radius=SIZE * 0.02, fill=FG
    )

    # 카메라 본체
    body_x0, body_y0 = SIZE * 0.20, SIZE * 0.38
    body_x1, body_y1 = SIZE * 0.80, SIZE * 0.78
    draw.rounded_rectangle([body_x0, body_y0, body_x1, body_y1], radius=SIZE * 0.06, fill=FG)

    # 렌즈 (배경색 테두리 + 흰 테두리로 이중 원)
    cx, cy = SIZE * 0.5, SIZE * 0.58
    r_outer = SIZE * 0.15
    r_inner = SIZE * 0.10
    draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=BG)
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=FG)
    r_center = SIZE * 0.055
    draw.ellipse([cx - r_center, cy - r_center, cx + r_center, cy + r_center], fill=BG)

    # 우측 상단 셔터 버튼
    btn_r = SIZE * 0.025
    btn_cx, btn_cy = body_x1 - SIZE * 0.08, body_y0 + SIZE * 0.05
    draw.ellipse([btn_cx - btn_r, btn_cy - btn_r, btn_cx + btn_r, btn_cy + btn_r], fill=BG)

    return img


def main():
    img = draw_camera_icon()
    img.save(OUT_DIR / "icon_preview.png")
    img.save(OUT_DIR / "icon.ico", sizes=ICO_SIZES)
    print("생성됨:", OUT_DIR / "icon.ico")


if __name__ == "__main__":
    main()
