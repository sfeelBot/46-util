# github_sync

git 접근이 막힌 사내망 PC에서, GitHub 저장소(`sfeelBot/46-util`)의 새 push 여부를 확인하고,
변경이 있으면 "Download ZIP"과 동일한 방식(HTTPS zip 다운로드)으로 받아 로컬에 반영하는 스크립트.

- git 명령/프로토콜 불필요 (HTTPS로 `github.com`, `api.github.com`, `codeload.github.com` 접속만 되면 동작)
- 기존 `.venv` 폴더는 항상 보존, 반영 후 `requirements.txt`로 `pip install` 자동 실행
- 필요 시 `.venv`를 완전히 새로 만드는 옵션도 포함

> **GUI로 조작하고 싶다면** [utils/github_sync_gui](../../utils/github_sync_gui/processing.md) 참고.
> 수동 동기화(강제 취소 가능), 상태/로그 확인을 창 하나에서 처리하며, 아래 스크립트를 그대로 사용한다.

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `Sync-FromGitHub.ps1` | 실제 동기화 로직 (커밋 확인 → zip 다운로드 → 반영 → pip install) |
| `config.json` | 실행 시 스크립트와 같은 폴더에 자동 생성됨 (없으면 기본값으로 생성). 설정은 여기서 관리 |

## 사전 준비 (동기화 대상 PC에서)

1. 이 `tools/github_sync/` 폴더를 대상 PC의 원하는 위치로 복사한다 (예: `C:\Work\46util-sync-scripts`).
2. `Sync-FromGitHub.ps1`을 한 번 실행하면 같은 폴더에 `config.json`이 기본값으로 생성된다. 이 파일을 열어 환경에 맞게 수정한다.

   ```json
   {
     "Owner": "sfeelBot",
     "Repo": "46-util",
     "Branch": "main",
     "DestDir": "C:\\Work\\46 util",
     "StateDir": "C:\\Work\\46util-sync\\state",
     "PythonExe": "py",
     "Token": ""
   }
   ```

   - `Owner`/`Repo`/`Branch`: 동기화할 GitHub 저장소 (이 스크립트를 다른 저장소용으로 그대로 재사용 가능)
   - `DestDir`: 실제 프로젝트가 위치할 경로
   - `StateDir`: 마지막 커밋 SHA / 로그 저장 위치 (**`DestDir` 바깥**에 둘 것)
   - `PythonExe`: `py` launcher 사용 (`py -3.12 -m venv ...`)
   - `Token`: **Private 저장소일 때만** GitHub Personal Access Token 입력 (Public이면 빈 문자열로 둘 것). API 조회와 zip 다운로드 양쪽에 `Authorization: token <PAT>` 헤더로 사용됨. 평문 저장이므로 필요한 최소 권한(read-only 등)의 토큰을 권장

   > `StateDir`는 반드시 `DestDir` 바깥에 둔다.

3. Python 3.12가 `py -3.12`로 실행 가능한지 확인한다 (`py -3.12 --version`).

## 수동 테스트

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1
```

- 최초 실행: `DestDir`가 없으면 새로 만들고 전체를 받아온다. `.venv`가 없으므로 새로 생성 후 `pip install -r requirements.txt` 실행.
- 이후 실행: GitHub의 최신 커밋 SHA를 `StateDir\last_sha.txt`와 비교해서, 같으면 아무것도 하지 않고 종료.
- 강제로 다시 받고 싶을 때: `-Force`
- `.venv`를 지우고 새로 만들고 싶을 때: `-RecreateVenv`
- 여러 저장소를 각각 동기화하고 싶을 때(예: 저장소별로 이 스크립트를 각각 예약 작업에 등록): `-ConfigPath`로 저장소마다 다른 config.json을 지정. 생략하면 기존과 동일하게 스크립트와 같은 폴더의 `config.json`을 사용한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1 -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1 -RecreateVenv
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1 -ConfigPath "C:\path\to\other-config.json"
```

로그는 `StateDir\sync.log`에 누적 기록된다. 단계(GitHub API 조회/ZIP 다운로드/ZIP 압축 해제/robocopy 반영/.venv 생성/pip install)가 바뀔 때마다 직전 단계 소요 시간이 `[단계 완료] <단계명>: N.N초` 형식으로 남고, 실행이 끝나면(성공/변경 없음/실패 어느 경우든) 마지막에 `총 소요 시간: N.N초`가 기록된다. 동기화가 느리게 느껴지면 이 로그로 어느 단계가 오래 걸리는지 바로 확인할 수 있다.

## 동작 방식 요약

1. `GET https://api.github.com/repos/{owner}/{repo}/commits/{branch}` 로 최신 커밋 SHA 조회.
2. 로컬에 저장된 이전 SHA와 다르면 `https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip` 다운로드
   (브라우저의 "Download ZIP" 버튼과 동일한 URL).
3. 압축 해제 후 `robocopy /E /XD .venv /R:3 /W:10` 로 `DestDir`에 반영 (`.venv`와 `DestDir`에만 있는 로컬 전용 파일은 보존).
   대상 파일이 다른 프로그램에 열려 있어 잠긴 경우 10초 간격으로 최대 3회만 재시도한 뒤 넘어간다
   (기본값인 100만 회 재시도로 사실상 무한 대기하는 것을 방지).
4. `.venv`가 없으면 `py -3.12 -m venv .venv`로 새로 생성.
5. `requirements.txt`가 있으면 해당 venv의 pip로 `pip install -r requirements.txt` 실행.
6. 최신 SHA를 상태 파일에 기록.

## 전제 조건 / 주의사항

- Public 저장소면 `config.json`의 `Token`을 빈 문자열로 두면 된다 (인증 불필요).
- Private 저장소면 `config.json`의 `Token`에 GitHub Personal Access Token을 입력해야 한다.
  API 조회(`Invoke-RestMethod`)와 zip 다운로드(`Invoke-WebRequest`) 양쪽에 자동으로
  `Authorization: token <PAT>` 헤더가 붙는다.
- 사내망 프록시 환경이면 시스템 프록시 설정을 따라가는 `Invoke-WebRequest`/`Invoke-RestMethod`
  특성상 브라우저에서 zip 다운로드가 되던 PC라면 대부분 그대로 동작한다.
- 이 폴더(`tools/github_sync/`)는 리포지토리 자동화용 스크립트이며, `utils/<util_name>/` 처리 관례
  (QA.md/processing.md)의 대상은 아니다.
