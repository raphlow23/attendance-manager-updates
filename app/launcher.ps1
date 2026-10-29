[CmdletBinding()]
param([switch]$SelfTest, [string]$PreviewPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = '출근정리'
$form.Size = New-Object Drawing.Size(860, 550)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$title = New-Object Windows.Forms.Label
$title.Text = 'ATTENDANCE MANAGER  |  출근정리'
$title.Location = New-Object Drawing.Point(0, 0)
$title.Size = New-Object Drawing.Size(845, 76)
$title.Padding = New-Object Windows.Forms.Padding(30, 0, 0, 0)
$title.Font = New-Object Drawing.Font('Malgun Gothic', 16, [Drawing.FontStyle]::Bold)
$title.TextAlign = 'MiddleLeft'
$title.BackColor = [Drawing.ColorTranslator]::FromHtml('#343C46')
$title.ForeColor = [Drawing.Color]::White
$form.Controls.Add($title)
. (Join-Path $PSScriptRoot 'ui-host.ps1')
$script:FeatureHosts = @{}
function Open-Feature([string]$Name) {
    foreach($entry in @(@($attendance,'control.ps1'),@($corrections,'corrections.ps1'),@($overtime,'overtime.ps1'),@($trips,'trips.ps1'),@($health,'status.ps1'),@($security,'보안안내.ps1'))){[WorkdaySoftTheme]::SetSelected($entry[0],($Name -eq $entry[1]))}
    if ($Name -ne 'launcher.ps1') {
        $hint.Text = '선택한 화면을 여는 중입니다…'
        Open-WorkdayFeatureHost $script:FeatureHosts $Name $form.Handle.ToInt64()
        [void](Update-WorkdayFeatureHosts $script:FeatureHosts)
        return
    }
    $arguments = @('-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', "`"$(Join-Path $PSScriptRoot $Name)`"")
    if ($Name -ne 'launcher.ps1') { $arguments += @('-OwnerHandle', $form.Handle.ToInt64()) }
    $child = Start-WorkdayHiddenProcess "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" ($arguments -join ' ')
    $child.Dispose()
}
$attendance = New-Object Windows.Forms.Button
$attendance.Text = '근태 자동관리 설정'
$attendance.Location = New-Object Drawing.Point(30, 289)
$attendance.Size = New-Object Drawing.Size(173, 52)
$attendance.Add_Click({ Open-Feature 'control.ps1' })
$form.Controls.Add($attendance)
$overtime = New-Object Windows.Forms.Button
$overtime.Text = '시간외근무 신청'
$overtime.Location = New-Object Drawing.Point(442, 289)
$overtime.Size = New-Object Drawing.Size(173, 52)
$overtime.Add_Click({ Open-Feature 'overtime.ps1' })
$form.Controls.Add($overtime)
$corrections = New-Object Windows.Forms.Button
$corrections.Text = '휴가·행사 / 근태 정리'
$corrections.Location = New-Object Drawing.Point(236, 289)
$corrections.Size = New-Object Drawing.Size(173, 52)
$corrections.Add_Click({ Open-Feature 'corrections.ps1' })
$form.Controls.Add($corrections)
$trips=New-Object Windows.Forms.Button
$trips.Text='출장일지';$trips.Location=New-Object Drawing.Point(648,289);$trips.Size=New-Object Drawing.Size(173,52)
$trips.Add_Click({Open-Feature 'trips.ps1'});$form.Controls.Add($trips)
$hint = New-Object Windows.Forms.Label
$hint.Text = '자동 실행을 멈추거나 재개하려면 근태 자동관리 설정을 열어 주세요.'
$hint.Location = New-Object Drawing.Point(25, 437)
$hint.Size = New-Object Drawing.Size(795, 40)
$hint.TextAlign = 'MiddleCenter'
$form.Controls.Add($hint)
$security = New-Object Windows.Forms.Button
$security.Text = '실행 차단 / 보안 안내'
$security.Location = New-Object Drawing.Point(30, 378)
$security.Size = New-Object Drawing.Size(385, 42)
$security.Add_Click({ Open-Feature '보안안내.ps1' })
$form.Controls.Add($security)
. (Join-Path $PSScriptRoot 'session.ps1')
$health = New-Object Windows.Forms.Button
$health.Text = '실행 상태 · 로그인 결과 · 오류 로그'
$health.Location = New-Object Drawing.Point(430, 378); $health.Size = New-Object Drawing.Size(385, 42)
$health.Add_Click({ Open-Feature 'status.ps1' })
$form.Controls.Add($health)
foreach ($card in @(@(20, '01', '근태 자동관리', "예약 출퇴근 등록`n자동 실행 설정", '#4BAFC9'), @(226, '02', '휴가·근태 정정', "휴가 · 연장근무 제외일`n근무 기록 확인 및 정정", '#55B6A6'), @(432, '03', '시간외근무 신청', "월별 연장일 조회`n근무목적 입력 후 신청", '#EB8345'),@(638,'04','출장일지',"목표 금액 · 날짜 선택`n장소·목적 입력 후 등록",'#55B6A6'))) {
    $panel = New-Object Windows.Forms.Panel
    $panel.Location = New-Object Drawing.Point($card[0], 106)
    $panel.Size = New-Object Drawing.Size(193, 253)
    $panel.BackColor = [Drawing.Color]::White
    $bar = New-Object Windows.Forms.Label
    $bar.Location = New-Object Drawing.Point(0, 0); $bar.Size = New-Object Drawing.Size(193, 7)
    $bar.BackColor = [Drawing.ColorTranslator]::FromHtml($card[4])
    $panel.Controls.Add($bar)
    $number = New-Object Windows.Forms.Label
    $number.Text = $card[1]; $number.Font = New-Object Drawing.Font('Segoe UI', 26, [Drawing.FontStyle]::Bold)
    $number.ForeColor = $bar.BackColor; $number.Location = New-Object Drawing.Point(20, 22); $number.Size = New-Object Drawing.Size(90, 53)
    $panel.Controls.Add($number)
    $heading = New-Object Windows.Forms.Label
    $heading.Text = $card[2]; $heading.Font = New-Object Drawing.Font('Malgun Gothic', 12, [Drawing.FontStyle]::Bold)
    $heading.Location = New-Object Drawing.Point(12, 83); $heading.Size = New-Object Drawing.Size(177, 38)
    $panel.Controls.Add($heading)
    $detail = New-Object Windows.Forms.Label
    $detail.Text = $card[3]; $detail.Location = New-Object Drawing.Point(12, 127); $detail.Size = New-Object Drawing.Size(177, 50)
    $detail.ForeColor = [Drawing.ColorTranslator]::FromHtml('#788592')
    $panel.Controls.Add($detail)
    $form.Controls.Add($panel); $panel.SendToBack()
}
. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
$overtime.BackColor = $script:UiOrange
$security.BackColor = $script:UiCyan
$health.BackColor = $script:UiCyan
$attendance.Location = New-Object Drawing.Point(30,289)
$trips.BackColor=$script:UiMint
$attendance.BringToFront(); $corrections.BringToFront(); $overtime.BringToFront();$trips.BringToFront()
if ($SelfTest) { Write-UiPreview $form $PreviewPath; Write-Output 'LAUNCHER_UI_OK'; $form.Dispose(); exit 0 }
if (-not (Enter-WorkdayUi 'launcher')) { $form.Dispose(); exit 0 }
. (Join-Path $PSScriptRoot 'install-integration.ps1')
if ($PSScriptRoot -eq (Join-Path $env:LOCALAPPDATA 'AutoAttendance')) {
    try { [void](Register-AttendanceInstall $PSScriptRoot) } catch { [void][Windows.Forms.MessageBox]::Show(('앱 제거 정보 등록을 확인해 주세요. ' + $_.Exception.Message), '등록 확인') }
}
. (Join-Path $PSScriptRoot 'update.ps1')
$hint.Text = '자동 업데이트를 백그라운드에서 확인합니다.'
$script:StartupUpdateJob = $null
$script:StartupUpdatePhase = 'idle'
$script:StartupUpdateManifest = $null
$script:RestartAfterUpdate = $false
$updateTimer = New-Object Windows.Forms.Timer
$updateTimer.Interval = 50
$updateTimer.Add_Tick({
    $featureError = @(Update-WorkdayFeatureHosts $script:FeatureHosts)
    if ($featureError.Count) { $hint.Text = $featureError[-1] }
    if ($script:StartupUpdatePhase -eq 'waiting') {
        if ((Test-WorkdayFeatureBusy $script:FeatureHosts) -or @($script:FeatureHosts.Values | Where-Object {$_.phase -eq 'warming'}).Count) { return }
        foreach ($button in $form.Controls) { if ($button -is [Windows.Forms.Button]) { $button.Enabled = $false } }
        $hint.Text = '새 버전을 적용하고 있습니다. 완료되면 메뉴가 다시 열립니다.'
        $script:StartupUpdatePhase = 'applying'
        $script:StartupUpdateJob = Start-WorkdayUpdateJob $PSScriptRoot $script:StartupUpdateManifest
        return
    }
    $job = $script:StartupUpdateJob
    if (-not $job -or -not $job.pending.IsCompleted) { return }
    try {
        $result = @($job.pipeline.EndInvoke($job.pending))
        if ($job.pipeline.Streams.Error.Count) { throw $job.pipeline.Streams.Error[0].Exception }
        if (-not $result.Count) { throw '업데이트 확인 결과가 없습니다.' }
        $value = $result[-1]
        if ($script:StartupUpdatePhase -eq 'checking') {
            $hint.Text = $value.status
            if ($value.available) { $script:StartupUpdateManifest = $value.manifest; $script:StartupUpdatePhase = 'waiting' }
            else { $script:StartupUpdatePhase = 'done' }
        } else {
            $hint.Text = [string]$value
            $script:StartupUpdatePhase = 'done'
            if ($hint.Text.StartsWith('업데이트 적용 완료')) { $script:RestartAfterUpdate = $true; $form.Close() }
        }
    } catch {
        $hint.Text = '업데이트 확인/적용 보류: ' + $_.Exception.Message
        $script:StartupUpdatePhase = 'done'
    } finally {
        $job.pipeline.Dispose()
        $script:StartupUpdateJob = $null
        if ($script:StartupUpdatePhase -eq 'done') {
            foreach ($button in $form.Controls) { if ($button -is [Windows.Forms.Button]) { $button.Enabled = $true } }
        }
    }
})
$form.Add_Shown({
    $script:FeatureHosts = New-WorkdayFeatureHosts $PSScriptRoot
    $script:StartupUpdatePhase = 'checking'
    $script:StartupUpdateJob = Start-WorkdayUpdateJob $PSScriptRoot
    $updateTimer.Start()
})
$form.Add_FormClosing({
    if ($script:StartupUpdatePhase -eq 'applying' -or (Test-WorkdayFeatureBusy $script:FeatureHosts)) { $_.Cancel = $true }
})
try { [void]$form.ShowDialog() } finally {
    $updateTimer.Stop(); $updateTimer.Dispose()
    Exit-WorkdayUi
    Close-WorkdayFeatureHosts $script:FeatureHosts
    if ($script:StartupUpdateJob) { $script:StartupUpdateJob.pipeline.Stop(); $script:StartupUpdateJob.pipeline.Dispose() }
}
if ($script:RestartAfterUpdate) { Open-Feature 'launcher.ps1' }
