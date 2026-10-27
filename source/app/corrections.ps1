[CmdletBinding()]
param([switch]$SelfTest, [string]$PreviewPath, [long]$OwnerHandle=0)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $PSScriptRoot 'session.ps1')
$dataRoot=Join-Path $PSScriptRoot 'dist'
$script:worker=$null; $script:snapshot=@{}; $script:jobPath=$null
$script:reviewId=$null;$script:reviewBaseRows=@();$script:reviewTargetDays=0;$script:loadingReview=$false
$form=New-Object Windows.Forms.Form
$form.Text='출근정리 — 휴가·연장 제외일 및 근태 정정'
$form.Size=New-Object Drawing.Size(1050,880)
$form.StartPosition='CenterScreen'; $form.FormBorderStyle='FixedDialog'; $form.MaximizeBox=$false
$form.Font=New-Object Drawing.Font('Malgun Gothic',10)
function Label($text,$x,$y,$width) {
 $c=New-Object Windows.Forms.Label; $c.Text=$text; $c.Location=New-Object Drawing.Point($x,$y); $c.Size=New-Object Drawing.Size($width,30); $form.Controls.Add($c)
}
function Button($text,$x,$y,$width) {
 $c=New-Object Windows.Forms.Button; $c.Text=$text; $c.Location=New-Object Drawing.Point($x,$y); $c.Size=New-Object Drawing.Size($width,38); $form.Controls.Add($c); return $c
}
Label '달력 저장 → 수정 목록 조회 → 날짜·시간 확인 → 선택 내역 정리 순서로 실행하세요.' 20 15 730
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
$scan=Button '선택 월 수정 목록 조회' 310 136 230
Label '계정은 자동관리 설정에 저장한 ID/PW를 사용합니다.' 560 147 450
$grid=New-Object Windows.Forms.DataGridView
$grid.Location=New-Object Drawing.Point(20,190); $grid.Size=New-Object Drawing.Size(990,260)
$grid.AllowUserToAddRows=$false; $grid.AllowUserToDeleteRows=$false; $grid.ReadOnly=$false; $grid.RowHeadersVisible=$false
$grid.SelectionMode='FullRowSelect'; $grid.MultiSelect=$false; $grid.AutoSizeColumnsMode='Fill'
$chooseColumn=New-Object Windows.Forms.DataGridViewCheckBoxColumn
$chooseColumn.Name='choose';$chooseColumn.HeaderText='선택';$chooseColumn.FillWeight=35
[void]$grid.Columns.Add($chooseColumn)
foreach($spec in @(@('date','날짜',95),@('before_checkin','기존 출근',75),@('before_checkout','기존 퇴근',75),@('checkin','변경 출근',85),@('checkout','변경 퇴근',85),@('reason','정리 사유',160),@('status','상태',160),@('note','비고',140))) {
 $column=New-Object Windows.Forms.DataGridViewTextBoxColumn
 $column.Name=$spec[0];$column.HeaderText=$spec[1];$column.FillWeight=$spec[2]
 $column.ReadOnly=($spec[0] -notin @('checkin','checkout'))
 [void]$grid.Columns.Add($column)
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
# Make room for the saved-date list above the site-query controls.
foreach($control in $form.Controls){
 if($control.Top -ge 130){$control.Top+=130}
}
$grid.Height=230
$rulesGrid=New-Object Windows.Forms.DataGridView
$rulesGrid.Location=New-Object Drawing.Point(20,140);$rulesGrid.Size=New-Object Drawing.Size(990,110)
$rulesGrid.AllowUserToAddRows=$false;$rulesGrid.AllowUserToDeleteRows=$false;$rulesGrid.ReadOnly=$true
$rulesGrid.RowHeadersVisible=$false;$rulesGrid.SelectionMode='FullRowSelect';$rulesGrid.MultiSelect=$false
$rulesGrid.AutoSizeColumnsMode='Fill'
foreach($spec in @(@('date','저장 날짜 (선택하여 설정 변경)'),@('vacation','휴가'),@('exclude','연장근무 제외'),@('hold','자동 처리 보류'))){[void]$rulesGrid.Columns.Add($spec[0],$spec[1])}
$form.Controls.Add($rulesGrid)
$summaryLabel=New-Object Windows.Forms.Label
$summaryLabel.Text='사이트 연장 기록: 조회 전 (근무일 19:00 이후 퇴근 기준)'
$summaryLabel.Location=New-Object Drawing.Point(20,558);$summaryLabel.Size=New-Object Drawing.Size(990,35)
$form.Controls.Add($summaryLabel)
$form.Controls.Remove($dayPicker)
foreach($control in @($form.Controls)){
 if($control.Text -eq '설정 날짜' -or $control.Text.StartsWith('체크를 해제하고 저장하면')){$form.Controls.Remove($control);$control.Dispose();continue}
 if($control.Top -ge 595){$control.Top+=24}
 elseif($control.Top -ge 260 -and $control.Top -le 300){$control.Top+=75}
}
$grid.Top=390;$grid.Height=180;$summaryLabel.Top=575

$vacation.Location=New-Object Drawing.Point(245,302);$exclude.Top=302;$saveRule.Top=298
$rulesGrid.Location=New-Object Drawing.Point(650,45);$rulesGrid.Size=New-Object Drawing.Size(360,205)
$deleteRule=Button '선택 항목 삭제' 650 255 360
$rulesGrid.Columns['date'].HeaderText='저장 날짜';$rulesGrid.Columns['date'].FillWeight=130
$rulesGrid.Columns['hold'].HeaderText='처리 상태'
$calendar=New-Object Windows.Forms.Panel
$calendar.Location=New-Object Drawing.Point(20,45);$calendar.Size=New-Object Drawing.Size(610,245);$calendar.BackColor=[Drawing.Color]::White
$form.Controls.Add($calendar)
$script:calendarMonth=(Get-Date -Day 1).Date
$script:chosenDates=New-Object 'Collections.Generic.HashSet[string]'
$script:savedRules=[PSCustomObject]@{}
$calendarTitle=New-Object Windows.Forms.Label
$calendarTitle.Location=New-Object Drawing.Point(110,8);$calendarTitle.Size=New-Object Drawing.Size(340,30);$calendarTitle.TextAlign='MiddleCenter';$calendar.Controls.Add($calendarTitle)
$chosenLabel=New-Object Windows.Forms.Label
$chosenLabel.Location=New-Object Drawing.Point(20,303);$chosenLabel.Size=New-Object Drawing.Size(220,30);$form.Controls.Add($chosenLabel)
$calendarPrev=New-Object Windows.Forms.Button;$calendarPrev.Text='◀';$calendarPrev.Location=New-Object Drawing.Point(5,5);$calendarPrev.Size=New-Object Drawing.Size(45,32);$calendar.Controls.Add($calendarPrev)
$calendarNext=New-Object Windows.Forms.Button;$calendarNext.Text='▶';$calendarNext.Location=New-Object Drawing.Point(55,5);$calendarNext.Size=New-Object Drawing.Size(45,32);$calendar.Controls.Add($calendarNext)
$clearDates=New-Object Windows.Forms.Button;$clearDates.Text='선택 해제';$clearDates.Location=New-Object Drawing.Point(485,5);$clearDates.Size=New-Object Drawing.Size(115,32);$calendar.Controls.Add($clearDates)
for($column=0;$column -lt 7;$column++){
 $dayLabel=New-Object Windows.Forms.Label;$dayLabel.Text=@('일','월','화','수','목','금','토')[$column]
 $dayLabel.Location=New-Object Drawing.Point((5+$column*86),40);$dayLabel.Size=New-Object Drawing.Size(82,23);$dayLabel.TextAlign='MiddleCenter';$calendar.Controls.Add($dayLabel)
}
$script:calendarButtons=@()
for($cell=0;$cell -lt 42;$cell++){
 $button=New-Object Windows.Forms.Button;$button.FlatStyle='Flat';$button.FlatAppearance.BorderSize=0
 $button.Location=New-Object Drawing.Point((5+($cell%7)*86),(65+[Math]::Floor($cell/7)*29));$button.Size=New-Object Drawing.Size(82,27)
 $button.Font=New-Object Drawing.Font('Malgun Gothic',9)
 $button.Add_Click({param($sender,$eventArgs)
  $key=[string]$sender.Tag
  if($script:chosenDates.Contains($key)){[void]$script:chosenDates.Remove($key)}else{[void]$script:chosenDates.Add($key)}
  Render-Calendar
 })
 $calendar.Controls.Add($button);$script:calendarButtons+=$button
}
function Render-Calendar {
 $calendarTitle.Text=$script:calendarMonth.ToString('yyyy년 MM월')+' · 휴가: 휴 / 연장 제외: 제'
 $offset=[int]$script:calendarMonth.DayOfWeek
 $length=[DateTime]::DaysInMonth($script:calendarMonth.Year,$script:calendarMonth.Month)
 for($index=0;$index -lt 42;$index++){
  $button=$script:calendarButtons[$index];$number=$index-$offset+1
  if($number -lt 1 -or $number -gt $length){$button.Visible=$false;$button.Text='';$button.Tag='';$button.BackColor=[Drawing.Color]::White;continue}
  $button.Visible=$true
  $key=$script:calendarMonth.AddDays($number-1).ToString('yyyy-MM-dd');$button.Tag=$key
  $rule=$script:savedRules.$key
  $marker=if($rule.vacation -and $rule.exclude_overtime){' 휴·제'}elseif($rule.vacation){' 휴'}elseif($rule.exclude_overtime){' 제'}else{''}
  $button.Text=[string]$number+$marker
  $button.BackColor=if($script:chosenDates.Contains($key)){[Drawing.ColorTranslator]::FromHtml('#E98244')}elseif($rule.vacation){[Drawing.ColorTranslator]::FromHtml('#55B6A6')}elseif($rule.exclude_overtime){[Drawing.ColorTranslator]::FromHtml('#4BAFC9')}else{[Drawing.ColorTranslator]::FromHtml('#F1F3F7')}
  $button.ForeColor=[Drawing.ColorTranslator]::FromHtml('#343C46')
 }
 $chosenLabel.Text="선택 $($script:chosenDates.Count)개 · 재클릭하면 해제"
 $saveRule.Text="선택 $($script:chosenDates.Count)개 설정 저장"
}
$calendarPrev.Add_Click({$script:calendarMonth=$script:calendarMonth.AddMonths(-1);Render-Calendar})
$calendarNext.Add_Click({$script:calendarMonth=$script:calendarMonth.AddMonths(1);Render-Calendar})
$clearDates.Add_Click({$script:chosenDates.Clear();Render-Calendar})
$script:loadingRuleList=$false
function Set-RuleRows($Rules) {
 $script:savedRules=if($Rules){$Rules}else{[PSCustomObject]@{}}
 $script:loadingRuleList=$true
 try {
  $rulesGrid.Rows.Clear()
  if($Rules){foreach($property in ($Rules.PSObject.Properties|Sort-Object Name)){
   $rule=$property.Value
   if(-not ($rule.vacation -or $rule.exclude_overtime -or $rule.manual_hold)){continue}
   $day=[DateTime]::MinValue
   if(-not [DateTime]::TryParseExact($property.Name,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::None,[ref]$day)){continue}
   $vacText=if($rule.vacation){'휴가'}else{''}
   $excludeText=if($rule.exclude_overtime){'제외'}else{''}
   $holdText=if($rule.manual_hold){'사이트 확인 필요'}else{''}
   [void]$rulesGrid.Rows.Add($property.Name,$vacText,$excludeText,$holdText)
  }}
  $rulesGrid.ClearSelection()
 }finally{$script:loadingRuleList=$false;Render-Calendar}
}
function Refresh-RuleList {
 $path=Join-Path $dataRoot '자동출퇴근상태.json'
 if(Test-Path -LiteralPath $path){
  $state=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
  Set-RuleRows $state.day_rules
 }else{Set-RuleRows $null}
}
function Select-SavedRule {
 if($script:loadingRuleList -or $rulesGrid.SelectedRows.Count -eq 0){return}
 $dayPicker.Value=[DateTime]::ParseExact([string]$rulesGrid.SelectedRows[0].Cells['date'].Value,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)
 $script:chosenDates.Clear();[void]$script:chosenDates.Add($dayPicker.Value.ToString('yyyy-MM-dd'))
 $script:calendarMonth=New-Object DateTime($dayPicker.Value.Year,$dayPicker.Value.Month,1)
 Read-Rule
 Render-Calendar
}
$rulesGrid.Add_SelectionChanged({Select-SavedRule})
$rulesGrid.Add_CellClick({Select-SavedRule})
$timer=New-Object Windows.Forms.Timer; $timer.Interval=150
function Read-Rule {
 $vacation.Checked=$false; $exclude.Checked=$false
 $path=Join-Path $dataRoot '자동출퇴근상태.json'
 if(Test-Path -LiteralPath $path) {
  try {
   $state=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
   $key=$dayPicker.Value.ToString('yyyy-MM-dd'); $rule=$state.day_rules.$key
   $vacation.Checked=[bool]$rule.vacation; $exclude.Checked=([bool]$rule.exclude_overtime -and -not $vacation.Checked)
  } catch { $status.Text='저장된 제외일을 읽지 못했습니다. 실행 상태에서 오류를 확인하세요.' }
 }
}
function Clock-Minutes($Value) {
 $text=([string]$Value)-replace '\s',''
 if($text -match '^(\d{1,2}):(\d{1,2})$'){
  $h=[int]$Matches[1];$m=[int]$Matches[2]
  if($h -lt 24 -and $m -lt 60){return $h*60+$m}
 }
 return -1
}
function Format-Clock($Value) {
 $m=Clock-Minutes $Value
 if($m -lt 0){return ''}
 return ('{0:D2}:{1:D2}' -f [int][Math]::Floor($m/60),($m%60))
}
function Update-ReviewSummary {
 if($script:loadingReview){return}
 $times=@{}
 foreach($entry in $script:reviewBaseRows){$times[$entry.date]=@{ci=(Clock-Minutes $entry.checkin);co=(Clock-Minutes $entry.checkout);eligible=[bool]$entry.eligible}}
 $chosen=0;$valid=$true
 foreach($row in $grid.Rows){
  if(-not $row.Cells['choose'].Value){continue}
  $chosen++;$ci=Clock-Minutes $row.Cells['checkin'].Value;$co=Clock-Minutes $row.Cells['checkout'].Value
  if($ci -lt 0 -or $co -lt 0 -or $ci -ge $co){$valid=$false}
  $key=[string]$row.Cells['date'].Value
  if($times.ContainsKey($key)){$times[$key].ci=$ci;$times[$key].co=$co}
 }
 $overtime=@($times.Values|Where-Object{$_.eligible -and $_.ci -ge 0 -and $_.co -ge 1140 -and $_.ci -lt $_.co}).Count
 $summaryLabel.Text=if($valid){"선택 $chosen 건 · 선택 내용 반영 시 연장 $overtime / 기준 $script:reviewTargetDays 일 · 체크 해제 = 이번 정리 제외"}else{'변경 시간은 HH:MM으로 입력하고 출근이 퇴근보다 이른지 확인하세요.'}
 $apply.Enabled=([bool]$script:reviewId -and $chosen -gt 0 -and $valid -and -not $script:worker)
}
function Set-ReviewView($Result) {
 $script:loadingReview=$true
 try{
  $grid.Rows.Clear();$script:snapshot=@{}
  $script:reviewId=[string]$Result.plan_id;$script:reviewBaseRows=@($Result.all_rows);$script:reviewTargetDays=[int]$Result.target_days
  foreach($entry in $Result.rows){
   $script:snapshot[$entry.date]=$entry.before
   $ci=if($entry.after.checkin){$entry.after.checkin}else{Format-Clock $entry.before.checkin}
   $co=if($entry.after.checkout){$entry.after.checkout}else{Format-Clock $entry.before.checkout}
   $rowStatus=if($script:reviewId){$entry.status}else{'정리 완료'}
   $index=$grid.Rows.Add(([bool]$script:reviewId -and [bool]$entry.selectable),$entry.date,$entry.before.checkin,$entry.before.checkout,$ci,$co,$entry.reason,$rowStatus,$entry.before.note)
   $locked=(-not $script:reviewId -or [bool]$entry.blocked)
   foreach($name in @('choose','checkin','checkout')){$grid.Rows[$index].Cells[$name].ReadOnly=$locked}
  }
  $status.Text=$Result.message
 }finally{$script:loadingReview=$false;Update-ReviewSummary}
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
 $status.Text=if($Job.operation -in @('rules','rules_delete')){'저장 날짜 설정을 변경 중입니다. 사이트에는 접속하지 않습니다.'}else{'사이트 처리 중입니다. 완료될 때까지 기다려 주세요.'}; $timer.Start()
}
$dayPicker.Add_ValueChanged({ Read-Rule })
$vacation.Add_CheckedChanged({if($vacation.Checked){$exclude.Checked=$false}})
$exclude.Add_CheckedChanged({if($exclude.Checked){$vacation.Checked=$false}})
$saveRule.Add_Click({try {
 if($script:chosenDates.Count -eq 0){throw '달력에서 저장할 날짜를 선택하세요. 여러 날짜를 클릭할 수 있습니다.'}
 Start-Job @{operation='rules';dates=@($script:chosenDates|Sort-Object);vacation=$vacation.Checked;exclude_overtime=$exclude.Checked}
}catch{ $status.Text=$_.Exception.Message }})
$deleteRule.Add_Click({try {
 if($rulesGrid.SelectedRows.Count -eq 0){throw '오른쪽 저장 날짜 목록에서 삭제할 항목을 선택하세요.'}
 $key=[string]$rulesGrid.SelectedRows[0].Cells['date'].Value
 Start-Job @{operation='rules_delete';dates=@($key)}
}catch{$status.Text=$_.Exception.Message}})
function Selected-Month { [DateTime]::ParseExact([string]$month.SelectedItem,'yyyy년 MM월',[Globalization.CultureInfo]::InvariantCulture).ToString('yyyy-MM') }
$scan.Add_Click({try {$summaryLabel.Text='수정 예정 목록을 조회 중입니다.';$grid.Rows.Clear();$script:snapshot=@{};$script:reviewId=$null;Start-Job @{operation='reconcile';month=(Selected-Month)}}catch{$status.Text=$_.Exception.Message}})
$month.Add_SelectedIndexChanged({$grid.Rows.Clear();$script:snapshot=@{};$script:reviewId=$null;$apply.Enabled=$false;$selected.Text='조회 후 행 선택';$summaryLabel.Text='사이트 연장 기록: 해당 월을 조회하세요.'})
$grid.Add_CurrentCellDirtyStateChanged({if($grid.IsCurrentCellDirty){[void]$grid.CommitEdit([Windows.Forms.DataGridViewDataErrorContexts]::Commit)}})
$grid.Add_CellValueChanged({Update-ReviewSummary})
$apply.Add_Click({
 try {
  [void]$grid.EndEdit()
  if(-not $script:reviewId){throw '수정 목록을 먼저 조회하세요.'}
  $entries=@()
  foreach($row in $grid.Rows){
   if(-not $row.Cells['choose'].Value){continue}
   $entries+=@{date=[string]$row.Cells['date'].Value;checkin=[string]$row.Cells['checkin'].Value;checkout=[string]$row.Cells['checkout'].Value}
  }
  if($entries.Count -eq 0){throw '정리할 날짜를 선택하세요.'}
  Start-Job @{operation='reconcile_apply';plan_id=$script:reviewId;rows=$entries}
 }catch{$status.Text=$_.Exception.Message}
})
$timer.Add_Tick({
 if(-not $script:worker -or -not $script:worker.HasExited){return};$timer.Stop()
 try {
  $result=Get-Content -LiteralPath ($script:jobPath+'.result.json') -Raw -Encoding UTF8|ConvertFrom-Json
  $resultError=if(-not $result.ok){[string]$result.error}else{$null}
  if($script:operation -in @('scan','reconcile','reconcile_apply')) {
   if(-not $resultError -or $result.rows){Set-ReviewView $result}
  }else{
   $status.Text=$result.message;$grid.Rows.Clear();$script:snapshot=@{};$script:reviewId=$null
   if($script:operation -in @('rules','rules_delete')){$script:chosenDates.Clear();$vacation.Checked=$false;$exclude.Checked=$false}
   $summaryLabel.Text='설정 변경 완료. 수정 목록을 조회해 주세요.'
  }
  Refresh-RuleList
  if($resultError){throw $resultError}
 }catch{$summaryLabel.Text='사이트 연장 기록: 확인 필요';$status.Text='처리 확인 필요: '+$_.Exception.Message+' (결과가 불확실하면 사이트를 확인하고 다시 조회하세요.)'}
 finally{
  $script:worker.Dispose();$script:worker=$null
  Remove-Item -LiteralPath $script:jobPath,($script:jobPath+'.result.json') -Force -ErrorAction SilentlyContinue
  foreach($c in $form.Controls){$c.Enabled=$true};Update-ReviewSummary
  if($script:operation -eq 'reconcile_apply'){$script:reviewId=$null;$apply.Enabled=$false}
 }
})
$form.Add_FormClosing({if($script:worker){$_.Cancel=$true;$status.Text='진행 중인 처리가 끝난 뒤 닫아 주세요.'}})
. (Join-Path $PSScriptRoot 'theme.ps1')
Set-UiTheme $form
$apply.BackColor=$script:UiOrange
# Monthly corrections are reviewed and edited in the grid before saving.
$manualControls=@($form.Controls|Where-Object{$_ -ne $status -and $_ -ne $apply -and $_.Top -ge 615})
foreach($control in $manualControls){$form.Controls.Remove($control)}
$form.Height=770;$status.Top=620;$status.Height=95
$apply.Location=New-Object Drawing.Point(730,620);$apply.Size=New-Object Drawing.Size(280,42)
$apply.Text='선택 내역 정리';$apply.Enabled=$false
$status.Width=690;$status.Text='수정 목록에서 체크를 해제하면 이번 정리에서 제외됩니다. 변경 출근·퇴근 시간을 직접 편집한 뒤 정리하세요.'
Render-Calendar
if($SelfTest){
 $vacation.Checked=$true;$exclude.Checked=$true
 if($vacation.Checked -or -not $exclude.Checked){throw '휴가/연장 제외 동시 선택 방지 실패'}
 $vacation.Checked=$true
 if($exclude.Checked -or -not $vacation.Checked){throw '휴가 우선 선택 전환 실패'}
 $vacation.Checked=$false;$exclude.Checked=$false
 if($dayPicker.CustomFormat -ne 'yyyy-MM-dd' -or $grid.Columns.Count -ne 9){throw '정정 화면 구조 오류'}
 $fixtureRules=('{"2026-11-02":{"vacation":true},"2026-10-29":{"exclude_overtime":true},"2026-10-01":{"vacation":false}}'|ConvertFrom-Json)
 Set-RuleRows $fixtureRules
 if($rulesGrid.Rows.Count -ne 2 -or $rulesGrid.Rows[0].Cells['date'].Value -ne '2026-10-29'){throw '저장 제외일 목록 검사 실패'}
 Set-RuleRows $null
 if($rulesGrid.Rows.Count -ne 0){throw '해제일 목록 갱신 실패'}
 $script:calendarMonth=[DateTime]'2026-10-01'
 Render-Calendar
 $available=@($script:calendarButtons|Where-Object{$_.Tag})
 if($available.Count -ne 31 -or @($available|Where-Object{$_.Text -eq '1'}).Count -ne 1){throw '달력 날짜 표시 실패'}
 $oct2=@($script:calendarButtons|Where-Object{$_.Tag -eq '2026-10-02'})[0]
 $oct29=@($script:calendarButtons|Where-Object{$_.Tag -eq '2026-10-29'})[0]
 foreach($target in @($oct2,$oct29)){
  [void]$target.GetType().GetMethod('OnClick',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($target,@([EventArgs]::Empty))
 }
 [void]$oct2.GetType().GetMethod('OnClick',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($oct2,@([EventArgs]::Empty))
 if($script:chosenDates.Count -ne 1 -or $script:chosenDates.Contains('2026-10-02')){throw '달력 재클릭 해제 실패'}
 [void]$oct2.GetType().GetMethod('OnClick',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($oct2,@([EventArgs]::Empty))
 [void]$calendarNext.GetType().GetMethod('OnClick',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($calendarNext,@([EventArgs]::Empty))
 if($script:chosenDates.Count -ne 2 -or $script:calendarMonth.Month -ne 11){throw '달력 다중 선택 보존 실패'}
 [void]$clearDates.GetType().GetMethod('OnClick',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($clearDates,@([EventArgs]::Empty));if($script:chosenDates.Count -ne 0){throw '달력 선택 해제 실패'}
 $script:calendarMonth=[DateTime]'2026-10-01'
 function Start-Job($job){$script:testDeleteJob=$job}
 Set-RuleRows $fixtureRules
 $rulesGrid.Rows[0].Selected=$true
 [void]$deleteRule.GetType().GetMethod('OnClick',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($deleteRule,@([EventArgs]::Empty))
 if($script:testDeleteJob.operation -ne 'rules_delete' -or $script:testDeleteJob.dates[0] -ne '2026-10-29'){throw '저장 날짜 삭제 버튼 검사 실패'}
 $fixtureReview=@{plan_id='ui-fixture';target_days=10;message='수정 예정 목록입니다. 변경 시간을 직접 편집할 수 있습니다.';all_rows=@(@{date='2026-10-07';checkin='08:35';checkout='19:20';eligible=$true});rows=@(@{date='2026-10-07';before=@{checkin='08:35';checkout='19:20';note='기존 비고'};after=@{checkin='09:00';checkout='18:00'};reason='연장근무 제외';status='수정 예정';selectable=$true;blocked=$false})}
 Set-ReviewView $fixtureReview
 if($grid.Rows.Count -ne 1 -or -not $apply.Enabled){throw '수정 목록 선택 실패'}
 if(-not $grid.Rows[0].Cells['before_checkin'].ReadOnly -or $grid.Rows[0].Cells['checkin'].ReadOnly){throw '시간 직접 편집 구조 오류'}
 $grid.Rows[0].Cells['checkout'].Value='잘못된 시간';Update-ReviewSummary
 if($apply.Enabled){throw '잘못된 시간 저장 차단 실패'}
 $grid.Rows[0].Cells['checkout'].Value='18:15';$grid.Rows[0].Cells['choose'].Value=$false;Update-ReviewSummary
 if($apply.Enabled){throw '체크 해제 제외 실패'}
 $grid.Rows[0].Cells['choose'].Value=$true;Update-ReviewSummary
 if(-not $apply.Enabled){throw '편집 시간 적용 실패'}
 if($PreviewPath){Set-RuleRows $fixtureRules}
 Write-UiPreview $form $PreviewPath;Write-Output 'CORRECTIONS_UI_OK';$form.Dispose();$timer.Dispose();return
}
Read-Rule
try{Refresh-RuleList}catch{$status.Text='저장된 제외일 목록을 읽지 못했습니다. '+$_.Exception.Message}
if(-not (Enter-WorkdayUi 'corrections')){$form.Dispose();$timer.Dispose();return}
try { Show-WorkdayDialog $form $OwnerHandle } finally {Exit-WorkdayUi;$timer.Dispose()}
