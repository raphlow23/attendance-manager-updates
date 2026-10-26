$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $taskRoot 'app\session.ps1')
$fixture=Join-Path $taskRoot ('.test-data\hidden-process-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force|Out-Null
$source=@'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class ConsoleProbe { [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); }
"@
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'console.txt'),[ConsoleProbe]::GetConsoleWindow().ToInt64().ToString())
'@
$script=Join-Path $fixture 'watchdog.ps1'
[IO.File]::WriteAllText($script,$source)
$p=Start-WorkdayHiddenProcess "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" ('-NoProfile -ExecutionPolicy Bypass -File "'+$script+'"') $fixture
try{$p.WaitForExit();if($p.ExitCode -ne 0 -or (Get-Content (Join-Path $fixture 'console.txt')) -ne '0'){throw 'Console was allocated'}}finally{$p.Dispose()}
Remove-Item (Join-Path $fixture 'console.txt')
Copy-Item (Join-Path $taskRoot 'app\WorkdayGuard.exe') $fixture
$p=Start-WorkdayHiddenProcess (Join-Path $fixture 'WorkdayGuard.exe') '--watchdog' $fixture
try{$p.WaitForExit();if($p.ExitCode -ne 0 -or (Get-Content (Join-Path $fixture 'console.txt')) -ne '0'){throw 'Scheduled watchdog allocated a console'}}finally{$p.Dispose()}
Write-Output 'HIDDEN_PROCESS_OK: actual GetConsoleWindow=0 for helper and native scheduled watchdog; no user tasks or websites touched'
