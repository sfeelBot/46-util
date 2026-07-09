<#
.SYNOPSIS
    Sync-FromGitHub.ps1을 매일 08:00 / 12:00 / 18:00에 실행하도록 Windows 작업 스케줄러에 등록/제어한다.
    46util-github-sync-gui(PyQt5)에서도 이 스크립트를 호출해 스케줄 on/off, 상태 조회를 수행한다.

.PARAMETER Action
    Register    : 3개 작업을 등록(이미 있으면 갱신). 기본값. 최초 1회 수동 실행 시에도 이 동작.
    EnableAll   : 이미 등록된 3개 작업을 모두 활성화(Enable)한다.
    DisableAll  : 이미 등록된 3개 작업을 모두 비활성화(Disable)한다 (삭제하지 않음).
    Status      : 3개 작업의 존재/활성화 여부/마지막 실행 정보를 JSON으로 출력한다.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File Register-ScheduledTasks.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File Register-ScheduledTasks.ps1 -Action Status
#>

[CmdletBinding()]
param(
    [ValidateSet("Register", "EnableAll", "DisableAll", "Status")]
    [string]$Action = "Register"
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "Sync-FromGitHub.ps1"
$Times = @("08:00", "12:00", "18:00")
$TaskNames = $Times | ForEach-Object { "46util-GitHubSync-$($_.Replace(':',''))" }

switch ($Action) {
    "Register" {
        if (-not (Test-Path $ScriptPath)) {
            throw "Sync-FromGitHub.ps1을 찾을 수 없습니다: $ScriptPath"
        }

        $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

        # PC가 꺼져 있어서 실행 시각을 놓쳤으면, 켜지자마자 놓친 동기화를 바로 실행한다.
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

        for ($i = 0; $i -lt $Times.Count; $i++) {
            $t = $Times[$i]
            $taskName = $TaskNames[$i]
            $trigger = New-ScheduledTaskTrigger -Daily -At $t
            Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Settings $settings `
                -Description "46 util 저장소를 GitHub zip으로 동기화 ($t 실행, 놓치면 부팅 직후 자동 실행)" `
                -RunLevel Limited -Force | Out-Null
            Write-Host "등록됨: $taskName ($t)"
        }

        Write-Host ""
        Write-Host "확인:        Get-ScheduledTask -TaskName '46util-GitHubSync-*' | Format-Table TaskName,State"
        Write-Host "수동 테스트: Start-ScheduledTask -TaskName '46util-GitHubSync-0800'"
        Write-Host "삭제:        Get-ScheduledTask -TaskName '46util-GitHubSync-*' | Unregister-ScheduledTask -Confirm:`$false"
    }

    "EnableAll" {
        foreach ($taskName in $TaskNames) {
            try { Enable-ScheduledTask -TaskName $taskName | Out-Null }
            catch { Write-Host "활성화 실패: $taskName ($($_.Exception.Message))" }
        }
    }

    "DisableAll" {
        foreach ($taskName in $TaskNames) {
            try { Disable-ScheduledTask -TaskName $taskName | Out-Null }
            catch { Write-Host "비활성화 실패: $taskName ($($_.Exception.Message))" }
        }
    }

    "Status" {
        $result = foreach ($taskName in $TaskNames) {
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($task) {
                $info = Get-ScheduledTaskInfo -TaskName $taskName
                # 한 번도 실행된 적 없으면 Task Scheduler가 1999-11-30 등 의미 없는 날짜를 돌려준다.
                $lastRunText = $null
                if ($info.LastRunTime -and $info.LastRunTime -gt [datetime]"2001-01-01") {
                    $lastRunText = $info.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss")
                }
                [PSCustomObject]@{
                    Name        = $taskName
                    Exists      = $true
                    Enabled     = ($task.State -ne "Disabled")
                    LastRunTime = $lastRunText
                    LastResult  = $info.LastTaskResult
                }
            }
            else {
                [PSCustomObject]@{
                    Name        = $taskName
                    Exists      = $false
                    Enabled     = $false
                    LastRunTime = $null
                    LastResult  = $null
                }
            }
        }
        # GUI가 파싱할 수 있도록 이 분기에서는 JSON만 stdout에 출력한다.
        ConvertTo-Json -InputObject $result
    }
}
