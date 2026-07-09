# github_sync

git 접근이 막힌 사내망 PC에서, GitHub 저장소(`sfeelBot/46-util`)의 새 push 여부를
지정된 시각(08:00 / 12:00 / 18:00)에 자동으로 확인하고, 변경이 있으면
"Download ZIP"과 동일한 방식(HTTPS zip 다운로드)으로 받아 로컬에 반영하는 스크립트.

- git 명령/프로토콜 불필요 (HTTPS로 `github.com`, `api.github.com`, `codeload.github.com` 접속만 되면 동작)
- 기존 `.venv` 폴더는 항상 보존, 반영 후 `requirements.txt`로 `pip install` 자동 실행
- 필요 시 `.venv`를 완전히 새로 만드는 옵션도 포함

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `Sync-FromGitHub.ps1` | 실제 동기화 로직 (커밋 확인 → zip 다운로드 → 반영 → pip install) |
| `Register-ScheduledTasks.ps1` | 위 스크립트를 08:00/12:00/18:00 매일 실행하도록 작업 스케줄러에 등록 (최초 1회) |

## 사전 준비 (동기화 대상 PC에서)

1. 이 `tools/github_sync/` 폴더를 대상 PC의 원하는 위치로 복사한다 (예: `C:\Work\46util-sync-scripts`).
2. `Sync-FromGitHub.ps1` 상단의 설정값을 환경에 맞게 수정한다.

   ```powershell
   $Owner      = "sfeelBot"
   $Repo       = "46-util"
   $Branch     = "main"
   $DestDir    = "C:\Work\46 util"              # 실제 프로젝트가 위치할 경로
   $StateDir   = "C:\Work\46util-sync-state"    # 마지막 커밋 SHA / 로그 저장 (DestDir 밖에 둘 것)
   $PythonExe  = "py"                            # py launcher 사용 (py -3.12 ...)
   ```

   > `StateDir`는 반드시 `DestDir` 바깥에 둔다. 동기화 시 `DestDir`는 robocopy `/MIR`로
   > 저장소 내용과 완전히 동일하게 미러링되므로, 안에 두면 상태 파일이 지워진다.

3. Python 3.12가 `py -3.12`로 실행 가능한지 확인한다 (`py -3.12 --version`).

## 수동 테스트

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1
```

- 최초 실행: `DestDir`가 없으면 새로 만들고 전체를 받아온다. `.venv`가 없으므로 새로 생성 후 `pip install -r requirements.txt` 실행.
- 이후 실행: GitHub의 최신 커밋 SHA를 `StateDir\last_sha.txt`와 비교해서, 같으면 아무것도 하지 않고 종료.
- 강제로 다시 받고 싶을 때: `-Force`
- `.venv`를 지우고 새로 만들고 싶을 때: `-RecreateVenv`

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1 -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\Sync-FromGitHub.ps1 -RecreateVenv
```

로그는 `StateDir\sync.log`에 누적 기록된다.

## 스케줄 등록 (최초 1회)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Register-ScheduledTasks.ps1
```

`46util-GitHubSync-0800`, `-1200`, `-1800` 세 개의 작업이 등록되며, 매일 해당 시각에
`Sync-FromGitHub.ps1`이 인자 없이 실행된다 (변경 있을 때만 반영, `.venv` 보존).

**한 번 등록하면 그걸로 끝이다.** Windows 작업 스케줄러에 등록된 작업은 PC를 껐다 켜도,
재부팅해도 그대로 남아있고 매일 자동으로 실행된다. `Register-ScheduledTasks.ps1`을
PC를 켤 때마다 다시 실행할 필요는 없다.

또한 `StartWhenAvailable` 옵션을 켜뒀기 때문에, 트리거 시각(08:00/12:00/18:00)에
PC가 꺼져 있었다면 그 실행은 건너뛰되, 다음에 PC를 켜는 즉시 놓친 동기화를 자동으로
한 번 실행한다.

확인/삭제:

```powershell
Get-ScheduledTask -TaskName "46util-GitHubSync-*" | Format-Table TaskName,State
Start-ScheduledTask -TaskName "46util-GitHubSync-0800"   # 수동 즉시 실행 테스트
Get-ScheduledTask -TaskName "46util-GitHubSync-*" | Unregister-ScheduledTask -Confirm:$false  # 전체 삭제
```

## 동작 방식 요약

1. `GET https://api.github.com/repos/{owner}/{repo}/commits/{branch}` 로 최신 커밋 SHA 조회.
2. 로컬에 저장된 이전 SHA와 다르면 `https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip` 다운로드
   (브라우저의 "Download ZIP" 버튼과 동일한 URL).
3. 압축 해제 후 `robocopy /MIR /XD .venv` 로 `DestDir`에 반영 (삭제된 파일도 함께 반영되고, `.venv`만 예외).
4. `.venv`가 없으면 `py -3.12 -m venv .venv`로 새로 생성.
5. `requirements.txt`가 있으면 해당 venv의 pip로 `pip install -r requirements.txt` 실행.
6. 최신 SHA를 상태 파일에 기록.

## 전제 조건 / 주의사항

- Public 저장소 기준으로 작성됨 (인증 토큰 불필요). 저장소가 Private으로 바뀌면
  `Invoke-RestMethod`/`Invoke-WebRequest`에 `Authorization = "token <PAT>"` 헤더 추가가 필요하다.
- 사내망 프록시 환경이면 시스템 프록시 설정을 따라가는 `Invoke-WebRequest`/`Invoke-RestMethod`
  특성상 브라우저에서 zip 다운로드가 되던 PC라면 대부분 그대로 동작한다.
- 이 폴더(`tools/github_sync/`)는 리포지토리 자동화용 스크립트이며, `utils/<util_name>/` 처리 관례
  (QA.md/processing.md)의 대상은 아니다.
