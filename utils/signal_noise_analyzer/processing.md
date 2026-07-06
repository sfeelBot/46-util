# signal_noise_analyzer — processing.md

## 목적
이미지 내 특정 ROI에서 Signal과 Noise를 측정하는 PyQt5 GUI 도구.
이진화(Threshold)를 기반으로 신호 영역(어두운 부분)과 배경 영역(밝은 부분)을 분리하여 수치를 계산한다.

---

## 알고리즘

### 이진화
- 사용자가 지정한 threshold T를 기준으로 ROI 내 픽셀을 분류
  - **신호 영역**: 픽셀값 < T (어두운 부분, 빨간 오버레이)
  - **배경 영역**: 픽셀값 ≥ T (밝은 부분, 초록 오버레이)

### 계산식
| 지표 | 정의 | 수식 |
|------|------|------|
| Signal | 배경 mean과 신호 최솟값의 차이 | `bg_mean − sig_min` |
| Noise1 | 배경 영역 표준편차 | `std(background_pixels)` |
| Noise2 | 배경 mean과 배경 최솟값의 차이 | `bg_mean − bg_min` |

---

## 사용법

```
.venv\Scripts\python.exe utils/signal_noise_analyzer/main.py
```

1. **+** 버튼으로 이미지 폴더 추가 (탭으로 관리)
2. 왼쪽 리스트에서 이미지 선택 → 뷰어에 표시
3. **도구** 선택:
   - **사각형 ROI**: 드래그로 자유 사각형 그리기
   - **정사각형 ROI**: 드래그로 정사각형 그리기 (짧은 변 기준)
   - **선 프로파일**: 드래그로 선 긋기 → 실시간 그레이스케일 차트
4. **Threshold 슬라이더** 또는 **숫자 입력**으로 이진화 조정
   - ROI 위에 실시간 컬러 오버레이 표시
   - 우측 측정값 패널에 Signal / Noise1 / Noise2 실시간 업데이트
5. **Enter 키** → 현재 측정값 저장 (이미지명 + XYWH + Thr + Signal + Noise1 + Noise2)
6. 저장된 항목은 **결과 트리**에서 확인; 항목 클릭 시 해당 ROI 복원

### 뷰어 조작
| 조작 | 동작 |
|------|------|
| 마우스 휠 | 줌 인/아웃 |
| 가운데 버튼 드래그 | 이미지 이동(패닝) |
| 왼쪽 드래그 | ROI / 선 그리기 (선택된 도구) |

---

## 지원 포맷
`.bmp`, `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`

## 의존성
`PyQt5`, `numpy`, `Pillow`, `pyqtgraph`

## 버전
- v1.0 — 2026-07-06 초기 작성
