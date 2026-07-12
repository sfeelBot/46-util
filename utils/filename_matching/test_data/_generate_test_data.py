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
}

for rel_path, content in FILES.items():
    full_path = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)

print(f"생성 완료: {ROOT}")
for rel_path in FILES:
    print(" -", rel_path)
