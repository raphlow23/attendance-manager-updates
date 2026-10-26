$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$fixture=Join-Path $taskRoot ('.test-data\task-controls-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'dist') -Force|Out-Null
Copy-Item (Join-Path $taskRoot 'app\session.ps1') $fixture
. (Join-Path $fixture 'session.ps1')
. (Join-Path $taskRoot 'app\task-control.ps1')
$settings=Join-Path $fixture 'dist\자동출근설정.json'
[IO.File]::WriteAllText($settings,'{"id":"fixture","pw":"fixture","enabled":true}')
$script:Tasks=@('자동출근','자동퇴근','자동출퇴근로그인','자동출퇴근점검')|ForEach-Object{[PSCustomObject]@{TaskName=$_;State='Ready';Actions=@([PSCustomObject]@{Execute='powershell.exe';Arguments=('-File "'+(Join-Path $fixture 'watchdog.ps1')+'"')})}}
$script:Launches=0;$script:FailEnable=$false
function Get-ScheduledTask {param([string[]]$TaskName,$ErrorAction);$script:Tasks|Where-Object{$_.TaskName -in $TaskName}}
function Stop-ScheduledTask {param($TaskName,$ErrorAction)}
function Disable-ScheduledTask {param($TaskName);($script:Tasks|Where-Object TaskName -eq $TaskName).State='Disabled'}
function Enable-ScheduledTask {param($TaskName);if($script:FailEnable){throw 'fixture enable failure'};($script:Tasks|Where-Object TaskName -eq $TaskName).State='Ready'}
function Start-Process {param($FilePath,$WindowStyle);$script:Launches++}
function New-ScheduledTaskAction {param($Execute,$Argument);[PSCustomObject]@{Execute=$Execute;Arguments=$Argument}}
function Set-ScheduledTask {param($TaskName,$Action,$ErrorAction);($script:Tasks|Where-Object TaskName -eq $TaskName).Actions=@($Action)}
[void](Invoke-WorkdayTaskAction $fixture 'pause')
if(@($script:Tasks|Where-Object State -ne 'Disabled').Count -or -not(Test-Path (Join-Path $fixture 'dist\automation.stop'))){throw 'Pause did not disable both mechanisms'}
Repair-WorkdayWatchdogTask $fixture
$watchdog=$script:Tasks|Where-Object TaskName -eq '자동출퇴근점검'
if($watchdog.State -ne 'Disabled' -or $watchdog.Actions[0].Arguments -ne '--watchdog'){throw 'Watchdog migration changed paused state'}
$script:FailEnable=$true
try{[void](Invoke-WorkdayTaskAction $fixture 'resume');throw 'Failed resume was accepted'}catch{if($_.Exception.Message -eq 'Failed resume was accepted'){throw}}
if($script:Launches -or -not(Test-Path (Join-Path $fixture 'dist\automation.stop'))){throw 'Failed resume started worker'}
$script:FailEnable=$false
[void](Invoke-WorkdayTaskAction $fixture 'resume')
if(@($script:Tasks|Where-Object State -ne 'Ready').Count -or (Test-Path (Join-Path $fixture 'dist\automation.stop')) -or $script:Launches -ne 1){throw 'Resume did not enable both mechanisms exactly once'}
Write-Output 'TASK_CONTROLS_OK: pause/resume unified; failed resume stays stopped; native watchdog migration preserves disabled state (scheduler mocked)'
