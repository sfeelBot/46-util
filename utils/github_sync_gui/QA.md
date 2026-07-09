# github_sync_gui — QA.md

이 util 작업 중 발견된 버그, 이상 동작, 검증 실패 사례를 기록한다.

---

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
