# filename_matching — QA.md

이 util 작업 중 발견된 버그, 이상 동작, 검증 실패 사례를 기록한다.

---

## 이슈 목록

| 날짜 | 상태 | 요약 |
|------|------|------|
| 2026-07-12 | 해결 | Windows 콘솔(cp949)에서 한글 파일명/로그 출력 시 mojibake 발생 |

---

## 상세 기록

### [2026-07-12] 콘솔 한글 깨짐

- 증상: `test_data/_generate_test_data.py` 등 print()로 한글 파일명을 출력하는 스크립트를 Windows 터미널에서 실행하면 한글이 깨져서(mojibake) 출력됨.
- 원인: Python이 파이프/비-conhost 환경에서 stdout 인코딩을 자동 감지할 때 시스템 로케일(cp949)로 폴백하는 경우가 있어, UTF-8로 인코딩된 한글 바이트를 다른 코드페이지로 잘못 해석함.
- 해결 방법: `gui.py`의 `main()`, `barcode_to_cellNum.py`, `cellNum_to_barcode.py`, `test_data/_generate_test_data.py` 시작 부분에 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (stderr도 동일)를 추가하여 항상 UTF-8로 출력하도록 강제. 서브에이전트가 `PYTHONIOENCODING`/`PYTHONUTF8` 환경변수를 제거한 상태에서도 stdout이 정상 UTF-8로 디코딩됨을 확인.
- 상태: 해결

---

## 검증 요약 (2026-07-12, gui.py + core.py 최초 구현)

서브에이전트가 GUI를 직접 조작하는 대신 `core.py`(GUI 비의존 로직)를 직접 호출해 파이프라인 전체를 검증하고, `gui.py`는 `QT_QPA_PLATFORM=offscreen`으로 `MainWindow` 생성까지 확인함. 발견된 버그 없음 (총 69개 assertion 통과).

- 매핑 CSV 로드(`load_barcode_cell_map`/`load_cell_material_map`) 정상.
- `discover_extensions`가 `.bmp`/`.raw`/`.txt`를 정확히 찾음.
- `build_rows`: `.txt` 확장자 제외, 바코드 패턴 없음/매핑표에 없는 바코드 각각 "매칭실패" + 사유로 정확히 표시, 한글 파일명(`노트_...`, `...테스트한글.raw`, `한글폴더`) 포함 최종 변환명이 정확히 계산됨.
- `find_duplicates`: 평탄화(flatten=True) 시 서로 다른 하위폴더의 동일 최종명(예: sub1/sub2의 `2025-01-16-7780-001.bmp`)을 중복으로 정확히 검출, 구조유지(flatten=False) 시에는 중복으로 잡지 않음(서로 다른 하위폴더라 충돌 없음).
- `check_conflicts`/`convert_files`: 중복 미해결 상태에서 변환 시 `ConversionConflictError` 발생 및 파일 복사가 전혀 일어나지 않음(사전 검사가 실제 복사보다 먼저 수행됨) 확인. 중복 해결(체크 해제) 후에는 정상 변환됨.
- 실제 변환 결과: 평탄화/구조유지(한글 폴더명 `한글폴더` 포함) 양쪽 모두 파일이 올바른 최종명으로 복사되고, 원본은 항상 그대로 보존됨을 바이트 단위로 확인.
- `save_log`/`undo_log`: 로그로 정확히 방금 생성된 결과 파일만 삭제, 원본은 건드리지 않음.
- 이후 `progress_cb` 추가(변환 진행률 콜백) 및 `_set_busy`(스캔/변환 중 버튼 잠금) 리팩터링에 대해 2차 검증 수행: `progress_cb`가 파일당 정확히 1회, `done` 1..N 순차 증가, 충돌 시 콜백이 전혀 호출되지 않음(복사 전 사전 검사) 확인. 기존 동작에 회귀 없음.
