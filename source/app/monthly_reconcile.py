"""Automatic monthly reconciliation for the user-declared fictional site.

The target is deliberately bound to the original site. Do not point this module
at production employee/payroll records. All changes preserve existing notes,
recheck the row before saving, and journal uncertain results instead of retrying.
"""
import calendar
import random
from datetime import date, datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from attendance_recovery import AttendancePage, parse_time, is_blank_time

DECLARED_SITE = 'http://sappd.kr'
FIELDS = ('checkin', 'checkout', 'note')


def require_site(app):
    if app.SITE_URL.rstrip('/') != DECLARED_SITE:
        raise ValueError('월 자동 정리는 사용자가 확인한 대상 사이트에서만 실행합니다.')


def clear_empty_holds(app, rows, today):
    """Resolve only local holds after a fresh, fully empty past-day read.

    This never writes to the site or creates a missing workday. Today's records
    and unrecognized displays remain held because they may still be in flight.
    """
    cleared = []
    with app.file_lock('state'):
        state = app.load_json(app.STATE_FILE, {})
        for row in rows:
            key = row['date']
            rule = state.get('day_rules', {}).get(key, {})
            if (not rule.get('manual_hold') or date.fromisoformat(key) >= today
                    or not is_blank_time(row['checkin']) or not is_blank_time(row['checkout'])):
                continue
            rule['manual_hold'] = False
            rule['hold_resolution'] = dict(status='empty_record', at=datetime.now().isoformat(timespec='seconds'))
            for field in ('monthly_reconcile_journal', 'attendance_corrections'):
                for entry in reversed(state.get(field, [])):
                    if entry.get('date') == key and entry.get('status') in ('sending', 'checking', 'uncertain'):
                        entry.update(status='empty_record_confirmed', resolution='사이트 출퇴근 모두 빈 기록 · 변경 안 함')
                        break
            cleared.append(key)
        if cleared:
            app.save_json(app.STATE_FILE, state)
    for key in cleared:
        app.log_event(f'{key} 빈 근태 기록 확인: 보류 해제, 사이트 기록 변경 없음')
    return cleared


def build_plan(rows, rules, settings, today, is_workday, rng=None):
    """Plan from completed fictional records; never create an absent workday."""
    rng = rng or random.SystemRandom()
    monthly = settings.get('monthly_overtime_hours', 10)
    daily = settings.get('daily_overtime_hours', 1)
    step = settings.get('time_step_minutes', 5)
    if type(monthly) is not int or not 0 <= monthly <= 62 or type(daily) is not int or daily not in (1, 2) or monthly % daily or type(step) is not int or step not in (1, 5):
        raise ValueError('월 연장시간·하루 기준·분 간격 설정을 확인하세요.')
    target = monthly // daily
    changes, normal, overtime, skipped = {}, [], [], []
    for row in sorted(rows, key=lambda r: r['date']):
        key = row['date']
        day = date.fromisoformat(key)
        rule = rules.get(key, {})
        ci, co = parse_time(row['checkin']), parse_time(row['checkout'])
        if day > today or not is_workday(day):
            skipped.append(key)
            continue
        if (is_blank_time(row['checkin']) and is_blank_time(row['checkout'])
                and (not rule.get('manual_hold') or day < today)):
            skipped.append(key)
            continue
        if rule.get('manual_hold'):
            raise RuntimeError(f'{key}: 이전 저장 결과가 불확실해 사이트 확인이 필요합니다.')
        if not ci or (co and ci >= co):
            skipped.append(key)
            continue
        if rule.get('vacation'):
            # Explicit request: vacation records before 19:00 stay untouched.
            if co and co >= (19, 0) and ci < (18, 0):
                changes[key] = dict(date=key, before={k: row[k] for k in FIELDS}, after={'checkout': '18:00'}, reason='휴가일 연장 기록 정리')
            elif co and co >= (19, 0):
                skipped.append(key)
            continue
        if rule.get('exclude_overtime'):
            if co is None and not (day < today and is_blank_time(row['checkout'])):
                skipped.append(key)
                continue
            after = {'checkin': '09:00', 'checkout': '18:00'}
            changed = {k: v for k, v in after.items() if parse_time(row[k]) != parse_time(v)}
            if changed:
                changes[key] = dict(date=key, before={k: row[k] for k in FIELDS}, after=changed, reason='연장 제외일 09:00~18:00')
            continue
        if co is None:
            skipped.append(key)
            continue
        if co >= (19, 0):
            overtime.append(row)
        elif ci < (19, 0):
            normal.append(row)
    # Keep existing overtime first. Dates already used by an application are
    # validated before writing; no hidden changes to already-submitted records.
    keep = overtime[:target]
    for row in overtime[target:]:
        if parse_time(row['checkin']) >= (18, 0):
            skipped.append(row['date'])
            keep.append(row)
            continue
        changes[row['date']] = dict(date=row['date'], before={k: row[k] for k in FIELDS}, after={'checkout': '18:00'}, reason='월 연장일 초과 정리')
    needed = max(0, target - len(keep))
    selected = normal[:needed]
    for row in selected:
        minutes = rng.choice(list(range(19*60, (19 if daily == 1 else 20)*60+56, step)))
        changes[row['date']] = dict(date=row['date'], before={k: row[k] for k in FIELDS},
            after={'checkout': f'{minutes//60:02}:{minutes%60:02}'}, reason='월 연장일 부족 보완')
    return dict(changes=list(changes.values()), target_days=target,
                overtime_days=len(keep)+len(selected), remaining_days=max(0, needed-len(selected)),
                skipped_dates=skipped)


def apply_plan(app, page, plan, month, background=False):
    # Validate all snapshots and application journals before the first write.
    with app.file_lock('state'):
        state = app.load_json(app.STATE_FILE, {})
    for change in plan['changes']:
        key = change['date']
        if key[:7] != month:
            raise ValueError('정리 월과 수정 날짜가 다릅니다.')
        if state.get('overtime_applications', {}).get(key, {}).get('status') in ('success', 'sending', 'uncertain'):
            raise ValueError(f'{key}: 시간외근무 신청 이력이 있어 자동 정리를 보류합니다.')
        current = page.record(date.fromisoformat(key))
        if any(current[k] != change['before'][k] for k in FIELDS):
            raise RuntimeError(f'{key}: 조회 중 기록이 변경되어 자동 정리를 중단합니다.')
    completed = []
    for change in plan['changes']:
        if background and not app.automation_enabled(app.load_json(app.SETTINGS_FILE, {})):
            raise RuntimeError('자동관리가 정지되어 월 정리를 중단했습니다.')
        key = change['date']
        day = date.fromisoformat(key)
        with app.file_lock('state'):
            state = app.load_json(app.STATE_FILE, {})
            state.setdefault('day_rules', {}).setdefault(key, {})['manual_hold'] = True
            journal = dict(change, status='sending', at=datetime.now().isoformat(timespec='seconds'))
            state.setdefault('monthly_reconcile_journal', []).append(journal)
            app.save_json(app.STATE_FILE, state)
        targets = {k: datetime.combine(day, datetime.min.time()).replace(hour=parse_time(v)[0], minute=parse_time(v)[1]) for k, v in change['after'].items()}
        # An uncertain save leaves its journal and hold set. Never reroll a new
        # checkout or proceed with the rest of the month after an ambiguous save.
        try:
            if page.correct(day, targets, change['before']) is not True:
                raise RuntimeError('사이트 저장 확인 결과가 없습니다.')
        except Exception:
            with app.file_lock('state'):
                state = app.load_json(app.STATE_FILE, {})
                state['monthly_reconcile_journal'][-1]['status'] = 'uncertain'
                app.save_json(app.STATE_FILE, state)
            raise
        with app.file_lock('state'):
            state = app.load_json(app.STATE_FILE, {})
            state['day_rules'][key]['manual_hold'] = False
            state['monthly_reconcile_journal'][-1]['status'] = 'verified'
            runs = state.setdefault('runs', {}).setdefault(key, {})
            for field, target_time in targets.items():
                runs.setdefault(field, {}).update(status='success', target=target_time.isoformat(timespec='minutes'), origin='월 자동 정리')
            app.save_json(app.STATE_FILE, state)
        completed.append(change)
        app.log_event(f'{key} 월 자동 정리 확인: {change["reason"]}')
    return completed


def run(app, months=None, background=False):
    require_site(app)
    today = date.today()
    months = sorted(set(months or [today.strftime('%Y-%m')]))
    months = [m for m in months if date.fromisoformat(m+'-01') <= today]
    if not months:
        return {'ok': True, 'message': '미래 날짜 설정을 저장했습니다. 해당 월에 자동 처리합니다.', 'months': []}
    settings = app.load_json(app.SETTINGS_FILE, {})
    if not settings.get('id') or not settings.get('pw'):
        raise ValueError('자동관리 설정에서 계정을 먼저 저장하세요.')
    app._LOG_SECRETS.add(settings['pw'])
    results, display_rows, warnings = [], [], []
    with app.file_lock('action', timeout=120):
        if background and not app.automation_enabled(app.load_json(app.SETTINGS_FILE, {})):
            return {'ok': True, 'message': '자동관리 정지 중', 'months': []}
        with app.file_lock('state'):
            state = app.load_json(app.STATE_FILE, {})
            pending = set(state.get('reconcile_pending_months', []))
            pending.update(months)
            state['reconcile_pending_months'] = sorted(pending)
            app.save_json(app.STATE_FILE, state)
        driver = app.create_driver()
        try:
            driver.set_page_load_timeout(45)
            driver.get(app.SITE_URL)
            wait = WebDriverWait(driver, 20)
            wait.until(EC.visibility_of_element_located((By.NAME, 'iduser'))).send_keys(settings['id'])
            driver.find_element(By.NAME, 'pass').send_keys(settings['pw'])
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            wait.until(EC.element_to_be_clickable((By.LINK_TEXT, '근태관리')))
            if background:
                try:
                    app.recover_previous_days(driver)
                except Exception as error:
                    warnings.append('누락 퇴근 보완 확인 필요: '+str(error)[:250])
            page = AttendancePage(driver, today)
            page.open()
            for month in months:
                first = date.fromisoformat(month+'-01')
                with app.file_lock('state'):
                    state = app.load_json(app.STATE_FILE, {})
                    rules = state.get('day_rules', {})
                month_settings = dict(settings)
                frozen = state.get('overtime_month_settings', {}).get(month, {})
                if frozen:
                    month_settings['monthly_overtime_hours'] = frozen.get('monthly_hours', settings.get('monthly_overtime_hours', 10))
                    month_settings['daily_overtime_hours'] = frozen.get('daily_hours', settings.get('daily_overtime_hours', 1))
                rows = []
                for n in range(1, calendar.monthrange(first.year, first.month)[1]+1):
                    day = first.replace(day=n)
                    if day > today:
                        break
                    row = page.record(day)
                    rows.append(dict(date=str(day), **{k: row[k] for k in FIELDS}))
                cleared = clear_empty_holds(app, rows, today)
                if cleared:
                    with app.file_lock('state'):
                        state = app.load_json(app.STATE_FILE, {})
                        rules = state.get('day_rules', {})
                plan = build_plan(rows, rules, month_settings, today, app.is_workday)
                done = apply_plan(app, page, plan, month, background)
                # Verify the whole resulting month, not just successful clicks.
                final_rows = []
                for row in rows:
                    current = page.record(date.fromisoformat(row['date']))
                    final_rows.append(dict(date=row['date'], **{k: current[k] for k in FIELDS}))
                verified = build_plan(final_rows, rules, month_settings, today, app.is_workday)
                if verified['changes']:
                    raise RuntimeError('월 정리 후 기록이 예상과 다릅니다. 다시 조회하세요.')
                result = dict(month=month, changed=len(done), target_days=verified['target_days'],
                              overtime_days=verified['overtime_days'], remaining_days=verified['remaining_days'],
                              skipped_dates=verified['skipped_dates'], empty_holds_cleared=len(cleared))
                with app.file_lock('state'):
                    state = app.load_json(app.STATE_FILE, {})
                    state.setdefault('monthly_reconcile_results', {})[month] = dict(result, at=datetime.now().isoformat(timespec='seconds'))
                    pending = set(state.get('reconcile_pending_months', [])); pending.discard(month)
                    state['reconcile_pending_months'] = sorted(pending)
                    app.save_json(app.STATE_FILE, state)
                results.append(result)
                display_rows = [dict(row, rule=state.get('day_rules', {}).get(row['date'], {}),
                                     empty_record=is_blank_time(row['checkin']) and is_blank_time(row['checkout'])) for row in final_rows]
                app.log_event(f'{month} 월 자동 정리: {result["changed"]}건, 연장 {result["overtime_days"]}/{result["target_days"]}일, 부족 {result["remaining_days"]}일')
            summary = ' / '.join(f'{r["month"]} 수정 {r["changed"]}건 · 연장 {r["overtime_days"]}/{r["target_days"]}일 · 후보 부족 {r["remaining_days"]}일 · 빈 기록 보류 해제 {r["empty_holds_cleared"]}건' for r in results)
            with app.file_lock('state'):
                state = app.load_json(app.STATE_FILE, {})
            pending = [key for key in state.get('repair_pending', []) if date.fromisoformat(key) < today
                       and app.is_workday(date.fromisoformat(key)) and not state.get('day_rules', {}).get(key, {}).get('vacation')]
            if pending:
                warnings.append(f'누락 퇴근 보완 대기 {len(pending)}건')
            if warnings:
                summary += ' / ' + '; '.join(warnings)
            from attendance_changes import summarize_month
            return {'ok': True, 'message': summary, 'months': results, 'rows': display_rows,
                    'summary': summarize_month(display_rows, month_settings, app.is_workday), 'warnings': warnings}
        finally:
            driver.quit()
