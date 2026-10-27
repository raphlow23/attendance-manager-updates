"""Date exclusions and explicitly reviewed corrections of actual attendance."""
import calendar
import re
from datetime import date, datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from attendance_recovery import AttendancePage, parse_time


def rule_for(state, day):
    return state.get('day_rules', {}).get(str(day), {})


def blocked(state, day):
    rule = rule_for(state, day)
    return bool(rule.get('vacation') or rule.get('manual_hold'))


def summarize_month(rows, settings, is_workday):
    """Report existing site records only; never assign replacement overtime."""
    hours = settings.get('monthly_overtime_hours', 10)
    daily = settings.get('daily_overtime_hours', 1)
    if type(hours) is not int or type(daily) is not int or hours < 0 or daily not in (1, 2) or hours % daily:
        raise ValueError('월 연장시간과 하루 기준 설정을 확인하세요.')
    target = hours // daily
    recorded = []
    flagged = []
    for row in rows:
        checkin, checkout = parse_time(row['checkin']), parse_time(row['checkout'])
        if (is_workday(date.fromisoformat(row['date'])) and checkin and checkout
                and checkin < checkout and checkout >= (19, 0)):
            recorded.append(row['date'])
            rule = row.get('rule', {})
            if rule.get('vacation') or rule.get('exclude_overtime'):
                flagged.append(row['date'])
    return dict(recorded_days=len(recorded), target_days=target,
                remaining_days=max(0, target-len(recorded)),
                excess_days=max(0, len(recorded)-target), excluded_record_days=len(flagged))


def save_rule(app, job):
    dates = job.get('dates', [job.get('date')])
    if not isinstance(dates, list) or not dates or len(dates) > 366:
        raise ValueError('저장할 날짜를 1~366개 선택하세요.')
    days = sorted({date.fromisoformat(value) for value in dates})
    if type(job.get('vacation')) is not bool or type(job.get('exclude_overtime')) is not bool:
        raise ValueError('휴가·연장 제외 여부를 확인하세요.')
    with app.file_lock('action', timeout=120), app.file_lock('state'):
        state = app.load_json(app.STATE_FILE, {})
        for day in days:
            rule = state.setdefault('day_rules', {}).setdefault(str(day), {})
            rule.update(vacation=job['vacation'], exclude_overtime=job['exclude_overtime'],
                        updated_at=datetime.now().isoformat(timespec='seconds'))
            # Cancel only a pending target. Never erase a successful/uncertain run.
            run = state.get('runs', {}).get(str(day), {}).get('checkout', {})
            if job['exclude_overtime'] and run.get('status') not in ('success', 'in_progress', 'uncertain'):
                run.pop('target', None)
        pending = set(state.get('reconcile_pending_months', []))
        pending.update(str(day)[:7] for day in days)
        state['reconcile_pending_months'] = sorted(pending)
        app.save_json(app.STATE_FILE, state)
    app.log_event(f'제외일 {len(days)}개 휴가={job["vacation"]}, 연장 제외={job["exclude_overtime"]} 저장')
    return {'ok': True, 'message': f'선택 날짜 {len(days)}개의 제외 설정을 저장했습니다. 기존 사이트 기록은 바뀌지 않습니다.'}


def reviewed_targets(job, today):
    day = date.fromisoformat(job['date'])
    if day > today:
        raise ValueError('미래 날짜의 근태 기록은 정정할 수 없습니다.')
    if job.get('confirmed_actual') is not True or not str(job.get('reason', '')).strip():
        raise ValueError('실제 근무 시간 확인과 정정 사유가 필요합니다.')
    targets = {}
    for key in ('checkin', 'checkout'):
        value = job.get(key, '')
        if value:
            parsed = parse_time(value)
            if parsed is None:
                raise ValueError('시간은 HH:MM 형식으로 입력하세요.')
            targets[key] = datetime.combine(day, datetime.min.time()).replace(hour=parsed[0], minute=parsed[1])
    if not targets:
        raise ValueError('정정할 시간을 하나 이상 입력하세요.')
    return day, targets


def correct_reviewed(app, page, job, today):
    day, targets = reviewed_targets(job, today)
    before = page.record(day)
    expected = job.get('before', {})
    if any(before[k] != expected.get(k) for k in ('checkin', 'checkout', 'note')):
        raise ValueError('조회 후 사이트 기록이 변경되었습니다. 다시 조회하세요.')
    combined = {k: (v.hour, v.minute) for k, v in targets.items()}
    for key in ('checkin', 'checkout'):
        combined.setdefault(key, parse_time(before[key]))
    if not all(combined.values()) or combined['checkin'] >= combined['checkout']:
        raise ValueError('출근과 퇴근을 확인하세요. 출근은 퇴근보다 빨라야 합니다.')
    with app.file_lock('state'):
        state = app.load_json(app.STATE_FILE, {})
        if state.get('overtime_applications', {}).get(str(day), {}).get('status') in ('success', 'sending', 'uncertain'):
            raise ValueError('이미 신청했거나 신청 결과 확인이 필요한 날짜입니다. 사이트에서 신청 상태를 먼저 확인하세요.')
        rule = state.setdefault('day_rules', {}).setdefault(str(day), {})
        rule['manual_hold'] = True
        state.setdefault('attendance_corrections', []).append({
            'date': str(day), 'at': datetime.now().isoformat(timespec='seconds'),
            'before': {k: before[k] for k in ('checkin', 'checkout', 'note')},
            'after': {k: v.strftime('%H:%M') for k, v in targets.items()},
            'reason': str(job['reason']).strip()[:1000], 'status': 'checking'})
        app.save_json(app.STATE_FILE, state)
    # Hold survives an uncertain remote result. It is cleared only by a verified
    # correction, so the background worker cannot overwrite or retry blindly.
    page.correct(day, targets, before)
    with app.file_lock('state'):
        state = app.load_json(app.STATE_FILE, {})
        state['day_rules'][str(day)]['manual_hold'] = False
        state['attendance_corrections'][-1]['status'] = 'verified'
        runs = state.setdefault('runs', {}).setdefault(str(day), {})
        for mode, value in combined.items():
            runs.setdefault(mode, {}).update(status='success', origin='사용자 실제 근태 정정',
                target=datetime.combine(day, datetime.min.time()).replace(hour=value[0], minute=value[1]).isoformat(timespec='minutes'))
        app.save_json(app.STATE_FILE, state)
    app.log_event(f'{day} 사용자 근태 정정 확인 완료')
    return {'ok': True, 'message': '사이트 저장을 확인했습니다. 시간외근무 신청에서 해당 월을 다시 조회하세요.'}


def run_job(app, job):
    operation = job.get('operation')
    if operation == 'rules':
        result = save_rule(app, job)
        from monthly_reconcile import run
        months = sorted({str(day)[:7] for day in job.get('dates', [job.get('date')])})
        try:
            synced = run(app, months)
            result['message'] = '제외일 저장 완료. ' + synced['message']
        except Exception as error:
            app.log_event(f'제외일 저장 후 월 자동 정리 보류: {type(error).__name__}: {error}')
            result['message'] = '제외일은 저장했습니다. 월 자동 정리 보류: ' + str(error)[:700]
            result['reconcile_ok'] = False
        return result
    if operation == 'reconcile':
        from monthly_reconcile import run
        return run(app, [job['month']])
    if operation not in ('scan', 'correct'):
        raise ValueError('지원하지 않는 근태 작업입니다.')
    if operation == 'correct':
        reviewed_targets(job, date.today())
    month = job.get('month', '')
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('조회 월 형식이 잘못되었습니다.')
    first = date.fromisoformat(month + '-01')
    if first > date.today():
        raise ValueError('미래 월은 조회할 수 없습니다.')
    if operation == 'correct' and job['date'][:7] != month:
        raise ValueError('조회 월과 정정 날짜가 다릅니다.')
    settings = app.load_json(app.SETTINGS_FILE, {})
    if not settings.get('id') or not settings.get('pw'):
        raise ValueError('근태 자동관리 설정에서 계정을 먼저 저장하세요.')
    app._LOG_SECRETS.add(settings['pw'])
    with app.file_lock('action', timeout=120):
        driver = app.create_driver()
        try:
            driver.set_page_load_timeout(45)
            driver.get(app.SITE_URL)
            wait = WebDriverWait(driver, 20)
            wait.until(EC.visibility_of_element_located((By.NAME, 'iduser'))).send_keys(settings['id'])
            driver.find_element(By.NAME, 'pass').send_keys(settings['pw'])
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            wait.until(EC.element_to_be_clickable((By.LINK_TEXT, '근태관리')))
            page = AttendancePage(driver, date.today())
            page.open()
            if operation == 'correct':
                return correct_reviewed(app, page, job, date.today())
            rows = []
            with app.file_lock('state'):
                state = app.load_json(app.STATE_FILE, {})
            for n in range(1, calendar.monthrange(first.year, first.month)[1] + 1):
                day = first.replace(day=n)
                if day > date.today():
                    break
                record = page.record(day)
                rows.append(dict(date=str(day), **{k: record[k] for k in ('checkin', 'checkout', 'note')},
                                 rule=rule_for(state, day)))
            return {'ok': True, 'rows': rows, 'summary': summarize_month(rows, settings, app.is_workday)}
        finally:
            driver.quit()
