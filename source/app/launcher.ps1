[CmdletBinding()]
param([switch]$SelfTest, [string]$PreviewPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = '근태매니저'
$form.Size = New-Object Drawing.Size(860, 645)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$title = New-Object Windows.Forms.Label
$title.Text = 'ATTENDANCE MANAGER  |  근태매니저'
$title.Location = New-Object Drawing.Point(0, 0)
$title.Size = New-Object Drawing.Size(845, 76)
$title.Padding = New-Object Windows.Forms.Padding(30, 0, 0, 0)
$title.Font = New-Object Drawing.Font('Malgun Gothic', 16, [Drawing.FontStyle]::Bold)
$title.TextAlign = 'MiddleLeft'
$title.BackColor = [Drawing.ColorTranslator]::FromHtml('#343C46')
$title.ForeColor = [Drawing.Color]::White
$form.Controls.Add($title)
function Open-Feature([string]$Name) {
    $arguments = @('-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', "`"$(Join-Path $PSScriptRoot $Name)`"")
    if ($Name -ne 'launcher.ps1') { $arguments += @('-OwnerHandle', $form.Handle.ToInt64()) }
    $child = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $arguments -WindowStyle Hidden -PassThru
    if ($Name -ne 'launcher.ps1') {
        Initialize-WorkdayWindows
        [void][WorkdayWindowOwner]::AllowSetForegroundWindow($child.Id)
    }
}
$attendance = New-Object Windows.Forms.Button
$attendance.Text = '근태 자동관리 설정'
$attendance.Location = New-Object Drawing.Point(50, 289)
$attendance.Size = New-Object Drawing.Size(345, 52)
$attendance.Add_Click({ Open-Feature 'control.ps1' })
$form.Controls.Add($attendance)
$overtime = New-Object Windows.Forms.Button
$overtime.Text = '시간외근무 신청 (월별 조회)'
$overtime.Location = New-Object Drawing.Point(450, 289)
$overtime.Size = New-Object Drawing.Size(345, 52)
$overtime.Add_Click({ Open-Feature 'overtime.ps1' })
$form.Controls.Add($overtime)
$hint = New-Object Windows.Forms.Label
$hint.Text = '이 창을 닫아도 자동 실행은 유지됩니다. 멈추려면 자동 실행 종료를 누르세요.'
$hint.Location = New-Object Drawing.Point(25, 537)
$hint.Size = New-Object Drawing.Size(795, 40)
$hint.TextAlign = 'MiddleCenter'
$form.Controls.Add($hint)
$security = New-Object Windows.Forms.Button
$security.Text = '실행 차단 / 보안 안내'
$security.Location = New-Object Drawing.Point(30, 378)
$security.Size = New-Object Drawing.Size(785, 42)
$security.Add_Click({ Open-Feature '보안안내.ps1' })
$form.Controls.Add($security)
. (Join-Path $PSScriptRoot 'session.ps1')
$startEngine = New-Object Windows.Forms.Button
$startEngine.Text = '자동 실행 시작'
$startEngine.Location = New-Object Drawing.Point(30, 431); $startEngine.Size = New-Object Drawing.Size(385, 42)
$startEngine.Add_Click({ try { Start-WorkdayEngine } catch { [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '시작 확인') } })
$form.Controls.Add($startEngine)
$stopEngine = New-Object Windows.Forms.Button
$stopEngine.Text = '자동 실행 종료 (재실행 안 함)'
$stopEngine.Location = New-Object Drawing.Point(430, 431); $stopEngine.Size = New-Object Drawing.Size(385, 42)
$stopEngine.Add_Click({ Stop-WorkdayEngine; [void][Windows.Forms.MessageBox]::Show('자동 실행을 종료합니다. 다시 시작을 선택할 때까지 재실행하지 않습니다.', '종료 요청') })
$form.Controls.Add($stopEngine)
$health = New-Object Windows.Forms.Button
$health.Text = '실행 상태 · 실제 로그인 결과 · 오류 로그'
$health.Location = New-Object Drawing.Point(30, 484); $health.Size = New-Object Drawing.Size(785, 42)
$health.Add_Click({ Open-Feature 'status.ps1' })
$form.Controls.Add($health)
foreach ($card in @(@(30, '01', '근태 자동관리', "기존 예약 출퇴근 등록`n누락 퇴근 보완 · 늦은 출근 보정", '#4BAFC9'), @(430, '02', '시간외근무 신청', "선택한 월의 실제 연장일 조회`n날짜별 근무목적 입력 후 신청", '#55B6A6'))) {
    $panel = New-Object Windows.Forms.Panel
    $panel.Location = New-Object Drawing.Point($card[0], 106)
    $panel.Size = New-Object Drawing.Size(385, 253)
    $panel.BackColor = [Drawing.Color]::White
    $bar = New-Object Windows.Forms.Label
    $bar.Location = New-Object Drawing.Point(0, 0); $bar.Size = New-Object Drawing.Size(385, 7)
    $bar.BackColor = [Drawing.ColorTranslator]::FromHtml($card[4])
    $panel.Controls.Add($bar)
    $number = New-Object Windows.Forms.Label
    $number.Text = $card[1]; $number.Font = New-Object Drawing.Font('Segoe UI', 26, [Drawing.FontStyle]::Bold)
    $number.ForeColor = $bar.BackColor; $number.Location = New-Object Drawing.Point(20, 22); $number.Size = New-Object Drawing.Size(90, 53)
    $panel.Controls.Add($number)
    $heading = New-Object Windows.Forms.Label
    $heading.Text = $card[2]; $heading.Font = New-Object Drawing.Font('Malgun Gothic', 16, [Drawing.FontStyle]::Bold)
    $heading.Location = New-Object Drawing.Point(20, 83); $heading.Size = New-Object Drawing.Size(345, 38)
    $panel.Controls.Add($heading)
    $detail = New-Object Windows.Forms.Label
    $detail.Text = $card[3]; $detail.Location = New-Object Drawing.Point(20, 127); $detail.Size = New-Object Drawing.Size(345, 50)
    $detail.ForeColor = [Drawing.ColorTranslator]::FromHtml('#788592')
    $panel.Controls.Add($detail)
    $form.Controls.Add($panel); $panel.SendToBack()
}
. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
$overtime.BackColor = $script:UiOrange
$security.BackColor = $script:UiInk
$stopEngine.BackColor = $script:UiOrange
$startEngine.BackColor = $script:UiMint
$health.BackColor = $script:UiInk
$attendance.BringToFront(); $overtime.BringToFront()
if ($SelfTest) { Write-UiPreview $form $PreviewPath; Write-Output 'LAUNCHER_UI_OK'; $form.Dispose(); exit 0 }
if (-not (Enter-WorkdayUi 'launcher')) { $form.Dispose(); exit 0 }
. (Join-Path $PSScriptRoot 'install-integration.ps1')
if ($PSScriptRoot -eq (Join-Path $env:LOCALAPPDATA 'AutoAttendance')) {
    try { [void](Register-AttendanceInstall $PSScriptRoot) } catch { [void][Windows.Forms.MessageBox]::Show(('앱 제거 정보 등록을 확인해 주세요. ' + $_.Exception.Message), '등록 확인') }
}
. (Join-Path $PSScriptRoot 'update.ps1')
$hint.Text = Invoke-WorkdayUpdate $PSScriptRoot
if ($hint.Text.StartsWith('업데이트 적용 완료')) {
    $form.Dispose()
    Exit-WorkdayUi
    Open-Feature 'launcher.ps1'
    exit 0
}
try { [void]$form.ShowDialog() } finally { Exit-WorkdayUi }
