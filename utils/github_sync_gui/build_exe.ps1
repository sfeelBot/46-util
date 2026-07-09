<#
.SYNOPSIS
    github_sync_gui(main.py)를 단일 실행파일(exe)로 빌드한다.
    tools/github_sync/*.ps1 스크립트와 assets/*.ico 아이콘을 리소스로 함께 번들하여,
    exe 하나만 옮겨도 실행 시 %LOCALAPPDATA%\46util-sync\ 에 스크립트를 풀어놓고
    정상 동작하도록 한다. exe 자체의 아이콘도 assets/icon_on.ico로 지정된다.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File build_exe.ps1
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "가상환경을 찾을 수 없습니다: $VenvPython`n먼저 저장소 루트에서 .venv를 만들고 requirements.txt를 설치하세요."
}

$SyncScript = Join-Path $RepoRoot "tools\github_sync\Sync-FromGitHub.ps1"
$ManageScript = Join-Path $RepoRoot "tools\github_sync\Register-ScheduledTasks.ps1"
$IconOn = Join-Path $PSScriptRoot "assets\icon_on.ico"
$IconOff = Join-Path $PSScriptRoot "assets\icon_off.ico"

foreach ($f in @($SyncScript, $ManageScript, $IconOn, $IconOff)) {
    if (-not (Test-Path $f)) {
        throw "필요한 파일을 찾을 수 없습니다: $f"
    }
}

Push-Location $PSScriptRoot
try {
    & $VenvPython -m PyInstaller `
        --onefile `
        --windowed `
        --noconfirm `
        --name "46util-sync-gui" `
        --icon "$IconOn" `
        --add-data "$SyncScript;resources" `
        --add-data "$ManageScript;resources" `
        --add-data "$IconOn;resources" `
        --add-data "$IconOff;resources" `
        "main.py"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "빌드 완료: $PSScriptRoot\dist\46util-sync-gui.exe"
Write-Host "이 exe 파일 하나만 옮겨서 실행하면 된다 (설치 과정 불필요)."
