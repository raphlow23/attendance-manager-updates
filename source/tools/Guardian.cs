using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Principal;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public static class WorkdayGuardian {
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    static string root, data;
    static bool testing;
    static int interval = 2000, staleSeconds = 45, graceSeconds = 60, maxRestarts = 3, windowSeconds = 900;
    static string workerFile, workerArguments;
    static Process child;
    static IntPtr workerJob = IntPtr.Zero;
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime, JobTime; public uint Flags;
        public UIntPtr MinimumWorkingSet, MaximumWorkingSet; public uint ActiveProcessLimit;
        public UIntPtr Affinity; public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOperations, WriteOperations, OtherOperations, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr security, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);

    static void OwnWorkerTree() {
        workerJob = CreateJobObject(IntPtr.Zero, null);
        var limits = new ExtendedLimits(); limits.Basic.Flags = 0x2000; // KILL_ON_JOB_CLOSE
        int size = Marshal.SizeOf(typeof(ExtendedLimits));
        IntPtr memory = Marshal.AllocHGlobal(size);
        try {
            Marshal.StructureToPtr(limits, memory, false);
            if (workerJob == IntPtr.Zero || !SetInformationJobObject(workerJob, 9, memory, (uint)size) || !AssignProcessToJobObject(workerJob, child.Handle)) {
                if (workerJob != IntPtr.Zero) CloseHandle(workerJob);
                workerJob = IntPtr.Zero;
                throw new Exception("Windows Job Object assignment failed");
            }
        } finally { Marshal.FreeHGlobal(memory); }
    }
    static int launches;
    static DateTime lastValidHeartbeat = DateTime.MinValue;
    static readonly Queue<DateTime> failures = new Queue<DateTime>();
    static readonly int[] Delays = {5, 15, 45};

    static Dictionary<string, object> Read(string path) {
        try { return Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path)); }
        catch { return new Dictionary<string, object>(); }
    }
    static string Value(Dictionary<string, object> item, string key) {
        return item.ContainsKey(key) && item[key] != null ? Convert.ToString(item[key], CultureInfo.InvariantCulture) : "";
    }
    static void Log(string text) {
        try { File.AppendAllText(Path.Combine(data, "guardian.log"), DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + text + Environment.NewLine); } catch { }
    }
    static void Write(string path, object value) {
        string temporary = path + ".new";
        File.WriteAllText(temporary, Json.Serialize(value));
        if (File.Exists(path)) File.Replace(temporary, path, null); else File.Move(temporary, path);
    }
    static void Status(string state, string error) {
        Write(Path.Combine(data, "guardian-status.json"), new {
            pid = Process.GetCurrentProcess().Id,
            worker_pid = child == null || child.HasExited ? 0 : child.Id,
            state = state, restart_count = failures.Count, launches = launches,
            updated_utc = DateTime.UtcNow.ToString("o"), last_error = error
        });
    }
    static bool Stopped() {
        if (File.Exists(Path.Combine(data, "automation.stop")) || File.Exists(Path.Combine(data, "update.pause"))) return true;
        if (testing) return false;
        var settings = Read(Path.Combine(data, "자동출근설정.json"));
        return !settings.ContainsKey("id") || (settings.ContainsKey("enabled") && !Convert.ToBoolean(settings["enabled"]));
    }
    static void KillOwnedWorker() {
        if (child == null) return;
        try {
            if (workerJob != IntPtr.Zero) { CloseHandle(workerJob); workerJob = IntPtr.Zero; child.WaitForExit(5000); }
            if (!child.HasExited) {
                var killer = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "taskkill.exe"), "/PID " + child.Id + " /T /F");
                killer.UseShellExecute = false; killer.CreateNoWindow = true;
                using (var operation = Process.Start(killer)) { if (operation != null) operation.WaitForExit(5000); }
                if (!child.HasExited) child.Kill();
                child.WaitForExit(5000);
            }
        } catch (Exception error) { Log("worker stop: " + error.GetType().Name + ": " + error.Message); }
        finally { child.Dispose(); child = null; }
    }
    static bool Unhealthy(DateTime started, out string reason) {
        reason = "";
        if (child == null || child.HasExited) {
            reason = child == null ? "worker did not start" : "unexpected worker exit: " + child.ExitCode;
            return true;
        }
        var health = Read(Path.Combine(data, "worker-health.json"));
        int pid;
        DateTime beat;
        if (!Int32.TryParse(Value(health, "pid"), out pid) || pid != child.Id || !DateTime.TryParse(Value(health, "heartbeat_utc"), null, DateTimeStyles.RoundtripKind, out beat)) {
            DateTime reference = lastValidHeartbeat == DateTime.MinValue ? started : lastValidHeartbeat;
            int tolerance = lastValidHeartbeat == DateTime.MinValue ? graceSeconds : staleSeconds;
            if ((DateTime.UtcNow - reference).TotalSeconds <= tolerance) return false;
            reason = "worker heartbeat missing or invalid"; return true;
        }
        if ((DateTime.UtcNow - beat.ToUniversalTime()).TotalSeconds > staleSeconds) {
            reason = "worker heartbeat expired"; return true;
        }
        lastValidHeartbeat = DateTime.UtcNow;
        if (health.ContainsKey("stalled") && Convert.ToBoolean(health["stalled"])) {
            reason = "automation operation stalled despite live process"; return true;
        }
        return false;
    }
    static void Notify(string message) {
        Log(message);
        File.WriteAllText(Path.Combine(data, "restart-failed.notice.txt"), DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message);
        if (testing) return;
        try {
            var notification = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe"),
                "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + Path.Combine(root, "notify.ps1") + "\"");
            notification.UseShellExecute = false; notification.CreateNoWindow = true; Process.Start(notification);
        } catch (Exception error) { Log("notification failed: " + error.Message); }
    }

    [STAThread] public static int Main(string[] args) {
        if (Array.IndexOf(args, "--self-test") >= 0) return 0;
        root = AppDomain.CurrentDomain.BaseDirectory;
        data = Path.Combine(root, "dist");
        if (Array.IndexOf(args, "--watchdog") >= 0) {
            var info = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe"),
                "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + Path.Combine(root, "watchdog.ps1") + "\"");
            info.WorkingDirectory = root; info.UseShellExecute = false; info.CreateNoWindow = true;
            using (var watcher = Process.Start(info)) { watcher.WaitForExit(); return watcher.ExitCode; }
        }
        int testIndex = Array.IndexOf(args, "--test-config");
        testing = testIndex >= 0;
        if (testing) {
            var config = Read(args[testIndex + 1]);
            data = Path.GetFullPath(Value(config, "data"));
            workerFile = Value(config, "executable"); workerArguments = Value(config, "arguments");
            interval = 100; staleSeconds = 2; graceSeconds = 4; windowSeconds = 60;
        } else {
            workerFile = Path.Combine(root, @"runtime\python.exe");
            workerArguments = "\"" + Path.Combine(root, "main.py") + "\" --resident-worker";
        }
        Directory.CreateDirectory(data);
        string identity = testing ? data.ToLowerInvariant() : WindowsIdentity.GetCurrent().User.Value;
        using (var hash = System.Security.Cryptography.SHA256.Create()) {
            identity = BitConverter.ToString(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(identity))).Replace("-", "");
        }
        bool owned = false;
        using (var mutex = new Mutex(false, "Local\\Workday.Guard." + identity)) {
            try {
                try { owned = mutex.WaitOne(0); } catch (AbandonedMutexException) { owned = true; }
                if (!owned) return 0;
                if (Stopped()) { Status("intentional_stop", ""); return 0; }
                if (File.Exists(Path.Combine(data, "restart.blocked"))) { Status("restart_blocked", "사용자 확인 후 다시 시작 필요"); return 2; }
                Log("guardian started");
                if (!testing && Array.IndexOf(args, "--show-ui") >= 0) {
                    try {
                        var ui = new ProcessStartInfo(Path.Combine(root, "출근정리.exe"));
                        ui.UseShellExecute = false; ui.CreateNoWindow = true; Process.Start(ui);
                    } catch (Exception error) { Log("UI launch failure: " + error.Message); }
                }
                DateTime started = DateTime.UtcNow;
                while (!Stopped()) {
                    if (child == null) {
                        try {
                            var info = new ProcessStartInfo(workerFile, workerArguments);
                            info.WorkingDirectory = root; info.UseShellExecute = false; info.CreateNoWindow = true;
                            child = Process.Start(info); OwnWorkerTree(); started = DateTime.UtcNow; lastValidHeartbeat = DateTime.MinValue; launches++;
                            Log("worker started pid=" + child.Id);
                        } catch (Exception error) { Log("worker launch failure: " + error.GetType().Name + ": " + error.Message); }
                    }
                    if (testing && File.Exists(Path.Combine(data, "test.kill-worker")) && child != null && !child.HasExited) {
                        File.Delete(Path.Combine(data, "test.kill-worker"));
                        child.Kill(); child.WaitForExit(3000); // actual process termination for isolated fault injection
                    }
                    string problem;
                    if (Unhealthy(started, out problem)) {
                        KillOwnedWorker();
                        while (failures.Count > 0 && (DateTime.UtcNow - failures.Peek()).TotalSeconds > windowSeconds) failures.Dequeue();
                        failures.Enqueue(DateTime.UtcNow);
                        Log(problem); Status("recovering", problem);
                        if (failures.Count >= maxRestarts) {
                            File.WriteAllText(Path.Combine(data, "restart.blocked"), DateTime.Now.ToString("o") + " " + problem);
                            Status("restart_blocked", problem);
                            Notify("자동 실행 복구에 반복 실패했습니다. 상태 및 오류 로그와 Windows 보안 보호 기록을 확인한 뒤 다시 시작해 주세요.");
                            return 2;
                        }
                        int delay = testing ? 150 : Delays[Math.Min(failures.Count - 1, Delays.Length - 1)] * 1000;
                        for (int elapsed = 0; elapsed < delay && !Stopped(); elapsed += interval) Thread.Sleep(interval);
                        continue;
                    }
                    Status("running", "");
                    Thread.Sleep(interval);
                }
                Log("intentional stop/update pause/settings disabled");
                Status("intentional_stop", "");
                return 0;
            } catch (Exception error) {
                Log("guardian fatal: " + error.GetType().Name + ": " + error.Message); return 1;
            } finally {
                KillOwnedWorker();
                if (owned) mutex.ReleaseMutex();
            }
        }
    }
}
