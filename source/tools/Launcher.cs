using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;
[assembly: AssemblyTitle("근태매니저")]
[assembly: AssemblyProduct("근태매니저")]
[assembly: AssemblyVersion("1.16.0.0")]
public sealed class WorkdayWindowOwner : IWin32Window {
    public IntPtr Handle { get; private set; }
    public WorkdayWindowOwner(long handle) { Handle = new IntPtr(handle); }
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr handle);
    [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int processId);
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)] public static extern int SetCurrentProcessExplicitAppUserModelID(string appId);
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
            MessageBox.Show(error.Message, "근태매니저 실행 확인", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
    }
}
