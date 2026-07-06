# image_cropper — processing.md

## 목적

폴더 내 이미지에서 복수의 ROI(관심 영역)를 GUI로 지정하고, 각 영역을 개별 파일로 크롭 저장하는 도구.

## 지원 포맷

| 포맷 | 비고 |
|------|------|
| JPG / JPEG | 8-bit RGB |
| PNG | 8/16-bit, RGBA 포함 |
| BMP | 8/24-bit |
| TIFF / TIF | 8/16-bit, LZW 압축 저장 |
| RAW | 16-bit unsigned, little-endian. 파일 로드 전 W/H 입력 필수 |

## 사용법

```
.venv\Scripts\python.exe utils/image_cropper/main.py
```

1. **폴더 선택** — 이미지가 있는 폴더를 선택하면 좌측 목록에 파일이 나열됨
2. **RAW 설정** — RAW 파일 포함 시 상단 W/H 필드에 픽셀 크기 입력
3. **ROI 개수** — 스핀박스로 1~20 지정
4. **ROI 드래그** — 이미지 위에서 순서대로 마우스 드래그 → 각 ROI 중앙에 번호 표시
5. **크롭 실행**
   - "현재 이미지에 적용" : 현재 파일에만 크롭
   - "폴더 전체에 적용" : 폴더 내 모든 이미지에 동일 ROI 적용

## 조작

| 동작 | 방법 |
|------|------|
| 줌인/줌아웃 | 마우스 휠 스크롤 |
| 패닝(이동) | 가운데 마우스 버튼 드래그 |
| ROI 그리기 | 좌클릭 드래그 (같은 번호 재드래그 시 덮어씀) |
| ROI 초기화 | "ROI 초기화" 버튼 |

## 출력 파일명 규칙

```
{원본파일명}_{ROI번호}_x{x}y{y}w{w}h{h}{확장자}
예) photo_1_x100y50w300h200.jpg
```

- XYWH는 원본 이미지 좌표계 기준 픽셀 값
- 파일명에서 XYWH를 읽어 재크롭 가능

## 출력 위치

`{원본폴더}/cropped/` 하위 폴더 (없으면 자동 생성)

## 알고리즘

- **RAW 표시**: `numpy.frombuffer(dtype='<u2').reshape(H,W)` → min-max 정규화 → 8-bit Grayscale QImage
- **RAW 저장**: 크롭된 uint16 배열을 `.tofile()` (little-endian 유지)
- **TIFF**: Pillow `crop()` → `tiff_lzw` 압축 저장
- **PNG/JPG/BMP**: Pillow `crop()` → 동일 확장자로 저장

## 버전 / 상태

| 항목 | 내용 |
|------|------|
| 버전 | 1.0.0 |
| 상태 | 정상 |
| 최초 작성 | 2026-07-06 |
| Python | 3.12 |
| 의존성 | PyQt5, Pillow, numpy |

## 제약 사항

- RAW 파일은 반드시 W/H를 먼저 입력해야 로드됨
- 폴더 전체 적용 시 모든 파일이 동일한 W/H, 동일 ROI를 사용 (RAW 파일 혼합 폴더 주의)
- 다중 프레임 TIFF는 첫 번째 프레임만 처리
