[CmdletBinding()]
param(
    [switch]$SelfTest,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "AutoAttendance")
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CoreInstaller = Join-Path $PackageRoot "install.ps1"
$ControlScript = Join-Path $InstallRoot "launcher.ps1"
$SettingsFile = Join-Path $InstallRoot "dist\자동출근설정.json"
$stamp = "{0}-{1}" -f $PID, [DateTime]::Now.Ticks
$logRoot = Join-Path $env:TEMP 'AttendanceManager-install-logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$outLog = Join-Path $logRoot ("install-$stamp.out.log")
$errLog = Join-Path $logRoot ("install-$stamp.err.log")
$resultLog = Join-Path $logRoot ("install-$stamp.result.log")
$utf8 = New-Object Text.UTF8Encoding($false)

$form = New-Object Windows.Forms.Form
$form.Text = "근태매니저 설치"
$form.Size = New-Object Drawing.Size(430, 185)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.ControlBox = $false
$form.TopMost = $true
$form.Font = New-Object Drawing.Font("Malgun Gothic", 10)

$title = New-Object Windows.Forms.Label
$title.Text = "자동 출퇴근 프로그램을 준비하고 있습니다."
$title.AutoSize = $true
$title.Location = New-Object Drawing.Point(55, 30)
$form.Controls.Add($title)

$detail = New-Object Windows.Forms.Label
$detail.Text = "잠시만 기다려 주세요."
$detail.AutoSize = $true
$detail.Location = New-Object Drawing.Point(55, 63)
$form.Controls.Add($detail)

$progress = New-Object Windows.Forms.ProgressBar
$progress.Style = "Marquee"
$progress.MarqueeAnimationSpeed = 30
$progress.Size = New-Object Drawing.Size(320, 24)
$progress.Location = New-Object Drawing.Point(55, 98)
$form.Controls.Add($progress)
. (Join-Path $PackageRoot 'app\theme.ps1')
Set-UiTheme $form

if (-not $SelfTest) {
    $form.Show()
    [Windows.Forms.Application]::DoEvents()
}
$selfTestFailed = $false
try {
    if (-not (Test-Path -LiteralPath $CoreInstaller)) { throw "설치 파일을 찾을 수 없습니다." }
    # Own the process handle: Windows PowerShell Start-Process with redirected
    # output can lose ExitCode after Refresh(), producing a false installation failure.
    $process = New-Object Diagnostics.Process
    $process.StartInfo = New-Object Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $process.StartInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$CoreInstaller`" -InstallRoot `"$InstallRoot`" -SkipLaunch"
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $process.StartInfo.StandardOutputEncoding = $utf8
    $process.StartInfo.StandardErrorEncoding = $utf8
    if (-not $process.Start()) { throw '설치 작업을 시작하지 못했습니다.' }
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    while (-not $process.WaitForExit(120)) {
        [Windows.Forms.Application]::DoEvents()
    }
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    $outputText = $outputTask.GetAwaiter().GetResult()
    $errorText = $errorTask.GetAwaiter().GetResult()
    [IO.File]::WriteAllText($outLog, $outputText, $utf8)
    [IO.File]::WriteAllText($errLog, $errorText, $utf8)
    $process.Dispose()
    [IO.File]::WriteAllText($resultLog, ("{0:o} CoreExitCode={1}; LauncherExists={2}" -f [DateTime]::Now, $exitCode, (Test-Path -LiteralPath $ControlScript)), $utf8)
    if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $ControlScript)) {
        $message = "설정 및 관리 화면 설치에 실패했습니다. (종료 코드: $exitCode)"
        $diagnostic = ($errorText + "`n" + $outputText).Trim()
        if ($diagnostic.Length -gt 1800) { $diagnostic = $diagnostic.Substring($diagnostic.Length - 1800) }
        if ($diagnostic) { $message += "`n`n$diagnostic" }
        throw $message
    }
    if ($SelfTest) { Write-Output "GUI_INSTALL_OK"; return }
    . (Join-Path $InstallRoot 'install-integration.ps1')
    [void](Register-AttendanceInstall $InstallRoot)
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) '근태매니저.lnk'))
        $shortcut.TargetPath = Join-Path $InstallRoot '근태매니저.exe'
        $shortcut.WorkingDirectory = $InstallRoot
        $shortcut.Save()
    } catch { Write-Warning '바탕화면 바로가기를 만들지 못했습니다. 설치 폴더의 출퇴근관리.exe를 실행해 주세요.' }
    $detail.Text = "설정 및 관리 창을 여는 중입니다."
    [Windows.Forms.Application]::DoEvents()
    $form.Hide()
    $control = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @("-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$ControlScript`"") -WindowStyle Hidden -PassThru
    if ($control.WaitForExit(800) -and $control.ExitCode -ne 0) { throw "설정 및 관리 창 실행에 실패했습니다." }
} catch {
    $selfTestFailed = $true
    $failure = $_.Exception.Message
    [IO.File]::AppendAllText($resultLog, ("`r`n{0:o} ERROR: {1}" -f [DateTime]::Now, $failure), $utf8)
    $form.Hide()
    if ($SelfTest) {
        Write-Output ("GUI_INSTALL_ERROR: " + $failure)
    } else {
        [Windows.Forms.MessageBox]::Show(($failure + "`n`n설치 로그: $resultLog"), "설치 실패", "OK", "Error") | Out-Null
    }
} finally {
    $form.Close()
}
if ($selfTestFailed) { exit 1 }
