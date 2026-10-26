$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$taskRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $taskRoot 'app\session.ps1')
. (Join-Path $taskRoot 'app\update.ps1')
Initialize-WorkdayWindows
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AppIdentityProbe {
 [DllImport("shell32.dll")] public static extern int GetCurrentProcessExplicitAppUserModelID(out IntPtr value);
}
'@
$identity=[IntPtr]::Zero
if([AppIdentityProbe]::GetCurrentProcessExplicitAppUserModelID([ref]$identity) -ne 0){throw 'Taskbar identity missing'}
try { if([Runtime.InteropServices.Marshal]::PtrToStringUni($identity) -ne 'Raphlow.AttendanceManager'){throw 'Wrong taskbar identity'} }
finally {[Runtime.InteropServices.Marshal]::FreeCoTaskMem($identity)}
$fixture=Join-Path $taskRoot ('.test-data\async-startup-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $fixture 'update.ps1'),"function Get-WorkdayUpdateOffer { param(`$Root); Start-Sleep -Seconds 4; [PSCustomObject]@{available=`$false;status='fixture latest';manifest=`$null} }")
$form=New-Object Windows.Forms.Form
$form.Opacity=0; $form.ShowInTaskbar=$false
$script:frames=0; $script:asyncJob=$null; $script:elapsedToStart=0
$timer=New-Object Windows.Forms.Timer
$timer.Interval=50
$timer.Add_Tick({
 $script:frames++
 if($script:asyncJob -and $script:asyncJob.pending.IsCompleted){$form.Close()}
})
$form.Add_Shown({
 $watch=[Diagnostics.Stopwatch]::StartNew()
 $script:asyncJob=Start-WorkdayUpdateJob $fixture
 $script:elapsedToStart=$watch.Elapsed.TotalMilliseconds
 $timer.Start()
})
try {
 [void]$form.ShowDialog()
 $result=@($script:asyncJob.pipeline.EndInvoke($script:asyncJob.pending))
 if($script:asyncJob.pipeline.HadErrors -or $result[-1].status -ne 'fixture latest'){throw 'Background update check failed'}
 if($script:elapsedToStart -ge 1500 -or $script:frames -lt 20){throw "UI blocked: start=$script:elapsedToStart; ticks=$script:frames"}
 Write-Output "STARTUP_ASYNC_OK: taskbar AppID set; 4-second update check kept UI responsive; begin=$([int]$script:elapsedToStart)ms; UI ticks=$script:frames"
} finally {$timer.Dispose();$form.Dispose();if($script:asyncJob){$script:asyncJob.pipeline.Dispose()}}
