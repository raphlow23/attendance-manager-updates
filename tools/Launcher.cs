using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;
[assembly: AssemblyTitle("출근정리")]
[assembly: AssemblyProduct("출근정리")]
[assembly: AssemblyVersion("1.48.0.0")]
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
            SetString(store, 4, "\uCD9C\uADFC\uC815\uB9AC");
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
public static class WorkdayLauncher {
    [STAThread] public static int Main(string[] args) {
        if (Array.IndexOf(args, "--self-test") >= 0) return 0;
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string script = Path.Combine(root, "__ENTRY_SCRIPT__");
            if (!File.Exists(script) && "__ENTRY_SCRIPT__" == "launcher.ps1") {
                root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AutoAttendance");
                script = Path.Combine(root, "launcher.ps1");
            }
            if (!File.Exists(script)) throw new FileNotFoundException("압축을 모두 풀거나 설치 폴더에서 실행해 주세요.", script);
            string shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe");
            var info = new ProcessStartInfo(shell, "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\"");
            info.WorkingDirectory = root; info.UseShellExecute = false; info.CreateNoWindow = true;
            using (var process = Process.Start(info)) {
                if (process == null) throw new Exception("관리 화면을 열지 못했습니다.");
                if (process.WaitForExit(3000) && process.ExitCode != 0)
                    throw new Exception("실행이 중단되었습니다. 설치 폴더의 보안안내.ps1과 Windows 보안의 보호 기록을 확인해 주세요.");
            }
            return 0;
        } catch (Exception error) {
            MessageBox.Show(error.Message, "출근정리 실행 확인", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
    }
}
