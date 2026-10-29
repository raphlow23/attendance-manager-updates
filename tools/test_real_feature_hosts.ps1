$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$taskRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $taskRoot 'app\session.ps1')
. (Join-Path $taskRoot 'app\ui-host.ps1')
Initialize-WorkdayWindows
$fixture=Join-Path $taskRoot ('.test-data\real-feature-hosts-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'dist') -Force|Out-Null
foreach($name in @('session.ps1','task-control.ps1','theme.ps1','attendance.ico','overtime-drafts.ps1')){Copy-Item (Join-Path $taskRoot ('app\'+$name)) $fixture}
$prefix=@'
$form.Opacity=0;$form.ShowInTaskbar=$false
$fixtureTimer=New-Object Windows.Forms.Timer
$fixtureTimer.Interval=500
$fixtureTimer.Add_Tick({$fixtureTimer.Stop();$form.Close()})
$form.Add_Shown({[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'shown.json'),(@{pid=$PID;shown=[DateTime]::UtcNow.Ticks}|ConvertTo-Json));$fixtureTimer.Start()})
'@
foreach($name in @('control.ps1','corrections.ps1','overtime.ps1','trips.ps1','status.ps1','보안안내.ps1')){
 $source=[IO.File]::ReadAllText((Join-Path $taskRoot ('app\'+$name)))
 $source=$source.Replace("Enter-WorkdayUi '",("Enter-WorkdayUi 'fixture-"+[IO.Path]::GetFileName($fixture)+'-'))
 $source=[regex]::Replace($source,'(?m)^(?=try \{ Show-WorkdayDialog|Show-WorkdayDialog)',($prefix+"`r`n"))
 [IO.File]::WriteAllText((Join-Path $fixture $name),$source,(New-Object Text.UTF8Encoding($true)))
}
# The launcher loads the shared theme before starting its STA feature hosts.
# Match that order so parallel warm-up never races Add-Type initialization.
. (Join-Path $fixture 'theme.ps1')
$hosts=New-WorkdayFeatureHosts $fixture
try{
 $metrics=@()
 foreach($name in @('control.ps1','control.ps1','corrections.ps1','overtime.ps1','trips.ps1','status.ps1','보안안내.ps1')){
  Remove-Item (Join-Path $fixture 'shown.json') -ErrorAction SilentlyContinue
  $start=[DateTime]::UtcNow
  Open-WorkdayFeatureHost $hosts $name 0
  do{
   $errors=@(Update-WorkdayFeatureHosts $hosts);if($errors.Count){throw ($errors -join '; ')}
   if([DateTime]::UtcNow -gt $start.AddSeconds(25)){throw "Timed out: $name"}
   Start-Sleep -Milliseconds 10
  }while(Test-WorkdayFeatureBusy $hosts)
  $shown=Get-Content (Join-Path $fixture 'shown.json') -Raw|ConvertFrom-Json
  if($shown.pid -ne $PID){throw 'Unexpected process'}
  $metrics+=($name+':'+[int]([TimeSpan]::FromTicks($shown.shown-$start.Ticks).TotalMilliseconds)+'ms')
 }
 Write-Output ('REAL_FEATURE_HOSTS_OK: actual forms; no account or website action; '+($metrics -join ', '))
}catch{
 Write-Output ('REAL_FEATURE_HOSTS_FAILED: '+($_ | Out-String))
 throw
}finally{Close-WorkdayFeatureHosts $hosts}
