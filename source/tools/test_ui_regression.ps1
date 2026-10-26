$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'app\session.ps1')
$fixture = Join-Path $root ('.test-data\ui regression ' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
$path = Join-Path $fixture 'settings.json'
Write-WorkdayText $path '{"id":"fixture-only","enabled":true}'
Write-WorkdayText $path '{"id":"fixture-only","enabled":false,"time_step_minutes":1}'
$saved = [IO.File]::ReadAllText($path) | ConvertFrom-Json
if ($saved.enabled -ne $false -or $saved.time_step_minutes -ne 1) { throw 'Existing file replacement failed' }
if (@(Get-ChildItem $fixture -Filter '*.tmp').Count) { throw 'Temporary settings file leaked' }
$months = @(Get-WorkdayMonthLabels ([DateTime]'2027-01-01'))
if ($months[0] -ne '2027년 01월' -or $months[1] -ne '2026년 12월') { throw 'Year rollover failed' }

# Exercise the actual cross-process modal owner without showing test windows.
$childScript = @'
param([long]$OwnerHandle,[string]$Session,[string]$Result)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. $Session
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WindowProbe {
 [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr window, uint kind);
 [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr window);
}
"@
$form=New-Object Windows.Forms.Form
$form.Opacity=0; $form.ShowInTaskbar=$false
$timer=New-Object Windows.Forms.Timer
$timer.Interval=200
$timer.Add_Tick({
 $timer.Stop()
 $actual=[WindowProbe]::GetWindow($form.Handle,4).ToInt64()
 $disabled=-not [WindowProbe]::IsWindowEnabled([IntPtr]$OwnerHandle)
 [IO.File]::WriteAllText($Result,(@{owner=$actual; disabled=$disabled; topmost=$form.TopMost}|ConvertTo-Json))
 $form.Close()
})
$form.Add_Shown({$timer.Start()})
try { Show-WorkdayDialog $form $OwnerHandle } finally {$timer.Dispose();$form.Dispose()}
'@
$childPath=Join-Path $fixture 'child.ps1'
$resultPath=Join-Path $fixture 'result.json'
[IO.File]::WriteAllText($childPath,$childScript,(New-Object Text.UTF8Encoding($true)))
$parent=New-Object Windows.Forms.Form
$parent.Opacity=0; $parent.ShowInTaskbar=$false
$parent.Show()
$info=New-Object Diagnostics.ProcessStartInfo
$info.FileName="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$info.Arguments='-NoProfile -STA -ExecutionPolicy Bypass -File "'+$childPath+'" -OwnerHandle '+$parent.Handle.ToInt64()+' -Session "'+(Join-Path $root 'app\session.ps1')+'" -Result "'+$resultPath+'"'
$info.UseShellExecute=$false; $info.CreateNoWindow=$true
$process=New-Object Diagnostics.Process
$process.StartInfo=$info
try {
 [void]$process.Start()
 $watch=[Diagnostics.Stopwatch]::StartNew()
 while(-not $process.WaitForExit(50)){
  [Windows.Forms.Application]::DoEvents()
  if($watch.Elapsed.TotalSeconds -gt 30){$process.Kill();throw 'Owner test timed out'}
 }
 if($process.ExitCode -ne 0){throw 'Child dialog failed'}
 $result=[IO.File]::ReadAllText($resultPath)|ConvertFrom-Json
 if($result.owner -ne $parent.Handle.ToInt64() -or -not $result.disabled -or $result.topmost){throw 'Modal owner was not applied'}
 if(-not $parent.Enabled){throw 'Menu was not enabled after dialog close'}
} finally {$parent.Close();$parent.Dispose();$process.Dispose()}
Write-Output 'UI_REGRESSION_OK: existing settings replaced; month/year rollover; cross-process owner; menu restored; no global TopMost'
