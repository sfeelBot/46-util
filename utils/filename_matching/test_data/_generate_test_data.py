# gui.py / core.py 동작 검증용 예제 파일을 생성하는 스크립트.
# 실제 이미지 데이터는 필요 없으므로(파일명 기반 로직만 검증) 더미 바이트만 채운다.
import os
import shutil
import sys

# Windows 콘솔(cp949 등)에서 한글 파일명 출력이 깨지는 것을 방지.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.path.dirname(__file__)
ROOT = os.path.join(BASE, "sample_root")

if os.path.exists(ROOT):
    shutil.rmtree(ROOT)

FILES = {
    # (상대경로, 내용)
    "sub1/2025-01-16-7780-001.bmp": b"dummy-bmp-1",          # barcode 7780 -> cell 83 -> CU400
    "sub1/2025-01-16-7514-002.raw": b"dummy-raw-1",          # barcode 7514 -> cell 174 -> CU400
    "sub1/노트_2025-01-16-7749-테스트.bmp": "한글 테스트 데이터".encode("utf-8"),  # barcode 7749 -> cell 63 -> SUS400
    "sub1/random_no_pattern.bmp": b"no-pattern",              # 매칭 실패 (바코드 패턴 없음)
    "sub1/2025-01-16-9999-003.bmp": b"unknown-barcode",       # 매칭 실패 (매핑표에 없는 바코드)
    "sub1/ignore.txt": b"should be filtered out by extension",
    "sub2/2025-01-16-7780-001.bmp": b"dummy-bmp-2",           # sub1 과 최종명이 같아져서 평탄화시 중복 발생
    "sub2/한글폴더/2025-01-16-7749-테스트한글.raw": "다른 한글 파일".encode("utf-8"),
    # 신형 파일명 (GitHub 이슈 #2): "Test#A8-0000008" 같은 저장번호를 포함
    "sub3/0_Test#A3-0000107-1-000-1_Insp_Ver_1_Vertical_Upper_20260711162533_952.raw": b"new-format-1",
    # storage Test#A3-0000107 -> cell_barcode Test_2025_01_16_7780 -> barcode 7780 -> cell 83 -> CU400 (성공)
    "sub3/0_Test#A1-0000001-1-000-1_Insp_Ver_1_Vertical_Upper_20260711162533_953.raw": b"new-format-2",
    # storage Test#A1-0000001 -> cell_barcode Test_2025_01_16_7517 -> barcode 7517 -> cell 171 -> CU400 (성공)
    # (이슈 #2 댓글로 barcode_cell_map.csv 가 247행으로 확장되면서 7517도 포함됨)
    "sub3/0_Test#A9-9999999-1-000-1_Insp_Ver_1_Vertical_Upper_20260711162533_954.raw": b"new-format-3",
    # storage Test#A9-9999999 자체가 storage_cellbarcode_map 에 없음 (매칭 실패)
    "sub3/0_Test#A8-0000032-1-000-1_Insp_Ver_1_Vertical_Upper_20260711162533_955.raw": b"new-format-4",
    # storage Test#A8-0000032 -> cell_barcode Test_2025_01_16_7747 -> barcode 7747 -> barcode_cell_map 에 없음 (매칭 실패)
    # ===== crop_remap 탭(Crop 이미지 재명명) 테스트용: image_cropper 출력 형식 =====
    # 원본(자르기 전) 파일명의 저장번호는 Test#A4-0000004 (시리얼 4, 4의 배수)
    "cropped/0_Test#A4-0000004-1-000-1_Insp_960_1_x0y0w100h100.raw": b"crop-1",
    # crop 1 -> 시리얼 그대로(4) -> 재명명: ..._Test#A4-0000004-1-000-1_Insp_960.raw
    "cropped/0_Test#A4-0000004-1-000-1_Insp_960_2_x100y0w100h100.raw": b"crop-2",
    # crop 2 -> 시리얼 3 -> Test#A3-0000003
    "cropped/0_Test#A4-0000004-1-000-1_Insp_960_3_x0y100w100h100.raw": b"crop-3",
    # crop 3 -> 시리얼 2 -> Test#A2-0000002
    "cropped/0_Test#A4-0000004-1-000-1_Insp_960_4_x100y100w100h100.raw": b"crop-4",
    # crop 4 -> 시리얼 1 -> Test#A1-0000001
    "cropped/not_a_crop_file.raw": b"crop-invalid-1",
    # 매칭 실패: image_cropper 출력 형식(_{idx}_x..y..w..h..)이 아님
    "cropped/0_Test#A4-0000004-1-000-1_Insp_960_5_x0y0w100h100.raw": b"crop-invalid-2",
    # 매칭 실패: ROI 번호 5 는 1~4 범위 밖
    # ===== folder_crop_remap(그룹폴더 기반 Crop 재명명) 테스트용: GitHub 이슈 #5 =====
    # 베이스 파일명에 박힌 Test#A9-9999999 는 일부러 "틀린" 값 (실제로는 폴더 구조를 신뢰해야 함)
    "group_test/A2_매칭(4셀 이미지)/01/cropped/0_Test#A9-9999999-1-000-1_Insp_961_1_x0y0w100h100.raw": b"g1-1",
    # 그룹 1 -> 셀 인덱스 1 -> No=1 -> A열저장번호 Test#A1-0000001 로 치환
    "group_test/A2_매칭(4셀 이미지)/01/cropped/0_Test#A9-9999999-1-000-1_Insp_961_2_x100y0w100h100.raw": b"g1-2",
    # 그룹 1, crop2 -> 셀 인덱스 2 -> Test#A2-0000002
    "group_test/A2_매칭(4셀 이미지)/01/cropped/0_Test#A9-9999999-1-000-1_Insp_961_3_x0y100w100h100.raw": b"g1-3",
    # 그룹 1, crop3 -> 셀 인덱스 3 -> Test#A3-0000003
    "group_test/A2_매칭(4셀 이미지)/01/cropped/0_Test#A9-9999999-1-000-1_Insp_961_4_x100y100w100h100.raw": b"g1-4",
    # 그룹 1, crop4 -> 셀 인덱스 4 -> Test#A4-0000004
    "group_test/A1_매칭(4셀 이미지)/02/cropped/0_Test#A9-9999999-1-000-1_Insp_962_1_x0y0w100h100.raw": b"g2-1",
    # 그룹 2(짝수, A1_매칭 하위), crop1 -> 셀 인덱스 5 -> Test#A5-0000005
    "group_test/A2_매칭(4셀 이미지)/35 (스크랩無)/cropped/0_Test#A9-9999999-1-000-1_Insp_963_1_x0y0w100h100.raw": b"g35-1",
    # 그룹 35(폴더명에 괄호 텍스트 포함), crop1 -> 셀 인덱스 4*34+1=137 -> Test#A1-0000137
    "group_test/misc/cropped/0_Test#A9-9999999-1-000-1_Insp_964_1_x0y0w100h100.raw": b"invalid-group",
    # 매칭 실패: 그룹폴더명("misc")에서 숫자를 찾을 수 없음
    "group_test/A1_매칭(4셀 이미지)/9999/cropped/0_Test#A9-9999999-1-000-1_Insp_965_1_x0y0w100h100.raw": b"out-of-range",
    # 매칭 실패: 셀 인덱스(4*9998+1=39993)가 매핑표(No)에 없음
}

for rel_path, content in FILES.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)

print(f"생성 완료: {ROOT}")
for rel_path in FILES:
    print(" -", rel_path)
