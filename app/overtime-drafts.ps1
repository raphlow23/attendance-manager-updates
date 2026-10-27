function Get-OvertimeDraftKey([string]$Account){
 $hash=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Account.Trim())))).Replace('-','')}finally{$hash.Dispose()}
}
function Read-OvertimeDraftDocument([string]$Path){
 if(-not(Test-Path -LiteralPath $Path)){return [PSCustomObject]@{}}
 $document=Get-Content -LiteralPath $Path -Raw -Encoding UTF8|ConvertFrom-Json
 if($document -isnot [PSCustomObject]){throw '목적 임시저장 파일 형식을 확인하세요. 기존 파일은 덮어쓰지 않습니다.'}
 return $document
}
function Read-OvertimePurposes([string]$Path,[string]$Account){
 $document=Read-OvertimeDraftDocument $Path;$key=Get-OvertimeDraftKey $Account
 $property=$document.PSObject.Properties[$key]
 if($property){return $property.Value};return [PSCustomObject]@{}
}
function Save-OvertimePurposes([string]$Path,[string]$Account,$Entries){
 if([string]::IsNullOrWhiteSpace($Account)){return}
 $document=Read-OvertimeDraftDocument $Path;$key=Get-OvertimeDraftKey $Account
 $property=$document.PSObject.Properties[$key]
 $values=if($property){$property.Value}else{[PSCustomObject]@{}}
 foreach($entry in $Entries){
  if(([string]$entry.date) -notmatch '^\d{4}-\d{2}-\d{2}$'){continue}
  $values|Add-Member -NotePropertyName ([string]$entry.date) -NotePropertyValue ([string]$entry.purpose) -Force
 }
 $document|Add-Member -NotePropertyName $key -NotePropertyValue $values -Force
 New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force|Out-Null
 Write-WorkdayText $Path ($document|ConvertTo-Json -Depth 8)
}
