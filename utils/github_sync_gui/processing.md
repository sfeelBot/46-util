# github_sync_gui — processing.md

## 목적
사내망 등 git 접근이 막힌 PC에서 [tools/github_sync](../../tools/github_sync/README.md)의
zip 기반 GitHub 동기화 기능을 조작하기 위한 PyQt5 데스크탑 GUI.
자동 동기화 스케줄(매일 08:00/12:00/18:00) on/off, 수동 동기화, 상태 확인, 로그 확인, 경로 설정을 하나의 창에서 처리한다.
시스템 트레이(작업표시줄 알림영역)에 상시 아이콘을 띄워, 창을 닫아도 백그라운드에서 계속 동작하며 자동 동기화 ON/OFF 상태를 아이콘 색상으로 바로 확인할 수 있다.

---

## 구조

이 GUI는 동기화 로직을 직접 구현하지 않고, `tools/github_sync/`의 두 PowerShell 스크립트를 그대로 사용한다.

- **안정 실행 위치**: 최초 실행 시 `%LOCALAPPDATA%\46util-sync\`에 `Sync-FromGitHub.ps1`, `Register-ScheduledTasks.ps1`을 복사해두고, 이후 모든 동작(예약 작업 등록, 수동 동기화)은 이 경로를 기준으로 한다.
  - 이유: Windows 작업 스케줄러에 등록된 작업은 GUI(또는 exe)가 어디 있든, 어디로 이동/삭제되든 상관없이 항상 같은 경로의 스크립트를 실행해야 하므로, GUI 자신의 위치와 무관한 고정 경로가 필요하다.
  - GUI를 새로 실행할 때마다 이 위치의 스크립트를 최신 버전(리포지토리의 `tools/github_sync/*.ps1` 또는 exe에 번들된 사본)으로 덮어써서 항상 최신 로직을 쓰도록 한다.
- **DestDir 반영 방식**: robocopy `/E`(하위 폴더 포함 복사)를 사용한다. `.venv`는 `/XD`로 제외. **DestDir에만 있고 저장소에는 없는 파일(로컬 전용 파일)은 삭제하지 않는다** — 예전에는 `/MIR`(미러+퍼지)를 써서 이런 파일이 매 동기화마다 자동 삭제되었음 ([QA.md](QA.md) 참고). 트레이드오프: GitHub에서 삭제된 파일은 DestDir에 계속 남아있는다(자동으로 정리되지 않음).
- **설정 파일**: `%LOCALAPPDATA%\46util-sync\config.json` (`Owner`, `Repo`, `Branch`, `DestDir`, `StateDir`, `PythonExe`, `Token`). `Sync-FromGitHub.ps1`과 GUI가 이 파일을 공유한다.

## 비동기 처리 (GUI 응답성)

GUI가 PowerShell을 호출하는 지점(수동 동기화, 예약 작업 상태 조회, 예약 작업 on/off 토글)과 GitHub API 조회(최신 커밋 확인)는 모두 **메인 스레드를 블로킹하지 않는 방식**으로 실행된다.

- `PsRunner(QObject)`: `QProcess` 기반으로 `powershell.exe -File ...`를 비동기 실행하는 공용 헬퍼. `finished(exit_code, stdout, stderr)` 시그널로 결과를 알려준다. `on_sync_now`(수동 동기화), `_refresh_schedule_state`(상태 조회, 60초 QTimer로 자동 호출), `on_toggle_schedule`(스케줄 on/off)이 모두 이 클래스를 사용한다.
- `CommitCheckWorker(QThread)`: `check_latest_commit()`의 GitHub API 호출(`urllib.request.urlopen`)을 별도 스레드에서 실행한다.
- 각 호출 지점은 이미 진행 중인 요청이 있으면 새 요청을 시작하지 않고 건너뛰는 가드(`self._status_runner`/`self._toggle_runner`/`self._commit_worker`가 `None`이 아니면 스킵)를 둔다. 완료 시 `deleteLater()`로 정리해, 60초마다 도는 상태 조회가 장시간 실행 시 QObject를 누적시키지 않도록 한다.
- 메인 스레드에는 블로킹 `subprocess.run`/`urllib.request.urlopen` 호출이 없다.

## 기능

| 그룹 | 기능 |
|---|---|
| 저장소 설정 | GitHub URL(`https://github.com/owner/repo`) 붙여넣기로 Owner/Repo 지정, 브랜치, Private 저장소용 Personal Access Token(선택, 비밀번호 입력창) 편집 후 저장 → `config.json`에 반영 |
| 경로 설정 | `DestDir`(프로젝트가 반영될 폴더), `StateDir`(SHA/로그 저장 폴더)를 GUI에서 편집 후 저장 → `config.json`에 반영 |
| 자동 동기화 스케줄 | 08:00/12:00/18:00 3개 예약 작업을 **하나의 토글**로 일괄 on/off. off해도 예약 작업 자체는 삭제되지 않고 비활성화(Disable)만 되어, 다시 켤 때 즉시 반영됨. 각 시각별 마지막 실행 시각/결과 코드 표시 |
| 수동 동기화 | "지금 바로 동기화" 버튼으로 `Sync-FromGitHub.ps1 -Force`를 비동기 실행, 실시간 로그 출력 |
| 상태 | 로컬에 반영된 커밋 SHA, 마지막 동기화 시각, "새로고침" 클릭 시 GitHub API로 최신 커밋 조회 (Private이면 Token 사용) |
| 로그 | `StateDir\sync.log` 최근 200줄 표시 |
| 트레이 아이콘 | 창을 닫아도 시스템 트레이에 상주. 아이콘 색상(초록=ON/회색=OFF)과 툴팁으로 자동 동기화 상태 확인, 우클릭 메뉴로 토글/수동 동기화/창 열기/종료 |

## Private 저장소 지원

- GitHub URL은 `https://github.com/owner/repo`, `.../repo.git`, `git@github.com:owner/repo.git` 형태를 인식해 Owner/Repo를 추출한다 (정규식 파싱, `parse_github_url`).
- Token을 입력하면 `Sync-FromGitHub.ps1`의 API 조회(`Invoke-RestMethod`)와 zip 다운로드(`Invoke-WebRequest`) 양쪽 모두에 `Authorization: token <PAT>` 헤더가 추가된다. GUI의 "GitHub 최신 커밋 확인"도 동일하게 Token을 사용한다.
- Token은 `%LOCALAPPDATA%\46util-sync\config.json`에 **평문으로 저장**된다 (이 PC 로컬에만 존재, git에는 포함되지 않음). 이 파일을 열어볼 수 있는 사람은 Token도 볼 수 있으므로, 필요한 최소 권한(해당 저장소 read 전용 등)의 PAT를 사용할 것을 권장한다.
- Public 저장소면 Token 칸을 비워두면 기존과 동일하게 동작한다.

## 스케줄 제어 구현

`tools/github_sync/Register-ScheduledTasks.ps1 -Action <Register|EnableAll|DisableAll|Status>`를 GUI가 `PsRunner`(QProcess, 비동기)로 호출한다.

- `Register`: 3개 예약 작업을 생성/갱신 (기존 스크립트의 기본 동작)
- `EnableAll` / `DisableAll`: 기존 작업을 삭제하지 않고 Enable/Disable만 전환
- `Status`: 3개 작업의 존재 여부/활성화 여부/마지막 실행 시각·결과를 JSON으로 반환 (GUI가 파싱)

## 트레이 아이콘 / 백그라운드 상주

- `assets/icon_on.ico`(초록)·`assets/icon_off.ico`(회색)는 `assets/generate_icons.py`(Pillow)로 생성한 순환 화살표 로고. 색상/모양을 바꾸려면 이 스크립트를 수정 후 재실행.
- 창의 X 버튼(닫기)을 누르면 `closeEvent`에서 실제 종료 대신 `hide()`만 하고 트레이 풍선 알림을 띄운다 (`QApplication.setQuitOnLastWindowClosed(False)`로 마지막 창이 닫혀도 앱이 종료되지 않도록 함). 완전히 종료하려면 트레이 아이콘 우클릭 메뉴의 "종료"를 사용해야 한다.
- 트레이 아이콘 좌클릭/더블클릭: 창 열기(복원). 우클릭 메뉴: "자동 동기화"(체크 가능, 클릭 즉시 on/off 토글 — 창의 토글 버튼과 동일한 `on_toggle_schedule`을 공유), "지금 동기화", "창 열기", "종료".
- 예약 작업 상태 조회(`_on_schedule_status_result`) 결과에 따라 `_update_tray_status()`가 창 아이콘·트레이 아이콘·트레이 툴팁·트레이 메뉴의 체크 상태를 한 번에 갱신한다 (창의 토글 버튼과 트레이 메뉴 항목은 항상 같은 상태를 보여줌).
- `QSystemTrayIcon.isSystemTrayAvailable()`이 `False`인 환경(트레이가 없는 특수 환경)에서는 트레이 관련 기능을 건너뛰고 X 버튼이 정상적으로 창을 닫도록 폴백한다.

## 사용법

```
.venv\Scripts\python.exe utils\github_sync_gui\main.py
```

1. 처음 실행하면 `%LOCALAPPDATA%\46util-sync\`에 스크립트/설정이 자동 생성된다.
2. "저장소 설정"에서 동기화할 GitHub 저장소 URL/브랜치를 지정한다 (기본값은 이 리포지토리). Private이면 Token도 입력.
3. "경로 설정"에서 실제 프로젝트가 위치할 폴더(DestDir)를 지정하고 저장한다.
   - 기존에 수동으로 다운받아 쓰던 폴더가 있다면 그 경로를 그대로 지정하면 `.venv`를 보존한 채 이어서 사용 가능.
4. "자동 동기화: OFF" 버튼을 눌러 ON으로 전환하면 08:00/12:00/18:00 예약 작업이 등록된다.
5. 당장 반영하고 싶으면 "지금 바로 동기화" 버튼을 사용한다.
6. 창을 닫아도(X 버튼) 프로그램은 트레이(작업표시줄 알림영역)에서 계속 실행된다. 트레이 아이콘을 클릭하면 창이 다시 열리고, 우클릭하면 자동 동기화 토글/수동 동기화/종료 메뉴가 나온다. 완전히 끄려면 트레이 메뉴의 "종료"를 사용한다.

## exe 빌드 (PyInstaller)

```
utils\github_sync_gui\build_exe.ps1
```

`tools/github_sync/*.ps1`과 `assets/*.ico`를 리소스로 번들하여 단일 실행파일(`dist\46util-sync-gui.exe`)을 생성한다.
exe 자체의 아이콘도 `assets/icon_on.ico`로 지정된다.
exe로 배포해도 실행 시 스크립트/아이콘을 `%LOCALAPPDATA%\46util-sync\`에 풀어놓고 동작하므로, 별도 설치 과정 없이
exe 파일 하나만 옮겨서 실행하면 된다.

## 의존성
`PyQt5` (실행), `pyinstaller` (exe 빌드 시에만 필요), `Pillow` (아이콘 재생성 스크립트 `assets/generate_icons.py` 실행 시에만 필요 — 이미 저장소 공용 requirements.txt에 포함됨)

## 제약사항
- Windows 전용 (작업 스케줄러/robocopy 의존).
- Token은 config.json에 평문 저장 (Windows 자격 증명 관리자 등 암호화 저장은 미구현).
- 한 PC당 하나의 저장소를 동기화하는 것을 전제로 한다 (예약 작업 이름이 고정값이라, 여러 저장소를 동시에 동기화하려면 별도 설치 위치/작업 이름 분리가 필요).

## 버전
- v1.0 — 2026-07-09 초기 작성
- v1.1 — 2026-07-09 GUI에서 저장소 URL/브랜치/PAT(Private 지원) 설정 추가
- v1.2 — 2026-07-09 robocopy ExitCode=16 버그 수정, 로그 한글 인코딩(UTF-8) 수정, GUI 전체 비동기화(QProcess/QThread), robocopy `/MIR`→`/E`로 변경해 로컬 전용 파일 보존 ([QA.md](QA.md) 참고)
- v1.3 — 2026-07-09 로고 아이콘 추가, 시스템 트레이 상주 기능(창 닫아도 백그라운드 실행, 트레이 아이콘 색상으로 ON/OFF 확인, 우클릭 메뉴로 토글) 추가
