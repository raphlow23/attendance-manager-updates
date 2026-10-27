Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$icon = New-Object Windows.Forms.NotifyIcon
$icon.Icon = [Drawing.SystemIcons]::Warning
$icon.Visible = $true
$icon.BalloonTipTitle = '근태매니저 — 자동 재실행 중단'
$icon.BalloonTipText = '복구에 반복 실패했습니다. 프로그램의 상태 및 오류 로그와 Windows 보안 보호 기록을 확인한 뒤 다시 시작해 주세요.'
$icon.BalloonTipIcon = 'Warning'
$icon.ShowBalloonTip(12000)
try { for ($i=0; $i -lt 60; $i++) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 250 } } finally { $icon.Visible = $false; $icon.Dispose() }
