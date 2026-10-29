# -*- coding: utf-8 -*-
import calendar
import base64
import json
import os
import random
import re
import subprocess
import sys
import time
import threading
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time, timedelta

import holidays
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager
from webdriver_manager.core.os_manager import OperationSystemManager

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
# The official embeddable runtime uses an isolated ._pth search path. Explicitly
# include the application directory for our sibling recovery module.
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)
from attendance_recovery import correct_late_checkin, repair_missing_checkouts
from attendance_changes import blocked, rule_for

APP_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else SOURCE_DIR
)
DATA_DIR = APP_DIR if getattr(sys, "frozen", False) else os.path.join(APP_DIR, "dist")
SETTINGS_FILE = os.path.join(DATA_DIR, "자동출근설정.json")
STATE_FILE = os.path.join(DATA_DIR, "자동출퇴근상태.json")
LOG_FILE = os.path.join(DATA_DIR, "자동출퇴근.log")
DRIVER_PATH = os.path.join(SOURCE_DIR, "driver", "chromedriver.exe")
SITE_URL = "http://sappd.kr"
WEEKDAYS = "Monday,Tuesday,Wednesday,Thursday,Friday"

os.makedirs(DATA_DIR, exist_ok=True)
HEALTH = None
_ACTION_CONTEXT = threading.local()
_LOG_SECRETS = set()


def automation_enabled(settings):
    return settings.get('enabled', True) and not any(
        os.path.exists(os.path.join(DATA_DIR, name)) for name in ('automation.stop', 'update.pause'))


def health_phase(mode, stage, seconds=180, error=None):
    if HEALTH is not None:
        HEALTH.phase(mode, stage, seconds, error)


@contextmanager
def file_lock(name, timeout=30):
    """Coordinate the logon task and daily tasks on Windows."""
    import msvcrt

    path = os.path.join(DATA_DIR, name + ".lock")
    with open(path, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("다른 출퇴근 작업이 처리 중입니다.")
                time.sleep(0.2)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def user_job_error(error,operation=''):
    detail=str(error).strip()
    if not detail or re.fullmatch(r'Message:\s*(?:None)?',detail):
        detail='화면 응답 대기 또는 요소 확인에 실패했습니다. 네트워크와 사이트 로그인 상태를 확인하세요.'
    text=f'{operation or "사용자 작업"} · {type(error).__name__}: {detail}'
    for secret in tuple(_LOG_SECRETS):
        if secret:text=text.replace(secret,'[숨김]')
    return text[:1500]


def log_event(message):
    message = str(message)
    for secret in tuple(_LOG_SECRETS):
        if secret:
            message = message.replace(secret, '[숨김]')
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with file_lock('log'):
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 5 * 1024 * 1024:
            os.replace(LOG_FILE, LOG_FILE + '.1')
        with open(LOG_FILE, "a", encoding="utf-8") as file:
            file.write(f"[{stamp}] {message}\n")
    if HEALTH is not None:
        HEALTH.activity()


def save_json(path, data):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as error:
        log_event(f"파일 읽기 실패: {os.path.basename(path)} - {error}")
        if path == STATE_FILE:
            raise RuntimeError("실행 기록을 읽지 못해 중복 방지를 위해 중단합니다.") from error
        return default


def is_workday(day):
    return day.weekday() < 5 and day not in holidays.country_holidays("KR", years=[day.year])


def overtime_settings(settings):
    hours = settings.get("monthly_overtime_hours", 10)
    daily = settings.get("daily_overtime_hours", 1)
    if type(hours) is not int or type(daily) is not int or not 0 <= hours <= 62 or daily not in (1, 2):
        raise ValueError("월 연장시간은 0~62의 정수, 하루 기준은 1 또는 2시간이어야 합니다.")
    if hours % daily:
        raise ValueError("월 연장시간은 하루 기준으로 나누어떨어져야 합니다. 하루 2시간이면 월 시간을 짝수로 설정하세요.")
    return hours, daily


def time_settings(settings):
    def minutes(key, default):
        value = settings.get(key, default)
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError(f"{key}: HH:MM 형식의 시각을 입력하세요.")
        hour, minute = map(int, value.split(':'))
        return hour * 60 + minute
    start_in = minutes('checkin_start', '08:30')
    end_in = minutes('checkin_end', '08:55')
    start_out = minutes('checkout_start', '18:05')
    if end_in >= start_out:raise ValueError('출근 종료보다 퇴근 시작이 늦어야 합니다.')
    start_out = max(start_out,18*60+5)
    end_out = minutes('checkout_end', '18:55')
    if end_out == 18*60:end_out=18*60+5
    step = settings.get('time_step_minutes', 5)
    if type(step) is not int or step not in (1, 5):
        raise ValueError('시간 간격은 1분 또는 5분이어야 합니다.')
    if not start_in <= end_in < start_out <= end_out:
        raise ValueError('출근 시작 ≤ 출근 종료 < 퇴근 시작 ≤ 퇴근 종료 순서로 설정하세요.')
    if settings.get('monthly_overtime_hours', 10) and end_out >= 19 * 60:
        raise ValueError('연장을 사용하는 경우 일반 퇴근 종료는 19:00 이전이어야 합니다.')
    return start_in, end_in, start_out, end_out, step


def eligible_days(day):
    return [date(day.year, day.month, n).isoformat()
            for n in range(1, calendar.monthrange(day.year, day.month)[1] + 1)
            if is_workday(date(day.year, day.month, n))]


def validate_overtime_capacity(settings, day):
    hours, daily = overtime_settings(settings)
    if hours // daily > len(eligible_days(day)):
        raise ValueError(f"{day.month}월 근무일보다 연장일이 많습니다. 월 연장시간을 줄여 주세요.")
    return hours, daily


def get_overtime_dates(day, state):
    month_key = day.strftime("%Y-%m")
    months = state.setdefault("overtime_months", {})
    plans = state.setdefault("overtime_month_settings", {})
    if state.get("overtime_month") and "overtime_dates" in state:
        months.setdefault(state["overtime_month"], state["overtime_dates"])
    if month_key in months:
        # Existing monthly dates/targets are frozen. Changes take effect when
        # a new month's plan is generated, preserving past attendance.
        plans.setdefault(month_key, {"monthly_hours": len(months[month_key]), "daily_hours": 1})
        return {key for key in months[month_key] if not blocked(state, key) and not rule_for(state, key).get('exclude_overtime')}

    settings = load_json(SETTINGS_FILE, {})
    hours, daily = validate_overtime_capacity(settings, day)
    available = [key for key in eligible_days(day) if not blocked(state, key) and not rule_for(state, key).get('exclude_overtime')]
    selected = sorted(random.SystemRandom().sample(available, min(hours // daily, len(available))))
    state["overtime_month"] = month_key
    state["overtime_dates"] = selected
    months[month_key] = selected
    plans[month_key] = {"monthly_hours": hours, "daily_hours": daily}
    state.setdefault("runs", {})
    save_json(STATE_FILE, state)
    log_event(f"{month_key} 연장 계획: 월 {hours}시간 / 하루 {daily}시간 / {len(selected)}일: {', '.join(selected)}")
    return set(selected)


def refresh_checkout_target(day,state,run):
    """Apply new bounds only to a not-yet-confirmed saved checkout target."""
    if not run.get('target'):return
    target=datetime.fromisoformat(run['target'])
    daily=state.get('overtime_month_settings',{}).get(day.strftime('%Y-%m'),{}).get('daily_hours',run.get('daily_overtime_hours',1))
    if (target.hour,target.minute)==(18,0):
        target=target.replace(minute=5)
    elif daily==2 and target.hour==19:
        step=time_settings(load_json(SETTINGS_FILE,{}))[-1]
        minute=random.SystemRandom().choice(list(range(0,56,step)))
        target=target.replace(hour=20,minute=minute)
    else:return
    run['target']=target.isoformat(timespec='minutes')
    save_json(STATE_FILE,state)


def choose_target(mode, today, state):
    day_key = today.isoformat()
    action_state = state.setdefault("runs", {}).setdefault(day_key, {}).setdefault(mode, {})
    if blocked(state, today):
        return None, dict(action_state, status='success')
    if action_state.get("status") in {"success", "in_progress", "uncertain"}:
        return None, action_state
    if mode=='checkout':refresh_checkout_target(today,state,action_state)
    if (mode == 'checkout' and rule_for(state, today).get('exclude_overtime')
            and action_state.get('target') and datetime.fromisoformat(action_state['target']).hour >= 19):
        action_state.pop('target', None)
    if action_state.get("target"):
        return datetime.fromisoformat(action_state["target"]), action_state

    start_in, end_in, start_out, end_out, step = time_settings(load_json(SETTINGS_FILE, {}))
    base = datetime.combine(today, dt_time(0, 0))
    if mode == "checkin":
        offsets = range(start_in, end_in + 1, step)
        action_state["kind"] = "출근"
    else:
        overtime = day_key in get_overtime_dates(today, state)
        daily_hours = state["overtime_month_settings"][today.strftime("%Y-%m")]["daily_hours"]
        offsets = range((18+daily_hours)*60, (18+daily_hours)*60+56, step) if overtime else range(start_out, end_out + 1, step)
        action_state["kind"] = "연장퇴근" if overtime else "일반퇴근"
        if overtime:
            action_state["daily_overtime_hours"] = daily_hours

    target = base + timedelta(minutes=random.SystemRandom().choice(list(offsets)))
    action_state["target"] = target.isoformat(timespec="minutes")
    save_json(STATE_FILE, state)
    return target, action_state


class QuietChromeOSManager(OperationSystemManager):
    """Read Chrome's version without webdriver-manager's console shell probes."""
    def get_browser_version_from_os(self, browser_type=None):
        if hasattr(self, '_chrome_version'):
            return self._chrome_version
        paths = [os.path.join(os.environ[name], 'Google', 'Chrome', 'Application', 'chrome.exe')
                 for name in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA') if os.environ.get(name)]
        expressions = ["$v=(Get-Item -LiteralPath '" + path.replace("'", "''") + "').VersionInfo.FileVersion; if($v){$v;exit}" for path in paths]
        script = "$ErrorActionPreference='SilentlyContinue';" + ';'.join(expressions)
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        match = re.search(r'\d+\.\d+\.\d+(?:\.\d+)?', result.stdout)
        self._chrome_version = match.group(0) if match else None
        return self._chrome_version


def create_driver():
    from site_access import reserve_session
    reserve_session(sys.modules[__name__])
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1440,1000')
    options.add_argument('--no-first-run')
    options.set_capability('goog:loggingPrefs', {'performance':'ALL'})
    def prepared(driver):
        driver._workday_before_write = before_site_write
        driver._workday_check_response = lambda: check_site_response(driver)
        return driver
    os_manager = QuietChromeOSManager()
    bundled_available=os.path.exists(DRIVER_PATH)
    if bundled_available:
        try:
            browser_version=os_manager.get_browser_version_from_os()
            probe=subprocess.run([DRIVER_PATH,'--version'],capture_output=True,text=True,
                                 timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
            match=re.search(r'ChromeDriver\s+(\d+)\.',probe.stdout)
            if browser_version and match and browser_version.split('.')[0]!=match.group(1):
                bundled_available=False
                log_event(f'Chrome {browser_version.split(".")[0]} / 포함 드라이버 {match.group(1)}: 호환 드라이버를 사용합니다.')
        except (OSError,subprocess.SubprocessError):
            pass
    if bundled_available:
        try:
            return prepared(webdriver.Chrome(options=options, service=Service(DRIVER_PATH, popen_kw={"creation_flags": subprocess.CREATE_NO_WINDOW})))
        except Exception as bundled_error:
            log_event(f"포함된 ChromeDriver 시작 실패, 호환 드라이버 확인: {type(bundled_error).__name__}: {str(bundled_error).splitlines()[0]}")
    cache = DriverCacheManager(os_system_manager=os_manager)
    path = ChromeDriverManager(cache_manager=cache, os_system_manager=os_manager).install()
    return prepared(webdriver.Chrome(options=options, service=Service(path, popen_kw={"creation_flags": subprocess.CREATE_NO_WINDOW})))


def before_site_write():
    from site_access import reserve_write
    reserve_write(sys.modules[__name__])


def check_site_response(driver):
    from site_access import check_page
    check_page(sys.modules[__name__], driver)


def recovery_target(day):
    """Reuse the persisted live-checkout target for a missing past record."""
    with file_lock("state"):
        state = load_json(STATE_FILE, {"runs": {}})
        run = state.setdefault("runs", {}).setdefault(day.isoformat(), {}).setdefault("checkout", {})
        if run.get("target"):
            # Called only after the site confirms that checkout is missing.
            refresh_checkout_target(day,state,run)
            return datetime.fromisoformat(run["target"])
        prior_status = run.pop("status", None)
        target, _ = choose_target("checkout", day, state)
        if prior_status:
            run["status"] = prior_status
            save_json(STATE_FILE, state)
        return target


def record_recovery(day, status, target=None):
    with file_lock("state"):
        state = load_json(STATE_FILE, {"runs": {}})
        pending = set(state.get("repair_pending", []))
        if status == "pending":
            pending.add(day.isoformat())
        else:
            pending.discard(day.isoformat())
        state["repair_pending"] = sorted(pending)
        if status == "success":
            run = state.setdefault("runs", {}).setdefault(day.isoformat(), {}).setdefault("checkout", {})
            run.update(status="success", repaired_at=datetime.now().isoformat(timespec="seconds"), origin="다음 출근 시 누락 보완")
            if target:
                run["target"] = target.isoformat(timespec="minutes")
        save_json(STATE_FILE, state)


def recover_previous_days(driver):
    with file_lock("state"):
        state = load_json(STATE_FILE, {"runs": {}})
        pending = set(state.get("repair_pending", []))
        for day_key, runs in state.get("runs", {}).items():
            if (date.fromisoformat(day_key) < date.today()
                    and runs.get("checkin", {}).get("status") == "success"
                    and runs.get("checkout", {}).get("status") != "success"):
                pending.add(day_key)
    repair_missing_checkouts(
        driver, date.today(), lambda day: is_workday(day) and not blocked(state, day), recovery_target, record_recovery,
        log_event, sorted(pending),
    )


def late_checkin_target(day):
    with file_lock("state"):
        state = load_json(STATE_FILE, {"runs": {}})
        run = state.setdefault("runs", {}).setdefault(day.isoformat(), {}).setdefault("checkin", {})
        if run.get("correction_target"):
            return datetime.fromisoformat(run["correction_target"])
        start, end, _, _, step = time_settings(load_json(SETTINGS_FILE, {}))
        if (start, end) == (510, 535):
            end = 530  # Preserve the original 08:30–08:50 late correction default.
        target = datetime.combine(day, dt_time(0, 0)) + timedelta(minutes=random.SystemRandom().choice(range(start, end + 1, step)))
        run["correction_target"] = target.isoformat(timespec="minutes")
        save_json(STATE_FILE, state)
        return target


def perform_action(user_id, password, mode):
    driver = None
    _ACTION_CONTEXT.submitted = False
    _LOG_SECRETS.add(password)
    try:
        health_phase(mode, 'browser_start', 240)
        driver = create_driver()
        driver.set_page_load_timeout(45)
        wait = WebDriverWait(driver, 20)
        health_phase(mode, 'login_page')
        driver.get(SITE_URL)
        check_site_response(driver)
        wait.until(EC.visibility_of_element_located((By.NAME, "iduser"))).send_keys(user_id)
        driver.find_element(By.NAME, "pass").send_keys(password)
        health_phase(mode, 'login_submit')
        _ACTION_CONTEXT.submitted = True
        driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        checkout_selector = "a[href*='sappd_g3_b.php']"
        # The existing site records check-in at login. Require its authenticated
        # checkout control as evidence, rather than treating a click as success.
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, checkout_selector)))
        if HEALTH is not None:
            HEALTH.login_verified()
        health_phase(mode, 'authenticated')

        if mode == "checkout":
            health_phase(mode, 'checkout_submit')
            checkout_link = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, checkout_selector))
            )
            checkout_url = checkout_link.get_attribute("href")
            before_site_write()
            driver.get(checkout_url)
            check_site_response(driver)
            wait.until(
                lambda current_driver: current_driver.execute_script(
                    "return document.readyState"
                )
                == "complete"
            )

            # 일부 화면은 링크 이동 후 별도의 확인 폼을 한 번 더 요구합니다.
            confirm_controls = driver.find_elements(
                By.CSS_SELECTOR,
                "form button[type='submit'], form input[type='submit']",
            )
            if len(confirm_controls) == 1 and confirm_controls[0].is_displayed():
                confirm_controls[0].click()
                check_site_response(driver)

            for _ in range(2):
                try:
                    WebDriverWait(driver, 3).until(EC.alert_is_present()).accept()
                except TimeoutException:
                    break

            driver.get(f"{SITE_URL}/sappd_start.php")
            check_site_response(driver)
            wait.until(
                lambda current_driver: current_driver.execute_script(
                    "return document.readyState"
                )
                == "complete"
            )
            time.sleep(2)
            if driver.find_elements(By.NAME, "iduser"):
                raise RuntimeError("로그인 화면으로 돌아가 퇴근 결과를 확인할 수 없습니다.")
            if driver.find_elements(By.CSS_SELECTOR, checkout_selector):
                raise RuntimeError("퇴근 등록 후 홈 화면 검증에 실패했습니다.")

        if mode == "checkin":
            health_phase(mode, 'attendance_corrections', 1800)
            _, end_in, _, _, _ = time_settings(load_json(SETTINGS_FILE, {}))
            late_from = max(9 * 60, end_in + 1)
            if datetime.now().hour * 60 + datetime.now().minute >= late_from:
                try:
                    correct_late_checkin(driver, date.today(), late_checkin_target, log_event, (late_from // 60, late_from % 60))
                except Exception as error:
                    log_event(f"당일 출근 시간 보정 보류: {type(error).__name__} / {error}")
            try:
                recover_previous_days(driver)
            except Exception as error:
                log_event(f"과거 퇴근 누락 보완 보류: {type(error).__name__} (화면 구조 또는 접속 상태 확인 필요)")
        log_event(f"{'출근' if mode == 'checkin' else '퇴근'} 등록 동작 완료")
        return True
    except Exception as error:
        if driver:
            try:
                check_site_response(driver)
            except Exception as site_error:
                error = site_error
        from site_access import SiteAccessPaused
        if HEALTH is not None and (isinstance(error,(ConnectionError,SiteAccessPaused)) or any(t in str(error).lower() for t in ('net::err_','connection refused','offline'))):
            HEALTH.network_online=False
            HEALTH.probe_interval=60
        log_event(f"{'출근' if mode == 'checkin' else '퇴근'} 등록 실패: {type(error).__name__}: {error}")
        return False
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def run_scheduled(mode, immediate=False):
    settings = load_json(SETTINGS_FILE, None)
    if not settings or not settings.get("id") or not settings.get("pw"):
        log_event("계정 설정이 없어 자동 실행을 중단함")
        return False
    if not automation_enabled(settings):
        log_event("자동 실행이 일시 정지되어 있음")
        return False

    today = date.today()
    if not is_workday(today):
        log_event(f"{today.isoformat()} 주말 또는 공휴일이므로 실행하지 않음")
        return True

    with file_lock("state"):
        state = load_json(STATE_FILE, {"runs": {}})
        day_runs = state.get("runs", {}).get(today.isoformat(), {})
        if mode == "checkin" and day_runs.get("checkout", {}).get("status") == "success":
            log_event("오늘 퇴근이 완료되어 재로그인 출근을 생략함")
            return True
        target, action_state = choose_target(mode, today, state)
        if target is None:
            success = action_state.get("status") == "success"
            log_event(f"{today.isoformat()} {mode} 중복 실행 방지: {action_state.get('status')}")
            return success
        if immediate:
            target = datetime.now()
            action_state["target"] = target.isoformat(timespec="seconds")
            action_state["origin"] = "Windows 로그인"
            save_json(STATE_FILE, state)

    delay = (target - datetime.now()).total_seconds()
    health_phase(mode, 'waiting')
    if delay > 0:
        log_event(f"{action_state['kind']} 예약: {target.strftime('%Y-%m-%d %H:%M')}")
        while datetime.now() < target:
            if date.today() != today:
                log_event("날짜가 변경되어 이전 날짜 작업을 취소함")
                return False
            current_settings = load_json(SETTINGS_FILE, {})
            if not automation_enabled(current_settings):
                return False
            with file_lock("state"):
                current_state = load_json(STATE_FILE, {"runs": {}})
                if blocked(current_state, today):
                    return True
                if mode == 'checkout' and rule_for(current_state, today).get('exclude_overtime'):
                    revised, _ = choose_target(mode, today, current_state)
                    if revised is not None:
                        target = revised
                current_run = current_state.get("runs", {}).get(today.isoformat(), {}).get(mode, {})
                if current_run.get("status") == "success":
                    return True
                # A logon task may have brought check-in forward.
                if current_run.get("target"):
                    target = datetime.fromisoformat(current_run["target"])
            time.sleep(max(0, min(10, (target - datetime.now()).total_seconds())))
    else:
        log_event(f"예약 시각 {target.strftime('%H:%M')}이 지나 즉시 실행")

    # Do not hold the state lock for the hours spent waiting for checkout.
    # Serialize only browser actions, then reload state to avoid lost updates.
    with file_lock("action", timeout=120):
        settings = load_json(SETTINGS_FILE, {})
        if date.today() != today or not automation_enabled(settings):
            return False
        if not settings.get("id") or not settings.get("pw"):
            return False
        with file_lock("state"):
            state = load_json(STATE_FILE, {"runs": {}})
            if blocked(state, today):
                return True
            if mode == 'checkout' and rule_for(state, today).get('exclude_overtime'):
                revised, _ = choose_target(mode, today, state)
                if revised is not None and revised > datetime.now():
                    return False
            day_runs = state.setdefault("runs", {}).setdefault(today.isoformat(), {})
            if mode == "checkin" and day_runs.get("checkout", {}).get("status") == "success":
                return True
            action_state = day_runs.setdefault(mode, {})
            if action_state.get("status") in {"success", "in_progress", "uncertain"}:
                return action_state["status"] == "success"
            action_state["status"] = "in_progress"
            action_state["started_at"] = datetime.now().isoformat(timespec="seconds")
            action_state['attempts'] = action_state.get('attempts', 0) + 1
            save_json(STATE_FILE, state)
        success = perform_action(settings["id"], settings["pw"], mode)
        with file_lock("state"):
            state = load_json(STATE_FILE, {"runs": {}})
            action_state = state.setdefault("runs", {}).setdefault(today.isoformat(), {}).setdefault(mode, {})
            # A browser error may follow a successful remote submission. Require
            # manual inspection rather than automatically sending it twice.
            retryable = not success and not getattr(_ACTION_CONTEXT, 'submitted', True)
            action_state["status"] = "success" if success else 'retryable' if retryable else "uncertain"
            if retryable:
                action_state['retry_at'] = (datetime.now() + timedelta(seconds=60 * action_state.get('attempts', 1))).isoformat(timespec='seconds')
            action_state["executed_at"] = datetime.now().isoformat(timespec="seconds")
            save_json(STATE_FILE, state)
        return success


def run_startup():
    # Save today's checkout plan before opening the browser, even if the PC
    # is later powered off before the scheduled time.
    today = date.today()
    settings = load_json(SETTINGS_FILE, {})
    if settings.get("id") and settings.get("pw") and settings.get("enabled", True) and is_workday(today):
        with file_lock("state"):
            state = load_json(STATE_FILE, {"runs": {}})
            choose_target("checkout", today, state)
    checkin_ok = run_scheduled("checkin", immediate=True)
    if not checkin_ok:
        return False
    checkout_ok = run_scheduled("checkout")
    return checkin_ok and checkout_ok


def register_tasks():
    config = load_json(SETTINGS_FILE, {})
    validate_overtime_capacity(config, date.today())
    start_in, _, start_out, _, _ = time_settings(config)
    guardian = os.path.join(SOURCE_DIR, 'WorkdayGuard.exe').replace("'", "''")
    commands = ["$ErrorActionPreference='Stop'", "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)"]

    definitions = [("자동출근", f"{start_in // 60:02}:{start_in % 60:02}"), ("자동퇴근", f"{start_out // 60:02}:{start_out % 60:02}")]
    for task_name, start_time in definitions:
        command = (
            f"$action=New-ScheduledTaskAction -Execute '{guardian}'; "
            f"$trigger=New-ScheduledTaskTrigger -Weekly -DaysOfWeek {WEEKDAYS} -At '{start_time}'; "
            "$user=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
            "$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited; "
            "$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
            f"Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null"
        )
        commands.append(f"$stage='{task_name}'; " + command)

    # AtLogOn runs as the installing user: the browser needs an interactive session.
    command = (
        "$user=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
        f"$action=New-ScheduledTaskAction -Execute '{guardian}' -Argument '--show-ui'; "
        "$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user; $trigger.Delay='PT30S'; "
        "$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited; "
        "$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
        "Register-ScheduledTask -TaskName '자동출퇴근로그인' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null"
    )
    commands.append("$stage='자동출퇴근로그인'; " + command)
    command = (
        "$user=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
        f"$action=New-ScheduledTaskAction -Execute '{guardian}' -Argument '--watchdog'; "
        "$triggers=@((New-ScheduledTaskTrigger -AtLogOn -User $user),(New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5))); "
        "$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited; "
        "$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
        "Register-ScheduledTask -TaskName '자동출퇴근점검' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null"
    )
    commands.append("$stage='자동출퇴근점검'; " + command)
    script = "try { " + '; '.join(commands) + " } catch { [Console]::Error.WriteLine(('예약 등록 실패 [{0}]: {1}' -f $stage,$_.Exception.Message)); exit 1 }"
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
            check=False, capture_output=True, encoding='utf-8', errors='replace',
            timeout=90, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('예약 작업 등록 응답이 90초 동안 없습니다. 작업 스케줄러 서비스를 확인하세요.') from error
    if result.returncode:
        detail = (result.stderr or result.stdout or f'종료 코드 {result.returncode}').strip()
        log_event('예약 작업 등록 오류: ' + detail)
        raise RuntimeError(detail[:900] + '\nWindows 작업 스케줄러 서비스와 현재 계정의 등록 권한을 확인하세요. 상세 원인은 실행 로그에 기록했습니다.')


def main():
    if '--resident-worker' in sys.argv:
        from resident import run
        with file_lock('resident', timeout=0):
            run(sys.modules[__name__])
        return
    if "--overtime-job" in sys.argv or "--attendance-job" in sys.argv or '--trip-job' in sys.argv:
        from pathlib import Path
        flag = '--trip-job' if '--trip-job' in sys.argv else '--attendance-job' if '--attendance-job' in sys.argv else '--overtime-job'
        if flag=='--trip-job':
            from business_trips import run_job
        elif flag == '--attendance-job':
            from attendance_changes import run_job
        else:
            from overtime_requests import run_job
        path = Path(sys.argv[sys.argv.index(flag) + 1]).resolve()
        if path.parent != Path(DATA_DIR).resolve() or path.suffix != '.json':
            raise ValueError('작업 파일은 프로그램 데이터 폴더에 있어야 합니다.')
        operation='작업 파일 읽기'
        try:
            job=json.loads(path.read_text(encoding='utf-8-sig'))
            category={'--trip-job':'출장','--attendance-job':'근태 정리','--overtime-job':'시간외근무'}[flag]
            step={'scan':'일정 조회','inspect':'기존 내역 확인','submit':'등록','allocate':'시간 배분'}.get(job.get('operation'),'사용자 작업')
            operation=f'{category} {step} {job.get("month", "")}'.strip()
            result = run_job(sys.modules[__name__], job)
        except Exception as error:
            log_event(f'사용자 작업 오류: {type(error).__name__}: {error}')
            result = {'ok': False, 'error': user_job_error(error,operation)}
        save_json(str(path) + '.result.json', result)
        raise SystemExit(0 if result['ok'] else 1)
    if "--startup" in sys.argv:
        raise SystemExit(0 if run_startup() else 1)
    if "--자동출근" in sys.argv:
        raise SystemExit(0 if run_scheduled("checkin") else 1)
    if "--자동퇴근" in sys.argv:
        raise SystemExit(0 if run_scheduled("checkout") else 1)
    if "--register-tasks" in sys.argv:
        settings = load_json(SETTINGS_FILE, None)
        if not settings or not settings.get("id") or not settings.get("pw"):
            raise RuntimeError("계정 설정이 없습니다.")
        try:
            register_tasks()
        except Exception as error:
            # Windows GUI redirects this stream for a Korean validation error.
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8")
            print(str(error), file=sys.stderr)
            raise SystemExit(1)
        print("TASKS_REGISTERED")
        return
    print("설치하기.bat를 실행하여 설정해 주세요.")


if __name__ == "__main__":
    main()
