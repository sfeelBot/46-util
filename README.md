# 46 util

이미지 처리용 유틸리티 모음 저장소. 새 util을 추가하거나 기존 util을 수정할 때는 [CLAUDE.md](CLAUDE.md)의 워크플로우를 따른다.

## 문서 안내

| 파일 | 용도 |
| --- | --- |
| [CLAUDE.md](CLAUDE.md) | 작업 워크플로우 규칙 (구현 전 확인 → 구현 → 검증 → push 확인) |
| [processing.md](processing.md) | util 전체 인덱스 (각 util이 어떤 프로그램인지 한눈에 보기) |
| [QA.md](QA.md) | util별 버그/이슈 인덱스 |

각 util의 상세 내용(알고리즘/사용법/버전/제약)과 버그 기록은 `utils/<util_name>/processing.md`, `utils/<util_name>/QA.md`에 있다.

## 환경 설정

Python 3.12 기준, 저장소 루트에 `.venv` 가상환경을 사용한다.

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## util 목록

자세한 설명은 [processing.md](processing.md) 참고.

### crop_locator

원본 이미지(bmp/png) 안에서 crop된 이미지(들)의 위치(x, y, w, h)를 찾는 PyQt5 GUI 도구.
Template matching → NMS로 상위 후보 추출 → score 높은 순으로 pixel-by-pixel 완전 일치 검사 방식으로 동작한다.
자세한 내용은 [utils/crop_locator/processing.md](utils/crop_locator/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\crop_locator\gui.py
```

### TTTM (RAW_Image_Comparator)

16-bit 단채널 RAW 이미지 2장을 Threshold/ROI/Blob 분석으로 비교하는 PyQt5 데스크탑 GUI (다른 작업 환경에서 이관됨).
자세한 내용은 [utils/TTTM/processing.md](utils/TTTM/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\TTTM\main.py
```

### raw_flipper

폴더 내 이미지 파일(RAW/PNG/BMP 등)을 재귀 탐색하여 일괄 상하반전 후 동일한 폴더 구조로 결과 폴더에 저장하는 PyQt5 GUI 도구.
자세한 내용은 [utils/raw_flipper/processing.md](utils/raw_flipper/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\raw_flipper\main.py
```

### image_cropper

폴더 내 이미지(JPG/PNG/BMP/TIFF/RAW 16-bit)에서 복수 ROI를 드래그/숫자입력/레퍼런스 이미지 파일명(XYWH) 로드로 지정해 크롭 저장하는 PyQt5 도구. ROI 개별 선택·재지정·삭제 지원. 파일명에 XYWH 좌표 포함.
"폴더 선택 (하위 폴더 포함)" 버튼으로 하위 폴더까지 재귀 스캔 가능(`cropped` 폴더는 자동 제외). 폴더 선택 시 존재하는 확장자가 체크박스로 표시되며, 원하는 확장자만 체크 후 "목록 불러오기"를 눌러야 파일 목록에 반영됨. 파일 목록은 파일명/폴더 2열 테이블로 헤더 클릭 시 정렬되고, "이미지 목록 모두 지우기"로 초기화 가능.
자세한 내용은 [utils/image_cropper/processing.md](utils/image_cropper/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\image_cropper\main.py
```

exe로 빌드해서 배포하려면:

```powershell
utils\image_cropper\build_exe.ps1
```

### signal_noise_analyzer

이미지 ROI에서 이진화(Threshold)를 기반으로 Signal / Noise1(σ_bg) / Noise2(bg_mean−bg_min)를 실시간 측정·저장하는 PyQt5 GUI 도구.
폴더 탭 관리, 줌/패닝 뷰어, 이진화 오버레이, 라인 프로파일 차트, 결과 트리(선택 저장/전체 저장 CSV) 제공.
자세한 내용은 [utils/signal_noise_analyzer/processing.md](utils/signal_noise_analyzer/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\signal_noise_analyzer\main.py
```

### y_axis_masker

지정한 y좌표 아래 영역을 검정/흰색/가우시안 블러/선택 영역 평균값/스포이드 색상 중 하나로 마스킹하는 PyQt5 GUI 도구.
Before(원본+드래그 가능한 경계선)/After(실시간 미리보기) 줌/패닝 뷰어, y값 숫자입력·슬라이더·드래그 3중 연동, 폴더 전체·체크된 이미지 일괄 적용, 파일명 검색 지원.
자세한 내용은 [utils/y_axis_masker/processing.md](utils/y_axis_masker/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\y_axis_masker\main.py
```

**사용법**

1. "📁 폴더 선택"으로 이미지 폴더를 열면 좌측에 파일 목록(체크박스 포함)이 나타남 (BMP/PNG/JPG/TIFF/RAW 지원, RAW는 상단 W/H 입력 필요)
   - "하위 폴더 포함" 체크박스(기본 OFF)를 켜면 하위 폴더의 이미지까지 재귀적으로 불러옴
   - 폴더를 다시 선택하면 기존 목록은 유지된 채 새 이미지만 이어붙여짐 (동일 경로 파일은 중복 추가 안 됨) — 여러 폴더를 순서대로 골라 하나의 목록으로 모을 수 있음
2. y좌표는 숫자 입력, 슬라이더, 또는 Before 뷰어의 빨간 경계선을 클릭+드래그하는 방법 중 아무거나 사용 (셋 다 서로 연동됨)
3. "마스킹 채우기 방식"에서 검정/흰색/가우시안 블러/선택 영역 평균값/스포이드 중 선택
   - 가우시안 블러는 강도 슬라이더로 조절
   - 평균값은 "샘플 영역 지정" 버튼 → Before 뷰어에서 드래그로 영역 지정
   - 스포이드는 "색상 추출" 버튼 → Before 뷰어에서 픽셀 클릭
4. After 뷰어에서 결과를 실시간으로 확인
5. "현재 이미지 적용" / "폴더 전체 적용" / "체크된 이미지만 적용" 중 선택해 실행 → `{원본폴더}/masked/`에 동일 파일명으로 저장 (폴더 스캔과 적용 모두 백그라운드에서 처리되어 창이 멈추지 않음)
6. 검색창에 파일명을 입력하면 좌측 목록이 필터링됨 (체크 상태 유지). 목록 위에 현재 체크된 개수("체크됨: N / 총 M개")가 표시됨
7. "선택 삭제 (체크된 항목)" / "전체 삭제"로 목록에서 이미지를 제외할 수 있음 (원본 파일은 삭제되지 않고, 목록과 메모리에서만 제거됨)
8. 목록에서 항목을 선택 후 Ctrl+C(또는 우클릭 메뉴)로 파일명이나 전체 경로를 클립보드에 복사할 수 있음

### github_sync_gui

[tools/github_sync](tools/github_sync/README.md)의 zip 기반 GitHub 동기화 기능을 조작하는 PyQt5 GUI.
지금 바로 동기화(실행 중 강제 취소 가능), 마지막 동기화 상태·로그 확인, 프로젝트 경로(DestDir)/상태 경로(StateDir) 설정을 창 하나에서 처리한다.
창을 닫아도 시스템 트레이(작업표시줄 알림영역)에 상주한다.
자세한 내용은 [utils/github_sync_gui/processing.md](utils/github_sync_gui/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\github_sync_gui\main.py
```

**사용법**

1. 처음 실행하면 `%LOCALAPPDATA%\46util-sync\`에 스크립트/설정이 자동 생성된다.
2. "저장소 설정"/"경로 설정"에서 동기화할 저장소와 프로젝트 폴더(DestDir)를 지정하고 저장한다.
3. "지금 바로 동기화"로 즉시 반영한다. 대상 폴더의 파일(예: 열려있는 csv)이 다른 프로그램에 잠겨 있어 오래 걸리는 경우 "강제 동기화 취소"로 즉시 중단할 수 있다.
4. 창을 닫아도(X 버튼) 프로그램은 종료되지 않고 트레이에 상주한다.
   - 트레이 아이콘을 클릭/더블클릭하면 창이 다시 열린다.
   - 트레이 아이콘을 우클릭하면 "지금 동기화", "창 열기", "종료" 메뉴가 나온다.
   - 완전히 끄려면 반드시 트레이 메뉴의 "종료"를 사용한다 (X 버튼은 트레이로 숨기기만 함).
5. "Windows 시작 시 자동 실행"을 켜면 컴퓨터를 껐다 켜서 로그인할 때 이 프로그램(트레이 상주)이 자동으로 실행된다 (exe로 빌드해서 사용하는 것을 전제로 함).
6. 로그가 길어지면 "로그 삭제"로 `sync.log`를 지울 수 있다 (동기화 동작/설정에는 영향 없음).

exe로 빌드해서 배포하려면:

```powershell
utils\github_sync_gui\build_exe.ps1
```

### filename_matching

이물검사 이미지 파일명을 재가공하는 PyQt5 GUI 도구 모음. 메인 GUI(`gui.py`)는 탭 2개로 구성되고, 별도로 독립 실행되는 GUI가 하나 더 있다.
**탭1 "바코드 → 재료명 변환"**: 기존에 따로 실행하던 `barcode_to_cellNum.py`(바코드→셀번호) → `cellNum_to_barcode.py`(셀번호→재료명) 2단계를 하나의 파이프라인으로 묶고, 폴더 재귀 스캔·확장자 필터·최종 변환명 미리보기·중복검사·우클릭 탐색기 열기·일괄 변환·되돌리기까지 GUI에서 처리한다. 구형 파일명(`YYYY-MM-DD-바코드-...`)과 신형 파일명(저장번호 `Test#A8-0000008` 포함) 둘 다 지원하며, 매칭실패 파일은 `error/` 폴더에 원본 이름 그대로 자동 백업된다.
**탭2 "Crop 이미지 재명명"**: `image_cropper`로 4등분한 crop 이미지를, 원래 개별 촬영이었다면 가졌을 저장번호 기반 파일명으로 되돌린다. 결과를 탭1에 다시 입력하면 바코드→재료명 변환까지 이어갈 수 있다.
**`gui_folder_remap.py`(별도 실행)**: crop 파일명에 박힌 저장번호를 신뢰할 수 없을 때(파일명이 실제 셀 위치와 어긋나는 경우) 대신 폴더 구조(`{그룹번호}/cropped/`)로 각 crop이 어느 셀인지 판단해 재명명한다.
자세한 내용은 [utils/filename_matching/processing.md](utils/filename_matching/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\filename_matching\gui.py
```

**사용법 (탭1: 바코드 → 재료명 변환)**

1. 시작 시 `mapping/barcode_cell_map.csv`, `mapping/cell_material_map.csv`, `mapping/storage_cellbarcode_map.csv`가 기본 매핑으로 로드됨 (다른 매핑표를 쓰려면 각각 "매핑 불러오기..."로 교체 가능, 코드 수정 불필요)
2. "폴더 선택"으로 대상 폴더를 고르면 하위 폴더까지 재귀 스캔해 존재하는 확장자를 체크박스로 보여줌 → 원하는 확장자(.bmp/.raw 등)만 선택 후 "목록 불러오기"
3. 표에 원본 파일명과 최종 변환명(`{재료명}_{셀번호}_{원본파일명}`)이 함께 표시됨. 바코드/저장번호 패턴이 없거나 매핑표에 없는 파일은 "매칭실패" + 사유로 표시되고 자동 제외됨
4. "중복검사"로 최종 변환명이 겹치는 항목을 찾아 빨간색으로 표시
5. 목록에서 항목을 우클릭하면 "파일탐색기에서 열기"로 원본 위치를 바로 확인 가능. 표의 모든 컬럼은 드래그로 자유롭게 폭 조절 가능하며, 셀을 드래그로 선택 후 Ctrl+C로 텍스트를 클립보드에 복사할 수 있음
6. "출력 폴더 선택" 후 "단일 폴더에 평탄화" / "원본 하위폴더 구조 유지" 중 출력 방식을 고름
7. "모두 변환"을 누르면 체크되고 매칭에 성공한 파일은 원본은 그대로 둔 채 출력 폴더로 복사됨 (진행률 표시줄로 진행 상황 확인 가능). **매칭실패 파일은 체크 여부와 무관하게 `error/` 폴더에 원본 이름 그대로 함께 복사됨.** 변환 직전 목적지 파일명 충돌을 재검사해서, 충돌이 있으면 아무 것도 복사하지 않고 팝업으로 충돌 목록을 보여줌
8. "되돌리기 (방금 실행)"으로 직전 변환 결과(정상분 + error 폴더분)만 삭제하거나, "로그 불러와서 되돌리기..."로 이전에 저장된 `_conversion_log_*.json`을 선택해 그 실행분만 되돌릴 수 있음 (두 경우 모두 원본 파일은 항상 그대로 유지됨)

**사용법 (탭2: Crop 이미지 재명명)**

1. `image_cropper`로 4등분한 crop 이미지 폴더(보통 `{원본폴더}/cropped/`)를 선택
2. "오름차순으로 번호 매기기" 체크박스로 방향 선택 가능 (기본은 미체크=내림차순, 기존 동작과 동일)
3. 확장자 선택 후 "목록 불러오기" — 각 crop 파일명의 ROI번호(1~4)와 원본 저장번호로 재명명 결과가 계산됨. 예: `Test#A4-0000004`를 담은 원본을 4등분하면
   - 내림차순(기본): crop 1~4 → `Test#A4-0000004`/`Test#A3-0000003`/`Test#A2-0000002`/`Test#A1-0000001` (crop1은 시리얼 유지, crop2~4는 시리얼 1~3 감소)
   - 오름차순(체크 시): crop 1~4 → `Test#A1-0000001`/`Test#A2-0000002`/`Test#A3-0000003`/`Test#A4-0000004` (crop4는 시리얼 유지, crop1~3은 시리얼 3~1 감소)
   - lane은 두 경우 모두 1~8 순환 규칙으로 재계산
4. 이후 중복검사/우클릭 탐색기/출력 폴더·모드/모두 변환/되돌리기는 탭1과 동일하게 동작

**사용법 (`gui_folder_remap.py`: 그룹폴더 기반 Crop 재명명)**

```bash
.venv\Scripts\python.exe utils\filename_matching\gui_folder_remap.py
```

1. 대상 폴더는 `{그룹번호}/cropped/{crop파일}` 구조여야 함 (예: `A1_매칭(4셀 이미지)/02/cropped/...`, 상위에 분류 폴더가 몇 겹 있어도 무방)
2. 시작 시 `mapping/storage_ab_defect_info.csv`가 기본 매핑으로 로드됨
3. 확장자 선택 후 "목록 불러오기" — 그룹번호 N(폴더명 앞자리 숫자, "02"→2, "35 (스크랩無)"→35)과 cropped 폴더 안 crop 순서(1~4, 오름차순)로 셀 인덱스([4N-3, 4N])를 계산하고, 매핑표에서 조회한 올바른 A열 저장번호로 베이스 파일명의 (틀렸을 수 있는) 기존 저장번호를 치환. 그룹번호를 못 찾거나 매핑표에 없으면 "매칭실패"
4. 이후 흐름은 탭1/탭2와 동일

## 도구 (tools/)

`utils/`의 image-processing util과 달리, 저장소 자체를 관리하기 위한 자동화 스크립트는 `tools/`에 둔다.

### github_sync

git 접근이 막힌 사내망 PC에서, GitHub 저장소의 새 push 여부를 확인하고
변경이 있으면 "Download ZIP"과 동일한 방식(HTTPS zip 다운로드)으로 받아 로컬에 반영하는 PowerShell 스크립트.
기존 `.venv`는 보존하고, 반영 후 `requirements.txt`로 `pip install`을 자동 실행한다.
GUI로 조작·상태 확인까지 하고 싶다면 위의 [github_sync_gui](#github_sync_gui) 참고.
자세한 사용법은 [tools/github_sync/README.md](tools/github_sync/README.md) 참고.

```powershell
# 수동 실행 / 테스트
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Sync-FromGitHub.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Sync-FromGitHub.ps1 -Force
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Sync-FromGitHub.ps1 -RecreateVenv
```
