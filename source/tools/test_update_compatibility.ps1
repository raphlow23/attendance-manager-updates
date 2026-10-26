$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$script:CompatibilitySourceRoot=$root
$old=Join-Path $root '.test-data\single-installer-smoke-11'
$target=Join-Path $root ('.test-data\update-compatibility-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $target 'dist') -Force | Out-Null
Get-ChildItem $old -File | Copy-Item -Destination $target
$settings=Join-Path $target 'dist\settings-fixture.json'
[IO.File]::WriteAllText($settings,'{"id":"test-only","enabled":false}')
[IO.File]::WriteAllText((Join-Path $target 'dist\automation.stop'),'test-only intentional stop')
$before=(Get-FileHash $settings).Hash
. (Join-Path $old 'update.ps1')
function Invoke-RestMethod { param($Uri,$TimeoutSec,$Headers); Get-Content (Join-Path $script:CompatibilitySourceRoot 'releases\latest.json') -Raw -Encoding UTF8 | ConvertFrom-Json }
function Invoke-WebRequest { param($Uri,$OutFile,$TimeoutSec,[switch]$UseBasicParsing); Copy-Item (Join-Path $script:CompatibilitySourceRoot 'releases\attendance-manager-v12.zip') $OutFile }
$result=Invoke-WorkdayUpdate $target
if($result -notlike '업데이트 적용 완료*'){throw $result}
if([int](Get-Content (Join-Path $target 'release-version.txt')) -ne 12){throw 'Version not updated'}
if((Get-FileHash $settings).Hash -ne $before){throw 'User data changed'}
if(-not(Test-Path (Join-Path $target 'dist\automation.stop'))){throw 'Intentional stop was lost'}
if(Test-Path (Join-Path $target 'dist\update.pause')){throw 'Update pause was left behind'}
# A prior disabled UI preference must no longer disable the fixed update channel.
[IO.File]::WriteAllText((Join-Path $target 'dist\업데이트설정.json'),'{"enabled":false,"manifest_url":""}')
. (Join-Path $target 'update.ps1')
$result=Invoke-WorkdayUpdate $target
if($result -notlike '자동 업데이트: 최신 버전*'){throw 'Legacy preference still bypasses automatic update'}
Write-Output 'UPDATE_COMPATIBILITY_OK: v11 updater accepts v12 archive; signature/digest verified; user data/stop preserved; automatic channel enforced'
