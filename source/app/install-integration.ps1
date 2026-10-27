function Get-AttendanceInstallPlan([string]$Root) {
    $full = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    [PSCustomObject]@{
        Root = $full
        RegistryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AttendanceManager'
        DisplayName = '출근정리'
        Executable = (Join-Path $full '출근정리.exe')
        Uninstaller = (Join-Path $full '제거.exe')
        Tasks = @('자동출근','자동퇴근','자동출퇴근로그인','자동출퇴근점검')
        Shortcuts = @('출근정리.lnk','근태매니저.lnk','Workday 출퇴근관리.lnk')
    }
}
function Assert-AttendanceInstallRoot([string]$Root) {
    $actual = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'AutoAttendance')).TrimEnd('\')
    if (-not $actual.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) { throw '등록/제거 대상이 출근정리의 기본 설치 폴더가 아닙니다.' }
    if ((Test-Path -LiteralPath $actual) -and ((Get-Item -LiteralPath $actual).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '설치 폴더가 링크여서 등록/제거를 중단합니다.' }
}
function Register-AttendanceInstall([string]$Root, [switch]$PlanOnly) {
    $plan = Get-AttendanceInstallPlan $Root
    if ($PlanOnly) { return $plan }
    Assert-AttendanceInstallRoot $Root
    if (-not (Test-Path -LiteralPath $plan.Executable) -or -not (Test-Path -LiteralPath $plan.Uninstaller)) { throw '프로그램 또는 제거 실행 파일이 없습니다.' }
    $version = [int](Get-Content -LiteralPath (Join-Path $Root 'release-version.txt') -Raw)
    New-Item -Path $plan.RegistryKey -Force | Out-Null
    $values = @{
        DisplayName='출근정리'; DisplayVersion="1.$version.0"; Publisher='출근정리'
        InstallLocation=$plan.Root; DisplayIcon=($plan.Executable + ',0')
        UninstallString=('"' + $plan.Uninstaller + '"')
        QuietUninstallString=('"' + "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" + '" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $plan.Root 'uninstall.ps1') + '" -Silent')
        InstallDate=(Get-Date).ToString('yyyyMMdd')
        HelpLink='https://github.com/raphlow23/attendance-manager-updates'
    }
    foreach ($name in $values.Keys) { New-ItemProperty -LiteralPath $plan.RegistryKey -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null }
    foreach ($name in @('NoModify','NoRepair')) { New-ItemProperty -LiteralPath $plan.RegistryKey -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
    # Repair only our existing desktop shortcut; never rewrite pinned PowerShell
    # shortcuts, which may also be used by other programs.
    $desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) '출근정리.lnk'
    $legacyLink = Join-Path ([Environment]::GetFolderPath('Desktop')) '근태매니저.lnk'
    if ((Test-Path -LiteralPath $legacyLink) -and -not (Test-Path -LiteralPath $desktopLink)) {
        $shell = New-Object -ComObject WScript.Shell
        $legacy = $shell.CreateShortcut($legacyLink)
        if ($legacy.TargetPath -in @($plan.Executable, (Join-Path $plan.Root '근태매니저.exe'))) {
            $updated = $shell.CreateShortcut($desktopLink)
            $updated.TargetPath=$plan.Executable; $updated.WorkingDirectory=$plan.Root
            $updated.IconLocation=$plan.Executable+',0'; $updated.Save()
            Initialize-WorkdayWindows
            [WorkdayWindowOwner]::SetShortcutAppId($desktopLink)
            Remove-Item -LiteralPath $legacyLink -Force
        }
    }
    if (Test-Path -LiteralPath $desktopLink) {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($desktopLink)
        if ($shortcut.TargetPath -eq $plan.Executable) {
            if ($shortcut.IconLocation -ne ($plan.Executable + ',0')) {
                $shortcut.IconLocation = $plan.Executable + ',0'; $shortcut.Save()
            }
            Initialize-WorkdayWindows
            [WorkdayWindowOwner]::SetShortcutAppId($desktopLink)
        }
    }
    return $plan
}
