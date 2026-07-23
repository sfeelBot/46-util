# feel_capture (필캡쳐) — processing.md

## 목적
시스템 트레이에 상주하며 단축키 한 번으로 화면을 캡쳐/녹화하는 PyQt5 데스크탑 도구.
드래그 방식 스크린샷, 고정 영역(빨간 박스) 스크린샷/녹화, 클립보드·파일 저장, 저장 시 리사이즈,
사용자 지정 단축키를 지원한다. PyInstaller로 단일 exe(`FeelCapture.exe`)로 빌드 가능.

---

## 구조

```
utils/feel_capture/
├── main.py             # TrayApp: 트레이 아이콘/메뉴, 단축키 연결, 캡쳐/녹화 흐름 오케스트레이션
├── config.py            # 설정 스키마 + %APPDATA%\FeelCapture\config.json 로드/저장
├── capture_core.py      # mss 기반 화면 캡처, 리사이즈, 클립보드 복사, 정지 이미지 저장, 파일명 생성
├── overlay_drag.py       # 드래그 방식 스크린샷 오버레이 (DragSelectOverlay)
├── overlay_region.py     # 영역(고정 박스) 위젯 (RegionBox) — 이동/리사이즈/우클릭 프리셋 메뉴
├── recorder.py            # 녹화 스레드 (RecorderThread) + REC 인디케이터 위젯 (RecordIndicator)
├── settings_dialog.py     # 설정 다이얼로그 (SettingsDialog)
├── assets/
│   ├── generate_icons.py  # 아이콘(.ico) 생성 스크립트 (Pillow)
│   └── icon.ico            # 생성된 아이콘 (보라색 카메라 글리프)
└── build_exe.ps1           # PyInstaller 빌드 스크립트
```

## 동작 흐름

### 1. 캡쳐 모드
- **드래그 방식** (`overlay_drag.DragSelectOverlay`): 단축키를 누르면 가상 데스크톱(모든 모니터를 아우르는 전체 영역) 스크린샷을 먼저 찍어두고, 그 화면 전체를 덮는 반투명(alpha 120) 검은 오버레이를 표시한다. 마우스 드래그 중에는 `QPainter.setClipRect`로 드래그 사각형 부분만 원본(밝은) 픽스맵을 다시 그려 "그 부분만 밝아지는" 효과를 낸다. 마우스를 떼면 선택 영역을 캡쳐하고 오버레이를 닫는다. ESC로 취소, 5px 미만 드래그는 무시.
- **영역(고정 박스) 방식** (`overlay_region.RegionBox`): 빨간 테두리의 프레임리스·투명배경 위젯이 화면에 항상 떠 있다. 가장자리(8px 이내) 근처를 드래그하면 8방향 리사이즈, 안쪽을 드래그하면 이동. **상단 14px는 반투명 빨간 바로 굵게 표시된 이동 전용 손잡이**(`HANDLE_HEIGHT`)로, 양쪽 맨 끝 모서리(nw/ne 대각선 리사이즈)를 제외한 상단 전체를 잡으면 리사이즈와 상관없이 항상 이동된다(2026-07-23 추가 — 테두리를 잡으면 리사이즈로 인식돼 이동이 어렵다는 피드백 반영). 우클릭 메뉴에서 프리셋 3종(설정에서 이름/W/H 편집 가능) 선택 또는 "사용자 지정 크기..."로 W/H를 직접 입력해 고정할 수 있다("현재 크기로 고정" 토글로 리사이즈 핸들 비활성화/재활성화). 우클릭 메뉴의 "설정 열기..."로 설정 다이얼로그를 바로 열 수 있다. 위치/크기/잠금 상태가 바뀔 때마다 `config.json`의 `region_box`에 즉시 저장된다.
- **멀티 모니터**: `mss`의 `monitors[0]`(모든 모니터를 합친 가상 데스크톱)을 기준으로 좌표를 계산하므로, 드래그 오버레이와 영역 박스 모두 모니터 경계를 넘나들며 배치/캡쳐할 수 있다.

### 2. 저장 방식 / 확장자
- `config.py`의 `STATIC_EXTS`(png/jpg/bmp/webp/tiff)와 `RECORD_EXTS`(gif/mp4/avi)로 구분된다.
- **정지 이미지 포맷**: 단축키를 누르면 즉시 1장 캡쳐 → 리사이즈(설정된 경우) → 클립보드 복사(`QClipboard.setImage`) 또는 출력 폴더에 `YYYYMMDD_HHMMSS.ext`로 저장 (동시각 충돌 시 `_1`, `_2` 접미사).
- **녹화 포맷(gif/mp4/avi)**: 클립보드 저장은 지원하지 않음(설정 UI에서 이 경우 클립보드 라디오가 비활성화되고 자동으로 "출력 폴더"로 전환됨). 단축키가 **토글** 방식으로 동작한다.
  - 드래그 모드 + 녹화 포맷: 단축키를 누르면 드래그 오버레이가 뜨고, 드래그로 영역을 한 번 지정하면 그 즉시 그 고정 영역에 대한 녹화가 시작된다.
  - 영역 모드 + 녹화 포맷: 단축키를 누르면 현재 빨간 박스 영역으로 즉시 녹화가 시작된다.
  - 녹화 중 화면에 `RecordIndicator`(빨간 배지, "● REC mm:ss")가 표시된다. 단축키를 다시 누르면(모드/영역 재확인 없이) 녹화를 종료하고 파일로 저장한다.
  - `RecorderThread`(QThread)가 `cfg["fps"]` 간격으로 해당 영역만 `mss`로 반복 캡처한다. gif는 프레임을 메모리에 모았다가 종료 시 Pillow `save_all=True`로 한 번에 인코딩(긴 녹화일수록 메모리 사용량이 늘어남 — 아래 제약사항 참고). mp4/avi는 프레임마다 OpenCV `VideoWriter`에 바로 기록(mp4v/XVID 코덱)하므로 메모리 부담이 적다.

### 3. 리사이즈
- `capture_core.apply_resize`: "사용 안 함" / "고정 크기(W·H, 한쪽을 비우면 비율 유지)" / "비율(%)" 3가지 모드. 정지 이미지·gif·동영상 모두 프레임 단위로 동일하게 적용된다(동영상은 첫 프레임 크기로 `VideoWriter` 해상도가 고정됨).

### 4. 단축키
- 하나의 전역 단축키가 "현재 선택된 모드"를 실행한다(모드별 단축키 분리 없음 — 사용자 확인 사항).
- 설정 다이얼로그의 `QKeySequenceEdit`로 조합을 입력하면, `QKeySequence.toString(PortableText).lower()`로 변환해 `keyboard.add_hotkey()`에 등록한다. 설정을 바꾸면 기존 등록을 해제하고 새로 등록한다(`HotkeyManager`).
- `keyboard` 라이브러리는 저수준 전역 후킹을 별도 스레드에서 수행하므로, 콜백은 `HotkeyBridge(QObject)`의 시그널(`fired`)을 통해 Qt 메인 스레드로 안전하게 전달한다.

### 5. 트레이 / 백그라운드 상주
- 창 없이 시스템 트레이 아이콘만 상주한다(`QApplication.setQuitOnLastWindowClosed(False)`). 우클릭 메뉴: 모드(드래그/영역) 전환, 설정..., 종료.
- 설정 변경/모드 전환 시 `_apply_config()`가 단축키 재등록과 영역 박스 표시/숨김을 함께 처리한다.

## 설정 파일
`%APPDATA%\FeelCapture\config.json` — `mode`, `save_target`, `output_folder`, `extension`, `resize_enabled`/`resize_mode`/`resize_width`/`resize_height`/`resize_percent`, `hotkey`, `fps`, `region_box`(x/y/w/h/locked), `region_presets`(이름/W/H 3개).

## 사용법
```
.venv\Scripts\python.exe utils\feel_capture\main.py
```
1. 처음 실행하면 트레이에 카메라 아이콘이 뜬다. 우클릭 → "설정..."에서 모드/저장방식/출력폴더/확장자/리사이즈/단축키/프리셋을 지정한다.
2. 지정한 단축키를 누르면 현재 모드로 캡쳐(또는 녹화 시작)가 실행된다.
3. 영역 모드일 때는 화면의 빨간 박스를 드래그로 옮기거나 가장자리를 끌어 크기를 조절할 수 있다. 우클릭하면 프리셋/사용자 지정 크기/고정 토글/설정 열기 메뉴가 뜬다.
4. 완전히 종료하려면 트레이 아이콘 우클릭 → "종료".

## exe 빌드 (PyInstaller)
```
utils\feel_capture\assets\generate_icons.py   # 아이콘이 없다면 먼저 생성 (이미 생성되어 저장소에 포함됨)
utils\feel_capture\build_exe.ps1
```
`assets/icon.ico`를 exe 아이콘 및 트레이 아이콘 리소스로 번들해 `dist\FeelCapture.exe`(단일 파일)를 생성한다. 실제 빌드 후 exe를 직접 실행해 트레이 아이콘이 뜨고 크래시 없이 유지되는 것을 확인함(2026-07-23).

## 의존성
`PyQt5`(GUI/트레이/오버레이), `mss`(화면 캡처), `Pillow`(리사이즈/정지이미지·gif 저장), `opencv-python`+`numpy`(mp4/avi 인코딩), `keyboard`(전역 단축키), `pyinstaller`(exe 빌드 시에만 필요) — 모두 저장소 공용 `requirements.txt`에 포함됨.

## 제약사항
- Windows 전용(트레이/전역 단축키/아이콘 생성 방식 기준으로 검증, 다른 OS는 미검증).
- `keyboard` 라이브러리의 전역 후킹은 일부 환경(관리자 권한으로 실행 중인 다른 프로그램, 특정 보안 소프트웨어 등)에서 차단될 수 있다.
- gif 녹화는 프레임을 메모리에 모았다가 종료 시 한 번에 인코딩하므로, 아주 길게(수 분 이상) 녹화하면 메모리 사용량이 커질 수 있다. 긴 녹화에는 mp4/avi 사용을 권장.
- 애니메이션 gif는 화면 캡쳐로 확인 가능한 "가벼운 gif 녹화" 목적이며, 색상 팔레트 제한(256색) 등 gif 포맷 자체의 한계를 그대로 따른다.
- 클립보드 저장은 정지 이미지 포맷에서만 지원한다(gif/mp4/avi는 항상 파일 저장).

## 버전
- v1.0 — 2026-07-23 최초 작성. 드래그/영역 캡쳐, 클립보드/파일 저장(정지 이미지 + gif/mp4/avi 녹화), 저장 시 리사이즈, 사용자 지정 전역 단축키, 시스템 트레이 상주, PyInstaller exe 빌드 + 아이콘 생성 스크립트 포함.
- v1.1 — 2026-07-23 서브에이전트 독립 검증에서 발견된 버그 2건 수정: `overlay_region.RegionBox`의 서/북 리사이즈 핸들을 반대쪽 경계 너머로 드래그하면 박스가 커서 위치로 순간이동하던 문제(반대쪽 경계를 앵커로 좌표 자체를 미리 클램프하도록 수정), `config.load_config()`가 `region_presets: []`인 config.json을 만나면 기본 프리셋 3개로 복구되지 않던 문제(사후 검사로 무조건 복구하도록 수정). 자세한 내용은 [QA.md](QA.md) 참고.
- v1.2 — 2026-07-23 영역 박스 상단에 굵은 반투명 이동 전용 손잡이(`HANDLE_HEIGHT=14px`) 추가 — 테두리를 잡으면 리사이즈로 인식돼 이동이 어렵다는 사용자 피드백 반영. 양쪽 맨 끝 모서리(nw/ne)는 대각선 리사이즈로 남겨두고, 그 외 상단 전체는 항상 이동으로 동작.
