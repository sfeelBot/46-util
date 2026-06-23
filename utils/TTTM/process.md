# 처리 로직 (Background Process)

## 현재 버전: v1.0

---

## 이미지 처리 파이프라인

각 이미지 패널에서 독립적으로 동작하는 단계별 처리 흐름.

```
[파일 로드]
    ↓
np.fromfile(path, dtype='<u2').reshape(H, W)
    → img16: ndarray(H, W, uint16)
    ↓
[Threshold]
    apply_threshold(img16, thresh, invert)
    → binary: ndarray(H, W, uint8)  [255=전경, 0=배경]
    - 기본: img16 < thresh → 255 (어두운 blob 검출)
    - invert: img16 > thresh → 255
    ↓
[ROI 마스킹]
    apply_roi(binary, x, y, w, h)
    → roi_binary: ROI 밖 0으로 마스킹
    - ROI 미설정(w=0 or h=0)이면 binary 그대로 사용
    ↓
[Blob 탐색]
    find_blobs(roi_binary, min_area)
    → cv2.findContours(RETR_EXTERNAL, CHAIN_APPROX_SIMPLE)
    → BlobInfo 리스트: {index, contour, area, bbox(x,y,w,h), mask}
    → 면적 기준 내림차순 정렬
    ↓
[Blob 선택]
    사용자가 QListWidget에서 선택 또는 이미지 클릭
    → selected_blob: BlobInfo
    ↓
[분석]
    analyze(blob, offset_px)
    → BlobAnalysis:
        y_at_offset  = bbox_top_y + offset_px
        left_edge_x  = np.where(mask > 0)[1].min()  (이미지 x=0 기준)
        area         = np.count_nonzero(mask)
```

---

## 비교 분석

```
compute_diff(a1: BlobAnalysis, a2: BlobAnalysis) → dict
    {
      "y_at_offset": (a1.y_at_offset, a2.y_at_offset, diff),
      "left_edge_x": (a1.left_edge_x, a2.left_edge_x, diff),
      "area":        (a1.area,        a2.area,        diff),
    }
diff = Image2 값 - Image1 값 (양수: Image2가 더 큼)
```

---

## 오버레이 합성

```
make_overlay(mask1, mask2, bg) → RGB ndarray
    only1  = mask1 > 0 AND mask2 == 0  → (0, 200, 0)   초록
    only2  = mask2 > 0 AND mask1 == 0  → (200, 0, 0)   빨강
    overlap= mask1 > 0 AND mask2 > 0   → (220, 220, 0) 노랑
    배경   = bg 그레이스케일 → RGB 변환 후 베이스
```

---

## 핵심 모듈: image_processor.py

| 함수 | 입력 | 출력 | 설명 |
|------|------|------|------|
| `read_raw` | path, W, H | uint16 ndarray | little-endian RAW 읽기 |
| `normalize_8bit` | uint16 | uint8 | 표시용 변환 (>>8) |
| `apply_threshold` | uint16, thresh, invert | uint8 binary | 이진화 |
| `apply_roi` | binary, x,y,w,h | uint8 binary | ROI 마스킹 |
| `find_blobs` | binary, min_area | List[BlobInfo] | 컨투어 검출 |
| `extract_mask` | shape, contour | uint8 mask | 단일 blob 마스크 |
| `analyze` | BlobInfo, offset_px | BlobAnalysis | 분석값 계산 |
| `compute_diff` | BlobAnalysis×2 | dict | 차이값 계산 |
| `make_overlay` | mask1, mask2, bg | RGB ndarray | 오버레이 합성 |

---

## 로깅 전략

- **DEBUG**: 처리 함수 입출력값 (픽셀 수, 좌표 등)
- **INFO**: 파일 로드, blob 탐색 결과, 분석 완료
- **WARNING**: 유효하지 않은 파라미터 (ROI 범위 초과 등)
- **ERROR**: 파일 읽기 실패, 처리 예외
- **CRITICAL**: 처리되지 않은 예외 (sys.excepthook)

로그 파일: `app.log` (최대 5MB × 3개 롤링)

---

## Threshold 빨간색 오버레이 (v1.1)

Threshold 모드 선택 시 바이너리 이미지 대신 빨간색 오버레이 표시.

```python
# image_panel.py: _make_thresh_overlay()
gray8 = (img16 >> 8).astype(np.uint8)
rgb = np.stack([gray8, gray8, gray8], axis=2)
rgb[binary > 0] = (220, 50, 50)   # QImage RGB888: R=220, G=50, B=50 = 빨강
```

슬라이더 valueChanged → `_on_thresh_changed()` → binary 갱신 → `_refresh_viewer()` → 오버레이 재생성 → viewer.set_image() → `_rebuild_overlay_pixmap()` 순으로 실시간 업데이트.

## 줌 성능 최적화 (v1.1)

```
이전: 줌 변경마다 numpy→QPixmap 전체 재빌드 (3072×3072, ~40ms/회 → 렉)

이후:
  _rebuild_overlay_pixmap()  ← 이미지/오버레이 변경 시만 호출 (비용 큼)
  _apply_fast()              ← 줌 변경 시 즉시 (FastTransformation, ~5ms)
  _smooth_timer(180ms)       ← wheel 멈춘 뒤 고품질 렌더 (SmoothTransformation)
```

## 변경 이력

| 날짜 | 버전 | 변경내용 |
|------|------|---------|
| 2026-06-06 | v1.0 | 초기 구현 |
| 2026-06-06 | v1.1 | 줌 성능 최적화 (캐시+디바운스), threshold 빨간 오버레이, 로드 시 auto-fit, 레이아웃 3/4 비율 |
