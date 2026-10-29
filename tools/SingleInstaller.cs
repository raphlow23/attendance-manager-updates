using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
using System.Windows.Forms;
[assembly: AssemblyTitle("출근정리 설치")]
[assembly: AssemblyProduct("출근정리")]
[assembly: AssemblyVersion("1.6.6.0")]

public static class AttendanceSetup {
    const string ExpectedHash = "__PAYLOAD_SHA256__";
    static string Quote(string value) { return "\"" + value.Replace("\"", "") + "\""; }
    static Stream Payload() {
        Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("AttendanceManager.Package.zip");
        if (stream == null) throw new InvalidDataException("설치 데이터가 없습니다.");
        using (SHA256 hash = SHA256.Create()) {
            string actual = BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "");
            if (!String.Equals(actual, ExpectedHash, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("설치 파일이 손상되었습니다. 다시 받아 주세요.");
        }
        stream.Position = 0; return stream;
    }
    static string Target(string root, string entry) {
        string prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (Path.IsPathRooted(entry)) throw new InvalidDataException("잘못된 설치 경로입니다.");
        string path = Path.GetFullPath(Path.Combine(prefix, entry.Replace('/', Path.DirectorySeparatorChar)));
        if (!path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("설치 경로가 폴더 밖을 가리킵니다.");
        return path;
    }
    static void Validate(ZipArchive archive, string root) {
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (ZipArchiveEntry entry in archive.Entries) {
            Target(root, entry.FullName);
            if (!names.Add(entry.FullName)) throw new InvalidDataException("중복 설치 파일입니다.");
            total += entry.Length;
            if (entry.Length > 256L * 1024 * 1024 || total > 512L * 1024 * 1024) throw new InvalidDataException("설치 데이터 크기가 올바르지 않습니다.");
        }
        foreach (string file in new [] {"gui-install.ps1", "install.ps1", "MANIFEST-SHA256.txt", "app/출근정리.exe", "app/제거.exe", "app/uninstall.ps1"})
            if (!names.Contains(file)) throw new InvalidDataException("필수 설치 파일이 없습니다: " + file);
    }
    static void Extract(string destination) {
        if (Directory.Exists(destination) || File.Exists(destination)) throw new IOException("시험 압축 해제 폴더가 이미 있습니다.");
        using (Stream stream = Payload()) using (var archive = new ZipArchive(stream, ZipArchiveMode.Read)) {
            Validate(archive, destination); Directory.CreateDirectory(destination);
            foreach (ZipArchiveEntry entry in archive.Entries) {
                string path = Target(destination, entry.FullName);
                if (String.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(path); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                using (Stream input = entry.Open()) using (var output = new FileStream(path, FileMode.CreateNew)) input.CopyTo(output);
            }
        }
    }
    static int RunInstaller(string staging, string testInstallRoot) {
        string shell = Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe");
        string args = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File ";
        args += Quote(Path.Combine(staging, "gui-install.ps1"));
        if (testInstallRoot != null) args += " -InstallRoot " + Quote(Path.GetFullPath(testInstallRoot)) + " -SelfTest";
        var info = new ProcessStartInfo(shell, args);
        info.WorkingDirectory = staging; info.UseShellExecute = false; info.CreateNoWindow = true;
        info.EnvironmentVariables["PSModulePath"] = Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\Modules") + ";" + Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"WindowsPowerShell\Modules");
        using (Process process = Process.Start(info)) { process.WaitForExit(); return process.ExitCode; }
    }
    static void Cleanup(string staging) {
        string temp = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string full = Path.GetFullPath(staging);
        if (!full.StartsWith(temp, StringComparison.OrdinalIgnoreCase) || !Path.GetFileName(full).StartsWith("AttendanceManager-", StringComparison.Ordinal)) return;
        try { if (Directory.Exists(full) && (File.GetAttributes(full) & FileAttributes.ReparsePoint) == 0) Directory.Delete(full, true); } catch { }
    }
    [STAThread] public static int Main(string[] args) {
        bool diagnostic = args.Length > 0;
        try {
            if (args.Length == 1 && args[0] == "--self-test") {
                using (Stream stream = Payload()) using (var archive = new ZipArchive(stream, ZipArchiveMode.Read)) Validate(archive, Path.Combine(Path.GetTempPath(), "AttendanceManager-validation"));
                return 0;
            }
            if (args.Length == 2 && args[0] == "--extract-only") { Extract(Path.GetFullPath(args[1])); return 0; }
            if (args.Length == 2 && args[0] == "--test-install") {
                string staging = Path.Combine(Path.GetTempPath(), "AttendanceManager-" + Guid.NewGuid().ToString("N"));
                try { Extract(staging); return RunInstaller(staging, args[1]); } finally { Cleanup(staging); }
            }
            if (args.Length != 0) return 2;
            Application.EnableVisualStyles();
            var form = new Form { Text="출근정리 설치", ClientSize=new Size(450,155), StartPosition=FormStartPosition.CenterScreen, FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false, ControlBox=false, BackColor=Color.FromArgb(236,238,243) };
            var label = new Label { Text="출근정리 설치를 준비하고 있습니다.", AutoSize=false, Location=new Point(28,25), Size=new Size(400,40), Font=new Font("Malgun Gothic",11) };
            var progress = new ProgressBar { Location=new Point(28,90), Size=new Size(395,22), Style=ProgressBarStyle.Marquee };
            form.Controls.Add(label); form.Controls.Add(progress);
            Exception failure = null; int exitCode = 1;
            form.Shown += delegate {
                ThreadPool.QueueUserWorkItem(delegate {
                    string staging = Path.Combine(Path.GetTempPath(), "AttendanceManager-" + Guid.NewGuid().ToString("N"));
                    try {
                        Extract(staging);
                        form.Invoke((Action)delegate { form.Hide(); });
                        exitCode = RunInstaller(staging, null);
                    } catch (Exception error) { failure = error; }
                    finally { Cleanup(staging); form.Invoke((Action)delegate { form.Close(); }); }
                });
            };
            Application.Run(form);
            if (failure != null) throw failure;
            return exitCode;
        } catch (Exception error) {
            if (!diagnostic) MessageBox.Show(error.Message, "출근정리 설치 확인", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
