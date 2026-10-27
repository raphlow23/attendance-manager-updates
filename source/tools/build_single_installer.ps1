$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$payload = Join-Path $root '출근정리_설치패키지_2026-10-26.zip'
$output = Join-Path $root '출근정리_설치.exe'
$hash = (Get-FileHash -LiteralPath $payload -Algorithm SHA256).Hash
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'SingleInstaller.cs') -Raw -Encoding UTF8
$generated = Join-Path $PSScriptRoot ('generated-setup-' + [Guid]::NewGuid().ToString('N') + '.cs')
try {
    [IO.File]::WriteAllText($generated, $source.Replace('__PAYLOAD_SHA256__', $hash), (New-Object Text.UTF8Encoding($true)))
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    & $compiler /nologo /target:winexe /platform:anycpu /optimize+ /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll "/win32icon:$(Join-Path $root 'app\attendance.ico')" "/resource:$payload,AttendanceManager.Package.zip" "/out:$output" $generated
    if ($LASTEXITCODE -ne 0) { throw '단일 EXE 빌드 실패' }
    $process = Start-Process -FilePath $output -ArgumentList '--self-test' -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw '단일 EXE 내장 파일 검증 실패' }
    [PSCustomObject]@{ File=$output; Bytes=(Get-Item -LiteralPath $output).Length; SHA256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash; EmbeddedPayloadSHA256=$hash } | ConvertTo-Json
} finally { Remove-Item -LiteralPath $generated -Force -ErrorAction SilentlyContinue }
