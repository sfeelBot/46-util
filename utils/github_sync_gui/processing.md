# github_sync_gui — processing.md

## 목적
사내망 등 git 접근이 막힌 PC에서 [tools/github_sync](../../tools/github_sync/README.md)의
zip 기반 GitHub 동기화 기능을 조작하기 위한 PyQt5 데스크탑 GUI.
**탭으로 여러 GitHub 저장소를 각각 다른 폴더에 등록해 한 번에 관리**할 수 있다. 탭마다 수동 동기화(실행 중 강제 취소 가능), 상태 확인, 로그 확인, 경로 설정을 독립적으로 처리한다.
시스템 트레이(작업표시줄 알림영역)에 상시 아이콘을 띄워, 창을 닫아도 백그라운드에서 계속 동작한다.

> v2.0에서 스케줄 기반 자동 동기화(매일 08:00/12:00/18:00 Windows 작업 스케줄러 등록) 기능을 제거했다.
> 수동 동기화만 지원하며, 대신 오래 걸리는 동기화를 즉시 중단할 수 있는 강제 취소 버튼을 추가했다 ([QA.md](QA.md) 참고).
>
> v3.0에서 단일 저장소 전제를 버리고 **탭 기반 다중 저장소 관리**로 바뀌었고, exe 이름도 `46util-sync-gui.exe` → `github-sync-feel.exe`로 바뀌었다 ([QA.md](QA.md) 참고).

---

## 구조

이 GUI는 동기화 로직을 직접 구현하지 않고, `tools/github_sync/Sync-FromGitHub.ps1`을 그대로 사용한다.

- **안정 실행 위치**: 최초 실행 시 `%LOCALAPPDATA%\46util-sync\`에 `Sync-FromGitHub.ps1`을 복사해두고, 이후 수동 동기화는 이 경로를 기준으로 한다. GUI를 새로 실행할 때마다 이 위치의 스크립트를 최신 버전(리포지토리의 `tools/github_sync/Sync-FromGitHub.ps1` 또는 exe에 번들된 사본)으로 덮어써서 항상 최신 로직을 쓰도록 한다. (이 폴더 이름 자체는 기존 사용자 데이터 보존을 위해 `46util-sync`로 그대로 유지한다 — exe 이름 변경과는 무관.)
- **DestDir 반영 방식**: robocopy `/E`(하위 폴더 포함 복사)를 사용한다. `.venv`는 `/XD`로 제외. **DestDir에만 있고 저장소에는 없는 파일(로컬 전용 파일)은 삭제하지 않는다** — 예전에는 `/MIR`(미러+퍼지)를 써서 이런 파일이 매 동기화마다 자동 삭제되었음 ([QA.md](QA.md) 참고). 트레이드오프: GitHub에서 삭제된 파일은 DestDir에 계속 남아있는다(자동으로 정리되지 않음).
  - `/R:3 /W:10`(재시도 3회, 간격 10초)도 함께 지정한다. 기본값(재시도 100만 회 x 30초 대기)이면 대상 파일이 다른 프로그램(예: Excel로 열어둔 csv)에 잠겨 있을 때 사실상 무한 대기하게 되는 문제가 있었다.
- **설정 파일(다중 저장소)**: `%LOCALAPPDATA%\46util-sync\config.json`에 `{"Profiles": [ {Id, Name, Owner, Repo, Branch, DestDir, StateDir, PythonExe, Token}, ... ] }` 형태로 탭(=저장소) 목록 전체를 저장한다. 각 프로필은 별도로 `%LOCALAPPDATA%\46util-sync\profiles\<Id>.json`에도 저장되며(`Sync-FromGitHub.ps1`이 실제로 읽는 파일), GUI는 동기화 시 `-ConfigPath`로 이 경로를 넘겨준다. `StateDir`(SHA/로그)도 프로필마다 별도 폴더(`%LOCALAPPDATA%\46util-sync\state\<Id>\`)를 기본값으로 써서 여러 저장소의 로그가 섞이지 않는다.
  - **하위 호환**: 이전 버전(v2.x 이하)의 단일-저장소 `config.json`(최상위에 `Owner`/`Repo`/... 키)이 있으면 최초 실행 시 자동으로 프로필 1개(첫 번째 탭)로 이전되며, 이때 기존 `StateDir` 값을 그대로 보존한다(로그/SHA 기록이 끊기지 않음). 또한 GUI를 거치지 않고 `Sync-FromGitHub.ps1`을 `-ConfigPath` 없이(예: Windows 작업 스케줄러에 직접 등록) 실행하는 기존 방식도 계속 동작하도록, `config.json`은 `Profiles` 배열과 별도로 **첫 번째 탭의 값을 최상위 키로도 함께 기록**한다.

## 비동기 처리 (GUI 응답성)

GUI가 PowerShell을 호출하는 지점(수동 동기화)과 GitHub API 조회(최신 커밋 확인)는 모두 **메인 스레드를 블로킹하지 않는 방식**으로 실행된다.

- `on_sync_now`는 `QProcess`로 `powershell.exe -File Sync-FromGitHub.ps1 -Force`를 비동기 실행하고, `finished` 시그널로 완료를 통보받는다.
- `CommitCheckWorker(QThread)`: `check_latest_commit()`의 GitHub API 호출(`urllib.request.urlopen`)을 별도 스레드에서 실행한다.
- `check_latest_commit()`은 이미 진행 중인 요청이 있으면 새 요청을 시작하지 않고 건너뛰는 가드(`self._commit_worker`가 `None`이 아니면 스킵)를 둔다. 완료 시 `deleteLater()`로 정리한다.
- 메인 스레드에는 블로킹 `subprocess.run`/`urllib.request.urlopen` 호출이 없다 (단, 강제 취소는 `QProcess.startDetached`로 `taskkill`을 비동기 실행한다).

## 강제 동기화 취소

"지금 바로 동기화" 실행 중에만 활성화되는 "강제 동기화 취소" 버튼.

- `QProcess.kill()`만으로는 그 QProcess(=powershell.exe)만 종료되고, powershell이 `&` 연산자로 실행한 자식 프로세스인 `robocopy.exe`는 고아 프로세스로 남아 재시도(잠긴 파일 대기)를 계속할 수 있다.
- 그래서 `on_cancel_sync()`는 `taskkill /PID <pid> /T /F`(`/T` = 프로세스 트리 전체)를 `QProcess.startDetached`로 비동기 실행해 powershell.exe와 robocopy.exe를 함께 종료한다.
- 취소 후 `on_sync_finished`에서 `self._sync_cancelled` 플래그를 보고 "취소됨"으로 표시한다 (실패와 구분).

## 단계별 소요 시간 로그

`Sync-FromGitHub.ps1`이 `초기화 → GitHub API 조회 → ZIP 다운로드 → ZIP 압축 해제 → robocopy 반영 → .venv 생성 → pip install` 단계를 거칠 때마다 `Set-Stage` 헬퍼(내부적으로 `[System.Diagnostics.Stopwatch]` 사용)가 직전 단계의 소요 시간을 `sync.log`에 `[단계 완료] <단계명>: N.N초` 형식으로 기록한다. 성공/"변경 없음" 조기 종료/오류 종료 세 경로 모두 마지막에 `총 소요 시간: N.N초`가 `finally` 블록에서 한 번 기록된다 (오류가 나도 어느 단계에서 몇 초 지나 실패했는지 `오류 발생 [<단계> 단계, N.N초 경과]: ...` 형태로 남는다). 실사용 중 동기화가 느리다고 느껴지면 이 로그(GUI의 "로그" 패널 또는 `StateDir\sync.log`)로 어느 단계가 병목인지 바로 확인할 수 있다.

## 완료 팝업

수동 동기화(`RepoTab.on_sync_now`)가 끝나면 `on_sync_finished`에서 결과에 맞는 `QMessageBox`를 띄운다: 취소됨(정보)/완료(정보)/실패(경고, 코드 포함). 트레이로 창을 숨겨둔 상태에서 동기화를 실행했더라도 팝업은 별도 최상위 창이라 화면에 뜬다.
단, 아래 "전체 동기화"처럼 `silent=True`로 호출된 경우에는 탭별 팝업을 생략하고, 대신 전체가 끝난 뒤 결과 요약 팝업 1개만 띄운다.

## 탭 기반 다중 저장소 관리

- 중앙 위젯이 `QTabWidget`이며, 탭 1개(`RepoTab`)가 저장소 URL + 대상 폴더(DestDir) 1세트에 대응한다. 각 탭은 자기 프로필(`cfg` dict: `Id`/`Name`/`Owner`/`Repo`/`Branch`/`DestDir`/`StateDir`/`PythonExe`/`Token`)과 자기 `sync_process`/로그/상태를 독립적으로 가진다.
- 탭 목록 오른쪽 위 "+ 저장소 추가" 코너 버튼(`MainWindow.on_add_profile`)으로 빈 프로필의 새 탭을 추가한다. 탭을 우클릭하면 "삭제" 메뉴가 뜨고(확인 팝업 후 삭제), 삭제해도 이미 반영된 파일과 `StateDir`의 로그/SHA는 지우지 않는다(탭 연결만 끊는다).
- 탭에서 "저장" 버튼을 누르면(`RepoTab._persist`) 그 프로필 전용 파일(`profiles/<Id>.json`)을 쓰고, `MainWindow._on_tab_saved`가 탭 제목(`Owner/Repo`)과 `config.json`(전체 목록)을 갱신한다.
- "Windows 시작 시 자동 실행"은 탭과 무관하게 GUI 앱 자체에 대한 전역 설정으로 유지된다 (탭이 몇 개든 앱을 한 번만 띄우면 모든 탭이 로드됨).

### 전체 동기화 (트레이 "지금 동기화 (전체)")

`MainWindow.on_sync_all()`이 등록된 모든 탭을 **한 번에 하나씩 순차** 동기화한다 (`_sync_all_pending` 큐 + `_sync_all_next`). 탭이 이미 수동으로 동기화 중이면 기다리지 않고 "건너뜀"으로 기록한 뒤 다음 탭으로 넘어간다. 모두 끝나면 탭별 결과(완료/실패/건너뜀) 요약 팝업 1개를 띄운다.

`_sync_all_waiting_tab`(현재 체인이 실제로 기다리는 탭 1개)으로 "지금 이 완료 신호가 전체 동기화 체인이 시작시킨 것인지"를 식별한다. 이게 없으면, 전체 동기화 도중 만난 "이미 실행 중인 탭"(다른 곳에서 수동으로 먼저 시작됨)이 나중에 실제로 끝날 때 그 완료 신호를 체인의 정상적인 다음 단계로 오인해 결과가 중복 기록되고 다음 탭이 동시에 시작되는 버그가 있었다 ([QA.md](QA.md) 2026-08-26 항목 참고).

## 기능

| 그룹 | 기능 |
|---|---|
| 저장소 설정 (탭별) | GitHub URL(`https://github.com/owner/repo`) 붙여넣기로 Owner/Repo 지정, 브랜치, Private 저장소용 Personal Access Token(선택, 비밀번호 입력창) 편집 후 저장 → 그 탭의 `profiles/<Id>.json`과 전체 `config.json`에 반영 |
| 경로 설정 (탭별) | `DestDir`(프로젝트가 반영될 폴더), `StateDir`(SHA/로그 저장 폴더)를 GUI에서 편집 후 저장 |
| 탭 추가/삭제 | "+ 저장소 추가"로 새 저장소 탭 생성, 탭 우클릭 → "삭제"로 제거(확인 팝업, 로그/반영 파일은 보존) |
| 수동 동기화 (탭별) | "지금 바로 동기화" 버튼으로 그 탭의 저장소만 `Sync-FromGitHub.ps1 -Force -ConfigPath <profiles/Id.json>`을 비동기 실행, 실시간 로그 출력. 실행 중에는 "강제 동기화 취소" 버튼으로 즉시 중단 가능 (위 "강제 동기화 취소" 절 참고) |
| 상태 (탭별) | 로컬에 반영된 커밋 SHA, 마지막 동기화 시각, "새로고침" 클릭 시 GitHub API로 최신 커밋 조회 (Private이면 Token 사용) |
| 로그 (탭별) | `StateDir\sync.log` 최근 200줄 표시. "로그 삭제" 버튼으로 확인 후 `sync.log` 파일 자체를 삭제(다음 로그부터 새로 생성됨). 삭제는 로그 파일에만 영향, 동기화 동작/설정과는 무관 |
| 트레이 아이콘 | 창을 닫아도 시스템 트레이에 상주. 우클릭 메뉴로 "지금 동기화 (전체, 등록된 모든 탭을 순차 실행)"/창 열기/종료 |
| Windows 시작 시 자동 실행 (전역) | 토글 버튼으로 레지스트리 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`에 등록/해제. 켜두면 컴퓨터를 재부팅/로그인할 때 이 프로그램(트레이 상주, 등록된 모든 탭 포함)이 자동으로 뜸. 스케줄 자동 동기화와는 별개 기능이라 v2.0 이후에도 유지됨 |

## Private 저장소 지원

- GitHub URL은 `https://github.com/owner/repo`, `.../repo.git`, `git@github.com:owner/repo.git` 형태를 인식해 Owner/Repo를 추출한다 (정규식 파싱, `parse_github_url`).
- Token을 입력하면 `Sync-FromGitHub.ps1`의 API 조회(`Invoke-RestMethod`)와 zip 다운로드(`Invoke-WebRequest`) 양쪽 모두에 `Authorization: token <PAT>` 헤더가 추가된다. GUI의 "GitHub 최신 커밋 확인"도 동일하게 Token을 사용한다.
- Token은 `%LOCALAPPDATA%\46util-sync\config.json`과 탭별 `profiles\<Id>.json`에 **평문으로 저장**된다 (이 PC 로컬에만 존재, git에는 포함되지 않음). 이 파일을 열어볼 수 있는 사람은 Token도 볼 수 있으므로, 필요한 최소 권한(해당 저장소 read 전용 등)의 PAT를 사용할 것을 권장한다.
- Public 저장소면 Token 칸을 비워두면 기존과 동일하게 동작한다.

## 트레이 아이콘 / 백그라운드 상주

- `assets/icon_on.ico`는 `assets/generate_icons.py`(Pillow)로 생성한 순환 화살표 로고. 모양을 바꾸려면 이 스크립트를 수정 후 재실행 (`assets/icon_off.ico`는 과거 자동 동기화 ON/OFF 표시용으로 생성해둔 파일로, 더 이상 코드에서 참조하지 않음).
- 창의 X 버튼(닫기)을 누르면 `closeEvent`에서 실제 종료 대신 `hide()`만 하고 트레이 풍선 알림을 띄운다 (`QApplication.setQuitOnLastWindowClosed(False)`로 마지막 창이 닫혀도 앱이 종료되지 않도록 함). 완전히 종료하려면 트레이 아이콘 우클릭 메뉴의 "종료"를 사용해야 한다.
- 트레이 아이콘 좌클릭/더블클릭: 창 열기(복원). 우클릭 메뉴: "지금 동기화 (전체)", "창 열기", "종료".
- `QSystemTrayIcon.isSystemTrayAvailable()`이 `False`인 환경(트레이가 없는 특수 환경)에서는 트레이 관련 기능을 건너뛰고 X 버튼이 정상적으로 창을 닫도록 폴백한다.

## Windows 시작 시 자동 실행 구현

- `winreg`(표준 라이브러리)로 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`에 값 이름 `github-sync-feel`(v3.0 이전에는 `46util-sync-gui`)을 등록/삭제한다. 관리자 권한 불필요(사용자 범위 HKCU).
- `_migrate_startup_registry_name()`: 앱 시작 시 옛 이름(`46util-sync-gui`)으로 등록된 항목이 있고 새 이름은 아직 없으면, 값만 새 이름으로 옮기고 옛 항목은 지운다 — exe 이름이 바뀌었다고 사용자가 토글을 다시 켤 필요는 없다.
- 등록되는 실행 커맨드는 `sys.frozen` 여부로 분기: exe로 빌드되어 실행 중이면 `sys.executable`(exe 경로) 그 자체, 개발 모드(스크립트 직접 실행)에서는 venv `python.exe`로 `main.py`를 실행하는 커맨드. **실사용은 exe로 빌드해서 등록하는 것을 전제로 한다** — 개발 모드로 등록하면 저장소/venv를 이동·삭제 시 시작 프로그램이 깨진다.
- 이 항목은 GUI(트레이 상주 앱) 자체를 로그인 시 띄우는 기능이며, (제거된) 스케줄 자동 동기화와는 별개였다.

## 사용법

```
.venv\Scripts\python.exe utils\github_sync_gui\main.py
```

1. 처음 실행하면 `%LOCALAPPDATA%\46util-sync\`에 스크립트/설정이 자동 생성되고, 탭 1개(기본 저장소)로 시작한다. 이전 버전(단일 저장소)을 쓰던 PC라면 기존 설정이 그대로 첫 번째 탭으로 이전된다.
2. 탭 안의 "저장소 설정"에서 동기화할 GitHub 저장소 URL/브랜치를 지정한다. Private이면 Token도 입력.
3. 탭 안의 "경로 설정"에서 실제 프로젝트가 위치할 폴더(DestDir)를 지정하고 저장한다.
   - 기존에 수동으로 다운받아 쓰던 폴더가 있다면 그 경로를 그대로 지정하면 `.venv`를 보존한 채 이어서 사용 가능.
4. 다른 저장소도 함께 관리하려면 탭 목록 오른쪽 위 "+ 저장소 추가"로 탭을 늘리고, 2~3번을 반복한다. 탭이 필요 없어지면 우클릭 → "삭제" (반영된 파일/로그는 남음).
5. 각 탭의 "지금 바로 동기화" 버튼으로 그 탭의 저장소만 즉시 반영한다. 대상 폴더의 파일이 다른 프로그램에 잠겨 있는 등의 이유로 오래 걸리면 "강제 동기화 취소" 버튼(실행 중에만 활성화)으로 즉시 중단할 수 있다.
6. 창을 닫아도(X 버튼) 프로그램은 트레이(작업표시줄 알림영역)에서 계속 실행된다. 트레이 아이콘을 클릭하면 창이 다시 열리고, 우클릭하면 "지금 동기화 (전체, 등록된 모든 탭 순차 실행)"/창 열기/종료 메뉴가 나온다. 완전히 끄려면 트레이 메뉴의 "종료"를 사용한다.
7. "Windows 시작 시 자동 실행"을 켜두면, 컴퓨터를 껐다 켜서 로그인할 때 이 프로그램이 자동으로 실행되어 트레이에 상주한다 (exe로 빌드해서 켠 경우를 기준으로 함, 모든 탭 포함).
8. 탭별로 로그가 너무 길어졌으면 그 탭의 "로그 삭제"로 `sync.log`를 지울 수 있다 (동기화 자체에는 영향 없음, 다음 동기화부터 새로 기록됨).

## exe 빌드 (PyInstaller)

```
utils\github_sync_gui\build_exe.ps1
```

`tools/github_sync/Sync-FromGitHub.ps1`과 `assets/icon_on.ico`를 리소스로 번들하여 단일 실행파일(`dist\github-sync-feel.exe`)을 생성한다.
exe 자체의 아이콘도 `assets/icon_on.ico`로 지정된다 (`--icon` 옵션 — 실제 빌드 후 PE 아이콘 리소스를 추출해 `icon_on.ico`와 픽셀 단위로 동일함을 확인함).
exe로 배포해도 실행 시 스크립트/아이콘을 `%LOCALAPPDATA%\46util-sync\`에 풀어놓고 동작하므로, 별도 설치 과정 없이
exe 파일 하나만 옮겨서 실행하면 된다.

## 의존성
`PyQt5` (실행), `pyinstaller` (exe 빌드 시에만 필요), `Pillow` (아이콘 재생성 스크립트 `assets/generate_icons.py` 실행 시에만 필요 — 이미 저장소 공용 requirements.txt에 포함됨)

## 제약사항
- Windows 전용 (robocopy/taskkill 의존).
- Token은 config.json/profiles\*.json에 평문 저장 (Windows 자격 증명 관리자 등 암호화 저장은 미구현).
- 스케줄 기반 자동 동기화는 없다 (v2.0에서 제거). 정기적으로 자동 반영이 필요하면 [tools/github_sync/Sync-FromGitHub.ps1](../../tools/github_sync/README.md)을 직접 Windows 작업 스케줄러에 등록해서 쓸 것. GUI 없이 등록하면서 여러 저장소를 각각 동기화하고 싶다면 각 저장소마다 별도 config.json을 만들어 `-ConfigPath`로 지정해서 각각 등록해야 한다 — `-ConfigPath`를 생략하면 GUI가 관리하는 첫 번째 탭의 설정(하위 호환용으로 `config.json` 최상위에 함께 기록됨)만 동기화된다.

## 버전
- v1.0 — 2026-07-09 초기 작성
- v1.1 — 2026-07-09 GUI에서 저장소 URL/브랜치/PAT(Private 지원) 설정 추가
- v1.2 — 2026-07-09 robocopy ExitCode=16 버그 수정, 로그 한글 인코딩(UTF-8) 수정, GUI 전체 비동기화(QProcess/QThread), robocopy `/MIR`→`/E`로 변경해 로컬 전용 파일 보존 ([QA.md](QA.md) 참고)
- v1.3 — 2026-07-09 로고 아이콘 추가, 시스템 트레이 상주 기능(창 닫아도 백그라운드 실행, 트레이 아이콘 색상으로 ON/OFF 확인, 우클릭 메뉴로 토글) 추가
- v1.4 — 2026-07-09 "로그 삭제" 버튼 추가, Windows 시작 시 자동 실행(레지스트리 Run 키) 토글 추가, exe 아이콘 적용 재확인
- v2.0 — 2026-07-13 스케줄 기반 자동 동기화(08/12/18시 예약 작업 on/off, 트레이 ON/OFF 토글) 기능 전체 제거 (`Register-ScheduledTasks.ps1` 삭제 포함). 대신 "강제 동기화 취소" 버튼 추가(`taskkill /T`로 robocopy까지 포함한 프로세스 트리 종료) — 대상 파일이 잠겨 있어 robocopy가 오래 대기할 때 즉시 중단 가능. `Sync-FromGitHub.ps1`의 robocopy에 `/R:3 /W:10`(재시도 3회, 10초 간격) 지정해 잠긴 파일에 대한 대기 시간도 자체적으로 단축
- v2.1 — 2026-07-13 `Sync-FromGitHub.ps1`에 단계별 소요 시간 로그(`Set-Stage`/`총 소요 시간`) 추가해 동기화가 느릴 때 병목 단계를 로그만으로 파악 가능하게 함. GUI에 수동 동기화 완료/실패/취소 팝업(`QMessageBox`) 추가
- v3.0 — 2026-08-26 exe 이름을 `46util-sync-gui.exe` → `github-sync-feel.exe`로 변경 (레지스트리 시작프로그램 값 이름도 자동 이전). **탭 기반 다중 저장소 관리** 추가: `config.json`이 `{"Profiles": [...]}` 형태로 바뀌었고(구버전 단일-저장소 config.json은 자동 이전, 하위 호환을 위해 첫 탭 값을 최상위 키로도 유지), 탭마다 독립된 저장소 설정/경로/수동 동기화/상태/로그를 가짐(`RepoTab`), `Sync-FromGitHub.ps1`에 `-ConfigPath` 파라미터 추가, 탭 자유 추가/삭제, 트레이 "지금 동기화"는 등록된 모든 탭을 순차 동기화. 구현 중 "전체 동기화"가 이미 실행 중인 탭과 경합해 결과가 꼬이는 버그를 서브에이전트 검증으로 발견해 수정 ([QA.md](QA.md) 참고)
