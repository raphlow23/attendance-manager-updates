$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'app\install-integration.ps1')
$script:Properties = @{}
$script:RegistryCreated = $false
# Simulate registry/file providers. This test never registers or removes an app.
function Test-Path { param([string]$LiteralPath); return $LiteralPath.EndsWith('.exe') }
function Get-Content { param([string]$LiteralPath, [switch]$Raw); return '10' }
function New-Item { param([string]$Path,[switch]$Force); $script:RegistryCreated = $Path.EndsWith('\Uninstall\AttendanceManager') }
function New-ItemProperty { param([string]$LiteralPath,[string]$Name,$Value,[string]$PropertyType,[switch]$Force); $script:Properties[$Name]=$Value }
$installRoot = Join-Path $env:LOCALAPPDATA 'AutoAttendance'
$plan = Register-AttendanceInstall $installRoot
if (-not $script:RegistryCreated -or $script:Properties.DisplayName -ne '출근정리') { throw '앱 등록 정보 실패' }
if ($script:Properties.UninstallString -ne ('"' + (Join-Path $installRoot '제거.exe') + '"')) { throw '제거 진입점 실패' }
if ($script:Properties.DisplayVersion -ne '1.1.0' -or $plan.Tasks.Count -ne 4) { throw '버전 또는 예약 정리 목록 실패' }
$rejected = $false
try { Assert-AttendanceInstallRoot 'C:\Windows' } catch { $rejected=$true }
if (-not $rejected) { throw '기본 설치 위치 이외 제거 경로를 허용했습니다.' }
Write-Output 'INSTALL_LIFECYCLE_TESTS_OK: app metadata, uninstaller path, four tasks, foreign-root rejection (providers mocked)'
