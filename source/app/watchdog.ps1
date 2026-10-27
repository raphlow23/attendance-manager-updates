[CmdletBinding()]
param([switch]$SelfTest)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$dataRoot = Join-Path $PSScriptRoot 'dist'
$settingsPath = Join-Path $dataRoot '자동출근설정.json'
if ($SelfTest) { Write-Output 'WATCHDOG_OK: no tasks inspected or notifications sent'; exit 0 }
if (-not (Test-Path -LiteralPath $settingsPath)) { exit 0 }
$settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($settings.PSObject.Properties['enabled'] -and -not $settings.enabled) { exit 0 }
if ((Test-Path -LiteralPath (Join-Path $dataRoot 'automation.stop')) -or (Test-Path -LiteralPath (Join-Path $dataRoot 'update.pause'))) { exit 0 }
Start-Process -FilePath (Join-Path $PSScriptRoot 'WorkdayGuard.exe') -WindowStyle Hidden
$noticePath = Join-Path $dataRoot '알림상태.json'
$notices = @{}
if (Test-Path -LiteralPath $noticePath) {
    $stored = Get-Content -LiteralPath $noticePath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($p in $stored.PSObject.Properties) { $notices[$p.Name] = $p.Value }
}
$today = (Get-Date).ToString('yyyy-MM-dd')
$failures = @()
foreach ($name in @('자동출근','자동퇴근','자동출퇴근로그인')) {
    $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
    if ($info -and $info.LastRunTime.Date -eq (Get-Date).Date -and $info.LastTaskResult -notin @(0,267009,267011) -and (Get-Date) -gt $info.LastRunTime.AddMinutes(2)) { $failures += "$name 작업 실패 (코드 $($info.LastTaskResult))" }
}
$statePath = Join-Path $dataRoot '자동출퇴근상태.json'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $runs = $state.runs.($today)
    foreach ($mode in @('checkin','checkout')) {
        $run = $runs.$mode
        if ($run -and $run.target -and $run.status -ne 'success' -and (Get-Date) -gt ([DateTime]::Parse($run.target)).AddMinutes(10)) { $failures += "$mode 예약 처리 확인 필요" }
    }
}
if ($failures.Count -eq 0 -or $notices.ContainsKey($today)) { exit 0 }
$notices[$today] = ($failures -join ' / ')
[IO.File]::WriteAllText($noticePath, ($notices | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
$icon = New-Object Windows.Forms.NotifyIcon
$icon.Icon = [Drawing.SystemIcons]::Warning
$icon.Visible = $true
$icon.BalloonTipTitle = '근태매니저 — 자동 처리 확인 필요'
$icon.BalloonTipText = (($failures -join ', ') + '. 프로그램과 실행 로그를 확인해 주세요.')
$icon.BalloonTipIcon = 'Warning'
$icon.ShowBalloonTip(12000)
try { for ($i=0; $i -lt 60; $i++) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 250 } } finally { $icon.Visible = $false; $icon.Dispose() }
