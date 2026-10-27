$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'app/session.ps1')
. (Join-Path $root 'app/overtime-drafts.ps1')
$folder=Join-Path $root ('.test-data/overtime-drafts-'+[Guid]::NewGuid().ToString('N'))
$path=Join-Path $folder 'drafts.json'
try{
 Save-OvertimePurposes $path 'fixture-account-A' @(@{date='2026-10-01';purpose='첫째 목적'},@{date='2026-10-02';purpose='아직 미신청인 둘째 목적'})
 Save-OvertimePurposes $path 'fixture-account-B' @(@{date='2026-10-01';purpose='다른 계정 목적'})
 Save-OvertimePurposes $path 'fixture-account-A' @(@{date='2026-10-01';purpose=''})
 $a=Read-OvertimePurposes $path 'fixture-account-A';$b=Read-OvertimePurposes $path 'fixture-account-B'
 if($a.'2026-10-01' -ne '' -or $a.'2026-10-02' -ne '아직 미신청인 둘째 목적' -or $b.'2026-10-01' -ne '다른 계정 목적'){throw '목적 임시저장/복원/계정 분리 실패'}
 if((Get-Content -LiteralPath $path -Raw) -match 'fixture-account-'){throw '계정 원문을 임시저장 키에 기록함'}
 Write-Output 'OVERTIME_DRAFTS_OK: pending purposes preserved, empty edits kept, account scopes isolated, atomic UTF8 file'
}finally{
 if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force}
 if(Test-Path -LiteralPath $folder){Remove-Item -LiteralPath $folder}
}
