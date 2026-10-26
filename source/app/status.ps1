[CmdletBinding()]
param([switch]$SelfTest, [long]$OwnerHandle = 0)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = '근태매니저 — 상태 및 오류 로그'
$form.Size = New-Object Drawing.Size(960, 700)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$status = New-Object Windows.Forms.TextBox
$status.Multiline = $true; $status.ReadOnly = $true; $status.ScrollBars = 'Vertical'
$status.Location = New-Object Drawing.Point(20, 20); $status.Size = New-Object Drawing.Size(900, 120)
$status.Anchor = 'Top, Left, Right'; $form.Controls.Add($status)
$log = New-Object Windows.Forms.TextBox
$log.Multiline = $true; $log.ReadOnly = $true; $log.ScrollBars = 'Both'
$log.Location = New-Object Drawing.Point(20, 155); $log.Size = New-Object Drawing.Size(900, 420)
$log.Anchor = 'Top, Bottom, Left, Right'; $form.Controls.Add($log)
$refresh = New-Object Windows.Forms.Button
$refresh.Text = '상태 새로고침'; $refresh.Location = New-Object Drawing.Point(670, 595); $refresh.Size = New-Object Drawing.Size(250, 42)
$refresh.Anchor = 'Bottom, Right'; $form.Controls.Add($refresh)
function Update-WorkdayStatus {
    $data = Join-Path $PSScriptRoot 'dist'
    $lines = @()
    foreach ($spec in @(@('guardian-status.json','감시 프로세스'), @('worker-health.json','자동 로그인 작업'))) {
        $path = Join-Path $data $spec[0]
        if (Test-Path -LiteralPath $path) {
            try {
                $value = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($spec[0] -eq 'guardian-status.json') { $lines += "감시 상태: $($value.state) / 재시도: $($value.restart_count) / 오류: $($value.last_error)" }
                else {
                    $beat = '아직 없음'; $login = '아직 없음'
                    if ($value.heartbeat_utc) { $beat = [DateTime]::Parse($value.heartbeat_utc).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss') }
                    if ($value.last_login_verified_utc) { $login = [DateTime]::Parse($value.last_login_verified_utc).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss') }
                    $lines += "응답: $beat / 사이트 연결: $($value.network_online) / 실제 로그인 확인: $login"
                    $lines += "출근: $($value.jobs.checkin.stage) / 퇴근: $($value.jobs.checkout.stage)"
                }
            } catch { $lines += "$($spec[1]): 상태를 읽는 중입니다." }
        } else { $lines += "$($spec[1]): 아직 실행 기록이 없습니다." }
    }
    if (Test-Path -LiteralPath (Join-Path $data 'automation.stop')) { $lines += '사용자 정지 상태: 자동 재실행하지 않습니다. 근태 자동관리 설정에서 다시 시작을 누르세요.' }
    $status.Text = $lines -join "`r`n"
    $text = @()
    foreach ($name in @('guardian.log','자동출퇴근.log','restart-failed.notice.txt')) {
        $path = Join-Path $data $name
        if (Test-Path -LiteralPath $path) { $text += "[$name]"; $text += Get-Content -LiteralPath $path -Tail 70 -Encoding UTF8 }
    }
    $log.Text = $text -join "`r`n"
}
$refresh.Add_Click({ Update-WorkdayStatus })
. (Join-Path $PSScriptRoot 'theme.ps1'); Set-UiTheme $form
Update-WorkdayStatus
if ($SelfTest) { Write-Output 'STATUS_UI_OK: liveness/connectivity/login verification distinguished'; $form.Dispose(); exit 0 }
. (Join-Path $PSScriptRoot 'session.ps1')
Show-WorkdayDialog $form $OwnerHandle
