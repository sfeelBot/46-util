# github_sync_gui — processing.md

## 목적
사내망 등 git 접근이 막힌 PC에서 [tools/github_sync](../../tools/github_sync/README.md)의
zip 기반 GitHub 동기화 기능을 조작하기 위한 PyQt5 데스크탑 GUI.
자동 동기화 스케줄(매일 08:00/12:00/18:00) on/off, 수동 동기화, 상태 확인, 로그 확인, 경로 설정을 하나의 창에서 처리한다.

---

## 구조

이 GUI는 동기화 로직을 직접 구현하지 않고, `tools/github_sync/`의 두 PowerShell 스크립트를 그대로 사용한다.

- **안정 실행 위치**: 최초 실행 시 `%LOCALAPPDATA%\46util-sync\`에 `Sync-FromGitHub.ps1`, `Register-ScheduledTasks.ps1`을 복사해두고, 이후 모든 동작(예약 작업 등록, 수동 동기화)은 이 경로를 기준으로 한다.
  - 이유: Windows 작업 스케줄러에 등록된 작업은 GUI(또는 exe)가 어디 있든, 어디로 이동/삭제되든 상관없이 항상 같은 경로의 스크립트를 실행해야 하므로, GUI 자신의 위치와 무관한 고정 경로가 필요하다.
  - GUI를 새로 실행할 때마다 이 위치의 스크립트를 최신 버전(리포지토리의 `tools/github_sync/*.ps1` 또는 exe에 번들된 사본)으로 덮어써서 항상 최신 로직을 쓰도록 한다.
- **설정 파일**: `%LOCALAPPDATA%\46util-sync\config.json` (`Owner`, `Repo`, `Branch`, `DestDir`, `StateDir`, `PythonExe`, `Token`). `Sync-FromGitHub.ps1`과 GUI가 이 파일을 공유한다.

## 기능

| 그룹 | 기능 |
|---|---|
| 저장소 설정 | GitHub URL(`https://github.com/owner/repo`) 붙여넣기로 Owner/Repo 지정, 브랜치, Private 저장소용 Personal Access Token(선택, 비밀번호 입력창) 편집 후 저장 → `config.json`에 반영 |
| 경로 설정 | `DestDir`(프로젝트가 반영될 폴더), `StateDir`(SHA/로그 저장 폴더)를 GUI에서 편집 후 저장 → `config.json`에 반영 |
| 자동 동기화 스케줄 | 08:00/12:00/18:00 3개 예약 작업을 **하나의 토글**로 일괄 on/off. off해도 예약 작업 자체는 삭제되지 않고 비활성화(Disable)만 되어, 다시 켤 때 즉시 반영됨. 각 시각별 마지막 실행 시각/결과 코드 표시 |
| 수동 동기화 | "지금 바로 동기화" 버튼으로 `Sync-FromGitHub.ps1 -Force`를 비동기 실행, 실시간 로그 출력 |
| 상태 | 로컬에 반영된 커밋 SHA, 마지막 동기화 시각, "새로고침" 클릭 시 GitHub API로 최신 커밋 조회 (Private이면 Token 사용) |
| 로그 | `StateDir\sync.log` 최근 200줄 표시 |

## Private 저장소 지원

- GitHub URL은 `https://github.com/owner/repo`, `.../repo.git`, `git@github.com:owner/repo.git` 형태를 인식해 Owner/Repo를 추출한다 (정규식 파싱, `parse_github_url`).
- Token을 입력하면 `Sync-FromGitHub.ps1`의 API 조회(`Invoke-RestMethod`)와 zip 다운로드(`Invoke-WebRequest`) 양쪽 모두에 `Authorization: token <PAT>` 헤더가 추가된다. GUI의 "GitHub 최신 커밋 확인"도 동일하게 Token을 사용한다.
- Token은 `%LOCALAPPDATA%\46util-sync\config.json`에 **평문으로 저장**된다 (이 PC 로컬에만 존재, git에는 포함되지 않음). 이 파일을 열어볼 수 있는 사람은 Token도 볼 수 있으므로, 필요한 최소 권한(해당 저장소 read 전용 등)의 PAT를 사용할 것을 권장한다.
- Public 저장소면 Token 칸을 비워두면 기존과 동일하게 동작한다.

## 스케줄 제어 구현

`tools/github_sync/Register-ScheduledTasks.ps1 -Action <Register|EnableAll|DisableAll|Status>`를 GUI가 subprocess로 호출한다.

- `Register`: 3개 예약 작업을 생성/갱신 (기존 스크립트의 기본 동작)
- `EnableAll` / `DisableAll`: 기존 작업을 삭제하지 않고 Enable/Disable만 전환
- `Status`: 3개 작업의 존재 여부/활성화 여부/마지막 실행 시각·결과를 JSON으로 반환 (GUI가 파싱)

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

## exe 빌드 (PyInstaller)

```
utils\github_sync_gui\build_exe.ps1
```

`tools/github_sync/*.ps1`을 리소스로 번들하여 단일 실행파일(`dist\46util-sync-gui.exe`)을 생성한다.
exe로 배포해도 실행 시 스크립트를 `%LOCALAPPDATA%\46util-sync\`에 풀어놓고 동작하므로, 별도 설치 과정 없이
exe 파일 하나만 옮겨서 실행하면 된다.

## 의존성
`PyQt5` (실행), `pyinstaller` (exe 빌드 시에만 필요)

## 제약사항
- Windows 전용 (작업 스케줄러/robocopy 의존).
- Token은 config.json에 평문 저장 (Windows 자격 증명 관리자 등 암호화 저장은 미구현).
- 한 PC당 하나의 저장소를 동기화하는 것을 전제로 한다 (예약 작업 이름이 고정값이라, 여러 저장소를 동시에 동기화하려면 별도 설치 위치/작업 이름 분리가 필요).

## 버전
- v1.0 — 2026-07-09 초기 작성
- v1.1 — 2026-07-09 GUI에서 저장소 URL/브랜치/PAT(Private 지원) 설정 추가
