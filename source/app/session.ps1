function Enter-WorkdayUi([string]$Feature) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $script:UiMutex = New-Object Threading.Mutex($false, "Local\Workday.UI.$Feature.$sid")
    $script:UiMutexOwned = $false
    try { $script:UiMutexOwned = $script:UiMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $script:UiMutexOwned = $true }
    if (-not $script:UiMutexOwned) { $script:UiMutex.Dispose(); return $false }
    return $true
}
function Get-WorkdayMonthLabels([DateTime]$Now = (Get-Date)) {
    $first = New-Object DateTime($Now.Year, $Now.Month, 1)
    for ($i = 0; $i -lt 60; $i++) { $first.AddMonths(-$i).ToString('yyyy년 MM월') }
}
function Write-WorkdayText([string]$Path, [string]$Text) {
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temporary, $Text, (New-Object Text.UTF8Encoding($false)))
    try {
        for ($attempt=0; $attempt -lt 50; $attempt++) {
            try {
                if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [System.Management.Automation.Language.NullString]::Value) }
                else { [IO.File]::Move($temporary, $Path) }
                return
            } catch [IO.IOException] { if ($attempt -eq 49) { throw }; Start-Sleep -Milliseconds 20 }
        }
    } finally { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
}
function Initialize-WorkdayWindows {
    if ('WorkdayWindowOwner' -as [type]) { return }
    # Load the precompiled helper from bytes so updates can replace the EXE.
    $helper = Join-Path $PSScriptRoot '근태매니저.exe'
    if (Test-Path -LiteralPath $helper) {
        $assembly = [Reflection.Assembly]::Load([IO.File]::ReadAllBytes($helper))
        if (-not $assembly.GetType('WorkdayWindowOwner')) { $assembly = $null }
    }
    if (-not ('WorkdayWindowOwner' -as [type])) {
        Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public sealed class WorkdayWindowOwner : IWin32Window {
    public IntPtr Handle { get; private set; }
    public WorkdayWindowOwner(long handle) { Handle = new IntPtr(handle); }
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int processId);
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)] public static extern int SetCurrentProcessExplicitAppUserModelID(string appId);
}
'@
    }
    # Give the WinForms windows their own taskbar group instead of PowerShell's.
    [void][WorkdayWindowOwner]::SetCurrentProcessExplicitAppUserModelID('Raphlow.AttendanceManager')
}
function Show-WorkdayDialog($Window, [long]$OwnerHandle = 0) {
    Initialize-WorkdayWindows
    $Window.Add_Shown({ param($sender, $eventArgs); $sender.BringToFront(); $sender.Activate() })
    if ($OwnerHandle -ne 0 -and [WorkdayWindowOwner]::IsWindow([IntPtr]$OwnerHandle)) {
        $owner = New-Object WorkdayWindowOwner($OwnerHandle)
        [void]$Window.ShowDialog($owner)
    } else {
        [void]$Window.ShowDialog()
    }
}
function Exit-WorkdayUi {
    if ($script:UiMutexOwned) { $script:UiMutex.ReleaseMutex(); $script:UiMutex.Dispose(); $script:UiMutexOwned = $false }
}
function Start-WorkdayEngine {
    $folder = Join-Path $PSScriptRoot 'dist'
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $settings = Get-Content -LiteralPath (Join-Path $folder '자동출근설정.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $settings.id -or -not $settings.pw) { throw '먼저 자동 출퇴근 설정에서 계정을 저장해 주세요.' }
    $settings | Add-Member -NotePropertyName enabled -NotePropertyValue $true -Force
    Write-WorkdayText (Join-Path $folder '자동출근설정.json') ($settings | ConvertTo-Json)
    foreach ($name in @('automation.stop','restart.blocked','restart-failed.notice.txt')) { Remove-Item -LiteralPath (Join-Path $folder $name) -Force -ErrorAction SilentlyContinue }
    Start-Process -FilePath (Join-Path $PSScriptRoot 'WorkdayGuard.exe') -WindowStyle Hidden
}
function Stop-WorkdayEngine {
    $folder = Join-Path $PSScriptRoot 'dist'
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $folder 'automation.stop'), (Get-Date).ToString('o') + ' user requested stop')
}
