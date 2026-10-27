$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$taskRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $taskRoot 'app\session.ps1')
. (Join-Path $taskRoot 'app\ui-host.ps1')
Initialize-WorkdayWindows
$fixture=Join-Path $taskRoot ('.test-data\feature-hosts-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force|Out-Null
Copy-Item (Join-Path $taskRoot 'app\session.ps1') $fixture
$source=@'
param([long]$OwnerHandle,[switch]$SelfTest)
if($SelfTest){return}
Get-Item -LiteralPath (Join-Path $PSScriptRoot '__fixture_missing__') -ErrorAction SilentlyContinue
$f=New-Object Windows.Forms.Form
$f.Opacity=0;$f.ShowInTaskbar=$false
$t=New-Object Windows.Forms.Timer
$t.Interval=180
$t.Add_Tick({$f.Close()})
$f.Add_Shown({[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'shown.json'),(@{pid=$PID;thread=[Threading.Thread]::CurrentThread.ManagedThreadId;shown=[DateTime]::UtcNow.Ticks}|ConvertTo-Json));$t.Start()})
try{[void]$f.ShowDialog()}finally{$t.Dispose();$f.Dispose()}
return
'@
foreach($name in @('control.ps1','corrections.ps1','overtime.ps1','trips.ps1','status.ps1','보안안내.ps1')){[IO.File]::WriteAllText((Join-Path $fixture $name),$source)}
$hosts=New-WorkdayFeatureHosts $fixture
try {
 $deadline=[DateTime]::UtcNow.AddSeconds(15)
 while(@($hosts.Values|Where-Object{$_.phase -eq 'warming'}).Count){
  $errors=@(Update-WorkdayFeatureHosts $hosts);if($errors.Count){throw ($errors -join '; ')}
  if([DateTime]::UtcNow -gt $deadline){throw 'Warm-up timed out'}
  Start-Sleep -Milliseconds 10
 }
 $times=@();$threads=@()
 foreach($name in @('control.ps1','control.ps1','corrections.ps1','overtime.ps1','trips.ps1','status.ps1','보안안내.ps1')){
  Remove-Item (Join-Path $fixture 'shown.json') -ErrorAction SilentlyContinue
  $start=[DateTime]::UtcNow
  Open-WorkdayFeatureHost $hosts $name 0
  do {
   $errors=@(Update-WorkdayFeatureHosts $hosts);if($errors.Count){throw ($errors -join '; ')}
   if([DateTime]::UtcNow -gt $start.AddSeconds(10)){throw 'Feature timed out'}
   Start-Sleep -Milliseconds 10
  } while(Test-WorkdayFeatureBusy $hosts)
  $shown=Get-Content (Join-Path $fixture 'shown.json') -Raw|ConvertFrom-Json
  if($shown.pid -ne $PID){throw 'Menu created another process'}
  $times += [int]([TimeSpan]::FromTicks($shown.shown-$start.Ticks).TotalMilliseconds)
  if($name -eq 'control.ps1'){$threads += $shown.thread}
 }
 if($threads[0] -ne $threads[1]){throw 'Feature thread was not reused'}
 Write-Output ('FEATURE_HOSTS_OK: same process; reused STA thread; five window show times ms='+($times -join ','))
} finally {Close-WorkdayFeatureHosts $hosts}
