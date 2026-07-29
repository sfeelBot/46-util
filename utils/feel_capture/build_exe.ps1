<#
.SYNOPSIS
    필캡쳐(feel_capture/main.py)를 단일 실행파일(exe)로 빌드한다.
    assets/icon.ico를 exe 아이콘 및 트레이 아이콘 리소스로 함께 번들한다.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File build_exe.ps1
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "가상환경을 찾을 수 없습니다: $VenvPython`n먼저 저장소 루트에서 .venv를 만들고 requirements.txt를 설치하세요."
}

$Icon = Join-Path $PSScriptRoot "assets\icon.ico"
if (-not (Test-Path $Icon)) {
    throw "아이콘을 찾을 수 없습니다: $Icon`n먼저 assets\generate_icons.py 를 실행해 아이콘을 생성하세요."
}

Push-Location $PSScriptRoot
try {
    & $VenvPython -m PyInstaller `
        --onefile `
        --windowed `
        --noconfirm `
        --name "FeelCapture" `
        --icon "$Icon" `
        --add-data "$Icon;assets" `
        "main.py"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "빌드 완료: $PSScriptRoot\dist\FeelCapture.exe"
Write-Host "exe 파일 하나만 옮겨서 실행하면 된다 (설치 과정 불필요, 트레이 상주)."
