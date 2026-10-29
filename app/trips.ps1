[CmdletBinding()]
param([switch]$SelfTest,[switch]$InteractiveTest,[string]$PreviewPath,[long]$OwnerHandle=0)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if(-not ('WorkdayTripEntryGrid' -as [type])){
 Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Windows.Forms;
public class WorkdayTripCheckCell : DataGridViewCheckBoxCell {
    protected override void OnContentClick(DataGridViewCellEventArgs e) { }
    protected override void OnContentDoubleClick(DataGridViewCellEventArgs e) { }
}
public class WorkdayTripEntryGrid : DataGridView {
    public bool PurposeEntryMode { get; set; }
    protected override void OnCellBeginEdit(DataGridViewCellCancelEventArgs e) {
        base.OnCellBeginEdit(e);
        // Checkboxes have no buffered editor: mouse/Space commits the value once.
        if(Rows[e.RowIndex].Cells[e.ColumnIndex] is DataGridViewCheckBoxCell) e.Cancel=true;
    }
    private bool ToggleCheckKey(Keys keyData) {
        if(keyData!=Keys.Space || CurrentCell==null || !(CurrentCell is DataGridViewCheckBoxCell)) return false;
        ToggleCheck(CurrentCell);return true;
    }
    private void ToggleCheck(DataGridViewCell cell) {
        if(cell.ReadOnly || !Enabled) return;
        if(!EndEdit()) return;
        CurrentCell=cell;
        cell.Value=!(cell.Value is bool && (bool)cell.Value);
        InvalidateCell(cell);
    }
    public void TestCellClick(int row,int column) {
        OnCellMouseClick(new DataGridViewCellMouseEventArgs(column,row,2,2,new MouseEventArgs(MouseButtons.Left,1,2,2,0)));
    }
    protected override void OnCellMouseClick(DataGridViewCellMouseEventArgs e) {
        // Handle the entire checkbox cell, once, rather than only the tiny glyph.
        if(e.RowIndex>=0 && e.ColumnIndex>=0 && e.Button==MouseButtons.Left) {
            DataGridViewCell cell=Rows[e.RowIndex].Cells[e.ColumnIndex];
            if(cell is DataGridViewCheckBoxCell) {
                ToggleCheck(cell);
                return;
            }
        }
        base.OnCellMouseClick(e);
        if(e.RowIndex>=0 && e.ColumnIndex>=0 && e.Button==MouseButtons.Left &&
           !Rows[e.RowIndex].Cells[e.ColumnIndex].ReadOnly) {
            CurrentCell=Rows[e.RowIndex].Cells[e.ColumnIndex]; BeginEdit(true);
            ComboBox combo=EditingControl as ComboBox;
            if(combo!=null) combo.DroppedDown=true;
        }
    }
    protected override void OnCellContentClick(DataGridViewCellEventArgs e) {
        if(e.RowIndex>=0 && e.ColumnIndex>=0 && Rows[e.RowIndex].Cells[e.ColumnIndex] is DataGridViewCheckBoxCell) return;
        base.OnCellContentClick(e);
    }
    protected override bool ProcessDialogKey(Keys keyData) {
        return ToggleCheckKey(keyData) || MoveEntryKey(keyData) || base.ProcessDialogKey(keyData);
    }
    protected override bool ProcessDataGridViewKey(KeyEventArgs e) {
        return ToggleCheckKey(e.KeyData) || MoveEntryKey(e.KeyData) || base.ProcessDataGridViewKey(e);
    }
    public bool MoveEntryKey(Keys keyData) {
        Keys code=keyData & Keys.KeyCode;
        if(!PurposeEntryMode || (code!=Keys.Tab && code!=Keys.Enter) ||
           (keyData & (Keys.Control|Keys.Alt))!=0 || CurrentCell==null) return false;
        string name=CurrentCell.OwningColumn.Name;
        if(name!="location" && name!="purpose") return false;
        bool back=(keyData & Keys.Shift)!=0;
        DataGridViewCell current=CurrentCell;
        if(!EndEdit()) return true;
        List<DataGridViewCell> cells=new List<DataGridViewCell>();
        foreach(DataGridViewRow row in Rows) {
            if(row.IsNewRow || !row.Visible) continue;
            foreach(string column in new string[]{"location","purpose"}) {
                DataGridViewCell cell=row.Cells[column];
                if(cell.Visible && !cell.ReadOnly && !row.ReadOnly) cells.Add(cell);
            }
        }
        int at=cells.IndexOf(current);
        int next=at+(back ? -1 : 1);
        if(at<0) return false;
        if(next<0 || next>=cells.Count) {
            if(Parent!=null) Parent.SelectNextControl(this,!back,true,true,true);
            return true;
        }
        CurrentCell=cells[next];
        BeginEdit(true);
        return true;
    }
}
'@
}
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
$note=Text-Label '구분: 센터 / 이동: 대중교통 · 행사 기본 09~18시 / 일반 기본 13~17시 · 휴가 숨김 · 기등록 날짜·금액을 최초 조회부터 표시 · 저장 전 재확인' 20 110 1190
$grid=New-Object WorkdayTripEntryGrid;$grid.Location=New-Object Drawing.Point(20,155);$grid.Size=New-Object Drawing.Size(1190,370);$grid.Anchor='Top,Bottom,Left,Right'
$grid.EditMode='EditProgrammatically';$grid.AllowUserToAddRows=$false;$grid.AllowUserToDeleteRows=$false;$grid.RowHeadersVisible=$false;$grid.AutoSizeColumnsMode='Fill';$grid.RowTemplate.Height=32
$check=New-Object Windows.Forms.DataGridViewCheckBoxColumn;$check.CellTemplate=New-Object WorkdayTripCheckCell;$check.Name='selected';$check.HeaderText='선택';$check.FillWeight=40;[void]$grid.Columns.Add($check)
foreach($spec in @(@('date','날짜',100),@('weekday','요일',45),@('attendance','출퇴근',115),@('required','구분',145),@('registered','출장 등록',95))){$c=New-Object Windows.Forms.DataGridViewTextBoxColumn;$c.Name=$spec[0];$c.HeaderText=$spec[1];$c.FillWeight=$spec[2];$c.ReadOnly=$true;[void]$grid.Columns.Add($c)}
foreach($spec in @(@('hours','인정시간',70),@('start_hour','출발 시',70),@('start_minute','분',60))){$c=New-Object Windows.Forms.DataGridViewComboBoxColumn;$c.Name=$spec[0];$c.HeaderText=$spec[1];$c.FillWeight=$spec[2];$c.FlatStyle='Flat';$items=if($spec[0] -eq 'hours'){@('2','4')}elseif($spec[0] -eq 'start_hour'){@(0..23|ForEach-Object{[string]$_})}else{@(0..59|ForEach-Object{[string]$_})};foreach($item in $items){[void]$c.Items.Add($item)};[void]$grid.Columns.Add($c)}
foreach($spec in @(@('end','복귀 (자동·수정)',100),@('amount','금액',90),@('location','출장 장소 (직접 입력)',180),@('purpose','출장 목적 (직접 입력)',300),@('status','상태',200))){$c=New-Object Windows.Forms.DataGridViewTextBoxColumn;$c.Name=$spec[0];$c.HeaderText=$spec[1];$c.FillWeight=$spec[2];$c.ReadOnly=($spec[0] -notin @('end','location','purpose'));[void]$grid.Columns.Add($c)}
foreach($name in @('selected','date','start_hour','start_minute','end')){$grid.Columns[$name].MinimumWidth=$(if($name -eq 'date'){100}elseif($name -eq 'end'){105}else{48})};$grid.Columns['location'].Visible=$false;$grid.Columns['purpose'].Visible=$false;$form.Controls.Add($grid)
$summary=Text-Label '목표 금액을 입력하고 출퇴근 일정을 조회하세요.' 20 540 1190;$summary.Height=58;$summary.Anchor='Bottom,Left,Right'
$status=Text-Label '설정을 저장하거나 메뉴를 여는 것만으로 사이트에 접속하지 않습니다.' 20 650 1190;$status.Height=45;$status.Anchor='Bottom,Left,Right'
$allocate=Make-Button '선택일 시간 배분' 20 600 230;$allocate.Anchor='Bottom,Left'
$complete=Make-Button '선택 완료 → 기존 출장 확인' 270 600 330;$complete.Anchor='Bottom,Left'
$back=Make-Button '일정 다시 선택' 20 600 230;$back.Anchor='Bottom,Left';$back.Visible=$false
$submit=Make-Button '선택 날짜 등록·수정' 855 600 355;$submit.Anchor='Bottom,Right';$submit.Visible=$false
$timer=New-Object Windows.Forms.Timer;$timer.Interval=400
function Selected-Month{[DateTime]::ParseExact([string]$month.SelectedItem,'yyyy년 MM월',[Globalization.CultureInfo]::InvariantCulture).ToString('yyyy-MM')}
function Clock-Minutes($value){$text=([string]$value)-replace '\s','';if($text -match '^(\d{1,2}):(\d{1,2})$' -and [int]$Matches[1] -lt 24 -and [int]$Matches[2] -lt 60){return [int]$Matches[1]*60+[int]$Matches[2]};return -1}
function Target-Amount{return [int]$total.Value*10000}
function Row-Amount($row){if($row.Tag.is_existing){return 0};return [int]$row.Cells['hours'].Value*5000}
function Update-Totals {
 if($script:loading){return};$script:loading=$true
 try{
  $sum=0;$count=0;$valid=$true;$details=$true;$missing=$false;$skipped=0;$hasNew=$false
  foreach($row in $grid.Rows){
   $entry=$row.Tag;$hours=[int]$row.Cells['hours'].Value;$hour=[int]$row.Cells['start_hour'].Value
   $minute=[int]$row.Cells['start_minute'].Value;$end=[string]$row.Cells['end'].Value
   $row.Cells['amount'].Value=$hours*5000
   if($entry.conflict){$missing=$true}
   $blankPurpose=[string]::IsNullOrWhiteSpace([string]$row.Cells['purpose'].Value)
   $include=[bool]$row.Cells['selected'].Value -and ($script:stage -ne 2 -or -not $blankPurpose)
   if($script:stage -eq 2){if(-not $row.Cells['selected'].Value){$skipped++;$row.Cells['status'].Value='체크 해제 · 등록 제외'}elseif($blankPurpose){$skipped++;$row.Cells['status'].Value='목적 미입력 · 등록 제외'}else{$row.Cells['status'].Value=$(if($entry.is_existing){'기존 출장 수정 대상'}else{'신규 등록 대상'})}}
   if($include){
    $count++;if(-not $entry.is_existing){$sum+=$hours*5000;$hasNew=$true}
    if($entry.blocked -or $minute -lt 0 -or ($hours -eq 2 -and (Clock-Minutes $end)-($hour*60+$minute) -ne 120) -or (Clock-Minutes $end) -lt ($hour*60+$minute+$hours*60) -or $hour*60+$minute -lt (Clock-Minutes $entry.checkin) -or (Clock-Minutes $end) -gt (Clock-Minutes $entry.checkout)){$valid=$false}
    if([string]::IsNullOrWhiteSpace([string]$row.Cells['location'].Value) -or [string]::IsNullOrWhiteSpace([string]$row.Cells['purpose'].Value)){$details=$false}
   }
   $entry.selected=[bool]$row.Cells['selected'].Value;$entry.hours=$hours;$entry.start_hour=$hour;$entry|Add-Member -NotePropertyName start_minute -NotePropertyValue $minute -Force;$entry.start=('{0:D2}:{1:D2}' -f $hour,$minute);$entry.end=$end;$entry.amount=$hours*5000
   $entry.location=[string]$row.Cells['location'].Value;$entry.purpose=[string]$row.Cells['purpose'].Value
  }
  $left=(Target-Amount)-$script:existing-$sum
  $result=if($left -gt 0){"출장 추가 필요: $($left/5000)시간 / $($left.ToString('N0'))원 부족"}elseif($left -lt 0){"목표 초과: $((-$left).ToString('N0'))원 · 선택을 줄이세요."}else{'목표 금액·인정시간 일치'}
  if($script:stage -eq 2){$result+=" · 등록 $count 건 / 제외 $skipped 건"}
  if($missing){$result+=' · 기존 출장 확인 필요'}
  if(-not $valid){$result+=' · 출발·복귀를 출퇴근 구간 안으로 조정하세요.'}
  $summary.Text="목표 $($total.Value.ToString('N0'))만원 / $((Target-Amount)/5000)시간 · 기존 $($script:existing.ToString('N0'))원 · 선택 $count 일 / $($sum.ToString('N0'))원`r`n$result"
  $summary.ForeColor=if($left -eq 0 -and $valid -and -not $missing){[Drawing.Color]::DarkGreen}else{[Drawing.Color]::Firebrick}
  $ready=([bool]$script:reviewId -and ($left -ge 0 -or -not $hasNew) -and $count -gt 0 -and $valid -and -not $missing -and -not $script:worker)
  $complete.Enabled=($ready -and $script:stage -eq 1);$submit.Enabled=([bool]$script:reviewId -and ($left -ge 0 -or -not $hasNew) -and $count -gt 0 -and $valid -and $details -and -not $missing -and -not $script:worker -and $script:stage -eq 2)
  $allocate.Enabled=([bool]$script:reviewId -and $count -gt 0 -and -not $script:worker)
 }finally{$script:loading=$false}
}
function Render-Rows($rows){
 $script:loading=$true
 try{
  $grid.Rows.Clear()
  foreach($entry in $rows){
   $index=$grid.Rows.Add([bool]$entry.selected,$entry.date,$entry.weekday,($entry.checkin+'~'+$entry.checkout),$(if($entry.event_day){'연장근무 제외(행사)'}else{''}),$(if($entry.is_existing){'기등록'}elseif($entry.existing_checked){'미등록'}else{'확인 안 됨'}),[string][int]$entry.hours,[string][int]$entry.start_hour,[string]((Clock-Minutes $entry.start)%60),$entry.end,[int]$entry.amount,$entry.location,$entry.purpose,$entry.status)
   $row=$grid.Rows[$index];$row.Tag=$entry
   foreach($name in @('selected','hours','start_hour','start_minute','end','location','purpose')){$row.Cells[$name].ReadOnly=[bool]$entry.blocked}
   if($entry.is_existing){$row.Cells['hours'].ReadOnly=$true}
   if($script:stage -eq 2){$row.Cells['hours'].ReadOnly=$true}
  }
 }finally{$script:loading=$false;Update-Totals}
}
function Change-Stage($stage){
 $script:stage=$stage;$details=($stage -eq 2);$grid.PurposeEntryMode=$details
 $grid.Columns['location'].Visible=$details;$grid.Columns['purpose'].Visible=$details;$grid.Columns['attendance'].Visible=-not $details
 $complete.Visible=-not $details;$allocate.Visible=-not $details;$back.Visible=$details;$submit.Visible=$details;$total.Enabled=-not $details;$month.Enabled=-not $details
 $heading.Text=if($details){'2. 장소·목적 입력 — 기존 출장은 수정하고, 신규 날짜는 추가 등록합니다.'}else{'1. 날짜·시간 선택 → 2. 선택한 날짜의 출장 장소·목적 입력 → 날짜별 등록'}
 $status.Text=if($details){'Tab·Enter: 장소 → 목적 → 다음 행 장소 / Shift: 역방향 · 체크 해제·목적 미입력은 등록 제외'}else{'금액이 차면 추가 체크를 막습니다. 선택을 해제하거나 시간을 줄이면 다시 선택할 수 있습니다.'}
 if($details){Render-Rows @($script:allRows|Where-Object{$_.selected})}else{Render-Rows $script:allRows}
}
function Open-TripDetails($Result,[scriptblock]$Confirm=$null){
 $proceed=$true
 if([int]$Result.summary.remaining_amount -gt 0){
  $notice="목표금액에 필요한 출장 일수·시간을 아직 채우지 못했습니다.`r`n선택 $(@($Result.rows|Where-Object{$_.selected}).Count)일 · $($Result.summary.message)`r`n`r`n현재 선택한 날짜만으로 장소·목적 입력 화면으로 넘어갈까요?"
  if($Confirm){$proceed=[bool](& $Confirm $notice)}else{$proceed=([Windows.Forms.MessageBox]::Show($form,$notice,'출장 일수·시간 미달 안내','OKCancel','Warning') -eq 'OK')}
 }
 if($proceed){Change-Stage 2}else{Change-Stage 1}
 return $proceed
}
function Entries{@($grid.Rows|ForEach-Object{@{date=[string]$_.Cells['date'].Value;selected=[bool]$_.Cells['selected'].Value;hours=[int]$_.Cells['hours'].Value;start_hour=[int]$_.Cells['start_hour'].Value;start_minute=[int]$_.Cells['start_minute'].Value;end=[string]$_.Cells['end'].Value;location=[string]$_.Cells['location'].Value;purpose=[string]$_.Cells['purpose'].Value}})}
function Start-TripJob($job){
 $python=Join-Path $PSScriptRoot 'runtime/python.exe';if(-not(Test-Path -LiteralPath $python)){throw '설치된 프로그램에서 실행하세요.'}
 $root=Join-Path $PSScriptRoot 'dist';New-Item -ItemType Directory -Path $root -Force|Out-Null
 $script:jobPath=Join-Path $root ('trip-job-'+[Guid]::NewGuid().ToString('N')+'.json');$script:operation=$job.operation;$script:closeAfterSubmit=$false;$script:expectedSubmitCount=@($job.rows|Where-Object{$_.selected -and -not [string]::IsNullOrWhiteSpace($_.purpose)}).Count
 [IO.File]::WriteAllText($script:jobPath,($job|ConvertTo-Json -Depth 10),(New-Object Text.UTF8Encoding($false)))
 $script:worker=Start-WorkdayHiddenProcess $python "`"$(Join-Path $PSScriptRoot 'main.py')`" --trip-job `"$script:jobPath`"" $PSScriptRoot
 foreach($c in $form.Controls){if($c -ne $status){$c.Enabled=$false}}
 $status.Text=if($job.operation -eq 'allocate'){'선택한 날짜 안에서 시간을 배분 중입니다. 사이트에는 접속하지 않습니다.'}elseif($job.operation -eq 'scan'){'근태관리에서 출퇴근 등록 날짜를 조회 중입니다.'}elseif($job.operation -eq 'inspect'){'선택 완료: 기존 출장 내역을 확인 중입니다. 아직 등록하지 않습니다.'}else{'사이트 처리 중입니다. 등록은 하루씩 확인한 뒤 다음 날짜로 진행합니다.'};$timer.Start()
}
$scan.Add_Click({try{$script:reviewId=$null;Start-TripJob @{operation='scan';month=(Selected-Month);total=(Target-Amount)}}catch{$status.Text=$_.Exception.Message}})
$allocate.Add_Click({try{[void]$grid.EndEdit();Start-TripJob @{operation='allocate';review_id=$script:reviewId;total=(Target-Amount);rows=@(Entries)}}catch{$status.Text=$_.Exception.Message}})
$complete.Add_Click({try{[void]$grid.EndEdit();Update-Totals;if($complete.Enabled){Start-TripJob @{operation='inspect';review_id=$script:reviewId;total=(Target-Amount);rows=@(Entries)}}}catch{$status.Text=$_.Exception.Message}})
$back.Add_Click({[void]$grid.EndEdit();Update-Totals;Change-Stage 1})
$submit.Add_Click({try{
 [void]$grid.EndEdit();Update-Totals
 if($submit.Enabled){
  $entries=@(Entries)
  $included=@($entries|Where-Object{$_.selected -and -not [string]::IsNullOrWhiteSpace($_.purpose)})
  $excluded=@($entries|Where-Object{-not $_.selected -or [string]::IsNullOrWhiteSpace($_.purpose)})
  $excludedLines=@($excluded|ForEach-Object{('{0}: {1}' -f $_.date,$(if(-not $_.selected){'체크 해제'}else{'목적 미입력'}))})
  $text="등록·수정 대상 $($included.Count)건: $((@($included|ForEach-Object{$_.date})) -join ', ')`r`n제외 $($excluded.Count)건"
  if($excludedLines.Count){$text+="`r`n"+($excludedLines -join "`r`n")}
  $text+="`r`n`r`n$($summary.Text)`r`n`r`n제외한 날짜는 처리하지 않습니다. 기존 출장은 출발·복귀와 장소·목적을 수정하고, 신규 날짜는 추가합니다. 진행할까요?"
  if([Windows.Forms.MessageBox]::Show($form,$text,'출장 등록 확인','OKCancel','Question') -ne 'OK'){return}
  Start-TripJob @{operation='submit';review_id=$script:reviewId;total=(Target-Amount);rows=$entries}
 }
}catch{$status.Text=$_.Exception.Message}})
$total.Add_ValueChanged({Update-Totals})
$month.Add_SelectedIndexChanged({if($script:loading){return};$script:reviewId=$null;$script:allRows=@();$script:existing=0;Change-Stage 1})
$grid.Add_CurrentCellDirtyStateChanged({if($grid.IsCurrentCellDirty){[void]$grid.CommitEdit([Windows.Forms.DataGridViewDataErrorContexts]::Commit)}})
$grid.Add_CellValueChanged({param($sender,$eventArgs)
 if($script:loading -or $eventArgs.RowIndex -lt 0 -or $eventArgs.ColumnIndex -lt 0){return}
 $row=$grid.Rows[$eventArgs.RowIndex];if(-not $row.Tag){return};$name=$grid.Columns[$eventArgs.ColumnIndex].Name
 $script:loading=$true
 try{
  if($script:stage -eq 1 -and -not $row.Tag.is_existing -and $name -eq 'selected' -and $row.Cells['selected'].Value -and -not $row.Tag.selected){
   $others=0;foreach($other in $grid.Rows){if($other -ne $row -and $other.Cells['selected'].Value){$others+=Row-Amount $other}}
   $left=(Target-Amount)-$script:existing-$others
   if($left -lt 10000){$row.Cells['selected'].Value=$false;$status.Text='목표 금액을 이미 채웠습니다. 다른 날짜를 해제하거나 시간을 줄이면 다시 선택할 수 있습니다.'}
   elseif((Row-Amount $row) -gt $left){$row.Cells['hours'].Value='2';$name='hours'}
  }
  if($script:stage -eq 1 -and $name -eq 'hours' -and $row.Cells['selected'].Value){
   $sum=0;foreach($other in $grid.Rows){if($other.Cells['selected'].Value){$sum+=Row-Amount $other}}
   if($script:existing+$sum -gt (Target-Amount)){$row.Cells['hours'].Value=[string]$row.Tag.hours;$status.Text='남은 금액보다 큰 시간은 선택할 수 없습니다.'}
  }
  if($name -in @('hours','start_hour','start_minute')){
   $hour=[int]$row.Cells['start_hour'].Value;$minute=[int]$row.Cells['start_minute'].Value;$hours=[int]$row.Cells['hours'].Value
   $endMinutes=($hour+$hours)*60+$minute
   if($row.Tag.event_day -and $hour -eq 9 -and $minute -eq 0 -and $hours -eq 4){$endMinutes=1080}
   $row.Cells['end'].Value=('{0:D2}:{1:D2}' -f [int][Math]::Floor($endMinutes/60),($endMinutes%60))
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
  }elseif($result.ok){
   $script:reviewId=$result.review_id;$script:allRows=@($result.rows)
   if($script:operation -eq 'inspect' -and $result.ready){
    if(-not (Open-TripDetails $result)){$result.message='다음 단계 이동을 취소했습니다. 날짜·시간 선택을 조정하세요.'}
   }else{Change-Stage 1}
  }
  if(-not $result.ok){throw $result.error}
  $status.Text=$result.message
  if($script:operation -eq 'submit'){$script:closeAfterSubmit=Test-WorkdaySubmissionComplete $result $script:expectedSubmitCount}
 }catch{$status.Text='처리 확인 필요: '+$_.Exception.Message;if($script:operation -ne 'inspect'){$script:reviewId=$null};$errorTitle=if($script:operation -eq 'scan'){'근태 일정 조회 오류'}elseif($script:operation -eq 'inspect'){'기존 출장 확인 오류'}else{'출장 처리 결과'};[void][Windows.Forms.MessageBox]::Show($form,$status.Text,$errorTitle,'OK','Error')}
 finally{
  $script:worker.Dispose();$script:worker=$null;Remove-Item -LiteralPath $script:jobPath,($script:jobPath+'.result.json') -Force -ErrorAction SilentlyContinue
  foreach($c in $form.Controls){$c.Enabled=$true};$grid.Enabled=[bool]$script:reviewId;$total.Enabled=($script:stage -eq 1);$month.Enabled=($script:stage -eq 1);Update-Totals
 }
 if($script:closeAfterSubmit){$form.Close()}
})
$form.Add_FormClosing({if($script:worker){$_.Cancel=$true;$status.Text='진행 중인 처리가 끝난 뒤 닫아 주세요.'}})
. (Join-Path $PSScriptRoot 'theme.ps1');Set-UiTheme $form;$submit.BackColor=$script:UiOrange
Update-Totals
if($SelfTest){
 if(@($form.Controls|Where-Object{$_.Text -eq '기존 출장 불러오기·수정'}).Count){throw '중복 버튼이 남아 있음'}
 $fixture='[{"date":"2026-10-07","weekday":"수","checkin":"09:00","checkout":"18:00","mandatory":false,"event_day":true,"selected":true,"blocked":false,"hours":4,"start_hour":9,"start":"09:00","end":"18:00","amount":20000,"existing_amount":0,"location":"","purpose":"","status":"선택 가능"},{"date":"2026-10-13","weekday":"화","checkin":"08:35","checkout":"18:00","mandatory":false,"selected":false,"blocked":false,"hours":4,"start_hour":13,"start":"13:00","end":"17:00","amount":20000,"existing_amount":0,"location":"","purpose":"","status":"선택 가능"},{"date":"2026-10-14","weekday":"수","checkin":"08:30","checkout":"18:00","mandatory":false,"selected":false,"blocked":false,"hours":4,"start_hour":13,"start":"13:00","end":"17:00","amount":20000,"existing_amount":0,"location":"","purpose":"","status":"선택 가능"}]'|ConvertFrom-Json
 $script:reviewId='fixture';$script:allRows=@($fixture);$total.Value=20;if((Target-Amount) -ne 200000){throw '만원 입력 변환 실패'};$total.Value=3;Render-Rows $script:allRows
 if(-not $complete.Enabled){throw '목표 미달 일정의 다음 단계 진행 불가'}
 $grid.CurrentCell=$grid.Rows[1].Cells['selected'];[void]$grid.BeginEdit($true)
 if($grid.IsCurrentCellInEditMode){throw '체크박스 편집 버퍼 진입'}
 $grid.TestCellClick(1,$grid.Columns['selected'].Index)
 if(-not $grid.Rows[1].Cells['selected'].Value){throw '체크 셀 한 번 클릭 실패'}
 $grid.TestCellClick(1,$grid.Columns['selected'].Index)
 if($grid.Rows[1].Cells['selected'].Value){throw '체크 셀 다시 클릭 해제 실패'}
 $under=[PSCustomObject]@{rows=$script:allRows;summary=[PSCustomObject]@{remaining_amount=10000;message='출장 추가 필요: 2시간 / 10,000원 부족'}}
 $script:lastUnderNotice=''
 if(Open-TripDetails $under {param($text)$script:lastUnderNotice=$text;return $false}){throw '미달 안내 취소 무시'}
 if($script:stage -ne 1 -or $script:lastUnderNotice -notlike '*출장 일수·시간*' -or $script:worker){throw '미달 안내/취소 시 선택 화면 유지 실패'}
 if(-not (Open-TripDetails $under {param($text)return $true}) -or $script:stage -ne 2 -or $grid.Rows.Count -ne 1){throw '미달 안내 확인 후 선택 날짜 이동 실패'}
 Change-Stage 1

 if($grid.Rows[0].Cells['selected'].ReadOnly -or $grid.Rows[0].Cells['start_hour'].ReadOnly -or $grid.Rows[0].Cells['required'].Value -ne '연장근무 제외(행사)'){throw '행사 선택/시간 수정 검사 실패'}
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
 $grid.CreateControl();$grid.TestCellClick(0,$grid.Columns['location'].Index)
 if(-not $grid.IsCurrentCellInEditMode){throw '장소 한 번 클릭 편집 실패'}
 $grid.TestCellClick(0,$grid.Columns['selected'].Index)
 if($grid.Rows[0].Cells['selected'].Value){throw '목적 화면 체크 해제 실패'}
 $grid.TestCellClick(0,$grid.Columns['selected'].Index)
 $grid.Rows[0].Cells['start_minute'].Value='15'
 if($grid.Rows[0].Cells['end'].Value -ne '13:15'){throw '분 변경 자동 복귀 실패'}
 $grid.Rows[0].Cells['end'].Value='17:45';Update-Totals
 if($grid.Rows[0].Cells['end'].Value -ne '17:45'){throw '직접 복귀 시간 유지 실패'}
 $grid.Rows[0].Cells['start_minute'].Value='0';$grid.Rows[0].Cells['end'].Value='18:00'
 $grid.TestCellClick(0,$grid.Columns['location'].Index)
 if(-not $grid.EditingControl){throw '장소 편집 컨트롤 없음'}
 $grid.EditingControl.Text='키보드 입력 장소'
 [void]$grid.MoveEntryKey([Windows.Forms.Keys]::Tab)
 if($grid.CurrentCell.ColumnIndex -ne $grid.Columns['purpose'].Index -or $grid.Rows[0].Cells['location'].Value -ne '키보드 입력 장소'){throw 'Tab 장소→목적/입력 보존 실패'}
 $grid.EditingControl.Text='키보드 입력 목적';[void]$grid.MoveEntryKey([Windows.Forms.Keys]::Enter)
 if($grid.CurrentCell.RowIndex -ne 1 -or $grid.CurrentCell.OwningColumn.Name -ne 'location' -or $grid.Rows[0].Cells['purpose'].Value -ne '키보드 입력 목적'){throw 'Enter 다음 행 장소/입력 보존 실패'}
 [void]$grid.MoveEntryKey([Windows.Forms.Keys]([int][Windows.Forms.Keys]::Shift -bor [int][Windows.Forms.Keys]::Enter))
 if($grid.CurrentCell.RowIndex -ne 0 -or $grid.CurrentCell.OwningColumn.Name -ne 'purpose'){throw 'Shift+Enter 역방향 실패'}
 [void]$grid.MoveEntryKey([Windows.Forms.Keys]([int][Windows.Forms.Keys]::Shift -bor [int][Windows.Forms.Keys]::Tab))
 if($grid.CurrentCell.OwningColumn.Name -ne 'location'){throw 'Shift+Tab 역방향 실패'}
 [void]$grid.EndEdit()
 foreach($row in $grid.Rows){$row.Cells['location'].Value='예시 출장장소';$row.Cells['purpose'].Value='예시 출장목적'}
 Update-Totals;if(-not $submit.Enabled){throw '출장 장소·목적 입력 완료 검사 실패'}
 if($grid.Rows[0].Cells['selected'].ReadOnly){throw '목적 화면 체크 해제 불가'}
 $grid.Rows[0].Cells['purpose'].Value='';Update-Totals;if(-not $submit.Enabled -or $grid.Rows[0].Cells['status'].Value -notlike '*등록 제외*'){throw '목적 빈 날짜 제외/부분 등록 실패'}
 $grid.Rows[0].Cells['purpose'].Value='예시 출장목적';$grid.Rows[0].Cells['selected'].Value=$false;Update-Totals;if(-not $submit.Enabled){throw '체크 해제 후 부분 등록 실패'}
 $grid.Rows[0].Cells['selected'].Value=$true;Update-Totals
 Change-Stage 1;if($grid.Rows.Count -ne 3){throw '전체 일정 복귀 실패'}
 $saved=[PSCustomObject]@{date='2026-10-13';weekday='화';checkin='08:35';checkout='18:00';mandatory=$false;event_day=$false;is_existing=$true;selected=$true;blocked=$false;hours=4;start_hour=13;start='13:00';end='17:00';amount=20000;existing_amount=20000;existing_hours=4;location='저장된 장소';purpose='저장된 목적';status='기존 등록'}
 $script:existing=20000;$script:allRows=@($saved);$total.Value=2;Change-Stage 2
 if(-not $submit.Enabled -or $grid.Rows[0].Cells['selected'].ReadOnly -or $grid.Rows[0].Cells['location'].ReadOnly -or $grid.Rows[0].Cells['start_hour'].ReadOnly){throw '기존 출장 수정/금액 중복 합산 검사 실패'}
 if($grid.Rows[0].Cells['registered'].Value -ne '기등록'){throw '기등록 날짜 표시 실패'}
 if($grid.Rows[0].Cells['location'].Value -ne '저장된 장소' -or $grid.Rows[0].Cells['purpose'].Value -ne '저장된 목적'){throw '기존 장소·목적 불러오기 실패'}

 if($PreviewPath){Change-Stage 2;$script:loading=$true;$form.Controls.Remove($allocate);$form.Controls.Remove($complete);$grid.Columns.Remove('attendance');Write-UiPreview $form $PreviewPath}
 if($InteractiveTest){
  foreach($entry in $fixture){$entry.selected=$false}
  $script:existing=0;$total.Value=20;$script:allRows=@($fixture);Change-Stage 1
  $form.Text='출장 체크 클릭 시험 (사이트 접속 없음)'
  $scan.Enabled=$false;$allocate.Visible=$false;$complete.Visible=$false
  $testNext=Make-Button '입력 화면 클릭 시험' 270 600 330
  $testNext.Add_Click({Update-Totals;Change-Stage 2;$submit.Enabled=$false})
  [void]$form.ShowDialog()
 }
 Write-Output 'TRIPS_UI_OK: budget limit, 2h fit, selected-only detail stage, optional events, under-budget advance, Tab/Enter entry navigation and manual details';$form.Dispose();$timer.Dispose();return
}
if(-not(Enter-WorkdayUi 'trips')){$form.Dispose();$timer.Dispose();return}
try { Show-WorkdayDialog $form $OwnerHandle } finally { Exit-WorkdayUi;$timer.Dispose() }
