[CmdletBinding()]
param([switch]$SelfTest, [long]$OwnerHandle = 0)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$TaskNames = @("자동출근", "자동퇴근", "자동출퇴근로그인", "자동출퇴근점검")
$ExpectedInstallRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "AutoAttendance")).TrimEnd('\')
$CurrentInstallRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$SettingsFile = Join-Path $CurrentInstallRoot "dist\자동출근설정.json"
$Python = Join-Path $CurrentInstallRoot "runtime\python.exe"
$MainScript = Join-Path $CurrentInstallRoot "main.py"
$script:CurrentSettings = $null
. (Join-Path $PSScriptRoot 'session.ps1')
. (Join-Path $PSScriptRoot 'task-control.ps1')

if (Test-Path -LiteralPath $SettingsFile) {
    try { $script:CurrentSettings = Get-Content -LiteralPath $SettingsFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}
}

$form = New-Object Windows.Forms.Form
$form.Text = "근태매니저 — 근태 자동관리"
$form.Size = New-Object Drawing.Size(470, 850)
$form.AutoScroll = $true
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Font = New-Object Drawing.Font("Malgun Gothic", 10)

$title = New-Object Windows.Forms.Label
$title.Text = "근태 자동관리 설정"
$title.Font = New-Object Drawing.Font("Malgun Gothic", 15, [Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object Drawing.Point(95, 18)
$form.Controls.Add($title)

$status = New-Object Windows.Forms.Label
$status.Size = New-Object Drawing.Size(410, 64)
$status.Font = New-Object Drawing.Font('Malgun Gothic', 9)
$status.Location = New-Object Drawing.Point(22, 57)
$status.TextAlign = "MiddleCenter"
$status.BorderStyle = "FixedSingle"
$form.Controls.Add($status)

$idLabel = New-Object Windows.Forms.Label
$idLabel.Text = "로그인 ID"
$idLabel.AutoSize = $true
$idLabel.Location = New-Object Drawing.Point(35, 128)
$form.Controls.Add($idLabel)
$idBox = New-Object Windows.Forms.TextBox
$idBox.Size = New-Object Drawing.Size(285, 28)
$idBox.Location = New-Object Drawing.Point(130, 124)
if ($script:CurrentSettings) { $idBox.Text = $script:CurrentSettings.id }
$form.Controls.Add($idBox)

$pwLabel = New-Object Windows.Forms.Label
$pwLabel.Text = "로그인 PW"
$pwLabel.AutoSize = $true
$pwLabel.Location = New-Object Drawing.Point(35, 168)
$form.Controls.Add($pwLabel)
$pwBox = New-Object Windows.Forms.TextBox
$pwBox.Size = New-Object Drawing.Size(285, 28)
$pwBox.Location = New-Object Drawing.Point(130, 164)
$pwBox.UseSystemPasswordChar = $true
$form.Controls.Add($pwBox)

$pwHelp = New-Object Windows.Forms.Label
$pwHelp.Text = "기존 PW를 유지하려면 비워 두세요."
$pwHelp.ForeColor = [Drawing.Color]::DimGray
$pwHelp.AutoSize = $true
$pwHelp.Location = New-Object Drawing.Point(130, 194)
$form.Controls.Add($pwHelp)

$monthlyLabel = New-Object Windows.Forms.Label
$monthlyLabel.Text = '월 연장시간'
$monthlyLabel.AutoSize = $true
$monthlyLabel.Location = New-Object Drawing.Point(35, 225)
$form.Controls.Add($monthlyLabel)
$monthlyBox = New-Object Windows.Forms.NumericUpDown
$monthlyBox.Minimum = 0
$monthlyBox.Maximum = 62
$monthlyBox.Value = 10
$monthlyBox.Location = New-Object Drawing.Point(130, 220)
$monthlyBox.Size = New-Object Drawing.Size(90, 28)
if ($script:CurrentSettings -and $null -ne $script:CurrentSettings.monthly_overtime_hours) {
    $monthlyBox.Value = [Math]::Min(62, [Math]::Max(0, [int]$script:CurrentSettings.monthly_overtime_hours))
}
$form.Controls.Add($monthlyBox)
$hoursLabel = New-Object Windows.Forms.Label
$hoursLabel.Text = '시간 (0이면 연장 없음)'
$hoursLabel.AutoSize = $true
$hoursLabel.Location = New-Object Drawing.Point(225, 225)
$form.Controls.Add($hoursLabel)
$dailyLabel = New-Object Windows.Forms.Label
$dailyLabel.Text = '하루 기준'
$dailyLabel.AutoSize = $true
$dailyLabel.Location = New-Object Drawing.Point(35, 266)
$form.Controls.Add($dailyLabel)
$dailyBox = New-Object Windows.Forms.ComboBox
$dailyBox.DropDownStyle = 'DropDownList'
$dailyBox.Location = New-Object Drawing.Point(130, 261)
$dailyBox.Size = New-Object Drawing.Size(285, 30)
[void]$dailyBox.Items.Add('1시간 (19:00~19:55)')
[void]$dailyBox.Items.Add('2시간 (19:00~20:55)')
$dailyBox.SelectedIndex = 0
if ($script:CurrentSettings -and $script:CurrentSettings.daily_overtime_hours -eq 2) { $dailyBox.SelectedIndex = 1 }
$form.Controls.Add($dailyBox)
$overtimeHelp = New-Object Windows.Forms.Label
$overtimeHelp.Text = "월 10시간: 하루 1시간이면 10일 / 2시간이면 5일`n당월 계획 생성 후 변경한 설정은 다음 달부터 적용"
$overtimeHelp.Size = New-Object Drawing.Size(420, 45)
$overtimeHelp.Location = New-Object Drawing.Point(25, 300)
$overtimeHelp.TextAlign = 'MiddleCenter'
$form.Controls.Add($overtimeHelp)

$timeGroup = New-Object Windows.Forms.GroupBox
$timeGroup.Text = '출근 · 일반 퇴근 시간 범위'
$timeGroup.Location = New-Object Drawing.Point(25, 348)
$timeGroup.Size = New-Object Drawing.Size(410, 160)
$form.Controls.Add($timeGroup)
$timeInputs = @{}
foreach ($spec in @(@('checkin_start','출근', '08:30',20,30), @('checkin_end','~','08:55',245,30), @('checkout_start','퇴근','18:00',20,70), @('checkout_end','~','18:55',245,70))) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $spec[1]; $label.Location = New-Object Drawing.Point($spec[3], ($spec[4]+3)); $label.Size = New-Object Drawing.Size(45,25)
    $timeGroup.Controls.Add($label)
    $picker = New-Object Windows.Forms.DateTimePicker
    $picker.Format = 'Custom'; $picker.CustomFormat = 'HH:mm'; $picker.ShowUpDown = $true
    $picker.Location = New-Object Drawing.Point(($spec[3]+48), $spec[4]); $picker.Size = New-Object Drawing.Size(102,28)
    $value = $spec[2]
    if ($script:CurrentSettings -and $script:CurrentSettings.($spec[0])) { $value = $script:CurrentSettings.($spec[0]) }
    $picker.Value = [DateTime]::ParseExact($value, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture)
    $timeGroup.Controls.Add($picker); $timeInputs[$spec[0]] = $picker
}
$stepLabel = New-Object Windows.Forms.Label
$stepLabel.Text = '선택 간격'; $stepLabel.Location = New-Object Drawing.Point(20,116); $stepLabel.Size = New-Object Drawing.Size(85,25)
$timeGroup.Controls.Add($stepLabel)
$stepBox = New-Object Windows.Forms.ComboBox
$stepBox.DropDownStyle = 'DropDownList'; $stepBox.Location = New-Object Drawing.Point(110,110); $stepBox.Size = New-Object Drawing.Size(150,30)
[void]$stepBox.Items.Add('1분 단위'); [void]$stepBox.Items.Add('5분 단위')
$stepBox.SelectedIndex = 1
if ($script:CurrentSettings -and $script:CurrentSettings.time_step_minutes -eq 1) { $stepBox.SelectedIndex = 0 }
$timeGroup.Controls.Add($stepBox)

function Update-Status {
    Start-ControlOperation 'status'
}
function Start-ControlOperation([string]$Action, $Previous = $null) {
    if ($script:TaskJob -and $Action -eq 'status') { return }
    if ($Action -ne 'status') {
        foreach ($button in @($saveButton,$pauseButton,$resumeButton,$deleteButton,$refreshButton)) { $button.Enabled=$false }
        $status.Text = switch ($Action) { 'register' {'설정 저장 및 예약 등록 중…'}; 'pause' {'예약 작업과 자동 실행을 정지하는 중…'}; 'resume' {'예약 작업과 자동 실행을 다시 시작하는 중…'} }
    } else { $status.Text = '예약 작업 상태를 확인하는 중…' }
    if ($script:TaskJob) { $script:QueuedOperation=@{action=$Action;previous=$Previous}; return }
    $script:TaskJob=Start-WorkdayTaskJob $script:TaskContext $CurrentInstallRoot $Action $Previous
}

function Set-AutomationEnabled([bool]$Enabled) {
    if (-not (Test-Path -LiteralPath $SettingsFile)) { return }
    $current = Get-Content -LiteralPath $SettingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $current | Add-Member -NotePropertyName enabled -NotePropertyValue $Enabled -Force
    Write-WorkdayText $SettingsFile ($current | ConvertTo-Json)
    $script:CurrentSettings = $current
}

$saveButton = New-Object Windows.Forms.Button
$saveButton.Text = "ID/PW 저장 및 작업 등록"
$saveButton.Size = New-Object Drawing.Size(250, 42)
$saveButton.Location = New-Object Drawing.Point(102, 520)
$saveButton.BackColor = [Drawing.Color]::Honeydew
$saveButton.Add_Click({
    try {
        $userId = $idBox.Text.Trim()
        $plainPassword = $pwBox.Text
        if ([string]::IsNullOrWhiteSpace($userId)) { throw "ID를 입력해 주세요." }
        if ([string]::IsNullOrEmpty($plainPassword)) {
            if ($script:CurrentSettings -and $script:CurrentSettings.pw) { $plainPassword = $script:CurrentSettings.pw } else { throw "PW를 입력해 주세요." }
        }
        if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $MainScript)) { throw "프로그램 설치 파일이 없습니다. 설치하기.bat를 먼저 실행해 주세요." }
        $monthlyHours = [int]$monthlyBox.Value
        $dailyHours = $dailyBox.SelectedIndex + 1
        if ($monthlyHours % $dailyHours -ne 0) { throw '하루 2시간을 선택하면 월 연장시간은 짝수로 입력해 주세요.' }
        New-Item -ItemType Directory -Path (Split-Path -Parent $SettingsFile) -Force | Out-Null
        $previousSettingsJson = $null
        if (Test-Path -LiteralPath $SettingsFile) { $previousSettingsJson = Get-Content -LiteralPath $SettingsFile -Raw -Encoding UTF8 }
        $values = @{ id = $userId; pw = $plainPassword; enabled = $true; monthly_overtime_hours = $monthlyHours; daily_overtime_hours = $dailyHours; time_step_minutes = $(if ($stepBox.SelectedIndex -eq 0) { 1 } else { 5 }) }
        foreach ($key in $timeInputs.Keys) { $values[$key] = $timeInputs[$key].Value.ToString('HH:mm') }
        if ($values.checkin_start -gt $values.checkin_end -or $values.checkin_end -ge $values.checkout_start -or $values.checkout_start -gt $values.checkout_end) { throw '출근 시작 ≤ 출근 종료 < 퇴근 시작 ≤ 퇴근 종료 순서로 설정하세요.' }
        if ($monthlyHours -gt 0 -and $values.checkout_end -ge '19:00') { throw '연장을 사용하는 경우 일반 퇴근 종료는 19:00 이전이어야 합니다.' }
        $settingsJson = $values | ConvertTo-Json
        Write-WorkdayText $SettingsFile $settingsJson
        $script:CurrentSettings = [PSCustomObject]$values
        Start-ControlOperation 'register' $previousSettingsJson
    } catch {
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, "등록 실패", "OK", "Error") | Out-Null
    }
})
$form.Controls.Add($saveButton)

$pauseButton = New-Object Windows.Forms.Button
$pauseButton.Text = "일시 정지"
$pauseButton.Size = New-Object Drawing.Size(120, 42)
$pauseButton.Location = New-Object Drawing.Point(30, 583)
$pauseButton.Add_Click({
    try {
        Set-AutomationEnabled $false
        Stop-WorkdayEngine
        Start-ControlOperation 'pause'
    } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message, "정지 실패", "OK", "Error") | Out-Null }
})
$form.Controls.Add($pauseButton)

$resumeButton = New-Object Windows.Forms.Button
$resumeButton.Text = "다시 시작"
$resumeButton.Size = New-Object Drawing.Size(120, 42)
$resumeButton.Location = New-Object Drawing.Point(167, 583)
$resumeButton.Add_Click({
    try {
        Start-ControlOperation 'resume'
    } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message, "시작 실패", "OK", "Error") | Out-Null }
})
$form.Controls.Add($resumeButton)

$deleteButton = New-Object Windows.Forms.Button
$deleteButton.Text = "완전 삭제"
$deleteButton.Size = New-Object Drawing.Size(120, 42)
$deleteButton.Location = New-Object Drawing.Point(304, 583)
$deleteButton.BackColor = [Drawing.Color]::MistyRose
$deleteButton.Add_Click({
    try {
        $uninstaller = Join-Path $CurrentInstallRoot '제거.exe'
        if (-not (Test-Path -LiteralPath $uninstaller)) { throw '새 설치본으로 업데이트 후 제거해 주세요.' }
        Start-Process -FilePath $uninstaller -WindowStyle Hidden
    } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message, "삭제 실패", "OK", "Error") | Out-Null }
})
$form.Controls.Add($deleteButton)

$refreshButton = New-Object Windows.Forms.Button
$refreshButton.Text = "상태 새로고침"
$refreshButton.Size = New-Object Drawing.Size(135, 34)
$refreshButton.Location = New-Object Drawing.Point(82, 647)
$refreshButton.Add_Click({ Update-Status })
$form.Controls.Add($refreshButton)
$closeButton = New-Object Windows.Forms.Button
$closeButton.Text = "닫기"
$closeButton.Size = New-Object Drawing.Size(135, 34)
$closeButton.Location = New-Object Drawing.Point(237, 647)
$closeButton.Add_Click({ $form.Close() })
$form.Controls.Add($closeButton)

$recoveryHelp = New-Object Windows.Forms.Label
$recoveryHelp.Text = "PC 로그인 시 즉시 출근 / 퇴근 누락 보완`n선택 간격은 시작 시각을 기준으로 적용`n시간 범위 변경은 새로 만드는 예약부터 적용`n주말·공휴일 제외 / 월 시간은 일수 배정 기준"
$recoveryHelp.Size = New-Object Drawing.Size(420, 96)
$recoveryHelp.Location = New-Object Drawing.Point(20, 694)
$recoveryHelp.TextAlign = 'MiddleCenter'
$form.Controls.Add($recoveryHelp)

. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
$saveButton.BackColor = $script:UiMint
$pauseButton.BackColor = $script:UiOrange
$deleteButton.BackColor = $script:UiInk
$status.BackColor = [Drawing.Color]::White
$status.Text = '예약 작업 상태를 확인하는 중…'
if ($SelfTest) {
    foreach ($control in $form.Controls) {
        if ($control.Right -gt $form.ClientSize.Width -or $control.Bottom -gt $form.ClientSize.Height) { throw '관리 화면 컨트롤이 창 경계를 벗어났습니다.' }
    }
    Write-Output "CONTROL_UI_OK: monthly=$($monthlyBox.Value), daily=$($dailyBox.SelectedIndex + 1), $($status.Text)"
    $form.Dispose()
    exit 0
}
if (-not (Enter-WorkdayUi 'control')) { $form.Dispose(); exit 0 }
$script:TaskContext=New-WorkdayTaskContext
$script:TaskJob=$null; $script:QueuedOperation=$null
$taskTimer=New-Object Windows.Forms.Timer
$taskTimer.Interval=50
$taskTimer.Add_Tick({
    $job=$script:TaskJob
    if(-not $job -or -not $job.pending.IsCompleted){return}
    try {
        $results=@($job.pipeline.EndInvoke($job.pending))
        if($job.pipeline.Streams.Error.Count){throw $job.pipeline.Streams.Error[0].Exception}
        $result=$results[-1]
        $status.Text=if($result.message){$result.message}else{$result.lines -join "`n"}
        if($job.action -eq 'register'){$pwBox.Clear()}
    } catch {
        $status.Text='처리 확인: '+$_.Exception.Message
        if($job.action -ne 'status'){[void][Windows.Forms.MessageBox]::Show($form,$_.Exception.Message,'처리 확인')}
        if(Test-Path -LiteralPath $SettingsFile){$script:CurrentSettings=Get-Content -LiteralPath $SettingsFile -Raw -Encoding UTF8|ConvertFrom-Json}
    } finally {
        $job.pipeline.Dispose(); $script:TaskJob=$null
        foreach($button in @($saveButton,$pauseButton,$resumeButton,$deleteButton,$refreshButton)){$button.Enabled=$true}
    }
    if($script:QueuedOperation){$next=$script:QueuedOperation;$script:QueuedOperation=$null;Start-ControlOperation $next.action $next.previous}
})
$form.Add_Shown({Update-Status;$taskTimer.Start()})
$form.Add_FormClosing({if($script:QueuedOperation -or ($script:TaskJob -and $script:TaskJob.action -ne 'status')){$_.Cancel=$true}})
try { Show-WorkdayDialog $form $OwnerHandle } finally {
    $taskTimer.Dispose()
    if($script:TaskJob){$script:TaskJob.pipeline.Stop();$script:TaskJob.pipeline.Dispose()}
    $script:TaskContext.Dispose()
    Exit-WorkdayUi
}
