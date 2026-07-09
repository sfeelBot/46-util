<#
.SYNOPSIS
    Sync-FromGitHub.ps1을 매일 08:00 / 12:00 / 18:00에 실행하도록
    Windows 작업 스케줄러에 등록한다. 최초 1회만 실행하면 된다.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Register-ScheduledTasks.ps1
#>

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "Sync-FromGitHub.ps1"
if (-not (Test-Path $ScriptPath)) {
    throw "Sync-FromGitHub.ps1을 찾을 수 없습니다: $ScriptPath"
}

$Times = @("08:00", "12:00", "18:00")

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# PC가 꺼져 있어서 실행 시각을 놓쳤으면, 켜지자마자 놓친 동기화를 바로 실행한다.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

foreach ($t in $Times) {
    $taskName = "46util-GitHubSync-$($t.Replace(':',''))"
    $trigger = New-ScheduledTaskTrigger -Daily -At $t
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Description "46 util 저장소를 GitHub zip으로 동기화 ($t 실행, 놓치면 부팅 직후 자동 실행)" `
        -RunLevel Limited -Force | Out-Null
    Write-Host "등록됨: $taskName ($t)"
}

Write-Host ""
Write-Host "확인:        Get-ScheduledTask -TaskName '46util-GitHubSync-*' | Format-Table TaskName,State"
Write-Host "수동 테스트: Start-ScheduledTask -TaskName '46util-GitHubSync-0800'"
Write-Host "삭제:        Get-ScheduledTask -TaskName '46util-GitHubSync-*' | Unregister-ScheduledTask -Confirm:`$false"
