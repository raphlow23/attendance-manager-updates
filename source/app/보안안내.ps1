[CmdletBinding()]
param([switch]$SelfTest, [long]$OwnerHandle = 0)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = '근태매니저 — 실행 차단 및 보안 안내'
$form.Size = New-Object Drawing.Size(760, 545)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$text = New-Object Windows.Forms.TextBox
$text.Multiline = $true; $text.ReadOnly = $true; $text.ScrollBars = 'Vertical'
$text.Location = New-Object Drawing.Point(20, 20); $text.Size = New-Object Drawing.Size(700, 350)
$text.Text = @"
실행이 중단되면 먼저 Windows 보안의 보호 기록에서 정확한 탐지명과 차단 파일을 확인해 주세요.

Defender 제외 안내
Windows 보안 → 바이러스 및 위협 방지 → 설정 관리 → 제외 추가 또는 제거.
정상 파일임을 확인한 후 필요하다면 탐지된 개별 파일만 선택합니다.
폴더 전체 또는 Python 프로세스 전체를 무조건 제외할 필요는 없습니다.

SmartScreen / Smart App Control
새 EXE의 평판·서명에 대한 경고는 Defender 백신 제외와 다른 기능입니다.
백신 제외를 추가해도 해결되지 않을 수 있으며 회사 정책은 관리자 확인이 필요합니다.

방화벽
이 프로그램은 외부 웹사이트에 접속합니다. 일반적으로 인바운드 포트 개방은 필요 없습니다.
회사에서 외부 접속을 차단한 경우 관리자에게 사이트와 Chrome/Python의 아웃바운드 접속 허용을 문의하세요.

프로그램 설치 경로: $PSScriptRoot
실행 로그: $(Join-Path $PSScriptRoot 'dist\자동출퇴근.log')

보안 기능과 방화벽 규칙은 이 안내 화면에서 자동 변경하지 않습니다.
프로그램 전체 또는 점검 작업까지 차단되면 프로그램 자체 알림도 표시되지 않을 수 있습니다.
"@
$form.Controls.Add($text)
$security = New-Object Windows.Forms.Button
$security.Text = 'Windows 보안 열기'; $security.Location = New-Object Drawing.Point(20, 390); $security.Size = New-Object Drawing.Size(215, 45)
$security.Add_Click({ Start-Process 'windowsdefender:' })
$form.Controls.Add($security)
$copy = New-Object Windows.Forms.Button
$copy.Text = '설치 경로 복사'; $copy.Location = New-Object Drawing.Point(250, 390); $copy.Size = New-Object Drawing.Size(215, 45)
$copy.Add_Click({ [Windows.Forms.Clipboard]::SetText($PSScriptRoot) })
$form.Controls.Add($copy)
$folder = New-Object Windows.Forms.Button
$folder.Text = '설치 폴더 열기'; $folder.Location = New-Object Drawing.Point(480, 390); $folder.Size = New-Object Drawing.Size(240, 45)
$folder.Add_Click({ Start-Process 'explorer.exe' -ArgumentList "`"$PSScriptRoot`"" })
$form.Controls.Add($folder)
. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
if ($SelfTest) { Write-Output 'SECURITY_HELP_UI_OK: no exclusions or firewall changes'; $form.Dispose(); exit 0 }
. (Join-Path $PSScriptRoot 'session.ps1')
Show-WorkdayDialog $form $OwnerHandle
