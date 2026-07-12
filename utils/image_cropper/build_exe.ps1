<#
.SYNOPSIS
    image_cropper(main.py)를 단일 실행파일(exe)로 빌드한다.
    exe 아이콘은 icon.ico로 지정된다. 별도 리소스 번들 없이 main.py 하나로 동작한다.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File build_exe.ps1
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "가상환경을 찾을 수 없습니다: $VenvPython`n먼저 저장소 루트에서 .venv를 만들고 requirements.txt를 설치하세요."
}

$Icon = Join-Path $PSScriptRoot "icon.ico"
if (-not (Test-Path $Icon)) {
    throw "아이콘 파일을 찾을 수 없습니다: $Icon"
}

Push-Location $PSScriptRoot
try {
    & $VenvPython -m PyInstaller `
        --onefile `
        --windowed `
        --noconfirm `
        --name "image_cropper" `
        --icon "$Icon" `
        "main.py"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "빌드 완료: $PSScriptRoot\dist\image_cropper.exe"
Write-Host "이 exe 파일 하나만 옮겨서 실행하면 된다 (설치 과정 불필요)."
