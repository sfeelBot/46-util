#셀넘버 to 이물정보
import os
import shutil
import re
import sys

# Windows 콘솔(cp949 등)에서 한글/이모지 출력이 깨지는 것을 방지.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ===== 경로 설정 =====
src_dir = r"D:\공유폴더\46x-ray\tilt model 비교_0703\sum_ng\renamed"
dst_dir = r"D:\공유폴더\46x-ray\tilt model 비교_0703\sum_ng\rrerererer"

# ===== 숫자 → 재료 매핑 =====
material_map = {
    "CU400": {
        80, 81, 82, 83, 84,
        85, 86, 87, 88, 89,
        170, 171, 172, 173, 174,
        253, 254, 255, 256, 257, 258,
        259, 260, 261
    },

    "CU500": {
        90, 91, 92, 93, 94, 95, 96, 97,
        98, 99, 100, 101, 102, 103, 104, 105,
        162, 163, 164, 165, 166, 167, 168, 169
    },

    "SUS400": {
        51, 52, 53, 54, 55,
        59, 60, 61, 62, 63,
        157, 158, 159, 160, 161,
        244, 245, 246, 247, 248,
        249, 250, 251, 252
    },

    "SUS500": {
        32, 33, 34, 35, 36, 37, 38, 39,
        40, 41, 42, 43, 44, 45, 46, 47,
        149, 150, 151, 152, 153, 154, 155, 156
    },

    "AL_A_1000": {
        48, 49, 50,
        56, 57, 58,
        110, 117, 119, 127,
        201, 202, 203, 204, 205,
        206, 207, 208, 209, 210,
        262, 263, 264, 265,
        266, 267
    },

    "AL_B_1000": {
        109, 120,
        141, 142, 143, 144, 145,
        146, 147, 148,
        268, 269, 270
    },

    "AL_A_1200": {
        175, 176, 177, 178, 179,
        180, 181, 182,
        187, 188, 189, 190, 191,
        192, 193, 194,
        195, 196, 198, 199, 200,
        219, 220, 221, 222, 223
    },

    "AL_B_1200": {
        128, 129, 130, 131, 132,
        133, 134, 135, 136, 137,
        138, 139, 140
    },

    "SCRAP6": {
        2, 3, 4, 5, 6, 7,
        8, 11, 12, 13, 14, 15,
        16, 17, 18, 19, 20, 21,
        22, 23,
        106, 107, 108,
        111, 112, 113, 114,
        235, 236, 237,
        271, 272, 273
    },

    "SCRAP7": {
        24, 25, 26, 27, 28, 29, 30, 31,
        115, 122, 124, 125, 126,
        183, 184, 185, 186,
        211, 213, 214, 215, 216, 217, 218,
        224, 225, 226, 227, 228, 229, 230, 231
    }
}

# ===== 대상 폴더 생성 =====
os.makedirs(dst_dir, exist_ok=True)

copied_files = []
skipped_files = []

# ===== 허용 확장자 =====
allowed_ext = (".bmp", ".webp")

# ===== 파일 처리 =====
for filename in os.listdir(src_dir):

    reason = None

    # 확장자 확인
    if not filename.lower().endswith(allowed_ext):
        reason = "bmp/webp 파일 아님"

    else:
        # 파일명 시작이 숫자_ 형식인지 검사
        match = re.match(r"^(\d{1,3})_", filename)

        if not match:
            reason = "파일명이 숫자_ 형식 아님"

        else:
            number = int(match.group(1))
            matched_material = None

            for material, numbers in material_map.items():
                if number in numbers:
                    matched_material = material
                    break

            if matched_material is None:
                reason = f"숫자 {number} 가 매핑표에 없음"

            else:
                new_filename = f"{matched_material}_{filename}"

                src_path = os.path.join(src_dir, filename)
                dst_path = os.path.join(dst_dir, new_filename)

                shutil.copy2(src_path, dst_path)

                copied_files.append(new_filename)
                continue

    skipped_files.append((filename, reason))

# ===== 결과 출력 =====
print("\n" + "=" * 60)
print(f"✅ 복사 완료 : {len(copied_files)}개")
print("=" * 60)

for f in copied_files:
    print(f)

print("\n" + "=" * 60)
print(f"❌ 제외 파일 : {len(skipped_files)}개")
print("=" * 60)

for f, reason in skipped_files:
    print(f"{f}  -->  {reason}")

print("\n처리 완료")