# crop_locator — processing.md

- 경로: `utils/crop_locator/`
  - `matcher.py`: 핵심 매칭 로직 (template matching + NMS + pixel-by-pixel 검증)
  - `gui.py`: PyQt5 GUI (실행 진입점)
- 목적: 원본 이미지(bmp/png) 안에서 crop된 이미지(들)의 위치(x, y, w, h)를 찾는다. w, h는 crop 이미지의 shape에서 결정.
- 의존성: numpy, opencv-python (루트 `requirements.txt`에 포함됨, 공용 `.venv` 사용)
- 버전: v1 (2026-06-19)
- 사용법:
  ```
  cd "E:\46 util"
  .venv\Scripts\python.exe utils\crop_locator\gui.py
  ```
  GUI에서 원본 이미지 1개, crop 이미지 1개 이상 선택 → colorspace(gray/color, 기본 gray) / Top-K(기본 5) / NMS 거리(기본: 자동 = 템플릿 min(w,h)/2) / dry-run 여부 설정 → "실행" 버튼.
- 알고리즘:
  1. `cv2.matchTemplate` (TM_CCOEFF_NORMED)로 score map 계산
  2. score가 가장 높은 지점을 고르고 주변(반경 = NMS 거리)을 억제하는 과정을 top-k번 반복 → 서로 겹치지 않는 top-k 후보 확보
  3. score 높은 순서대로 원본에서 동일 크기로 잘라 `np.array_equal`로 완전 동일 여부 검사
  4. 처음으로 완전히 일치하는 후보를 결과로 확정 (x, y, w, h, score). 5개 모두 불일치하면 "찾지 못함" 처리
- dry-run 동작: 각 후보의 score/좌표/pixel-match 결과를 모두 로그에 출력하되, 최종 `[RESULT]` 확정 라인은 출력하지 않음.
- 상태: 완료 (서브에이전트 검증 통과, 버그 없음)
- 비고:
  - `gui.py`는 같은 폴더의 `matcher.py`를 `from matcher import ...`로 import하므로, **스크립트로 직접 실행**해야 한다 (다른 위치에서 모듈로 import하면 `ModuleNotFoundError` 발생).
  - TM_CCOEFF_NORMED 특성상 완전 일치 영역은 항상 score=1.0이므로, 완전 일치가 존재하면 항상 최상위 후보로 검출됨. "후보 누락으로 못 찾는" 경우는 NMS 억제 반경 안에 더 높은 score의 가짜 후보가 있어 정답 위치 자체가 top-k에서 빠지는 경우에 발생할 수 있음 (topk를 늘리거나 NMS 거리를 줄이면 완화 가능).
