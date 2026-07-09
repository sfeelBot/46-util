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
자세한 내용은 [utils/image_cropper/processing.md](utils/image_cropper/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\image_cropper\main.py
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
자동 동기화 스케줄(08:00/12:00/18:00) 전체 on/off 토글, 지금 바로 동기화, 마지막 동기화 상태·로그 확인,
프로젝트 경로(DestDir)/상태 경로(StateDir) 설정을 창 하나에서 처리한다.
창을 닫아도 시스템 트레이(작업표시줄 알림영역)에 상주하며, 트레이 아이콘 색상(초록=ON/회색=OFF)으로 자동 동기화 상태를 바로 확인할 수 있다.
자세한 내용은 [utils/github_sync_gui/processing.md](utils/github_sync_gui/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\github_sync_gui\main.py
```

**사용법**

1. 처음 실행하면 `%LOCALAPPDATA%\46util-sync\`에 스크립트/설정이 자동 생성된다.
2. "저장소 설정"/"경로 설정"에서 동기화할 저장소와 프로젝트 폴더(DestDir)를 지정하고 저장한다.
3. "자동 동기화" 토글로 08:00/12:00/18:00 예약 동기화를 켜고 끈다. "지금 바로 동기화"로 즉시 반영할 수도 있다.
4. 창을 닫아도(X 버튼) 프로그램은 종료되지 않고 트레이에 상주한다.
   - 트레이 아이콘을 클릭/더블클릭하면 창이 다시 열린다.
   - 트레이 아이콘을 우클릭하면 "자동 동기화" 토글(체크 표시로 ON/OFF 확인), "지금 동기화", "창 열기", "종료" 메뉴가 나온다.
   - 완전히 끄려면 반드시 트레이 메뉴의 "종료"를 사용한다 (X 버튼은 트레이로 숨기기만 함).
5. "Windows 시작 시 자동 실행"을 켜면 컴퓨터를 껐다 켜서 로그인할 때 이 프로그램(트레이 상주)이 자동으로 실행된다 (exe로 빌드해서 사용하는 것을 전제로 함).
6. 로그가 길어지면 "로그 삭제"로 `sync.log`를 지울 수 있다 (동기화 동작/설정에는 영향 없음).

exe로 빌드해서 스케줄 등록용 PowerShell 명령 없이 배포하려면:

```powershell
utils\github_sync_gui\build_exe.ps1
```

## 도구 (tools/)

`utils/`의 image-processing util과 달리, 저장소 자체를 관리하기 위한 자동화 스크립트는 `tools/`에 둔다.

### github_sync

git 접근이 막힌 사내망 PC에서, GitHub 저장소의 새 push 여부를 08:00/12:00/18:00에 자동으로 확인하고
변경이 있으면 "Download ZIP"과 동일한 방식(HTTPS zip 다운로드)으로 받아 로컬에 반영하는 PowerShell 스크립트.
기존 `.venv`는 보존하고, 반영 후 `requirements.txt`로 `pip install`을 자동 실행한다.
GUI로 스케줄 on/off·상태 확인까지 하고 싶다면 위의 [github_sync_gui](#github_sync_gui) 참고.
자세한 사용법은 [tools/github_sync/README.md](tools/github_sync/README.md) 참고.

```powershell
# 최초 1회: 설정값(대상 경로 등) 수정 후 스케줄 등록
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Register-ScheduledTasks.ps1

# 수동 실행 / 테스트
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Sync-FromGitHub.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Sync-FromGitHub.ps1 -Force
powershell -NoProfile -ExecutionPolicy Bypass -File tools\github_sync\Sync-FromGitHub.ps1 -RecreateVenv
```
