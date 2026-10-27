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
function Start-WorkdayHiddenProcess([string]$FileName, [string]$Arguments = '', [string]$WorkingDirectory = $PSScriptRoot, [switch]$CaptureError) {
    $process = New-Object Diagnostics.Process
    $process.StartInfo = New-Object Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName = $FileName
    $process.StartInfo.Arguments = $Arguments
    $process.StartInfo.WorkingDirectory = $WorkingDirectory
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardError = [bool]$CaptureError
    if ($CaptureError) { $process.StartInfo.StandardErrorEncoding = New-Object Text.UTF8Encoding($false) }
    if (-not $process.Start()) { $process.Dispose(); throw '작업을 시작하지 못했습니다.' }
    return $process
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
    if ('WorkdayWindowOwner' -as [type]) {
        [void][WorkdayWindowOwner]::SetCurrentProcessExplicitAppUserModelID('Raphlow.AttendanceManager')
        return
    }
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
    // Window relaunch properties are required for pinning a hosted PowerShell UI.
    [StructLayout(LayoutKind.Sequential)] private struct PropertyKey {
        public Guid format; public uint id;
        public PropertyKey(uint value) { format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"); id = value; }
    }
    [StructLayout(LayoutKind.Explicit, Size=24)] private struct PropVariant {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr pointer;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface PropertyStore {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }
    [DllImport("shell32.dll")] private static extern int SHGetPropertyStoreForWindow(IntPtr window, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out PropertyStore store);
    [DllImport("ole32.dll")] private static extern int PropVariantClear(ref PropVariant value);
    private static PropertyStore WindowStore(IntPtr window) {
        Guid iid = typeof(PropertyStore).GUID; PropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreForWindow(window, ref iid, out store));
        return store;
    }
    private static void SetString(PropertyStore store, uint id, string text) {
        var key = new PropertyKey(id);
        var value = new PropVariant();
        if (text != null) { value.type = 31; value.pointer = Marshal.StringToCoTaskMemUni(text); }
        try { Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value)); }
        finally { if (value.pointer != IntPtr.Zero) Marshal.FreeCoTaskMem(value.pointer); }
    }
    public static void SetTaskbarDetails(IntPtr window, string executable) {
        executable = System.IO.Path.GetFullPath(executable);
        if (!System.IO.File.Exists(executable)) throw new System.IO.FileNotFoundException("Taskbar executable not found", executable);
        PropertyStore store = WindowStore(window);
        try {
            // Set relaunch information before the explicit per-window AppID.
            SetString(store, 2, "\"" + executable + "\"");
            SetString(store, 3, executable + ",0");
            SetString(store, 4, "\uADFC\uD0DC\uB9E4\uB2C8\uC800");
            SetString(store, 5, "Raphlow.AttendanceManager");
        } finally { Marshal.ReleaseComObject(store); }
    }
    public static string GetTaskbarProperty(IntPtr window, uint id) {
        PropertyStore store = WindowStore(window);
        var key = new PropertyKey(id); PropVariant value = new PropVariant();
        try {
            Marshal.ThrowExceptionForHR(store.GetValue(ref key, out value));
            return value.type == 31 ? Marshal.PtrToStringUni(value.pointer) : null;
        } finally { PropVariantClear(ref value); Marshal.ReleaseComObject(store); }
    }

    [DllImport("shell32.dll", CharSet=CharSet.Unicode)] private static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr bind, uint flags, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out PropertyStore store);
    public static void SetShortcutAppId(string path) {
        Guid iid = typeof(PropertyStore).GUID; PropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out store));
        var key = new PropertyKey(5); var value = new PropVariant();
        try {
            Marshal.ThrowExceptionForHR(store.GetValue(ref key, out value));
            if (value.type == 31 && Marshal.PtrToStringUni(value.pointer) == "Raphlow.AttendanceManager") return;
            SetString(store, 5, "Raphlow.AttendanceManager");
            Marshal.ThrowExceptionForHR(store.Commit());
        } finally { PropVariantClear(ref value); Marshal.ReleaseComObject(store); }
    }
    public static void ClearTaskbarDetails(IntPtr window) {
        if (!IsWindow(window)) return;
        PropertyStore store = WindowStore(window);
        try { foreach (uint id in new uint[] {2,3,4,5}) SetString(store, id, null); }
        finally { Marshal.ReleaseComObject(store); }
    }

}
'@
    }
    # Give the WinForms windows their own taskbar group instead of PowerShell's.
    [void][WorkdayWindowOwner]::SetCurrentProcessExplicitAppUserModelID('Raphlow.AttendanceManager')
}
function Set-WorkdayTaskbarWindow($Window) {
    Initialize-WorkdayWindows
    $executable = Join-Path $PSScriptRoot '근태매니저.exe'
    # Source-only test fixtures do not contain the native launcher.
    if (-not (Test-Path -LiteralPath $executable)) { return }
    $create = {
        param($sender, $eventArgs)
        [WorkdayWindowOwner]::SetTaskbarDetails($sender.Handle, $executable)
    }.GetNewClosure()
    $Window.Add_HandleCreated($create)
    # Handle recreation (DPI/style changes) reapplies the same properties.
    if ($Window.IsHandleCreated) { [WorkdayWindowOwner]::SetTaskbarDetails($Window.Handle, $executable) }
    $Window.Add_FormClosed({
        param($sender, $eventArgs)
        if ($sender.IsHandleCreated) { [WorkdayWindowOwner]::ClearTaskbarDetails($sender.Handle) }
    })
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
