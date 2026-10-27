"""Resident scheduler: liveness, functional progress and connectivity are separate."""
import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen


def utc_now():
    return datetime.now(timezone.utc)


class Health:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.jobs = {}
        self.network_online = None
        self.last_login_verified = None
        self.started = utc_now().isoformat()
        self.shutdown = threading.Event()

    def phase(self, mode, stage, seconds=180, error=None):
        with self.lock:
            job = self.jobs.setdefault(mode, {})
            job.update(stage=stage, progress_utc=utc_now().isoformat(), error=error)
            job['deadline_utc'] = ((utc_now() + timedelta(seconds=seconds)).isoformat()
                                   if stage not in ('waiting', 'success', 'failed', 'idle') else None)

    def activity(self):
        name = threading.current_thread().name
        with self.lock:
            if self.jobs.get(name, {}).get('deadline_utc'):
                self.jobs[name]['deadline_utc'] = (utc_now() + timedelta(seconds=180)).isoformat()
                self.jobs[name]['progress_utc'] = utc_now().isoformat()

    def login_verified(self):
        with self.lock:
            self.last_login_verified = utc_now().isoformat()

    def snapshot(self):
        with self.lock:
            jobs = json.loads(json.dumps(self.jobs))
            stalled = any(v.get('deadline_utc') and utc_now() > datetime.fromisoformat(v['deadline_utc']) for v in jobs.values())
            return dict(pid=os.getpid(), heartbeat_utc=utc_now().isoformat(), started_utc=self.started,
                        network_online=self.network_online, last_login_verified_utc=self.last_login_verified,
                        jobs=jobs, stalled=bool(stalled))

    def write_loop(self):
        path = os.path.join(self.app.DATA_DIR, 'worker-health.json')
        while not self.shutdown.is_set():
            try:
                self.app.save_json(path, self.snapshot())
            except Exception as error:
                self.app.log_event(f'상태 파일 저장 실패: {type(error).__name__}: {error}')
            self.shutdown.wait(2)

    def probe(self):
        try:
            with urlopen(self.app.SITE_URL, timeout=8) as response:
                response.read(1)
            online, error = True, None
        except Exception as caught:
            online, error = False, f'{type(caught).__name__}: {caught}'
        if online != self.network_online:
            self.app.log_event('사이트 연결 복구/정상 (실제 로그인 성공과 별도)' if online else f'사이트 연결 실패: {error}')
        self.network_online = online
        return online


def enabled(app):
    settings = app.load_json(app.SETTINGS_FILE, {})
    return (settings.get('enabled', True) and settings.get('id') and settings.get('pw')
            and not any((Path(app.DATA_DIR) / name).exists() for name in ('automation.stop', 'update.pause')))


def run(app):
    app.HEALTH = health = Health(app)
    heartbeat = threading.Thread(target=health.write_loop, name='heartbeat', daemon=True)
    heartbeat.start()
    threads = {}
    current_day = None
    first_day = True
    last_probe = -float('inf')

    def launch(mode, immediate):
        def action():
            try:
                result = app.run_scheduled(mode, immediate=immediate)
                health.phase(mode, 'success' if result else 'failed', error=None if result else '사이트 결과 또는 실행 기록 확인 필요')
            except Exception as error:
                app.log_event(f'{mode} 작업 오류: {type(error).__name__}: {error}')
                health.phase(mode, 'failed', error=f'{type(error).__name__}: {error}')
        thread = threading.Thread(target=action, name=mode, daemon=True)
        threads[mode] = thread
        thread.start()

    try:
        while enabled(app):
            today = date.today()
            if current_day != today:
                if any(t.is_alive() for t in threads.values()):
                    time.sleep(1)
                    continue
                current_day, threads = today, {}
                if app.is_workday(today):
                    with app.file_lock('state'):
                        state = app.load_json(app.STATE_FILE, {'runs': {}})
                        app.choose_target('checkout', today, state)
            if time.monotonic() - last_probe > 30:
                health.probe()
                last_probe = time.monotonic()
            if app.is_workday(today) and health.network_online:
                for mode in ('checkin', 'checkout'):
                    if mode not in threads:
                        launch(mode, immediate=(mode == 'checkin' and first_day))
                    elif not threads[mode].is_alive():
                        with app.file_lock('state'):
                            record = app.load_json(app.STATE_FILE, {}).get('runs', {}).get(str(today), {}).get(mode, {})
                        if (record.get('status') == 'retryable' and record.get('attempts', 0) < 3
                                and datetime.now() >= datetime.fromisoformat(record['retry_at'])):
                            launch(mode, immediate=(mode == 'checkin'))
                first_day = False
            time.sleep(1)
    finally:
        health.shutdown.set()
        app.log_event('자동 실행 정상 종료: 사용자 종료/일시 정지/업데이트 대기')
        # Waiting jobs see the same stop flag. The guardian owns and terminates
        # the worker's process tree if a browser action has not returned yet.
        for thread in threads.values():
            thread.join(timeout=2)
        app.HEALTH = None
