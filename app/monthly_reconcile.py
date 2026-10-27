"""Automatic monthly reconciliation for the user-declared fictional site.

The target is deliberately bound to the original site. Do not point this module
at production employee/payroll records. All changes preserve existing notes,
recheck the row before saving, and journal uncertain results instead of retrying.
"""
import calendar
import random
import re
import uuid
import time
import hashlib
from datetime import date, datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

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


def resolve_holds(app, rows, today):
    cleared = clear_empty_holds(app, rows, today)
    with app.file_lock('state'):
        state=app.load_json(app.STATE_FILE,{})
        changed=False
        for row in rows:
            key=row['date'];rule=state.get('day_rules',{}).get(key,{})
            if not rule.get('manual_hold') or date.fromisoformat(key)>=today:
                continue
            history=[e for name in ('monthly_reconcile_journal','attendance_corrections') for e in state.get(name,[]) if e.get('date')==key and e.get('status') in ('sending','checking','uncertain')]
            entry=max(history,key=lambda e:e.get('at',''),default=None)
            def same(a,b):
                return all((parse_time(a[k])==parse_time(b[k]) if parse_time(a[k]) and parse_time(b[k]) else a[k]==b[k] or (is_blank_time(a[k]) and is_blank_time(b[k]))) for k in ('checkin','checkout')) and a.get('note')==b.get('note')
            resolution=None
            if entry and set(FIELDS)<=set(entry.get('before',{})):
                before=entry['before'];after=dict(before,**entry.get('after',{}))
                if same(row,after):
                    resolution='verified_after_requery'
                elif same(row,before):
                    resolution='not_applied_confirmed'
                    value=entry.get('after',{}).get('checkout')
                    if parse_time(value):
                        day=date.fromisoformat(key);hour,minute=parse_time(value)
                        state.setdefault('runs',{}).setdefault(key,{}).setdefault('checkout',{})['target']=datetime.combine(day,datetime.min.time()).replace(hour=hour,minute=minute).isoformat(timespec='minutes')
            # The user explicitly defines this rule as 09:00--18:00. It can be
            # safely re-applied from a fresh snapshot even after a legacy hold.
            known=all(parse_time(row[k]) or is_blank_time(row[k]) for k in ('checkin','checkout'))
            present=any(parse_time(row[k]) for k in ('checkin','checkout'))
            if not resolution and rule.get('exclude_overtime') and not rule.get('vacation') and known and present:
                resolution='exclusion_rule_reconfirmed'
            if resolution:
                rule['manual_hold']=False
                rule['hold_resolution']=dict(status=resolution,at=datetime.now().isoformat(timespec='seconds'))
                if entry:
                    entry['status']=resolution
                changed=True;cleared.append(key)
        if changed:
            app.save_json(app.STATE_FILE,state)
    return cleared


def build_plan(rows, rules, settings, today, is_workday, rng=None, saved_targets=None):
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
        if not ci and not co:
            skipped.append(key)
            continue
        if rule.get('vacation'):
            # Explicit request: vacation records before 19:00 stay untouched.
            if co and co >= (19, 0) and ci and ci < (18, 0):
                changes[key] = dict(date=key, before={k: row[k] for k in FIELDS}, after={'checkout': '18:00'}, reason='휴가일 연장 기록 정리')
            elif co and co >= (19, 0):
                skipped.append(key)
            continue
        if rule.get('exclude_overtime'):
            known=all(parse_time(row[k]) or is_blank_time(row[k]) for k in ('checkin','checkout'))
            if not known or (day==today and (ci is None or co is None)):
                skipped.append(key)
                continue
            after = {'checkin': '09:00', 'checkout': '18:00'}
            changed = {k: v for k, v in after.items() if parse_time(row[k]) != parse_time(v)}
            if changed:
                changes[key] = dict(date=key, before={k: row[k] for k in FIELDS}, after=changed, reason='연장 제외일 09:00~18:00')
            continue
        if not ci or (co and ci>=co):
            skipped.append(key)
            continue
        if co is None:
            if day>=today or not is_blank_time(row['checkout']):
                skipped.append(key)
                continue
            candidate=None
            saved=(saved_targets or {}).get(key)
            if saved:
                try:
                    saved=datetime.fromisoformat(saved)
                    if saved.date()==day and (saved.hour,saved.minute)>ci:
                        candidate=saved.hour*60+saved.minute
                except (ValueError,TypeError):
                    pass
            if candidate is None:
                start=parse_time(settings.get('checkout_start','18:00'))
                end=parse_time(settings.get('checkout_end','18:55'))
                if not start or not end:
                    raise ValueError('일반 퇴근 시간 범위를 확인하세요.')
                choices=[m for m in range(start[0]*60+start[1],end[0]*60+end[1]+1,step) if m>ci[0]*60+ci[1] and m<19*60]
                if not choices:
                    skipped.append(key)
                    continue
                candidate=rng.choice(choices)
            co=(candidate//60,candidate%60)
            changes[key]=dict(date=key,before={k:row[k] for k in FIELDS},after={'checkout':f'{co[0]:02}:{co[1]:02}'},reason='퇴근 누락 보완')
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
        minutes=None
        saved=(saved_targets or {}).get(row['date'])
        if saved:
            try:
                value=datetime.fromisoformat(saved)
                candidate=value.hour*60+value.minute
                if str(value.date())==row['date'] and 19*60<=candidate<=(19 if daily==1 else 20)*60+55 and candidate%(step)==0:
                    minutes=candidate
            except (ValueError,TypeError):
                pass
        if minutes is None:
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
            app.log_event(f'{key} 날짜별 수정 시작 · 이 날짜 저장 확인 후 다음 날짜 처리')
            if page.correct(day, targets, change['before']) is not True:
                raise RuntimeError('사이트 저장 확인 결과가 없습니다.')
        except Exception as error:
            with app.file_lock('state'):
                state = app.load_json(app.STATE_FILE, {})
                submitted = getattr(getattr(page,'driver',None),'_workday_write_submitted',True)
                state['monthly_reconcile_journal'][-1]['status'] = 'not_submitted' if submitted is False else 'uncertain'
                if submitted is False:
                    state['day_rules'][key]['manual_hold'] = False
                app.save_json(app.STATE_FILE, state)
            error.completed_changes=list(completed)
            error.failed_date=key
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


def _month_settings(settings, state, month):
    result=dict(settings)
    frozen=state.get('overtime_month_settings',{}).get(month,{})
    if frozen:
        result['monthly_overtime_hours']=frozen.get('monthly_hours',settings.get('monthly_overtime_hours',10))
        result['daily_overtime_hours']=frozen.get('daily_hours',settings.get('daily_overtime_hours',1))
    return result


def _settings(app):
    require_site(app)
    settings=app.load_json(app.SETTINGS_FILE,{})
    if not settings.get('id') or not settings.get('pw'):
        raise ValueError('자동관리 설정에서 계정을 먼저 저장하세요.')
    app._LOG_SECRETS.add(settings['pw'])
    return settings


def _connect(app,settings):
    driver=app.create_driver()
    phase='로그인 페이지 열기'
    try:
        driver.set_page_load_timeout(45);driver.get(app.SITE_URL);app.check_site_response(driver)
        wait=WebDriverWait(driver,20)
        phase='로그인 입력 화면 확인'
        wait.until(EC.visibility_of_element_located((By.NAME,'iduser'))).send_keys(settings['id'])
        driver.find_element(By.NAME,'pass').send_keys(settings['pw'])
        driver.find_element(By.CSS_SELECTOR,'button[type="submit"]').click()
        phase='로그인 후 근태관리 메뉴 확인'
        wait.until(EC.element_to_be_clickable((By.LINK_TEXT,'근태관리')))
        phase='근태관리 화면 열기'
        page=AttendancePage(driver,date.today());page.open()
        return driver,page
    except Exception as error:
        try:app.check_site_response(driver)
        finally:driver.quit()
        if isinstance(error,TimeoutException):
            raise RuntimeError(f'{phase}: 제한 시간 안에 화면을 확인하지 못했습니다. 근태 수정 저장은 시작하지 않았습니다.') from error
        raise


def _read_month(page,month,today,is_workday):
    first=date.fromisoformat(month+'-01')
    if first>today:
        raise ValueError('미래 월은 조회할 수 없습니다.')
    rows=[]
    for n in range(1,calendar.monthrange(first.year,first.month)[1]+1):
        day=first.replace(day=n)
        if day>today:break
        try:record=page.record(day)
        except Exception as error:
            detail=str(error).strip()
            if not detail or re.fullmatch(r'Message:\s*(?:None)?',detail):detail='화면 응답 또는 요소 확인에 실패했습니다.'
            raise RuntimeError(f'{month} 근태 조회 · {day} 기록 읽기 실패 ({type(error).__name__}): {detail[:500]}') from error
        rows.append(dict(date=str(day),**{k:record[k] for k in FIELDS},eligible=is_workday(day)))
    return rows


def _clock(value):
    parsed=parse_time(value)
    return f'{parsed[0]:02}:{parsed[1]:02}' if parsed else ''


def _signature(rule):
    return dict(vacation=bool(rule.get('vacation')),exclude_overtime=bool(rule.get('exclude_overtime')))


def run(app,months=None,background=False):
    """Read and propose only. Explicit apply_reviewed is the only write path."""
    if background:
        return {'ok':False,'error':'월 정리는 목록 확인 후 정리 버튼으로 실행하세요.'}
    months=months or [date.today().strftime('%Y-%m')]
    if len(months)!=1:raise ValueError('조회할 월을 하나 선택하세요.')
    month=months[0];today=date.today()
    date.fromisoformat(month+'-01')
    settings=_settings(app)
    with app.file_lock('action',timeout=120):
        driver,page=_connect(app,settings)
        try:
            rows=_read_month(page,month,today,app.is_workday)
            resolve_holds(app,rows,today)
            with app.file_lock('state'):state=app.load_json(app.STATE_FILE,{})
            rules=state.get('day_rules',{});effective=_month_settings(settings,state,month)
            safe_rules={key:dict(rule,manual_hold=False) for key,rule in rules.items()}
            targets={key:runs.get('checkout',{}).get('target') for key,runs in state.get('runs',{}).items()}
            plan=build_plan(rows,safe_rules,effective,today,app.is_workday,saved_targets=targets)
            entries=[];seen=set()
            by_date={r['date']:r for r in rows}
            for change in plan['changes']:
                key=change['date'];seen.add(key)
                after={k:_clock(change['before'][k]) for k in ('checkin','checkout')};after.update(change['after'])
                held=bool(rules.get(key,{}).get('manual_hold'))
                blocked=state.get('overtime_applications',{}).get(key,{}).get('status') in ('success','sending','uncertain')
                entries.append(dict(change,after=after,selectable=not held and not blocked,blocked=blocked,
                                    status='신청 이력 확인 필요' if blocked else '저장 결과 확인 필요 · 직접 검토' if held else '수정 예정'))
            for row in rows:
                key=row['date']
                if key in seen or not rules.get(key,{}).get('manual_hold') or not row['eligible']:continue
                entries.append(dict(date=key,before={k:row[k] for k in FIELDS},after={k:_clock(row[k]) for k in ('checkin','checkout')},
                                    reason='저장 결과 재확인',selectable=False,blocked=False,status='시간 확인 후 선택'))
            review_id=uuid.uuid4().hex
            review=dict(id=review_id,month=month,created_at=time.time(),site=app.SITE_URL,
                        account=hashlib.sha256(settings['id'].encode()).hexdigest(),changes=entries,rows=rows,
                        target_days=plan['target_days'],rule_signatures={r['date']:_signature(rules.get(r['date'],{})) for r in rows})
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{});state['monthly_review']=review;app.save_json(app.STATE_FILE,state)
            return dict(ok=True,plan_id=review_id,rows=entries,all_rows=rows,target_days=plan['target_days'],
                        message=f'수정 예정 {len(entries)}건. 날짜를 제외하거나 시간을 고친 뒤 선택 내역 정리를 누르세요.')
        except Exception:
            app.check_site_response(driver);raise
        finally:driver.quit()


def apply_reviewed(app,job):
    settings=_settings(app)
    with app.file_lock('action',timeout=120):
        with app.file_lock('state'):state=app.load_json(app.STATE_FILE,{})
        review=state.get('monthly_review') or {}
        if review.get('id')!=job.get('plan_id') or not job.get('plan_id') or review.get('consumed'):
            raise ValueError('처리할 조회 목록이 없습니다. 해당 월을 다시 조회하세요.')
        if time.time()-review['created_at']>7200:
            raise ValueError('조회 후 시간이 오래 지났습니다. 다시 조회하세요.')
        if review['site']!=app.SITE_URL or review['account']!=hashlib.sha256(settings['id'].encode()).hexdigest():
            raise ValueError('조회 후 대상 또는 계정이 바뀌었습니다. 다시 조회하세요.')
        requested=job.get('rows',[])
        if not isinstance(requested,list) or not requested or len(requested)>31:
            raise ValueError('정리할 날짜를 선택하세요.')
        allowed={r['date']:r for r in review['changes']};selected=[];seen=set()
        for item in requested:
            key=item['date']
            if key not in allowed or key in seen:raise ValueError('조회 목록에 없거나 중복된 날짜입니다.')
            seen.add(key);entry=allowed[key]
            if entry.get('blocked'):raise ValueError(f'{key}: 기존 신청 이력을 먼저 확인하세요.')
            if _signature(state.get('day_rules',{}).get(key,{}))!=review['rule_signatures'][key]:
                raise ValueError('조회 후 달력 설정이 바뀌었습니다. 다시 조회하세요.')
            after={k:item.get(k,'') for k in ('checkin','checkout')}
            parsed={k:parse_time(v) for k,v in after.items()}
            if not all(parsed.values()) or parsed['checkin']>=parsed['checkout']:
                raise ValueError(f'{key}: 출근·퇴근을 HH:MM으로 입력하고 시간 순서를 확인하세요.')
            if all(is_blank_time(entry['before'][k]) for k in ('checkin','checkout')):
                raise ValueError('출퇴근이 모두 없는 날짜는 새 근무일로 만들지 않습니다.')
            changes={k:_clock(v) for k,v in after.items() if parsed[k]!=parse_time(entry['before'][k])}
            selected.append(dict(date=key,before=entry['before'],after=changes,reason='사용자 목록 확인 · '+entry['reason']))
        driver,page=_connect(app,settings)
        applying=False;completed=[]
        try:
            # Check every selected snapshot before the first write.
            for item in selected:
                current=page.record(date.fromisoformat(item['date']))
                if any(current[k]!=item['before'][k] for k in FIELDS):
                    raise ValueError(f'{item["date"]}: 조회 후 사이트 기록이 바뀌었습니다. 다시 조회하세요.')
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{});state['monthly_review']['consumed']=True;app.save_json(app.STATE_FILE,state)
            changed=[item for item in selected if item['after']]
            applying=True
            completed=apply_plan(app,page,{'changes':changed},review['month'])
            for item in selected:
                if not item['after']:
                    with app.file_lock('state'):
                        state=app.load_json(app.STATE_FILE,{})
                        state.setdefault('day_rules',{}).setdefault(item['date'],{})['manual_hold']=False
                        day=date.fromisoformat(item['date'])
                        for field in ('checkin','checkout'):
                            value=parse_time(item['before'][field])
                            if value:
                                state.setdefault('runs',{}).setdefault(item['date'],{}).setdefault(field,{}).update(status='success',target=datetime.combine(day,datetime.min.time()).replace(hour=value[0],minute=value[1]).isoformat(timespec='minutes'),origin='목록 확인 · 기존 시간 유지')
                        app.save_json(app.STATE_FILE,state)
            final_rows=_read_month(page,review['month'],date.today(),app.is_workday)
            final_by_date={r['date']:r for r in final_rows}
            for item in selected:
                current=final_by_date[item['date']]
                expected=dict(item['before'],**item['after'])
                if any(parse_time(current[k])!=parse_time(expected[k]) for k in ('checkin','checkout')) or current['note']!=expected['note']:
                    raise RuntimeError(f'{item["date"]}: 최종 월 조회 값이 선택한 시간과 일치하지 않습니다. 완료 처리하지 않습니다.')
                item['status']='저장 확인 완료' if item['after'] else '기존 시간 일치 · 변경 없음'
            from attendance_changes import summarize_month
            summary=summarize_month(final_rows,dict(settings,monthly_overtime_hours=review['target_days'],daily_overtime_hours=1),app.is_workday)
            return dict(ok=True,rows=selected,all_rows=final_rows,target_days=review['target_days'],
                        message=f'정리 완료: 선택 {len(selected)}건 사이트 확인 완료 · 시간 변경 {len(changed)}건 · 연장 기록 {summary["recorded_days"]}/{review["target_days"]}일')
        except Exception as error:
            if not applying:
                app.check_site_response(driver);raise
            completed=getattr(error,'completed_changes',completed)
            saved={r['date'] for r in completed}
            failed=getattr(error,'failed_date',None)
            for item in selected:
                item['status']='개별 저장 확인 · 최종 재조회 필요' if item['date'] in saved else '저장 실패 · 재조회 필요' if item['date']==failed else '미처리 · 재조회 필요'
            detail=str(error).strip() or type(error).__name__
            app.log_event(f'월 선택 정리 중단 · 개별 저장 확인 {len(saved)}건: {detail}')
            return dict(ok=False,error=f'전체 정리가 완료되지 않았습니다. 개별 저장 확인 {len(saved)}건. {detail}',
                        rows=selected,all_rows=review['rows'],target_days=review['target_days'],message='정리 실패 · 아래 원인과 날짜별 상태를 확인한 뒤 다시 조회하세요.')
        finally:driver.quit()

