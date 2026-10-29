$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
. (Join-Path $PSScriptRoot '../app/session.ps1')
$success=[PSCustomObject]@{ok=$true;rows=@([PSCustomObject]@{status='신청 확인 완료'},[PSCustomObject]@{status='수정 확인 완료'})}
$partial=[PSCustomObject]@{ok=$true;rows=@([PSCustomObject]@{status='신청 확인 완료'})}
$uncertain=[PSCustomObject]@{ok=$true;rows=@([PSCustomObject]@{status='신청 확인 완료'},[PSCustomObject]@{status='확인 필요: 응답 없음'})}
$failed=[PSCustomObject]@{ok=$false;rows=$success.rows}
foreach($case in @($partial,$uncertain,$failed)){
 if(Test-WorkdaySubmissionComplete $case 2){throw '부분/실패 결과 자동 닫힘'}
}
if(Test-WorkdaySubmissionComplete ([PSCustomObject]@{ok=$true;rows=@()}) 0){throw '빈 결과 자동 닫힘'}
foreach($name in @('신청 확인 완료','수정 확인 완료','등록 확인 완료','기존 내용 동일 · 유지')){
 if(-not(Test-WorkdaySubmissionComplete ([PSCustomObject]@{ok=$true;rows=@([PSCustomObject]@{status=$name})}) 1)){throw '성공 결과 인식 실패'}
}
$window=New-Object Windows.Forms.Form
$window.Opacity=0;$window.ShowInTaskbar=$false
$window.Show();[Windows.Forms.Application]::DoEvents()
if(Test-WorkdaySubmissionComplete $uncertain 2){$window.Close()}
if(-not $window.Visible){throw '미완료 창 유지 실패'}
if(Test-WorkdaySubmissionComplete $success 2){$window.Close()}
if($window.Visible){throw '완료 창 닫기 실패'}
$window.Dispose()
foreach($name in @('overtime.ps1','trips.ps1')){
 $source=[IO.File]::ReadAllText((Join-Path $PSScriptRoot ('../app/'+$name)))
 if($source -notmatch 'if\(\$script:closeAfterSubmit\)\{\$form.Close\(\)\}'){throw ('완료 창 닫기 연결 없음: '+$name)}
}
Write-Output 'SUBMISSION_COMPLETION_OK: all selected saved -> close; partial/error/uncertain/empty -> keep open'
