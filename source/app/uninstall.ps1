[CmdletBinding()]
param([switch]$Silent, [switch]$SelfTest)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
. (Join-Path $PSScriptRoot 'install-integration.ps1')
if ($SelfTest) {
    Get-AttendanceInstallPlan (Join-Path $env:LOCALAPPDATA 'AutoAttendance') | ConvertTo-Json -Depth 4
    Write-Output 'UNINSTALL_PLAN_OK: no registry, process, task or file changes'
    exit 0
}
try {
    Assert-AttendanceInstallRoot $PSScriptRoot
    $plan = Get-AttendanceInstallPlan $PSScriptRoot
    if (-not $Silent) {
        $answer = [Windows.Forms.MessageBox]::Show("출근정리를 제거할까요?`n`n자동 실행/감시 프로세스, 예약 작업 4개, 바로가기, 계정과 실행 기록을 모두 삭제합니다.", '출근정리 제거', 'YesNo', 'Question')
        if ($answer -ne 'Yes') { exit 0 }
    }
    $data = Join-Path $plan.Root 'dist'
    New-Item -ItemType Directory -Path $data -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $data 'automation.stop'), 'user requested uninstall')
    foreach ($name in $plan.Tasks) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            if ($task.State -eq 'Running') { Stop-ScheduledTask -TaskName $name -ErrorAction Stop }
            Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop
        }
    }
    # Match our installed executables and scripts, then include their child tree.
    # Exclude this uninstaller even when its parent is the installed 제거.exe.
    $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $owned = New-Object 'Collections.Generic.HashSet[int]'
    $prefix = $plan.Root + '\'
    foreach ($process in $all) {
        if ($process.ProcessId -eq $PID) { continue }
        $inside = $process.ExecutablePath -and $process.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
        $script = $process.Name -in @('powershell.exe','pwsh.exe') -and $process.CommandLine -and $process.CommandLine.IndexOf($prefix, [StringComparison]::OrdinalIgnoreCase) -ge 0
        if ($inside -or $script) { [void]$owned.Add([int]$process.ProcessId) }
    }
    do {
        $added = $false
        foreach ($process in $all) {
            if ($process.ProcessId -ne $PID -and $owned.Contains([int]$process.ParentProcessId) -and $owned.Add([int]$process.ProcessId)) { $added = $true }
        }
    } while ($added)
    foreach ($processId in $owned) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) { Stop-Process -Id $processId -Force -ErrorAction Stop }
    }
    $cleanup = Join-Path $env:TEMP ('AttendanceManager-uninstall-' + [Guid]::NewGuid().ToString('N') + '.ps1')
    $escapedRoot = $plan.Root.Replace("'", "''")
    $escapedRegistry = $plan.RegistryKey.Replace("'", "''")
    $cleanupText = @'
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$root = '__ROOT__'
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'AutoAttendance')).TrimEnd('\')
if (-not [IO.Path]::GetFullPath($root).TrimEnd('\').Equals($expected, [StringComparison]::OrdinalIgnoreCase)) { throw '제거 경로 확인 실패' }
try {
    for ($i=0; $i -lt 60; $i++) {
        if (-not (Get-Process -Id __PARENT__ -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    foreach ($name in @('출근정리.lnk','근태매니저.lnk','Workday 출퇴근관리.lnk')) {
        $path = Join-Path ([Environment]::GetFolderPath('Desktop')) $name
        if (Test-Path -LiteralPath $path) {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($path)
            if ($shortcut.TargetPath.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $path -Force }
        }
    }
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        try {
            if (Test-Path -LiteralPath $root) {
                if ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '설치 폴더 링크 감지' }
                Remove-Item -LiteralPath $root -Recurse -Force
            }
            break
        } catch { if ($attempt -eq 19) { throw }; Start-Sleep -Milliseconds 500 }
    }
    if (Test-Path -LiteralPath '__REGISTRY__') { Remove-Item -LiteralPath '__REGISTRY__' -Force }
    if (-not __SILENT__) { [void][Windows.Forms.MessageBox]::Show('출근정리와 자동 실행/예약 작업을 제거했습니다.', '제거 완료', 'OK', 'Information') }
} catch { [void][Windows.Forms.MessageBox]::Show(('제거를 완료하지 못했습니다. ' + $_.Exception.Message), '제거 확인', 'OK', 'Warning') }
finally { Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue }
'@
    $silentValue = '$false'
    if ($Silent) { $silentValue = '$true' }
    $cleanupText = $cleanupText.Replace('__ROOT__', $escapedRoot).Replace('__REGISTRY__', $escapedRegistry).Replace('__PARENT__', [string]$PID).Replace('__SILENT__', $silentValue)
    [IO.File]::WriteAllText($cleanup, $cleanupText, (New-Object Text.UTF8Encoding($true)))
    Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @('-NoProfile','-STA','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',"`"$cleanup`"") -WindowStyle Hidden
} catch {
    [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '출근정리 제거 실패', 'OK', 'Error')
    exit 1
}
