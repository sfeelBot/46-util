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
# GUI(QProcess)/콘솔로 리다이렉트된 stdout이 UTF-8 바이트로 나가도록 강제한다.
# (이게 없으면 Write-Host 출력이 시스템 기본 코드페이지(CP949 등)로 나가서, UTF-8로 읽는 쪽에서 한글이 깨진다.)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---- 설정: 스크립트와 같은 폴더의 config.json에서 읽는다 (없으면 기본값으로 생성) ----
$ConfigPath = Join-Path $PSScriptRoot "config.json"

$defaultConfig = [ordered]@{
    Owner     = "sfeelBot"
    Repo      = "46-util"
    Branch    = "main"
    DestDir   = "C:\Work\46 util"                       # 실제로 반영될 프로젝트 경로
    StateDir  = (Join-Path $PSScriptRoot "state")        # SHA 기록/로그 저장 위치 (DestDir 밖! mirror 시 지워지지 않게)
    PythonExe = "py"                                     # py launcher (py -3.12 -m venv ...)
    Token     = ""                                       # Private 저장소일 때만 GitHub Personal Access Token 입력
}

$config = [ordered]@{}
foreach ($key in $defaultConfig.Keys) { $config[$key] = $defaultConfig[$key] }

if (Test-Path $ConfigPath) {
    $loaded = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    foreach ($prop in $loaded.PSObject.Properties) { $config[$prop.Name] = $prop.Value }
}
else {
    ($config | ConvertTo-Json) | Set-Content -Path $ConfigPath -Encoding UTF8
}

$Owner     = $config.Owner
$Repo      = $config.Repo
$Branch    = $config.Branch
$DestDir   = $config.DestDir
$StateDir  = $config.StateDir
$PythonExe = $config.PythonExe
$Token     = $config.Token
# --------------------------------------------------------------------

$StateFile = Join-Path $StateDir "last_sha.txt"
$LogFile   = Join-Path $StateDir "sync.log"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

# Add-Content는 인코딩을 지정하지 않으면 시스템 기본 코드페이지(CP949 등)로 저장되어,
# 이 로그를 UTF-8로 읽는 GUI에서 한글이 깨진다. BOM 없는 UTF-8로 명시적으로 append한다.
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    [System.IO.File]::AppendAllText($LogFile, $line + "`r`n", $Utf8NoBom)
}

$tempDir = $null
$stage = "초기화"
try {
    Write-Log "=== Sync 시작 ==="

    $stage = "GitHub API 조회"
    $headers = @{ "User-Agent" = "46util-sync-script" }
    if ($Token) {
        $headers["Authorization"] = "token $Token"
    }
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

    $stage = "ZIP 다운로드"
    $zipUrl = "https://github.com/$Owner/$Repo/archive/refs/heads/$Branch.zip"
    Invoke-WebRequest -Uri $zipUrl -Headers $headers -OutFile $zipPath -UseBasicParsing
    Write-Log "ZIP 다운로드 완료: $zipUrl"

    $stage = "ZIP 압축 해제"
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

    $stage = "robocopy 반영"
    Write-Log "robocopy로 반영 중 (.venv 폴더 및 로컬 전용 파일은 보존): $($innerDir.FullName) -> $DestDir"
    $robocopyArgs = @(
        $innerDir.FullName,
        $DestDir,
        # /MIR(미러)는 대상에만 있고 원본에는 없는 파일/폴더를 전부 삭제(purge)한다.
        # DestDir에 사용자가 로컬로만 추가한 파일이 있을 수 있으므로, 삭제 없이 하위 폴더 포함 복사만
        # 하는 /E를 사용한다 (대신 GitHub에서 삭제된 파일이 DestDir에 남아있게 되는 트레이드오프가 있음).
        "/E",
        "/XD", ".venv",
        "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
    )
    # 주의: Start-Process -ArgumentList <array>는 배열 원소에 공백(예: "C:\Work\46 util")이 있으면
    # 자동으로 따옴표 처리를 해주지 않아 robocopy가 엉뚱한 인자를 받는다 (실사용 환경에서 ExitCode=16
    # 재현 확인됨). 네이티브 호출 연산자(&)는 배열 원소를 각각 올바르게 인용해 전달한다.
    & robocopy.exe $robocopyArgs
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy 실패 (ExitCode=$rc)"
    }
    Write-Log "robocopy 완료 (ExitCode=$rc)"

    $stage = ".venv 생성"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Log ".venv 없음 -> 새로 생성 (py -3.12)"
        & $PythonExe -3.12 -m venv $venvPath
    }

    $stage = "pip install"
    $reqFile = Join-Path $DestDir "requirements.txt"
    if (Test-Path $reqFile) {
        Write-Log "pip install -r requirements.txt 실행"
        & $venvPython -m pip install -r $reqFile
    }

    Set-Content -Path $StateFile -Value $latestSha
    Write-Log "동기화 완료. 최신 커밋 $latestSha 로 갱신됨."
}
catch {
    # 이 PC에서 직접 확인/조치가 필요한 경우를 위한 단계별 힌트.
    # StateDir/sync.log에 그대로 남으므로, 다른 PC의 로그를 나중에 봐도 무엇을 확인해야 하는지 알 수 있다.
    $hint = switch ($stage) {
        "GitHub API 조회" { "이 PC의 인터넷/프록시/방화벽 설정을 확인하세요. Private 저장소라면 config.json의 Token이 유효한지도 확인하세요." }
        "ZIP 다운로드"    { "이 PC의 인터넷/프록시 설정을 확인하세요. (GitHub API 조회는 성공했으므로 다운로드 단계에서만 막혔을 가능성이 있습니다.)" }
        "ZIP 압축 해제"   { "다운로드된 ZIP이 손상되었을 수 있습니다. %TEMP% 여유 공간을 확인하세요." }
        "robocopy 반영"  {
            if ($rc -eq 16) { "심각한 오류(경로 문제 또는 접근 권한 부족). 이 PC에서 DestDir 경로($DestDir)가 실제로 쓰기 가능한지, 상위 폴더가 존재하는지 확인하세요." }
            else { "일부 파일 복사에 실패했습니다(ExitCode=$rc). DestDir($DestDir) 내 파일이 다른 프로그램에서 열려 있지 않은지, 디스크 여유 공간을 이 PC에서 확인하세요." }
        }
        ".venv 생성"      { "이 PC에 Python 3.12가 설치되어 있는지 확인하세요 (`"py -3.12 -V`" 실행)." }
        "pip install"    { "이 PC의 pip 프록시/사내망 미러 설정을 확인하세요." }
        default           { $null }
    }
    Write-Log "오류 발생 [$stage 단계]: $($_.Exception.Message)"
    if ($hint) {
        Write-Log "[조치 필요 - 이 PC에서 확인] $hint"
    }
    throw
}
finally {
    if ($tempDir -and (Test-Path $tempDir)) {
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
    Write-Log "=== Sync 종료 ==="
}
