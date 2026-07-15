# github_sync_gui — QA.md

이 util 작업 중 발견된 버그, 이상 동작, 검증 실패 사례를 기록한다.

---

## 검증 요약 (2026-07-13, 단계별 소요 시간 로그 + 완료 팝업)

서브에이전트가 독립적으로 실제 실행하여 검증 (코드는 건드리지 않고 실행/테스트만 수행), 발견된 버그 없음.
- **단계별 로그**: `%TEMP%` 스크래치 경로에서 실제 공개 저장소(`sfeelBot/46-util`)를 대상으로 `Sync-FromGitHub.ps1`을 3가지 경로로 실행 — ① 최초 동기화(전체 단계 진행) → 각 단계(`GitHub API 조회`/`ZIP 다운로드`/`ZIP 압축 해제`/`robocopy 반영`/`.venv 생성`/`pip install`)마다 `[단계 완료] ...초` 로그와 마지막 `총 소요 시간: 35.2초` 확인. ② `-Force` 없이 재실행("변경 없음" 조기 종료) → `[단계 완료] GitHub API 조회: 0.3초` + `총 소요 시간: 0.3초`가 `finally`에서 정상적으로 남는지 확인 (가장 누락되기 쉬운 경로). ③ 존재하지 않는 Owner/Repo로 강제 실패 → `오류 발생 [GitHub API 조회 단계, 0.2초 경과]: ...` + `총 소요 시간: 0.3초` 확인. 세 경로 모두 통과.
- **완료 팝업**: 헤드리스(`QT_QPA_PLATFORM=offscreen`)로 실제 `MainWindow`를 띄우고 `QMessageBox.information`/`.warning`을 모킹한 뒤 `on_sync_finished`를 취소/성공/실패 3가지 조합으로 직접 호출 — 취소 시 "동기화 취소됨" 정보 팝업+라벨 "취소됨", 성공 시 "동기화 완료" 정보 팝업+라벨 "완료", 실패 시 "동기화 실패" 경고 팝업(코드 포함)+라벨 "실패 (code=N)"로 매 케이스 정확히 분기됨을 확인.

## 2026-07-13 — robocopy가 잠긴 파일 앞에서 사실상 무한 대기 (강제 취소 버튼 없음)

- **증상**: `DestDir` 안의 파일(예: Excel/텍스트 편집기로 열어둔 csv)이 다른 프로그램에 열려 있으면, "지금 바로 동기화"가 끝나지 않고 오래 멈춰있는 것처럼 보임. GUI 자체는 `QProcess` 비동기 실행이라 멈추지 않지만, 사용자가 이를 중단할 방법이 없었음.
- **원인**: `Sync-FromGitHub.ps1`의 robocopy 호출에 `/R`(재시도 횟수)·`/W`(재시도 간격) 옵션이 없어 기본값(재시도 100만 회, 간격 30초)이 적용됨. 잠긴 파일이 하나라도 있으면 사실상 끝나지 않는 대기로 이어짐.
- **해결**:
  1. `Sync-FromGitHub.ps1`의 robocopy 인자에 `/R:3 /W:10`(재시도 3회, 10초 간격) 추가해 잠긴 파일에 대한 대기 시간 자체를 제한.
  2. GUI에 "강제 동기화 취소" 버튼 추가 (`on_cancel_sync`). `QProcess.kill()`은 최상위 프로세스(powershell.exe)만 종료하고 그 자식인 robocopy.exe는 고아 프로세스로 남을 수 있어, `taskkill /PID <pid> /T /F`(`/T` = 프로세스 트리 전체)를 `QProcess.startDetached`로 비동기 호출해 powershell+robocopy를 함께 종료하도록 구현.
- **부수 변경**: 요청에 따라 스케줄 기반 자동 동기화(08:00/12:00/18:00 Windows 작업 스케줄러 등록, GUI의 자동 동기화 토글/트레이 ON-OFF) 기능 전체 삭제. `tools/github_sync/Register-ScheduledTasks.ps1` 파일 삭제, `main.py`에서 관련 코드(`PsRunner`, `on_toggle_schedule`, `_refresh_schedule_state` 등) 제거. "Windows 시작 시 자동 실행"(로그인 시 GUI 자체를 띄우는 기능)은 스케줄 자동 동기화와 별개 기능이라 유지함.
- **검증**: 서브에이전트가 독립적으로 실제 실행하여 검증 (코드는 건드리지 않고 실행/테스트만 수행), 발견된 버그 없음.
  - robocopy 재시도 제한: 대상 파일을 다른 프로세스로 잠근 뒤 실제 스크립트와 동일한 옵션(`/E /XD .venv /R:3 /W:10 /NFL /NDL /NJH /NJS /NP`)으로 robocopy 직접 실행 → 1회 시도 + 3회 재시도(10초 간격) 후 `RETRY LIMIT EXCEEDED`(ExitCode=8)로 30.03초 만에 종료됨을 실측 확인 (기본값이면 최대 100만 회 x 30초로 사실상 무한 대기).
  - 강제 취소: sync 스크립트가 자식 프로세스(robocopy 역할)를 또 실행하는 더미 wrapper .ps1로 `SYNC_SCRIPT`를 대체해 실제 GUI 코드 경로(`on_sync_now` → `on_cancel_sync`)를 이벤트 루프로 구동. `tasklist`로 부모+자식 PID가 실행 중임을 확인한 뒤 취소 → `taskkill /PID <pid> /T /F`가 부모와 모든 자식 프로세스를 함께 종료함을 `tasklist`로 재확인. `finished` 이후 `sync_now_label`이 "취소됨"으로 표시되고(실패/완료와 구분됨), 버튼 상태(`cancel_sync_btn` 비활성화, `sync_now_btn` 재활성화)도 정상 복원됨을 2회 반복 확인.
  - 잔여 참조: `TASK_NAMES`/`TASK_TIMES`/`MANAGE_SCRIPT`/`PsRunner`/`on_toggle_schedule`/`ICON_OFF`/`Register-ScheduledTasks` 등이 코드/설정에 더 이상 남아있지 않음을 grep으로 확인 (QA.md/processing.md의 변경 이력 서술은 정상).
  - `build_exe.ps1`: 삭제된 `Register-ScheduledTasks.ps1`을 더 이상 참조하지 않고, 참조 중인 `Sync-FromGitHub.ps1`/`assets\icon_on.ico`가 실제로 존재해 `Test-Path` 검사를 통과함을 확인 (실제 PyInstaller 빌드는 별도 실행하지 않음).

## 검증 요약 (2026-07-09, 로그 삭제 버튼 + Windows 시작 시 자동 실행 + exe 아이콘 재확인)

직접 실행하여 검증 (서브에이전트는 세션 한도로 중도 실패해 대신 실제 실행으로 확인). 발견된 버그 없음.
- **Windows 시작 시 자동 실행**: 실제 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 레지스트리에 테스트 전용 값 이름으로 등록→조회→해제 라운드트립을 실제로 실행해 정상 동작 확인. GUI 토글(`on_toggle_startup`)을 통해서도 동일하게 확인. 테스트 종료 후 실제 프로덕션 값(`46util-sync-gui`)이 레지스트리에 남아있지 않음을 `Get-ItemProperty`로 재확인(테스트 중 항상 별도 이름을 사용해 실수로 건드리지 않도록 함).
- **로그 삭제**: 임시 `sync.log`를 만들고 "로그 삭제" 실행 → 파일이 실제로 삭제되고 로그 뷰가 "(아직 로그 없음)"으로 갱신됨을 확인. 로그가 없는 상태에서 다시 눌러도 크래시 없이 안내 메시지만 뜸을 확인.
- **exe 아이콘**: `build_exe.ps1`과 동일한 옵션으로 실제 재빌드 → 생성된 exe의 PE 아이콘 리소스를 추출해 픽셀 RGB(46,160,67)가 `icon_on.ico`(초록/ON)와 정확히 일치함을 확인. exe를 실제로 실행해 3초간 정상 유지(크래시 없음) 후 정리.

## 2026-07-09 — robocopy가 ExitCode=16으로 완전히 실패 (수동 동기화 동작 안 함)

- **증상**: 사용자 PC에서 "지금 바로 동기화" 실행 시 로그에 `오류 발생: robocopy 실패 (ExitCode=16)`가 남고 반영이 전혀 되지 않음.
- **원인**: `Sync-FromGitHub.ps1`이 `Start-Process -FilePath robocopy.exe -ArgumentList <배열>`로 robocopy를 호출했는데, 이 방식은 배열 원소에 공백이 포함된 경로(기본 `DestDir`가 `C:\Work\46 util`처럼 공백 포함)를 자동으로 따옴표 처리해주지 않는다. 그 결과 robocopy가 경로를 엉뚱하게 나눠 받아 "지정된 파일을 찾을 수 없습니다" 오류(ExitCode=16, 경우에 따라 대상 폴더가 생성되지 않은 채 ExitCode=0으로 위장되기도 함)로 실패함. 공백 있는 경로로 직접 재현해 원인 확정.
- **해결**: `Start-Process -ArgumentList` 대신 네이티브 호출 연산자 `& robocopy.exe $robocopyArgs`로 변경 (배열 원소를 PowerShell이 자동으로 올바르게 인용함) + `$LASTEXITCODE`로 결과 판정. 공백 포함 경로로 재현 테스트 후 정상 동작(파일이 실제로 복사됨, ExitCode 0~7) 확인. 서브에이전트가 독립적으로 `%TEMP%\...with space\...` 경로에 실제 `Sync-FromGitHub.ps1`을 2회(신규+재실행) 실행해 재검증함.

## 2026-07-09 — robocopy `/MIR`가 DestDir의 로컬 전용 파일을 매번 삭제함

- **증상**: 동기화할 때마다 `DestDir`(예: `C:\Work\46 util`)에 로컬로만 추가해둔 파일이 사라짐.
- **원인**: robocopy `/MIR` 옵션은 미러링 + 퍼지(purge) 동작이라, 원본(GitHub 저장소 zip)에는 없고 대상에만 있는 파일/폴더를 전부 삭제한다. `.venv`는 `/XD`로 예외 처리했지만 그 외 로컬 전용 파일은 보호되지 않았음.
- **해결**: `/MIR`을 `/E`(하위 폴더 포함 복사, 퍼지 없음)로 변경. 로컬 전용 파일 보존을 실제 robocopy 실행(로컬 전용 파일 생성 → `/E`로 반영 → 파일이 그대로 남아있는지)으로 확인.
- **트레이드오프(제약사항)**: GitHub 저장소에서 파일이 삭제되어도 이미 로컬에 반영된 사본은 자동으로 지워지지 않는다. 저장소에서 파일을 삭제한 경우 이 PC에서는 수동 정리가 필요할 수 있음.

## 2026-07-09 — sync.log 및 실시간 로그의 한글이 깨져서 표시됨

- **증상**: GUI의 "로그" 패널과 `StateDir\sync.log` 파일에 한글이 `????` 형태로 깨져서 보임 (예: `=== Sync ���� ===`).
- **원인**: 두 가지가 겹친 문제.
  1. `Write-Log` 함수가 `Add-Content -Path $LogFile -Value $line`로 파일에 쓸 때 인코딩을 지정하지 않아, Windows 기본 코드페이지(한글 Windows에서는 CP949)로 저장됨. 반면 GUI(`main.py`)는 이 로그 파일을 `read_text(encoding="utf-8")`로 읽어서 불일치 발생.
  2. PowerShell의 `Write-Host` 출력도 stdout이 리다이렉트(파이프/캡처)되면 콘솔 코드페이지(CP949)로 나가는데, GUI가 `QProcess`로 캡처한 뒤 `decode("utf-8")`로 디코드하고 있어서 "지금 바로 동기화"의 실시간 로그도 동일하게 깨짐.
  - 직접 바이트 단위로 재현: `Add-Content`로 쓴 파일을 읽어보면 UTF-8이 아닌 CP949 바이트였음.
- **해결**:
  - `Sync-FromGitHub.ps1`, `Register-ScheduledTasks.ps1` 상단에 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 추가 → 리다이렉트된 stdout이 UTF-8 바이트로 나가도록 강제.
  - `Write-Log`를 `[System.IO.File]::AppendAllText($LogFile, $line + "` `r` `n", (New-Object System.Text.UTF8Encoding($false)))`로 변경 → BOM 없는 UTF-8로 파일에 직접 기록.
  - sync.log 파일 재검증(UTF-8로 정상 디코드) + `QProcess`로 실제 캡처한 실시간 로그 재검증, 둘 다 정상 확인.
- **주의**: 이 두 `.ps1` 스크립트 파일 자체는 반드시 UTF-8 **with BOM**으로 저장되어 있어야 한다 (스크립트 소스 코드 안의 한글 리터럴이 파싱되는 방식과 관련된, 위와는 별개의 기존 이슈 — 아래 "PowerShell 스크립트 한글 인코딩 깨짐" 항목 참고). 앞으로 이 파일을 수정할 때 BOM 없이 재저장하면 `OutputEncoding` 수정과 무관하게 다시 깨질 수 있다.

## 2026-07-09 — GUI가 60초마다/토글할 때마다 잠깐씩 멈춤 (동기 서브프로세스 호출)

- **증상**: 예약 작업 상태를 자동 새로고침하는 60초 주기 타이머, "자동 동기화" 토글, "GitHub 최신 커밋 확인" 버튼 클릭 시 GUI 전체가 순간적으로 멈춤(끊김).
- **원인**: `_refresh_schedule_state()`와 `on_toggle_schedule()`이 `subprocess.run(...)`으로 `powershell.exe`를 GUI 메인 스레드에서 동기적으로 실행했고, `check_latest_commit()`도 `urllib.request.urlopen(...)`을 메인 스레드에서 동기 호출했음. 이 중 `_refresh_schedule_state()`는 60초 QTimer로 자동 반복 호출되어 주기적으로 멈춤 현상이 발생.
- **해결**: `PsRunner(QObject)`(QProcess 기반 비동기 실행)와 `CommitCheckWorker(QThread)`를 새로 만들어 세 지점 모두 논블로킹으로 전환. 중복 호출 방지 가드(`_status_runner`/`_toggle_runner`/`_commit_worker`)와 완료 후 `deleteLater()` 정리 포함. `main.py`에 더 이상 블로킹 `subprocess.run`/`urllib.request.urlopen` 호출이 메인 스레드에 없음을 정적 확인 + `QT_QPA_PLATFORM=offscreen`으로 실제 `MainWindow`를 띄워 각 호출이 즉시 반환되고(비블로킹 증명), 이벤트 루프를 몇 차례 돌리면 실제로 완료되어 상태가 갱신되는 것을 확인. 자세한 내용은 [processing.md](processing.md)의 "비동기 처리" 절 참고.

## 검증 요약 (2026-07-09, 로고 아이콘 + 시스템 트레이 상주 기능 추가)

서브에이전트가 독립적으로 검증 (코드는 건드리지 않고 실행/테스트만 수행). 발견된 버그 없음.
- `assets/icon_on.ico`(초록)/`icon_off.ico`(회색): 유효한 다중 해상도 ICO, 색상이 명확히 다름을 확인.
- `main.py`: 이 검증 환경은 `QSystemTrayIcon.isSystemTrayAvailable()`이 `False`라 실제 트레이 렌더링/클릭은 검증 불가 — 대신 `isSystemTrayAvailable`을 강제로 `True`로 만든 인스턴스로 트레이 생성/메뉴 4개 액션(자동 동기화 토글/지금 동기화/창 열기/종료) 연결/`closeEvent`의 hide-not-close 동작/`_update_tray_status`의 아이콘·툴팁·체크상태 동기화를 실제로 트리거해 검증. 트레이 없는 폴백 분기(정상 종료)도 별도 확인.
- `build_exe.ps1`: 실제로 빌드 실행해 exe 생성 확인, exe 바이너리에 두 아이콘·두 ps1 스크립트가 번들됨을 확인, exe의 PE 아이콘 리소스가 `icon_on.ico`와 픽셀 단위로 일치함을 확인, exe 정상 기동 확인 후 프로세스 정리.
- 이 PC에 실제 예약 작업은 등록되지 않았음 (검증 전/후 확인). `dist/`, `build/`는 `.gitignore`에 이미 포함되어 있어 git에는 영향 없음.

## 검증 요약 (2026-07-09, robocopy/인코딩/비동기 수정 4건)

서브에이전트가 독립적으로 검증 (코드는 건드리지 않고 실행/테스트만 수행):
- robocopy ExitCode=16: 공백 포함 경로로 `Sync-FromGitHub.ps1`을 2회(신규+`-Force` 재실행) 실제 실행 → 둘 다 성공 범위 ExitCode(1, 2), 파일이 실제로 복사됨을 확인.
- 로그 인코딩: 생성된 `sync.log`를 UTF-8로 읽어 한글이 정상 표시됨을 확인. `QProcess`로 캡처한 실시간 로그도 동일하게 정상 확인. (`Register-ScheduledTasks.ps1`의 `Register`/`EnableAll`/`DisableAll` 분기 안의 한글 메시지는 실제 예약 작업을 건드리게 되어 안전상 직접 실행 검증하지 않음 — 정적 확인 및 동일 수정 패턴 적용 확인으로 대체.)
- GUI 비동기화: `QT_QPA_PLATFORM=offscreen`으로 실제 `MainWindow` 기동, `_refresh_schedule_state`/`check_latest_commit`/`on_toggle_schedule` 호출이 즉시 반환(비블로킹)되고 이벤트 루프 진행 후 정상 완료되는 것을 확인. `on_toggle_schedule`은 실제 예약 작업을 건드리지 않도록 `MANAGE_SCRIPT`를 더미 스크립트로 임시 치환해 검증. 테스트 전후로 이 PC에 `46util-GitHubSync-*` 예약 작업이 등록되지 않은 상태임을 확인(부작용 없음).
- `/MIR` → `/E` (로컬 전용 파일 보존): 로컬 전용 파일을 만들어두고 robocopy 반영 후에도 그대로 남아있는지 직접 실행 확인 (이 항목은 서브에이전트 검증 이후 사용자 요청으로 추가된 수정이라 별도로 직접 실행 검증함, 서브에이전트 재검증은 하지 않음).

## 2026-07-09 — PowerShell 스크립트 한글 인코딩 깨짐

- **증상**: `tools/github_sync/Sync-FromGitHub.ps1`, `Register-ScheduledTasks.ps1` 실행 시 로그의 한글 일부가 깨져서 출력됨 (예: "시작" → "?쒖옉").
- **원인**: 두 스크립트 파일이 BOM 없는 UTF-8로 저장되어 있었음. Windows PowerShell 5.1은 BOM이 없는 스크립트 파일을 시스템 기본 코드페이지(CP949)로 해석하기 때문에, 파일 안의 UTF-8 한글 리터럴이 깨짐.
- **해결**: 두 스크립트를 UTF-8 with BOM으로 재저장. 이후 실제로 스크립트를 실행해 로그 출력이 정상적으로 한글로 표시되는지 확인함.
- **주의**: 앞으로 이 폴더의 `.ps1` 파일을 수정할 때는 반드시 UTF-8 BOM 인코딩을 유지해야 한다.

## 2026-07-09 — 예약 작업 LastRunTime이 의미 없는 날짜로 표시됨

- **증상**: `Register-ScheduledTasks.ps1 -Action Status`로 조회 시, 한 번도 실행되지 않은 예약 작업의 `LastRunTime`이 `1999-11-30 00:00:00` 같은 값으로 나옴.
- **원인**: Windows 작업 스케줄러는 "한 번도 실행되지 않음"을 나타낼 때 `1999-11-30` 등 특수 날짜를 반환하는데, 최초 구현에서는 `Year -gt 1`로만 걸러서 이 값이 그대로 통과됨.
- **해결**: `LastRunTime -gt [datetime]"2001-01-01"` 조건으로 걸러서, 실행된 적 없는 작업은 `null`을 반환하도록 수정. 격리된 테스트용 예약 작업(`46util-synctest-*`)으로 Register → Status → DisableAll → EnableAll 전체 흐름을 실제로 실행해 검증 후 정리함.

## 검증 요약 (2026-07-09)

- Sync-FromGitHub.ps1: 격리된 스크래치 경로에서 config.json 기반 설정 로드 → GitHub API 조회 → zip 다운로드 → robocopy 반영(.venv 보존) → venv 생성 → pip install 전체 흐름을 실제로 실행하여 성공 확인.
- Register-ScheduledTasks.ps1: 격리된 테스트용 작업 이름으로 Register/Status/DisableAll/EnableAll 전체 사이클 실제 실행 확인 후 정리.
- main.py: 실제로 실행해 창이 정상적으로 뜨고, 시작 시 `%LOCALAPPDATA%\46util-sync\`에 스크립트/config.json이 올바르게 생성되는 것을 확인. (개발 PC에 실제 예약 작업을 등록하는 토글 ON 동작은 대상 PC가 아니므로 이 검증에서는 실행하지 않음 — 별도 격리 테스트로 대체.)
- exe(PyInstaller): `build_exe.ps1`로 빌드 후 실행해 정상 기동 확인. 실행 중 exe가 파일을 점유하고 있으면 재빌드 시 `PermissionError`가 발생하므로, 재빌드 전에는 실행 중인 exe를 먼저 종료해야 함 (도구 자체 버그는 아님, 운영 시 참고사항).

## 2026-07-09 — Private 저장소 지원(GitHub URL/브랜치/Token) 검증

- GUI에 "저장소 설정"(GitHub URL 붙여넣기 → Owner/Repo 파싱, 브랜치, Token 입력) 추가. `parse_github_url`을 다양한 URL 형태(`https://.../repo`, `.../repo.git`, `git@github.com:owner/repo.git`)로 단위 테스트하여 정상 파싱 확인.
- Token이 설정되면 `Sync-FromGitHub.ps1`의 API 조회/zip 다운로드 헤더에 `Authorization: token <PAT>`가 실제로 추가되는지, 격리 환경에서 **의도적으로 잘못된 토큰**을 넣어 실행 → GitHub이 401 오류를 반환하는 것을 확인함 (헤더가 실제로 전달·처리된다는 증거). 정상 토큰으로의 전체 성공 경로는 실제 Private 저장소가 없어 이번 검증에서는 수행하지 못함 — Private 저장소를 사용하게 되면 실제 토큰으로 한 번 더 확인 필요.
