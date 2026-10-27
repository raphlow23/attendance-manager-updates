"""Windows process-level tests. No OS restart, adapter change or task install."""
import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'app' / 'WorkdayGuard.exe'


def read(path):
    # The native guard replaces its JSON atomically. Windows can briefly deny
    # a simultaneous open during replacement; do not treat this as absent data.
    for attempt in range(5):
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            if attempt == 4:
                return {}
            time.sleep(.01)


def alive(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return False
    code = ctypes.c_ulong()
    try:
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


@unittest.skipUnless(os.name == 'nt' and GUARD.exists(), 'Windows guardian EXE required')
class GuardianIntegration(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-data').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.test-data')
        self.data = Path(self.temp.name)
        self.config = self.data / 'test-config.json'
        self.processes = []

    def start(self, mode='healthy', url=None):
        args = [str(ROOT / 'tests' / 'guardian_fixture.py'), str(self.data), mode]
        if url:
            args.append(url)
        self.config.write_text(json.dumps({'data': str(self.data), 'executable': sys.executable,
                                          'arguments': subprocess.list2cmdline(args)}), encoding='utf-8')
        process = subprocess.Popen([str(GUARD), '--test-config', str(self.config)], creationflags=subprocess.CREATE_NO_WINDOW)
        self.processes.append(process)
        return process

    def wait_for(self, predicate, timeout=16):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(.1)
        self.fail('Timed out. Guardian log: ' + (self.data / 'guardian.log').read_text(encoding='utf-8-sig'))

    def status(self):
        return read(self.data / 'guardian-status.json')

    def health(self):
        return read(self.data / 'worker-health.json')

    def tearDown(self):
        (self.data / 'automation.stop').write_text('test cleanup')
        for process in self.processes:
            try:
                process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self.temp.cleanup()

    def test_logon_action_starts_worker_and_duplicate_guard_is_ignored(self):
        self.start()
        self.wait_for(lambda: self.status().get('state') == 'running' and self.health().get('pid'))
        pid = self.health()['pid']
        duplicate = self.start()
        self.assertEqual(duplicate.wait(timeout=3), 0)
        self.assertEqual(self.health()['pid'], pid)
        self.assertEqual(self.status()['launches'], 1)

    def test_forced_worker_exit_is_restarted(self):
        self.start()
        self.wait_for(lambda: self.health().get('pid'))
        first = self.health()['pid']
        # The guarded worker can run in a nested Windows Job Object under a
        # sandbox token. Ask its owner to inject Process.Kill, then exercise
        # the same unexpected-exit recovery path as an external termination.
        (self.data / 'test.kill-worker').write_text('isolated test fault')
        self.wait_for(lambda: self.health().get('pid') not in (None, first) and self.status().get('launches', 0) >= 2)
        self.assertIn('unexpected worker exit', (self.data / 'guardian.log').read_text(encoding='utf-8-sig'))

    def test_locked_status_file_does_not_stop_guard_or_worker(self):
        process=self.start()
        self.wait_for(lambda:self.status().get('state')=='running' and self.health().get('pid'))
        first=self.health()['pid'];path=self.data/'guardian-status.json'
        kernel=ctypes.windll.kernel32
        kernel.CreateFileW.restype=ctypes.c_void_p
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p]
        handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
        self.assertNotIn(handle,(None,ctypes.c_void_p(-1).value))
        try:
            time.sleep(1.2)
            self.assertIsNone(process.poll())
            self.assertEqual(self.health()['pid'],first)
            self.assertIn('status write deferred',(self.data/'guardian.log').read_text(encoding='utf-8-sig'))
        finally:kernel.CloseHandle(ctypes.c_void_p(handle))
        previous=self.status()['updated_utc']
        self.wait_for(lambda:self.status().get('updated_utc')!=previous)
        self.assertEqual(self.status()['launches'],1)
        self.assertEqual(list(self.data.glob('guardian-status.json.new.*')),[])

    def test_repeated_crashes_stop_retrying_and_create_notification(self):
        process = self.start('crash')
        self.assertEqual(process.wait(timeout=12), 2)
        self.assertTrue((self.data / 'restart.blocked').exists())
        self.assertTrue((self.data / 'restart-failed.notice.txt').exists())
        self.assertEqual(self.status()['launches'], 3)

    def test_live_but_stalled_automation_is_detected(self):
        process = self.start('stalled')
        self.assertEqual(process.wait(timeout=12), 2)
        self.assertIn('automation operation stalled', (self.data / 'guardian.log').read_text(encoding='utf-8-sig'))

    def test_expired_heartbeat_is_detected(self):
        process = self.start('hang')
        self.assertEqual(process.wait(timeout=16), 2)
        self.assertIn('heartbeat expired', (self.data / 'guardian.log').read_text(encoding='utf-8-sig'))

    def test_intentional_stop_is_not_restarted_even_on_next_launch(self):
        process = self.start()
        self.wait_for(lambda: self.health().get('pid'))
        pid = self.health()['pid']
        (self.data / 'automation.stop').write_text('user requested stop')
        self.assertEqual(process.wait(timeout=5), 0)
        self.wait_for(lambda: not alive(pid))
        self.assertEqual(self.start().wait(timeout=3), 0)
        self.assertEqual(self.status()['state'], 'intentional_stop')

    def test_forced_guard_exit_cleans_process_tree_then_logon_can_recover(self):
        process = self.start('tree')
        self.wait_for(lambda: (self.data / 'fixture-child.pid').exists() and self.health().get('pid'))
        worker = self.health()['pid']
        child = int((self.data / 'fixture-child.pid').read_text())
        process.kill()
        process.wait(timeout=3)
        self.wait_for(lambda: not alive(worker) and not alive(child))
        self.start()
        self.wait_for(lambda: self.health().get('pid') not in (None, worker) and self.status().get('state') == 'running')

    def test_local_connection_drop_and_recovery_does_not_restart_healthy_process(self):
        state = {'online': True}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if not state['online']:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"authenticated":true}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.start(url=f'http://127.0.0.1:{server.server_port}/fixture-login')
            self.wait_for(lambda: self.health().get('network_online') is True)
            pid = self.health()['pid']
            state['online'] = False
            self.wait_for(lambda: self.health().get('network_online') is False)
            state['online'] = True
            self.wait_for(lambda: self.health().get('network_online') is True)
            self.assertEqual(self.health()['pid'], pid)
            self.assertEqual(self.status()['launches'], 1)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
