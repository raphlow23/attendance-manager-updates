$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$fixture = Join-Path $root ('.test-data\gui-regression-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $fixture 'app') -Force | Out-Null
Copy-Item (Join-Path $root 'gui-install.ps1') $fixture
Copy-Item (Join-Path $root 'app\theme.ps1') (Join-Path $fixture 'app')
foreach ($name in @('session.ps1','attendance.ico','근태매니저.exe')) { Copy-Item (Join-Path $root ('app\'+$name)) (Join-Path $fixture 'app') }
$utf8 = New-Object Text.UTF8Encoding($true)
foreach ($code in @(0,7)) {
    $mock = @'
param([string]$InstallRoot, [switch]$SkipLaunch)
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $InstallRoot 'launcher.ps1'), '# fixture')
Write-Output '한글 설치 결과'
exit __CODE__
'@
    [IO.File]::WriteAllText((Join-Path $fixture 'install.ps1'), $mock.Replace('__CODE__', [string]$code), $utf8)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $info.Arguments = '-NoProfile -STA -ExecutionPolicy Bypass -File "' + (Join-Path $fixture 'gui-install.ps1') + '" -SelfTest -InstallRoot "' + (Join-Path $fixture "installed-$code") + '"'
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    [void]$process.Start()
    $output = $process.StandardOutput.ReadToEndAsync()
    if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'GUI test timed out' }
    $text = $output.GetAwaiter().GetResult()
    $expected = if ($code -eq 0) { 0 } else { 1 }
    if ($process.ExitCode -ne $expected) { throw "Unexpected GUI exit for core=$code : $($process.ExitCode); $text" }
    if ($code -eq 0 -and $text -notmatch 'GUI_INSTALL_OK') { throw 'GUI success marker missing' }
    if ($code -eq 7 -and $text -notmatch '7') { throw 'Original core error code missing' }
    $process.Dispose()
}
Write-Output 'GUI_REGRESSION_OK: success accepted; core error rejected with original code; logs retained'
