# raw_flipper — processing.md

- 경로: `utils/raw_flipper/`
  - `flipper.py`: 핵심 처리 로직 (스캔, 상하반전, 저장)
  - `gui.py`: PyQt5 GUI (실행 진입점)
- 목적: 폴더 내 이미지 파일들을 재귀 탐색하여 일괄 상하반전(vertical flip)한 뒤, 동일한 폴더 구조로 결과 폴더에 저장한다.
- 지원 형식:
  - `.raw` : 16-bit little-endian unsigned (`np.fromfile dtype='<u2'`). W×H는 GUI에서 사용자가 입력.
  - `.png` / `.bmp` / `.tiff` / `.tif` / `.jpg` / `.jpeg` : `cv2.IMREAD_UNCHANGED`로 읽어 비트심도·채널 수 그대로 유지.
- 의존성: numpy, opencv-python, PyQt5 (루트 `requirements.txt`에 포함됨, 공용 `.venv` 사용)
- 버전: v1 (2026-07-06)
- 사용법:
  ```
  cd "E:\46 util"
  .venv\Scripts\python.exe utils\raw_flipper\gui.py
  ```
  1. "소스 폴더" 선택 → 하위 폴더까지 재귀 탐색 후 파일 목록 표시
  2. "결과 폴더" 선택
  3. RAW 크기(W×H) SpinBox 설정 (기본 3072×3072)
  4. 처리할 확장자 체크박스 선택 (기본: .raw / .png / .bmp)
  5. "실행" 버튼 → 진행 상황은 프로그레스바와 로그로 표시
- 알고리즘:
  - 소스 폴더에서 `Path.rglob`으로 선택된 확장자 파일 전수 탐색
  - RAW: `reshape(H, W)` → `np.flipud()` → `tofile()` (동일 바이트 포맷 저장)
  - 기타: `cv2.imread(IMREAD_UNCHANGED)` → `np.flipud()` → `cv2.imwrite()`
  - 결과 경로 = `dst_dir / src.relative_to(src_dir)` (폴더 구조 복제, 중간 폴더 자동 생성)
  - 처리는 QThread에서 실행 → GUI 블로킹 없음
- 상태: 완료 (서브에이전트 검증 통과)
- 비고:
  - `gui.py`는 같은 폴더의 `flipper.py`를 직접 import하므로 **스크립트로 직접 실행**해야 한다.
  - 소스 폴더와 결과 폴더가 같으면 원본이 덮어써짐. 별도 경로를 지정할 것.
