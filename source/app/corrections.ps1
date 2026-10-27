[CmdletBinding()]
param([switch]$SelfTest, [string]$PreviewPath, [long]$OwnerHandle=0)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $PSScriptRoot 'session.ps1')
$dataRoot=Join-Path $PSScriptRoot 'dist'
$script:worker=$null; $script:snapshot=@{}; $script:jobPath=$null
$form=New-Object Windows.Forms.Form
$form.Text='근태매니저 — 휴가·연장 제외일 및 근태 정정'
$form.Size=New-Object Drawing.Size(1050,730)
$form.StartPosition='CenterScreen'; $form.FormBorderStyle='FixedDialog'; $form.MaximizeBox=$false
$form.Font=New-Object Drawing.Font('Malgun Gothic',10)
function Label($text,$x,$y,$width) {
 $c=New-Object Windows.Forms.Label; $c.Text=$text; $c.Location=New-Object Drawing.Point($x,$y); $c.Size=New-Object Drawing.Size($width,30); $form.Controls.Add($c)
}
function Button($text,$x,$y,$width) {
 $c=New-Object Windows.Forms.Button; $c.Text=$text; $c.Location=New-Object Drawing.Point($x,$y); $c.Size=New-Object Drawing.Size($width,38); $form.Controls.Add($c); return $c
}
Label '휴가·제외일 설정은 자동 등록에 반영됩니다. 기존 사이트 기록은 아래에서 별도로 정정하세요.' 20 15 995
Label '설정 날짜' 20 61 85
$dayPicker=New-Object Windows.Forms.DateTimePicker
$dayPicker.Format='Custom'; $dayPicker.CustomFormat='yyyy-MM-dd'
$dayPicker.Location=New-Object Drawing.Point(110,56); $dayPicker.Width=150; $form.Controls.Add($dayPicker)
$vacation=New-Object Windows.Forms.CheckBox
$vacation.Text='휴가 (출퇴근 자동 등록 제외)'; $vacation.Location=New-Object Drawing.Point(280,58); $vacation.Size=New-Object Drawing.Size(260,28); $form.Controls.Add($vacation)
$exclude=New-Object Windows.Forms.CheckBox
$exclude.Text='연장근무 제외'; $exclude.Location=New-Object Drawing.Point(550,58); $exclude.Size=New-Object Drawing.Size(180,28); $form.Controls.Add($exclude)
$saveRule=Button '선택 날짜 설정 저장' 770 53 240
Label '체크를 해제하고 저장하면 제외를 해제합니다. 연장 제외로 줄어든 일수를 다른 날짜로 자동 이동하지 않습니다.' 20 101 995
Label '조회 월' 20 147 85
$month=New-Object Windows.Forms.ComboBox; $month.DropDownStyle='DropDownList'; $month.Location=New-Object Drawing.Point(110,140); $month.Width=180
foreach($item in (Get-WorkdayMonthLabels (Get-Date))) { [void]$month.Items.Add($item) }; $month.SelectedIndex=0; $form.Controls.Add($month)
$scan=Button '사이트 근태 조회' 310 136 230
Label '계정은 자동관리 설정에 저장한 ID/PW를 사용합니다.' 560 147 450
$grid=New-Object Windows.Forms.DataGridView
$grid.Location=New-Object Drawing.Point(20,190); $grid.Size=New-Object Drawing.Size(990,260)
$grid.AllowUserToAddRows=$false; $grid.AllowUserToDeleteRows=$false; $grid.ReadOnly=$true; $grid.RowHeadersVisible=$false
$grid.SelectionMode='FullRowSelect'; $grid.MultiSelect=$false; $grid.AutoSizeColumnsMode='Fill'
foreach($spec in @(@('date','날짜'),@('checkin','기존 출근'),@('checkout','기존 퇴근'),@('rule','제외 설정 / 확인 상태'),@('note','기존 비고'))) {
 [void]$grid.Columns.Add($spec[0],$spec[1])
}
$form.Controls.Add($grid)
Label '정정 날짜' 20 471 90
$selected=New-Object Windows.Forms.Label; $selected.Text='조회 후 행 선택'; $selected.Location=New-Object Drawing.Point(115,471); $selected.Size=New-Object Drawing.Size(160,30); $form.Controls.Add($selected)
Label '실제 출근' 300 471 85
$checkin=New-Object Windows.Forms.TextBox; $checkin.Location=New-Object Drawing.Point(390,466); $checkin.Width=90; $form.Controls.Add($checkin)
Label '실제 퇴근' 520 471 85
$checkout=New-Object Windows.Forms.TextBox; $checkout.Location=New-Object Drawing.Point(610,466); $checkout.Width=90; $form.Controls.Add($checkout)
Label 'HH:MM / 비우면 기존 시간 유지' 730 471 280
Label '정정 사유' 20 517 90
$reason=New-Object Windows.Forms.TextBox; $reason.Location=New-Object Drawing.Point(115,512); $reason.Width=895; $reason.MaxLength=1000; $form.Controls.Add($reason)
$actual=New-Object Windows.Forms.CheckBox; $actual.Text='입력한 시간이 실제 근무 기록임을 확인했습니다.'; $actual.Location=New-Object Drawing.Point(20,557); $actual.Size=New-Object Drawing.Size(600,30); $form.Controls.Add($actual)
$apply=Button '변경 내용 확인 후 사이트 저장' 690 551 320; $apply.Enabled=$false
$status=New-Object Windows.Forms.Label; $status.Text='휴가는 사이트의 휴가 처리 규정에 따라 등록하세요. 정정 후 시간외근무 신청에서 월을 다시 조회하세요.'
$status.Location=New-Object Drawing.Point(20,610); $status.Size=New-Object Drawing.Size(990,65); $form.Controls.Add($status)
$timer=New-Object Windows.Forms.Timer; $timer.Interval=150
function Read-Rule {
 $vacation.Checked=$false; $exclude.Checked=$false
 $path=Join-Path $dataRoot '자동출퇴근상태.json'
 if(Test-Path -LiteralPath $path) {
  try {
   $state=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
   $key=$dayPicker.Value.ToString('yyyy-MM-dd'); $rule=$state.day_rules.$key
   $vacation.Checked=[bool]$rule.vacation; $exclude.Checked=[bool]$rule.exclude_overtime
  } catch { $status.Text='저장된 제외일을 읽지 못했습니다. 실행 상태에서 오류를 확인하세요.' }
 }
}
function Start-Job($job) {
 $python=Join-Path $PSScriptRoot 'runtime\python.exe'
 if(-not (Test-Path -LiteralPath $python)) { throw '설치된 프로그램에서 실행하세요.' }
 New-Item -ItemType Directory -Path $dataRoot -Force|Out-Null
 $script:jobPath=Join-Path $dataRoot ('attendance-job-'+[Guid]::NewGuid().ToString('N')+'.json')
 [IO.File]::WriteAllText($script:jobPath,($job|ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
 $script:operation=$job.operation
 $script:worker=Start-WorkdayHiddenProcess $python "`"$(Join-Path $PSScriptRoot 'main.py')`" --attendance-job `"$script:jobPath`"" $PSScriptRoot
 foreach($c in $form.Controls) { if($c -ne $status) { $c.Enabled=$false } }
 $status.Text='처리 중입니다. 사이트 응답을 기다려 주세요.'; $timer.Start()
}
$dayPicker.Add_ValueChanged({ Read-Rule })
$saveRule.Add_Click({try {Start-Job @{operation='rules';date=$dayPicker.Value.ToString('yyyy-MM-dd');vacation=$vacation.Checked;exclude_overtime=$exclude.Checked}}catch{ $status.Text=$_.Exception.Message }})
function Selected-Month { [DateTime]::ParseExact([string]$month.SelectedItem,'yyyy년 MM월',[Globalization.CultureInfo]::InvariantCulture).ToString('yyyy-MM') }
$scan.Add_Click({try {$grid.Rows.Clear();$script:snapshot=@{};Start-Job @{operation='scan';month=(Selected-Month)}}catch{$status.Text=$_.Exception.Message}})
$month.Add_SelectedIndexChanged({$grid.Rows.Clear();$script:snapshot=@{};$apply.Enabled=$false;$selected.Text='조회 후 행 선택'})
$grid.Add_SelectionChanged({
 if($grid.SelectedRows.Count -eq 0) {$apply.Enabled=$false;return}
 $key=[string]$grid.SelectedRows[0].Cells['date'].Value
 $selected.Text=$key; $checkin.Clear();$checkout.Clear();$actual.Checked=$false;$reason.Clear()
 $dayPicker.Value=[DateTime]::ParseExact($key,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture);Read-Rule
 $apply.Enabled=$true
})
$apply.Add_Click({
 try {
  if(-not $actual.Checked) {throw '실제 근무 시간 확인에 체크하세요.'}
  if([string]::IsNullOrWhiteSpace($reason.Text)) {throw '정정 사유를 입력하세요.'}
  $key=$selected.Text; $before=$script:snapshot[$key]
  if(-not $before) {throw '사이트 기록을 다시 조회하세요.'}
  foreach($value in @($checkin.Text,$checkout.Text)) {if($value -and $value -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') {throw '시간은 HH:MM 형식으로 입력하세요.'}}
  if(-not $checkin.Text -and -not $checkout.Text) {throw '정정할 시간을 입력하세요.'}
  $newIn=if($checkin.Text){$checkin.Text}else{'기존 유지'}; $newOut=if($checkout.Text){$checkout.Text}else{'기존 유지'}
  $message="$key`n출근: $($before.checkin) → $newIn`n퇴근: $($before.checkout) → $newOut`n사유: $($reason.Text)`n실제 근무 기록으로 저장할까요?"
  if([Windows.Forms.MessageBox]::Show($form,$message,'근태 정정 확인','YesNo','Question') -ne 'Yes'){return}
  Start-Job @{operation='correct';month=(Selected-Month);date=$key;before=$before;checkin=$checkin.Text;checkout=$checkout.Text;reason=$reason.Text;confirmed_actual=$true}
 }catch{$status.Text=$_.Exception.Message}
})
$timer.Add_Tick({
 if(-not $script:worker -or -not $script:worker.HasExited){return};$timer.Stop()
 try {
  $result=Get-Content -LiteralPath ($script:jobPath+'.result.json') -Raw -Encoding UTF8|ConvertFrom-Json
  if(-not $result.ok){throw $result.error}
  if($script:operation -eq 'scan') {
   $grid.Rows.Clear();$script:snapshot=@{}
   foreach($row in $result.rows){
    $script:snapshot[$row.date]=@{checkin=$row.checkin;checkout=$row.checkout;note=$row.note}
    $ruleText=if($row.rule.manual_hold){'자동 처리 보류 · 사이트 확인'}elseif($row.rule.vacation){'휴가'}elseif($row.rule.exclude_overtime){'연장 제외'}else{''}
    [void]$grid.Rows.Add($row.date,$row.checkin,$row.checkout,$ruleText,$row.note)
   }
   $status.Text='정정할 행을 선택하고 실제 시간과 사유를 입력하세요. 빈 입력칸은 기존 값을 유지합니다.'
  }else{
   $status.Text=$result.message
   $grid.Rows.Clear();$script:snapshot=@{};$selected.Text='조회 후 행 선택';Read-Rule
  }
 }catch{$status.Text='처리 확인 필요: '+$_.Exception.Message+' (결과가 불확실하면 사이트를 확인하고 다시 조회하세요.)'}
 finally{
  $script:worker.Dispose();$script:worker=$null
  Remove-Item -LiteralPath $script:jobPath,($script:jobPath+'.result.json') -Force -ErrorAction SilentlyContinue
  foreach($c in $form.Controls){$c.Enabled=$true};$apply.Enabled=($grid.SelectedRows.Count -gt 0)
 }
})
$form.Add_FormClosing({if($script:worker){$_.Cancel=$true;$status.Text='진행 중인 처리가 끝난 뒤 닫아 주세요.'}})
. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
$apply.BackColor=$script:UiOrange
if($SelfTest){
 if($dayPicker.CustomFormat -ne 'yyyy-MM-dd' -or $grid.Columns.Count -ne 5){throw '정정 화면 구조 오류'}
 Write-UiPreview $form $PreviewPath;Write-Output 'CORRECTIONS_UI_OK';$form.Dispose();$timer.Dispose();exit 0
}
Read-Rule
if(-not (Enter-WorkdayUi 'corrections')){$form.Dispose();$timer.Dispose();exit 0}
try { Show-WorkdayDialog $form $OwnerHandle } finally {Exit-WorkdayUi;$timer.Dispose()}
