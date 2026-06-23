# TTTM (RAW_Image_Comparator) — processing.md

- 경로: `utils/TTTM/`
  - `main.py`: 진입점 + MainWindow
  - `image_panel.py`: 이미지별 처리 패널 위젯
  - `viewer_widget.py`: 줌/팬 이미지 뷰어
  - `image_processor.py`: OpenCV 처리 + 분석 로직
  - `overlay_dialog.py`: 마스크 오버레이 비교 다이얼로그
  - `logger_setup.py`: 로깅 설정 (`app.log`)
  - `tests/create_test_images.py`: 테스트용 RAW 이미지 생성
  - 상세 문서: [process.md](process.md) (처리 파이프라인), [ui.md](ui.md) (화면 구성), [user.md](user.md) (요청사항 이력) — 다른 작업 환경에서 이관됨, 형식은 원본 그대로 유지
- 목적: 16-bit 단채널 RAW 이미지 2장을 비교 분석하는 PyQt5 데스크탑 GUI. Threshold/ROI/Blob 탐색 후 두 이미지의 Y좌표·좌측 엣지·면적을 비교하고 오버레이로 시각화한다.
- 의존성: numpy, opencv-python, PyQt5 (루트 `requirements.txt`에 포함됨, 공용 `.venv` 사용)
- 버전: v1.3 (2026-06-06, 이전 작업 환경에서 이관)
- 사용법:
  ```
  cd "E:\46 util"
  .venv\Scripts\python.exe utils\TTTM\main.py
  ```
  GUI에서 RAW 이미지 2개를 각각 로드 → Threshold/ROI 설정 → Blob 탐색 및 선택 → 자동 비교 분석 / 오버레이 보기.
- 핵심 제약: 16-bit little-endian RAW 전용 (`np.fromfile(path, dtype='<u2').reshape(H, W)`로 읽음, `cv2.imread` 사용 금지). 기본 이미지 크기 3072×3072 (GUI에서 변경 가능).
- 상태: 이관 완료, 본 저장소 워크플로우 기준 재검증은 아직 하지 않음 (이전 환경에서 v1.0~v1.3까지 자체 테스트 체크리스트 통과 기록 있음 — `process.md`, `ui.md` 참고)
- 비고:
  - `build/`, `dist/`, `__pycache__/`, `app.log`, `*.raw`는 `utils/TTTM/.gitignore`(자체 보유)로 커밋 제외됨.
  - 알려진 제한사항은 [QA.md](QA.md) 참고.
