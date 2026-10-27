$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Launcher.cs') -Raw -Encoding UTF8
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
foreach ($spec in @(@('gui-install.ps1','설치.exe'), @('launcher.ps1','app\출근정리.exe'), @('uninstall.ps1','app\제거.exe'))) {
    $codePath = Join-Path $PSScriptRoot ('generated-' + [Guid]::NewGuid().ToString('N') + '.cs')
    try {
        [IO.File]::WriteAllText($codePath, $source.Replace('__ENTRY_SCRIPT__', $spec[0]), (New-Object Text.UTF8Encoding($true)))
        & $compiler /nologo /target:winexe /platform:anycpu /optimize+ /reference:System.Windows.Forms.dll "/win32icon:$(Join-Path $root 'app\attendance.ico')" "/out:$(Join-Path $root $spec[1])" $codePath
        if ($LASTEXITCODE -ne 0) { throw 'EXE 빌드 실패' }
    } finally { Remove-Item -LiteralPath $codePath -Force -ErrorAction SilentlyContinue }
}
$privateKey = Join-Path $root '.release-private.xml'
$rsa = New-Object Security.Cryptography.RSACryptoServiceProvider(3072)
try {
    if (Test-Path -LiteralPath $privateKey) { $rsa.FromXmlString([IO.File]::ReadAllText($privateKey)) }
    else { [IO.File]::WriteAllText($privateKey, $rsa.ToXmlString($true)) }
    [IO.File]::WriteAllText((Join-Path $root 'app\update-public.xml'), $rsa.ToXmlString($false))
} finally { $rsa.PersistKeyInCsp = $false; $rsa.Dispose() }
Write-Output 'EXE_AND_UPDATE_PUBLIC_KEY_OK (private key excluded from packages)'
Copy-Item -LiteralPath (Join-Path $root 'app\출근정리.exe') -Destination (Join-Path $root '출근정리.exe') -Force
# Keep existing shortcuts and old updater entry points functional.
Copy-Item -LiteralPath (Join-Path $root 'app\출근정리.exe') -Destination (Join-Path $root 'app\근태매니저.exe') -Force
Copy-Item -LiteralPath (Join-Path $root 'app\출근정리.exe') -Destination (Join-Path $root '근태매니저.exe') -Force
Copy-Item -LiteralPath (Join-Path $root 'app\출근정리.exe') -Destination (Join-Path $root '출퇴근관리.exe') -Force
Copy-Item -LiteralPath (Join-Path $root 'app\출근정리.exe') -Destination (Join-Path $root 'app\출퇴근관리.exe') -Force
& $compiler /nologo /target:winexe /platform:anycpu /optimize+ /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll "/win32icon:$(Join-Path $root 'app\attendance.ico')" "/out:$(Join-Path $root 'app\WorkdayGuard.exe')" (Join-Path $PSScriptRoot 'Guardian.cs')
if ($LASTEXITCODE -ne 0) { throw '감시 EXE 빌드 실패' }
