[CmdletBinding()]
param([switch]$SelfTest,[string]$PreviewPath,[long]$OwnerHandle=0)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $PSScriptRoot 'session.ps1')
$script:worker=$null;$script:reviewId=$null;$script:allRows=@();$script:stage=1;$script:loading=$false;$script:existing=0
$form=New-Object Windows.Forms.Form
$form.Text='출근정리 — 출장일지';$form.Size=New-Object Drawing.Size(1260,750);$form.MinimumSize=New-Object Drawing.Size(1100,650)
$form.StartPosition='CenterScreen';$form.Font=New-Object Drawing.Font('Malgun Gothic',10)
function Text-Label($text,$x,$y,$width){$c=New-Object Windows.Forms.Label;$c.Text=$text;$c.Location=New-Object Drawing.Point($x,$y);$c.Size=New-Object Drawing.Size($width,30);$form.Controls.Add($c);return $c}
function Make-Button($text,$x,$y,$width){$c=New-Object Windows.Forms.Button;$c.Text=$text;$c.Location=New-Object Drawing.Point($x,$y);$c.Size=New-Object Drawing.Size($width,38);$form.Controls.Add($c);return $c}
$heading=Text-Label '1. 날짜·시간 선택 → 2. 선택한 날짜의 출장 장소·목적 입력 → 날짜별 등록' 20 18 1170
$heading.Font=New-Object Drawing.Font('Malgun Gothic',12,[Drawing.FontStyle]::Bold)
[void](Text-Label '조회 월' 20 65 70)
$month=New-Object Windows.Forms.ComboBox;$month.DropDownStyle='DropDownList';$month.Location=New-Object Drawing.Point(90,61);$month.Width=165
foreach($label in (Get-WorkdayMonthLabels (Get-Date))){[void]$month.Items.Add($label)};$month.SelectedIndex=0;$form.Controls.Add($month)
[void](Text-Label '목표 금액' 275 65 85)
$total=New-Object Windows.Forms.NumericUpDown;$total.Location=New-Object Drawing.Point(360,61);$total.Width=145;$total.Maximum=1000;$total.Increment=1;$total.ThousandsSeparator=$true;$form.Controls.Add($total)
[void](Text-Label '만원 · 예: 20 = 20만원' 515 65 295)
$scan=Make-Button '출퇴근 일정 조회' 855 55 355
$note=Text-Label '구분: 센터 / 이동: 대중교통 · 연장 제외일: 09~18시, 인정 4시간·2만원 · 기존 등록은 선택 완료 시 확인·중복 제외' 20 110 1190
$grid=New-Object Windows.Forms.DataGridView;$grid.Location=New-Object Drawing.Point(20,155);$grid.Size=New-Object Drawing.Size(1190,370);$grid.Anchor='Top,Bottom,Left,Right'
$grid.AllowUserToAddRows=$false;$grid.AllowUserToDeleteRows=$false;$grid.RowHeadersVisible=$false;$grid.AutoSizeColumnsMode='Fill';$grid.RowTemplate.Height=32
$check=New-Object Windows.Forms.DataGridViewCheckBoxColumn;$check.Name='selected';$check.HeaderText='선택';$check.FillWeight=40;[void]$grid.Columns.Add($check)
foreach($spec in @(@('date','날짜',100),@('weekday','요일',45),@('attendance','출퇴근',115),@('required','필수',80))){$c=New-Object Windows.Forms.DataGridViewTextBoxColumn;$c.Name=$spec[0];$c.HeaderText=$spec[1];$c.FillWeight=$spec[2];$c.ReadOnly=$true;[void]$grid.Columns.Add($c)}
foreach($spec in @(@('hours','인정시간',70),@('start_hour','출발 시',70))){$c=New-Object Windows.Forms.DataGridViewComboBoxColumn;$c.Name=$spec[0];$c.HeaderText=$spec[1];$c.FillWeight=$spec[2];$c.FlatStyle='Flat';$items=if($spec[0] -eq 'hours'){@('2','4')}else{@(0..23|ForEach-Object{[string]$_})};foreach($item in $items){[void]$c.Items.Add($item)};[void]$grid.Columns.Add($c)}
foreach($spec in @(@('end','자동 복귀',85),@('amount','금액',90),@('location','출장 장소 (직접 입력)',180),@('purpose','출장 목적 (직접 입력)',300),@('status','상태',200))){$c=New-Object Windows.Forms.DataGridViewTextBoxColumn;$c.Name=$spec[0];$c.HeaderText=$spec[1];$c.FillWeight=$spec[2];$c.ReadOnly=($spec[0] -notin @('location','purpose'));[void]$grid.Columns.Add($c)}
$grid.Columns['location'].Visible=$false;$grid.Columns['purpose'].Visible=$false;$form.Controls.Add($grid)
$summary=Text-Label '목표 금액을 입력하고 출퇴근 일정을 조회하세요.' 20 540 1190;$summary.Height=58;$summary.Anchor='Bottom,Left,Right'
$status=Text-Label '설정을 저장하거나 메뉴를 여는 것만으로 사이트에 접속하지 않습니다.' 20 650 1190;$status.Height=45;$status.Anchor='Bottom,Left,Right'
$allocate=Make-Button '선택일 시간 배분' 20 600 230;$allocate.Anchor='Bottom,Left'
$complete=Make-Button '선택 완료 → 기존 출장 확인' 270 600 330;$complete.Anchor='Bottom,Left'
$back=Make-Button '일정 다시 선택' 20 600 230;$back.Anchor='Bottom,Left';$back.Visible=$false
$submit=Make-Button '선택 날짜 순서대로 등록' 855 600 355;$submit.Anchor='Bottom,Right';$submit.Visible=$false
$timer=New-Object Windows.Forms.Timer;$timer.Interval=400
function Selected-Month{[DateTime]::ParseExact([string]$month.SelectedItem,'yyyy년 MM월',[Globalization.CultureInfo]::InvariantCulture).ToString('yyyy-MM')}
function Clock-Minutes($value){$text=([string]$value)-replace '\s','';if($text -match '^(\d{1,2}):(\d{1,2})$'){return [int]$Matches[1]*60+[int]$Matches[2]};return -1}
function Target-Amount{return [int]$total.Value*10000}
function Row-Amount($row){return [int]$row.Cells['hours'].Value*5000}
function Update-Totals {
 if($script:loading){return};$script:loading=$true
 try{
  $sum=0;$count=0;$valid=$true;$details=$true;$missing=$false
  foreach($row in $grid.Rows){
   $entry=$row.Tag;$hours=[int]$row.Cells['hours'].Value;$hour=[int]$row.Cells['start_hour'].Value
   if($entry.blocked -and $entry.existing_amount){$hours=[int]$entry.existing_hours;$hour=[int]$entry.start_hour;$end=$entry.end}elseif($entry.mandatory){$hours=4;$hour=9;$end='18:00'}else{$end=('{0:D2}:00' -f ($hour+$hours))}
   $row.Cells['end'].Value=$end;$row.Cells['amount'].Value=$hours*5000
   if($entry.conflict -or ($entry.mandatory -and $entry.blocked -and -not $entry.existing_amount)){$missing=$true}
   if($row.Cells['selected'].Value){
    $count++;$sum+=$hours*5000
    if($entry.blocked -or (-not $entry.mandatory -and ($hour*60 -lt (Clock-Minutes $entry.checkin) -or ($hour+$hours)*60 -gt (Clock-Minutes $entry.checkout)))){$valid=$false}
    if([string]::IsNullOrWhiteSpace([string]$row.Cells['location'].Value) -or [string]::IsNullOrWhiteSpace([string]$row.Cells['purpose'].Value)){$details=$false}
   }
   $entry.selected=[bool]$row.Cells['selected'].Value;$entry.hours=$hours;$entry.start_hour=$hour;$entry.start=('{0:D2}:00' -f $hour);$entry.end=$end;$entry.amount=$hours*5000
   $entry.location=[string]$row.Cells['location'].Value;$entry.purpose=[string]$row.Cells['purpose'].Value
  }
  $left=(Target-Amount)-$script:existing-$sum
  $result=if($left -gt 0){"출장 추가 필요: $($left/5000)시간 / $($left.ToString('N0'))원 부족"}elseif($left -lt 0){"목표 초과: $((-$left).ToString('N0'))원 · 선택을 줄이세요."}else{'목표 금액·인정시간 일치'}
  if($missing){$result+=' · 필수 제외일의 근태/기존 출장 확인 필요'}
  if(-not $valid){$result+=' · 출발·복귀를 출퇴근 구간 안으로 조정하세요.'}
  $summary.Text="목표 $($total.Value.ToString('N0'))만원 / $((Target-Amount)/5000)시간 · 기존 $($script:existing.ToString('N0'))원 · 선택 $count 일 / $($sum.ToString('N0'))원`r`n$result"
  $summary.ForeColor=if($left -eq 0 -and $valid -and -not $missing){[Drawing.Color]::DarkGreen}else{[Drawing.Color]::Firebrick}
  $ready=([bool]$script:reviewId -and $left -eq 0 -and $count -gt 0 -and $valid -and -not $missing -and -not $script:worker)
  $complete.Enabled=($ready -and $script:stage -eq 1);$submit.Enabled=($ready -and $details -and $script:stage -eq 2)
  $allocate.Enabled=([bool]$script:reviewId -and $count -gt 0 -and -not $script:worker)
 }finally{$script:loading=$false}
}
function Render-Rows($rows){
 $script:loading=$true
 try{
  $grid.Rows.Clear()
  foreach($entry in $rows){
   $index=$grid.Rows.Add([bool]$entry.selected,$entry.date,$entry.weekday,($entry.checkin+'~'+$entry.checkout),$(if($entry.mandatory){'제외일'}else{''}),[string][int]$entry.hours,[string][int]$entry.start_hour,$entry.end,[int]$entry.amount,$entry.location,$entry.purpose,$entry.status)
   $row=$grid.Rows[$index];$row.Tag=$entry
   foreach($name in @('selected','hours','start_hour','location','purpose')){$row.Cells[$name].ReadOnly=[bool]$entry.blocked}
   if($entry.mandatory){foreach($name in @('selected','hours','start_hour')){$row.Cells[$name].ReadOnly=$true}}
   if($script:stage -eq 2){$row.Cells['selected'].ReadOnly=$true;$row.Cells['hours'].ReadOnly=$true}
  }
 }finally{$script:loading=$false;Update-Totals}
}
function Change-Stage($stage){
 $script:stage=$stage;$details=($stage -eq 2)
 $grid.Columns['location'].Visible=$details;$grid.Columns['purpose'].Visible=$details;$grid.Columns['attendance'].Visible=-not $details
 $complete.Visible=-not $details;$allocate.Visible=-not $details;$back.Visible=$details;$submit.Visible=$details;$total.Enabled=-not $details;$month.Enabled=-not $details
 $heading.Text=if($details){'2. 선택한 날짜의 출장 장소·목적을 입력하고 날짜별로 등록하세요.'}else{'1. 날짜·시간 선택 → 2. 선택한 날짜의 출장 장소·목적 입력 → 날짜별 등록'}
 $status.Text=if($details){'선택한 날짜의 출장 장소와 목적을 직접 입력하세요. 날짜·인정시간 변경은 일정 다시 선택을 누르세요.'}else{'금액이 차면 추가 체크를 막습니다. 선택을 해제하거나 시간을 줄이면 다시 선택할 수 있습니다.'}
 if($details){Render-Rows @($script:allRows|Where-Object{$_.selected})}else{Render-Rows $script:allRows}
}
function Entries{@($grid.Rows|ForEach-Object{@{date=[string]$_.Cells['date'].Value;selected=[bool]$_.Cells['selected'].Value;hours=[int]$_.Cells['hours'].Value;start_hour=[int]$_.Cells['start_hour'].Value;location=[string]$_.Cells['location'].Value;purpose=[string]$_.Cells['purpose'].Value}})}
function Start-TripJob($job){
 $python=Join-Path $PSScriptRoot 'runtime/python.exe';if(-not(Test-Path -LiteralPath $python)){throw '설치된 프로그램에서 실행하세요.'}
 $root=Join-Path $PSScriptRoot 'dist';New-Item -ItemType Directory -Path $root -Force|Out-Null
 $script:jobPath=Join-Path $root ('trip-job-'+[Guid]::NewGuid().ToString('N')+'.json');$script:operation=$job.operation
 [IO.File]::WriteAllText($script:jobPath,($job|ConvertTo-Json -Depth 10),(New-Object Text.UTF8Encoding($false)))
 $script:worker=Start-WorkdayHiddenProcess $python "`"$(Join-Path $PSScriptRoot 'main.py')`" --trip-job `"$script:jobPath`"" $PSScriptRoot
 foreach($c in $form.Controls){if($c -ne $status){$c.Enabled=$false}}
 $status.Text=if($job.operation -eq 'allocate'){'선택한 날짜 안에서 시간을 배분 중입니다. 사이트에는 접속하지 않습니다.'}elseif($job.operation -eq 'scan'){'근태관리에서 출퇴근 등록 날짜를 조회 중입니다.'}elseif($job.operation -eq 'inspect'){'선택 완료: 기존 출장 내역을 확인 중입니다. 아직 등록하지 않습니다.'}else{'사이트 처리 중입니다. 등록은 하루씩 확인한 뒤 다음 날짜로 진행합니다.'};$timer.Start()
}
$scan.Add_Click({try{$script:reviewId=$null;Start-TripJob @{operation='scan';month=(Selected-Month);total=(Target-Amount)}}catch{$status.Text=$_.Exception.Message}})
$allocate.Add_Click({try{[void]$grid.EndEdit();Start-TripJob @{operation='allocate';review_id=$script:reviewId;total=(Target-Amount);rows=@(Entries)}}catch{$status.Text=$_.Exception.Message}})
$complete.Add_Click({try{[void]$grid.EndEdit();Update-Totals;if($complete.Enabled){Start-TripJob @{operation='inspect';review_id=$script:reviewId;total=(Target-Amount);rows=@(Entries)}}}catch{$status.Text=$_.Exception.Message}})
$back.Add_Click({[void]$grid.EndEdit();Update-Totals;Change-Stage 1})
$submit.Add_Click({try{[void]$grid.EndEdit();Update-Totals;if($submit.Enabled){Start-TripJob @{operation='submit';review_id=$script:reviewId;total=(Target-Amount);rows=@(Entries)}}}catch{$status.Text=$_.Exception.Message}})
$total.Add_ValueChanged({Update-Totals})
$month.Add_SelectedIndexChanged({if($script:loading){return};$script:reviewId=$null;$script:allRows=@();$script:existing=0;Change-Stage 1})
$grid.Add_CurrentCellDirtyStateChanged({if($grid.IsCurrentCellDirty){[void]$grid.CommitEdit([Windows.Forms.DataGridViewDataErrorContexts]::Commit)}})
$grid.Add_CellValueChanged({param($sender,$eventArgs)
 if($script:loading -or $eventArgs.RowIndex -lt 0 -or $eventArgs.ColumnIndex -lt 0){return}
 $row=$grid.Rows[$eventArgs.RowIndex];if(-not $row.Tag){return};$name=$grid.Columns[$eventArgs.ColumnIndex].Name
 $script:loading=$true
 try{
  if($name -eq 'selected' -and $row.Cells['selected'].Value -and -not $row.Tag.selected){
   $others=0;foreach($other in $grid.Rows){if($other -ne $row -and $other.Cells['selected'].Value){$others+=Row-Amount $other}}
   $left=(Target-Amount)-$script:existing-$others
   if($left -lt 10000){$row.Cells['selected'].Value=$false;$status.Text='목표 금액을 이미 채웠습니다. 다른 날짜를 해제하거나 시간을 줄이면 다시 선택할 수 있습니다.'}
   elseif((Row-Amount $row) -gt $left){$row.Cells['hours'].Value='2'}
  }
  if($name -eq 'hours' -and $row.Cells['selected'].Value){
   $sum=0;foreach($other in $grid.Rows){if($other.Cells['selected'].Value){$sum+=Row-Amount $other}}
   if($script:existing+$sum -gt (Target-Amount)){$row.Cells['hours'].Value=[string]$row.Tag.hours;$status.Text='남은 금액보다 큰 시간은 선택할 수 없습니다.'}
  }
 }finally{$script:loading=$false;Update-Totals}
})
$timer.Add_Tick({
 if(-not $script:worker -or -not $script:worker.HasExited){return};$timer.Stop()
 try{
  $result=Get-Content -LiteralPath ($script:jobPath+'.result.json') -Raw -Encoding UTF8|ConvertFrom-Json
  if($result.summary){$script:existing=[int]$result.summary.existing_amount}
  if($script:operation -eq 'submit'){
   $script:reviewId=$null
   if($result.all_rows){$script:allRows=@($result.all_rows);Change-Stage 1}
   elseif($result.rows){foreach($entry in $result.rows){$entry.selected=$false;$entry.blocked=$true};$script:allRows=@($result.rows);Render-Rows $result.rows}
  }elseif($result.ok){$script:reviewId=$result.review_id;$script:allRows=@($result.rows);if($script:operation -eq 'inspect' -and $result.ready){Change-Stage 2}else{Change-Stage 1}}
  if(-not $result.ok){throw $result.error}
  $status.Text=$result.message
  if($script:operation -eq 'submit'){[void][Windows.Forms.MessageBox]::Show($form,$result.message,'출장 등록 결과','OK','Information')}
 }catch{$status.Text='처리 확인 필요: '+$_.Exception.Message;if($script:operation -ne 'inspect'){$script:reviewId=$null};$errorTitle=if($script:operation -eq 'scan'){'근태 일정 조회 오류'}elseif($script:operation -eq 'inspect'){'기존 출장 확인 오류'}else{'출장 처리 결과'};[void][Windows.Forms.MessageBox]::Show($form,$status.Text,$errorTitle,'OK','Error')}
 finally{
  $script:worker.Dispose();$script:worker=$null;Remove-Item -LiteralPath $script:jobPath,($script:jobPath+'.result.json') -Force -ErrorAction SilentlyContinue
  foreach($c in $form.Controls){$c.Enabled=$true};$grid.Enabled=[bool]$script:reviewId;$total.Enabled=($script:stage -eq 1);$month.Enabled=($script:stage -eq 1);Update-Totals
 }
})
$form.Add_FormClosing({if($script:worker){$_.Cancel=$true;$status.Text='진행 중인 처리가 끝난 뒤 닫아 주세요.'}})
. (Join-Path $PSScriptRoot 'theme.ps1');Set-UiTheme $form;$submit.BackColor=$script:UiOrange
Update-Totals
if($SelfTest){
 $fixture='[{"date":"2026-10-07","weekday":"수","checkin":"09:00","checkout":"18:00","mandatory":true,"selected":true,"blocked":false,"hours":4,"start_hour":9,"start":"09:00","end":"18:00","amount":20000,"existing_amount":0,"location":"","purpose":"","status":"필수 포함"},{"date":"2026-10-13","weekday":"화","checkin":"08:35","checkout":"18:00","mandatory":false,"selected":false,"blocked":false,"hours":4,"start_hour":9,"start":"09:00","end":"13:00","amount":20000,"existing_amount":0,"location":"","purpose":"","status":"선택 가능"},{"date":"2026-10-14","weekday":"수","checkin":"08:30","checkout":"18:00","mandatory":false,"selected":false,"blocked":false,"hours":4,"start_hour":9,"start":"09:00","end":"13:00","amount":20000,"existing_amount":0,"location":"","purpose":"","status":"선택 가능"}]'|ConvertFrom-Json
 $script:reviewId='fixture';$script:allRows=@($fixture);$total.Value=20;if((Target-Amount) -ne 200000){throw '만원 입력 변환 실패'};$total.Value=3;Render-Rows $script:allRows
 $grid.Rows[1].Cells['selected'].Value=$true
 if($grid.Rows[1].Cells['hours'].Value -ne '2' -or -not $complete.Enabled){throw '남은 1만원의 2시간 자동 배분 실패'}
 $grid.Rows[2].Cells['selected'].Value=$true
 if($grid.Rows[2].Cells['selected'].Value){throw '금액 충족 후 추가 체크 차단 실패'}
 $grid.Rows[1].Cells['hours'].Value='4'
 if($grid.Rows[1].Cells['hours'].Value -ne '2'){throw '선택 시간의 목표 초과 차단 실패'}
 $grid.Rows[1].Cells['selected'].Value=$false;$grid.Rows[2].Cells['selected'].Value=$true
 if(-not $grid.Rows[2].Cells['selected'].Value){throw '선택 해제 후 다시 선택 허용 실패'}
 $grid.Rows[2].Cells['selected'].Value=$false;$grid.Rows[1].Cells['selected'].Value=$true
 Change-Stage 2
 if($grid.Rows.Count -ne 2 -or -not $grid.Columns['location'].Visible -or $submit.Enabled){throw '선택 일정만 표시/직접 입력 검사 실패'}
 foreach($row in $grid.Rows){$row.Cells['location'].Value='예시 출장장소';$row.Cells['purpose'].Value='예시 출장목적'}
 Update-Totals;if(-not $submit.Enabled){throw '출장 장소·목적 입력 완료 검사 실패'}
 Change-Stage 1;if($grid.Rows.Count -ne 3){throw '전체 일정 복귀 실패'}
 if($PreviewPath){Change-Stage 2;$script:loading=$true;$form.Controls.Remove($allocate);$form.Controls.Remove($complete);$grid.Columns.Remove('attendance');Write-UiPreview $form $PreviewPath}
 Write-Output 'TRIPS_UI_OK: budget limit, 2h fit, selected-only detail stage, mandatory dates and manual details';$form.Dispose();$timer.Dispose();return
}
if(-not(Enter-WorkdayUi 'trips')){$form.Dispose();$timer.Dispose();return}
try { Show-WorkdayDialog $form $OwnerHandle } finally { Exit-WorkdayUi;$timer.Dispose() }
