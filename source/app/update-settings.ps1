[CmdletBinding()]
param([switch]$SelfTest)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = '근태매니저 — 자동 업데이트'
$form.Size = New-Object Drawing.Size(720, 310)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('Malgun Gothic', 10)
$label = New-Object Windows.Forms.Label
$label.Text = "프로그램 실행 시 게시자가 서명한 새 버전을 확인합니다.`n배포 주소가 연결되기 전에는 자동 다운로드가 실행되지 않습니다."
$label.Location = New-Object Drawing.Point(20, 20); $label.Size = New-Object Drawing.Size(660, 55)
$form.Controls.Add($label)
$enabled = New-Object Windows.Forms.CheckBox
$enabled.Text = '실행 시 자동 업데이트 확인'; $enabled.Location = New-Object Drawing.Point(20, 85); $enabled.Size = New-Object Drawing.Size(400, 30)
$form.Controls.Add($enabled)
$url = New-Object Windows.Forms.TextBox
$url.Location = New-Object Drawing.Point(20, 130); $url.Size = New-Object Drawing.Size(660, 28)
$form.Controls.Add($url)
$path = Join-Path $PSScriptRoot 'dist\업데이트설정.json'
$defaultPath = Join-Path $PSScriptRoot 'update-config.json'
$readPath = $defaultPath
if (Test-Path -LiteralPath $path) { $readPath = $path }
if (Test-Path -LiteralPath $readPath) {
    $current = Get-Content -LiteralPath $readPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $enabled.Checked = [bool]$current.enabled; $url.Text = $current.manifest_url
}
$save = New-Object Windows.Forms.Button
$save.Text = '설정 저장'; $save.Location = New-Object Drawing.Point(450, 193); $save.Size = New-Object Drawing.Size(230, 42)
$save.Add_Click({
    try {
        if ($enabled.Checked -and (-not $url.Text.Trim() -or ([Uri]$url.Text.Trim()).Scheme -ne 'https')) { throw '게시자의 HTTPS 업데이트 주소를 입력해 주세요.' }
        New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
        [IO.File]::WriteAllText($path, (@{ enabled = $enabled.Checked; manifest_url = $url.Text.Trim() } | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
        [void][Windows.Forms.MessageBox]::Show('다음 실행부터 적용됩니다.', '저장 완료'); $form.Close()
    } catch { [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, '설정 확인') }
})
$form.Controls.Add($save)
. (Join-Path $PSScriptRoot 'theme.ps1'); Set-UiTheme $form
if ($SelfTest) { Write-Output 'UPDATE_SETTINGS_UI_OK'; $form.Dispose(); exit 0 }
[void]$form.ShowDialog()
