<#
.SYNOPSIS
    사내망 등 git 접근이 막힌 환경에서 GitHub 저장소를 "Download ZIP"과 동일한 방식(HTTPS zip 다운로드)으로
    로컬에 동기화한다. .venv 폴더는 보존하고, 반영 후 requirements.txt로 pip install을 자동 실행한다.

.PARAMETER Force
    최신 커밋 SHA가 이전과 같아도 강제로 다시 다운로드/반영한다.

.PARAMETER RecreateVenv
    기존 .venv를 삭제하고 새로 생성한 뒤 반영한다 (평소에는 .venv를 보존만 함).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Sync-FromGitHub.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File Sync-FromGitHub.ps1 -RecreateVenv
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---- 환경에 맞게 수정 ----
$Owner      = "sfeelBot"
$Repo       = "46-util"
$Branch     = "main"
$DestDir    = "C:\Work\46 util"              # 실제로 반영될 프로젝트 경로 (필요시 수정)
$StateDir   = "C:\Work\46util-sync-state"    # SHA 기록/로그 저장 위치 (DestDir 밖! mirror 시 지워지지 않게)
$PythonExe  = "py"                           # py launcher (py -3.12 -m venv ...)
# --------------------------

$StateFile = Join-Path $StateDir "last_sha.txt"
$LogFile   = Join-Path $StateDir "sync.log"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

$tempDir = $null
try {
    Write-Log "=== Sync 시작 ==="

    $headers = @{ "User-Agent" = "46util-sync-script" }
    $apiUrl = "https://api.github.com/repos/$Owner/$Repo/commits/$Branch"
    $commit = Invoke-RestMethod -Uri $apiUrl -Headers $headers -UseBasicParsing
    $latestSha = $commit.sha
    Write-Log "GitHub 최신 커밋: $latestSha"

    $lastSha = $null
    if (Test-Path $StateFile) {
        $lastSha = (Get-Content $StateFile -Raw).Trim()
    }

    if (-not $Force -and -not $RecreateVenv -and $lastSha -eq $latestSha) {
        Write-Log "변경 없음 (이미 최신 $latestSha). 종료."
        return
    }

    Write-Log "변경 감지/강제 실행 (이전: $lastSha). ZIP 다운로드 시작."

    $tempDir = Join-Path $env:TEMP ("46util-sync-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    $zipPath = Join-Path $tempDir "repo.zip"
    $extractDir = Join-Path $tempDir "extract"

    $zipUrl = "https://github.com/$Owner/$Repo/archive/refs/heads/$Branch.zip"
    Invoke-WebRequest -Uri $zipUrl -Headers $headers -OutFile $zipPath -UseBasicParsing
    Write-Log "ZIP 다운로드 완료: $zipUrl"

    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $innerDir = Get-ChildItem -Path $extractDir -Directory | Select-Object -First 1
    if (-not $innerDir) {
        throw "ZIP 압축 해제 결과 폴더를 찾을 수 없습니다."
    }

    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

    $venvPath = Join-Path $DestDir ".venv"
    if ($RecreateVenv -and (Test-Path $venvPath)) {
        Write-Log ".venv 삭제 후 재생성 모드"
        Remove-Item -Recurse -Force $venvPath
    }

    Write-Log "robocopy로 반영 중 (.venv 폴더는 보존)"
    $robocopyArgs = @(
        $innerDir.FullName,
        $DestDir,
        "/MIR",
        "/XD", ".venv",
        "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
    )
    $rc = Start-Process -FilePath "robocopy.exe" -ArgumentList $robocopyArgs -NoNewWindow -Wait -PassThru
    if ($rc.ExitCode -ge 8) {
        throw "robocopy 실패 (ExitCode=$($rc.ExitCode))"
    }
    Write-Log "robocopy 완료 (ExitCode=$($rc.ExitCode))"

    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Log ".venv 없음 -> 새로 생성 (py -3.12)"
        & $PythonExe -3.12 -m venv $venvPath
    }

    $reqFile = Join-Path $DestDir "requirements.txt"
    if (Test-Path $reqFile) {
        Write-Log "pip install -r requirements.txt 실행"
        & $venvPython -m pip install -r $reqFile
    }

    Set-Content -Path $StateFile -Value $latestSha
    Write-Log "동기화 완료. 최신 커밋 $latestSha 로 갱신됨."
}
catch {
    Write-Log "오류 발생: $($_.Exception.Message)"
    throw
}
finally {
    if ($tempDir -and (Test-Path $tempDir)) {
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
    Write-Log "=== Sync 종료 ==="
}
