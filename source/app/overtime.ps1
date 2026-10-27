[CmdletBinding()]
param([switch]$SelfTest, [string]$PreviewPath, [long]$OwnerHandle = 0)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $PSScriptRoot 'session.ps1')
$dataRoot = Join-Path $PSScriptRoot 'dist'
$settingsFile = Join-Path $dataRoot '자동출근설정.json'
$python = Join-Path $PSScriptRoot 'runtime\python.exe'
$mainScript = Join-Path $PSScriptRoot 'main.py'
$script:worker = $null
$script:jobPath = $null
$script:scanMonth = $null
$script:operation = $null

$form = New-Object Windows.Forms.Form
$form.Text = '출근정리 — 시간외근무 신청'
$form.Size = New-Object Drawing.Size(1080, 650)
$form.MinimumSize = New-Object Drawing.Size(960, 600)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('Malgun Gothic', 10)
function Add-Label($Text, $X, $Y, $Width) {
    $control = New-Object Windows.Forms.Label
    $control.Text = $Text
    $control.Location = New-Object Drawing.Point($X, $Y)
    $control.Size = New-Object Drawing.Size($Width, 26)
    $form.Controls.Add($control)
}
Add-Label 'ID' 20 25 35
$idBox = New-Object Windows.Forms.TextBox
$idBox.Location = New-Object Drawing.Point(58, 20)
$idBox.Size = New-Object Drawing.Size(200, 28)
$form.Controls.Add($idBox)
Add-Label 'PW' 278 25 35
$pwBox = New-Object Windows.Forms.TextBox
$pwBox.Location = New-Object Drawing.Point(316, 20)
$pwBox.Size = New-Object Drawing.Size(200, 28)
$pwBox.UseSystemPasswordChar = $true
$form.Controls.Add($pwBox)
if (Test-Path -LiteralPath $settingsFile) {
    try { $settings = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json; $idBox.Text = $settings.id } catch {}
}
Add-Label '기존 PW 유지 시 비워두세요. 계정은 조회 시 저장됩니다.' 535 24 510
Add-Label '조회 월' 20 77 68
$monthPicker = New-Object Windows.Forms.ComboBox
$monthPicker.DropDownStyle = 'DropDownList'
$monthPicker.MaxDropDownItems = 12
$monthPicker.IntegralHeight = $false
$monthPicker.DropDownHeight = 300
function Update-MonthChoices([DateTime]$Now = (Get-Date)) {
    $anchor = $Now.ToString('yyyy-MM')
    if ($script:monthListAnchor -eq $anchor) { return }
    $selected = [string]$monthPicker.SelectedItem
    $script:updatingMonths = $true
    $monthPicker.BeginUpdate()
    try {
        $monthPicker.Items.Clear()
        foreach ($label in (Get-WorkdayMonthLabels $Now)) { [void]$monthPicker.Items.Add($label) }
        if ($selected -and -not $monthPicker.Items.Contains($selected)) { [void]$monthPicker.Items.Add($selected) }
        if ($selected) { $monthPicker.SelectedItem = $selected } else { $monthPicker.SelectedIndex = 0 }
        $script:monthListAnchor = $anchor
    } finally { $monthPicker.EndUpdate(); $script:updatingMonths = $false }
}
function Get-SelectedMonth {
    [DateTime]::ParseExact([string]$monthPicker.SelectedItem, 'yyyy년 MM월', [Globalization.CultureInfo]::InvariantCulture).ToString('yyyy-MM')
}
Update-MonthChoices
$calendarTimer = New-Object Windows.Forms.Timer
$calendarTimer.Interval = 60000
$calendarTimer.Add_Tick({ Update-MonthChoices })
$form.Add_Shown({ $calendarTimer.Start() })
$form.Add_FormClosed({ $calendarTimer.Stop(); $calendarTimer.Dispose() })
$monthPicker.Location = New-Object Drawing.Point(94, 70)
$monthPicker.Size = New-Object Drawing.Size(190, 28)
$form.Controls.Add($monthPicker)
$scan = New-Object Windows.Forms.Button
$scan.Text = '선택 월 실제 연장일 조회'
$scan.Location = New-Object Drawing.Point(305, 67)
$scan.Size = New-Object Drawing.Size(245, 35)
$form.Controls.Add($scan)
Add-Label '부서: 센터 / 시작: 18:00 / 종료: 실제 퇴근의 분 제외' 570 77 470
$description = New-Object Windows.Forms.Label
$description.Text = '조회 후 날짜별 근무목적을 입력하고 신청할 날짜를 체크하세요. 예: 19:55 퇴근 → 18:00~19:00 신청'
$description.Location = New-Object Drawing.Point(20, 118)
$description.Size = New-Object Drawing.Size(1020, 40)
$form.Controls.Add($description)
$grid = New-Object Windows.Forms.DataGridView
$grid.Location = New-Object Drawing.Point(20, 165)
$grid.Size = New-Object Drawing.Size(1020, 337)
$grid.Anchor = 'Top, Bottom, Left, Right'
$grid.AllowUserToAddRows = $false
$grid.AllowUserToDeleteRows = $false
$grid.RowHeadersVisible = $false
$grid.AutoSizeColumnsMode = 'Fill'
$grid.RowTemplate.Height = 32
$choose = New-Object Windows.Forms.DataGridViewCheckBoxColumn
$choose.Name = 'choose'; $choose.HeaderText = '선택'; $choose.FillWeight = 45
[void]$grid.Columns.Add($choose)
foreach ($spec in @(@('date','근무일',110), @('weekday','요일',50), @('checkout','실제 퇴근',85), @('start','시작',70), @('end','신청 종료',85), @('purpose','근무목적 (직접 입력)',320), @('status','처리 상태',180))) {
    $col = New-Object Windows.Forms.DataGridViewTextBoxColumn
    $col.Name = $spec[0]; $col.HeaderText = $spec[1]; $col.FillWeight = $spec[2]
    $col.ReadOnly = ($spec[0] -ne 'purpose')
    if ($spec[0] -eq 'purpose') { $col.MaxInputLength = 1000 }
    [void]$grid.Columns.Add($col)
}
$grid.Add_CurrentCellDirtyStateChanged({ if ($grid.IsCurrentCellDirty) { [void]$grid.CommitEdit([Windows.Forms.DataGridViewDataErrorContexts]::Commit) } })
$form.Controls.Add($grid)
$statusLabel = New-Object Windows.Forms.Label
$statusLabel.Text = '당월이 기본값입니다. 9월을 선택하면 9월 기록과 9월 날짜로 신청합니다.'
$statusLabel.Location = New-Object Drawing.Point(20, 520)
$statusLabel.Size = New-Object Drawing.Size(1020, 32)
$statusLabel.Anchor = 'Bottom, Left, Right'
$form.Controls.Add($statusLabel)
$submit = New-Object Windows.Forms.Button
$submit.Text = '확인 — 선택 날짜 신청'
$submit.Location = New-Object Drawing.Point(730, 558)
$submit.Size = New-Object Drawing.Size(310, 42)
$submit.Anchor = 'Bottom, Right'
$submit.Enabled = $false
$form.Controls.Add($submit)
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 700

function Save-Account {
    if ([string]::IsNullOrWhiteSpace($idBox.Text)) { throw 'ID를 입력해 주세요.' }
    $config = [PSCustomObject]@{ enabled = $false }
    if (Test-Path -LiteralPath $settingsFile) { $config = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json }
    $secret = $pwBox.Text
    if (-not $secret -and $config.id -eq $idBox.Text.Trim()) { $secret = $config.pw }
    if (-not $secret) { throw 'PW를 입력해 주세요. ID 변경 시에는 PW도 다시 입력해야 합니다.' }
    $config | Add-Member -NotePropertyName id -NotePropertyValue $idBox.Text.Trim() -Force
    $config | Add-Member -NotePropertyName pw -NotePropertyValue $secret -Force
    New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
    Write-WorkdayText $settingsFile ($config | ConvertTo-Json)
    $pwBox.Clear()
}
function Invoke-OvertimeJob($Job) {
    if (-not (Test-Path -LiteralPath $python)) { throw '새 설치 패키지로 먼저 설치해 주세요.' }
    Save-Account
    $script:jobPath = Join-Path $dataRoot ("overtime-job-{0}.json" -f [Guid]::NewGuid().ToString('N'))
    [IO.File]::WriteAllText($script:jobPath, ($Job | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
    $script:operation = $Job.operation
    $script:worker = Start-WorkdayHiddenProcess $python "`"$mainScript`" --overtime-job `"$script:jobPath`"" $PSScriptRoot
    $scan.Enabled = $false; $submit.Enabled = $false; $monthPicker.Enabled = $false
    $idBox.Enabled = $false; $pwBox.Enabled = $false; $grid.Enabled = $false
    $statusLabel.Text = '사이트 처리 중입니다. 완료될 때까지 기다려 주세요.'
    $timer.Start()
}
$scan.Add_Click({
    try {
        $script:scanMonth = Get-SelectedMonth
        $grid.Rows.Clear()
        Invoke-OvertimeJob @{ operation = 'scan'; month = $script:scanMonth }
    } catch { [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '조회 오류', 'OK', 'Error') }
})
$monthPicker.Add_SelectedIndexChanged({ if ($script:updatingMonths) { return }; $submit.Enabled = $false; $grid.Rows.Clear(); $script:scanMonth = $null })
$submit.Add_Click({
    try {
        [void]$grid.EndEdit()
        if ($script:scanMonth -ne (Get-SelectedMonth)) { throw '월을 변경했으면 다시 조회해 주세요.' }
        $entries = @()
        foreach ($row in $grid.Rows) {
            if (-not $row.Cells['choose'].Value) { continue }
            $purpose = [string]$row.Cells['purpose'].Value
            if ([string]::IsNullOrWhiteSpace($purpose)) { throw "$($row.Cells['date'].Value)의 근무목적을 입력해 주세요." }
            $entries += @{ date = [string]$row.Cells['date'].Value; checkout = [string]$row.Cells['checkout'].Value; start = '18:00'; end = [string]$row.Cells['end'].Value; purpose = $purpose.Trim() }
        }
        if ($entries.Count -eq 0) { throw '신청할 날짜를 선택해 주세요.' }
        $answer = [Windows.Forms.MessageBox]::Show("$script:scanMonth 선택 날짜 $($entries.Count)건을 신청합니다.`n부서: 센터 / 시작: 18:00 / 종료: 퇴근 시각의 분 제외`n입력한 근무목적과 날짜를 확인하셨나요?", '시간외근무 신청 확인', 'YesNo', 'Question')
        if ($answer -ne 'Yes') { return }
        Invoke-OvertimeJob @{ operation = 'submit'; month = $script:scanMonth; rows = @($entries) }
    } catch { [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '신청 오류', 'OK', 'Error') }
})
$timer.Add_Tick({
    if (-not $script:worker) { return }
    $script:worker.Refresh()
    if (-not $script:worker.HasExited) { return }
    $timer.Stop()
    try {
        $resultPath = $script:jobPath + '.result.json'
        if (-not (Test-Path -LiteralPath $resultPath)) { throw '처리 결과 파일이 없습니다. 실행 로그를 확인해 주세요.' }
        $result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $result.ok) { throw $result.error }
        if ($script:operation -eq 'scan') {
            $grid.Rows.Clear()
            foreach ($entry in $result.rows) {
                [void]$grid.Rows.Add([bool]$entry.selectable, $entry.date, $entry.weekday, $entry.checkout, $entry.start, $entry.end, '', $entry.status)
            }
            $statusLabel.Text = "$script:scanMonth 연장 퇴근 $($grid.Rows.Count)일. 근무목적을 입력하세요. $($result.message)"
        } else {
            foreach ($entry in $result.rows) {
                foreach ($row in $grid.Rows) {
                    if ($row.Cells['date'].Value -eq $entry.date) { $row.Cells['status'].Value = $entry.status; $row.Cells['choose'].Value = $false }
                }
            }
            $statusLabel.Text = '처리 결과를 확인하세요. 확인 필요 항목은 사이트에서 먼저 확인한 후 다시 조회하세요.'
        }
    } catch {
        $statusLabel.Text = $_.Exception.Message
        [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '처리 결과', 'OK', 'Error')
    } finally {
        Remove-Item -LiteralPath $script:jobPath,($script:jobPath + '.result.json') -Force -ErrorAction SilentlyContinue
        $script:worker = $null
        $scan.Enabled = $true; $monthPicker.Enabled = $true; $idBox.Enabled = $true; $pwBox.Enabled = $true; $grid.Enabled = $true
        $submit.Enabled = ($grid.Rows.Count -gt 0 -and $script:scanMonth -eq (Get-SelectedMonth))
    }
})
$form.Add_FormClosing({ if ($script:worker -and -not $script:worker.HasExited) { $_.Cancel = $true; [void][Windows.Forms.MessageBox]::Show('진행 중인 사이트 처리가 끝난 뒤 닫아 주세요.', '처리 중') } })
. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
$submit.BackColor = $script:UiOrange
if ($SelfTest) {
    if ($grid.Columns.Count -ne 8 -or (Get-SelectedMonth) -ne (Get-Date).ToString('yyyy-MM')) { throw '신청 화면 검사 실패' }
    $monthPicker.SelectedIndex = 1
    $chosenMonth = Get-SelectedMonth
    Update-MonthChoices ((Get-Date).AddMonths(1))
    if ((Get-SelectedMonth) -ne $chosenMonth -or $monthPicker.Items[0] -ne (Get-Date).AddMonths(1).ToString('yyyy년 MM월')) { throw '월 변경/선택 보존 검사 실패' }
    $monthPicker.SelectedIndex = 1
    if ($PreviewPath) {
        [void]$grid.Rows.Add($true, '2026-10-06', '화', '19:15', '18:00', '19:00', '상담 기록 정리', '신청 가능')
        [void]$grid.Rows.Add($true, '2026-10-12', '월', '20:55', '18:00', '20:00', '프로그램 운영 및 자료 정리', '신청 가능')
        $statusLabel.Text = '디자인 미리보기 — 예시 데이터입니다.'
        Write-UiPreview $form $PreviewPath
    }
    Write-Output 'OVERTIME_UI_OK: current-month default, 8 columns, no login/submission executed'
    $form.Dispose(); $timer.Dispose(); $calendarTimer.Dispose(); return
}
. (Join-Path $PSScriptRoot 'session.ps1')
if (-not (Enter-WorkdayUi 'overtime')) { $form.Dispose(); $timer.Dispose(); return }
try { Show-WorkdayDialog $form $OwnerHandle } finally { Exit-WorkdayUi }
$timer.Dispose()
