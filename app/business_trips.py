"""Reviewed business-trip plans for the user-declared fictional site."""
import calendar
import hashlib
import re
import time
import uuid
from datetime import date
from copy import deepcopy

from attendance_recovery import parse_time

CATEGORY='센터'
CATEGORIES=('센터','협회')
TRANSPORT='대중교통'
RATE=5000

def trip_category(value=None):
    value=CATEGORY if value is None else str(value).strip()
    if value not in CATEGORIES:raise ValueError('출장 구분은 센터 또는 협회를 선택하세요.')
    return value


def money(value):
    if type(value) is not int or value<0 or value>10000000 or value%10000:
        raise ValueError('목표 금액은 0~1,000만원 범위의 1만원 단위로 입력하세요.')
    return value


def minutes(value):
    parsed=parse_time(value)
    return parsed[0]*60+parsed[1] if parsed else None


def window(row,hours=None,start_hour=None,start_minute=0,end=None):
    hours=row.get('hours',4) if hours is None else hours
    if type(hours) is not int or hours not in (2,4):raise ValueError('출장 인정시간은 2시간 또는 4시간입니다.')
    ci=minutes(row['checkin']);co=minutes(row['checkout'])
    start_hour=(9 if row.get('event_day') else 13) if start_hour is None else start_hour
    end_hour=18 if row.get('event_day') and start_hour==9 and hours==4 and row.get('end','18:00')=='18:00' else start_hour+hours
    if type(start_hour) is not int or not 0<=start_hour<=23 or type(start_minute) is not int or not 0<=start_minute<60:
        raise ValueError('출발 시각과 복귀 시각을 확인하세요.')
    start=start_hour*60+start_minute
    finish=minutes(end) if end is not None else end_hour*60+start_minute
    if finish is None or finish>=1440 or finish-start<120 or (hours==2 and finish-start!=120) or (hours==4 and finish-start<240):
        raise ValueError('복귀 시각은 출발 이후이며 인정시간(2시간/4시간)에 맞아야 합니다.')
    if ci is None or co is None or start<ci or finish>co:
        raise ValueError(f'{row["date"]}: 출퇴근 시간 안에서 출발 시각을 선택하세요.')
    return dict(hours=hours,start_hour=start_hour,start_minute=start_minute,start=f'{start_hour:02}:{start_minute:02}',end=f'{finish//60:02}:{finish%60:02}',amount=hours*RATE)


def existing_totals(records):
    grouped={}
    for record in records:grouped.setdefault(record['date'],[]).append(record)
    totals={}
    for key,entries in grouped.items():
        intervals=[]
        for item in entries:
            start=minutes(item['start']);end=minutes(item['end'])
            if start is None or end is None or start>=end:raise ValueError(f'{key}: 기존 출장 시간을 해석할 수 없습니다.')
            intervals.append((start,end))
        intervals.sort()
        if any(a[1]>b[0] for a,b in zip(intervals,intervals[1:])):raise ValueError(f'{key}: 기존 출장 시간이 서로 겹쳐 확인이 필요합니다.')
        actual=sum(end-start for start,end in intervals)
        if actual!=120 and actual<240:raise ValueError(f'{key}: 기존 출장의 인정시간을 확인하세요. 2시간/4시간 기준과 다릅니다.')
        hours=min(4,actual//60)
        totals[key]=dict(hours=hours,amount=hours*RATE,records=entries)
    return totals


def make_rows(attendance,rules,existing,today):
    totals=existing_totals(existing);by_date={r['date']:r for r in attendance}
    keys=set(by_date)|{key for key,rule in rules.items() if rule.get('exclude_overtime')}
    rows=[]
    for key in sorted(keys):
        record=by_date.get(key,{})
        rule=rules.get(key,{})
        if rule.get('vacation'):continue
        event_day=bool(rule.get('exclude_overtime'))
        ci=minutes(record.get('checkin',''));co=minutes(record.get('checkout',''))
        valid=ci is not None and co is not None and ci<co and date.fromisoformat(key)<=today
        if not valid:continue
        registered=totals.get(key)
        row=dict(date=key,weekday='월화수목금토일'[date.fromisoformat(key).weekday()],checkin=record.get('checkin',''),checkout=record.get('checkout',''),
                 mandatory=False,event_day=event_day,selected=False,existing_checked=True,blocked=not valid or bool(registered and len(registered['records'])!=1),is_existing=bool(registered),
                 category=CATEGORY,location='',purpose='',existing_hours=registered['hours'] if registered else 0,existing_amount=registered['amount'] if registered else 0)
        row['status']=('기존 등록 · 장소·목적 수정 가능' if len(registered['records'])==1 else '같은 날 여러 출장 · 사이트에서 수정 필요') if registered else '선택 가능'
        try:row.update(window(row,4))
        except (ValueError,TypeError):
            try:row.update(window(row,2))
            except (ValueError,TypeError):row.update(hours=2,start_hour=9,start='09:00',end='11:00',amount=10000,blocked=True,selected=False,status='출퇴근 구간에 2시간 출장 불가')
        if registered:
            ordered=sorted(registered['records'],key=lambda item:item['start'])
            row.update(hours=registered['hours'],amount=registered['amount'],start=ordered[0]['start'],end=ordered[-1]['end'],start_hour=minutes(ordered[0]['start'])//60,location=ordered[0].get('location',''),purpose=ordered[0].get('purpose',''),blocked=len(registered['records'])!=1,status='기존 등록 · 장소·목적 수정 가능' if len(registered['records'])==1 else '같은 날 여러 출장 · 사이트에서 수정 필요')
            row['category']=ordered[0].get('category',CATEGORY)
            if row['category'] not in CATEGORIES:row.update(blocked=True,status='지원하지 않는 출장 구분 · 사이트에서 확인')
        rows.append(row)
    return rows


def summarize(rows,total,existing_amount=0):
    money(total)
    planned=sum(r['amount'] for r in rows if r.get('selected') and not r.get('blocked') and not r.get('is_existing'))
    remaining=total-existing_amount-planned
    message=(f'출장 추가 필요: {remaining//RATE}시간 / {remaining:,}원 부족' if remaining>0 else
             f'목표 초과: {-remaining//RATE}시간 / {-remaining:,}원' if remaining<0 else '목표 금액·인정시간 일치')
    return dict(target_amount=total,target_hours=total//RATE,existing_amount=existing_amount,planned_amount=planned,
                recognized_hours=(existing_amount+planned)//RATE,remaining_amount=remaining,message=message)


def allocate(rows,total,existing_amount=0,preferred_hours=4):
    money(total)
    if preferred_hours not in (2,4):raise ValueError('기본 출장 시간을 선택하세요.')
    result=deepcopy(rows)
    remaining=total-existing_amount
    candidates=[r for r in result if r.get('selected') and not r['blocked'] and (not r.get('is_existing') or previous[r['date']].get('is_existing'))]
    states={0:[]}
    for row in candidates:
        choices=[]
        for hours in dict.fromkeys((row.get('hours',preferred_hours),preferred_hours,2,4)):
            try:choices.append(window(row,hours,row.get('start_hour')))
            except ValueError:continue
        if not choices:raise ValueError(f'{row["date"]}: 출발 시각을 출퇴근 범위 안으로 조정하세요.')
        next_states={}
        for amount,path in states.items():
            for choice in choices:next_states.setdefault(amount+choice['amount'],path+[choice])
        states=next_states
    if candidates:
        possible=[amount for amount in states if amount<=remaining]
        amount=remaining if remaining in states else max(possible) if possible else min(states)
        for row,choice in zip(candidates,states[amount]):row.update(choice)
    return result,summarize(result,total,existing_amount)


def merge_entries(rows,entries,require_details=False):
    result=deepcopy(rows);allowed={r['date']:r for r in result};seen=set()
    for entry in entries:
        key=entry.get('date')
        if key not in allowed or key in seen:raise ValueError('조회 목록에 없거나 중복된 날짜입니다.')
        seen.add(key);row=allowed[key]
        selected=bool(entry.get('selected'))
        if row['blocked'] and selected:raise ValueError(f'{key}: {row["status"]}')
        row.update(selected=selected,location=str(entry.get('location','')).strip(),purpose=str(entry.get('purpose','')).strip())
        row['category']=trip_category(entry.get('category',row.get('category'))) if selected or row.get('category') in CATEGORIES else row.get('category')
        if row.get('is_existing') and not selected:continue
        if row.get('is_existing') and entry.get('hours',row['hours'])!=row['hours']:
            raise ValueError('기존 출장의 인정시간은 유지하고 출발·복귀 및 장소·목적을 수정하세요.')
        if not row['blocked']:
            changed=window(dict(row,end=entry.get('end',row.get('end'))),entry.get('hours',row['hours']),entry.get('start_hour',row['start_hour']),entry.get('start_minute',minutes(row['start'])%60),entry.get('end'))
            row.update(changed)
        if selected and require_details and (not row['location'] or not row['purpose']):raise ValueError(f'{key}: 출장 장소와 목적을 직접 입력하세요.')
        if len(row['location'])>500 or len(row['purpose'])>1000:raise ValueError('출장 장소 또는 목적이 너무 깁니다.')
    return result


def submission_rows(rows,entries):
    # Only dates explicitly checked with a nonblank purpose may be submitted.
    base=deepcopy(rows)
    for row in base:row['selected']=False
    normalized=[]
    for entry in entries:
        item=dict(entry)
        item['selected']=bool(item.get('selected')) and bool(str(item.get('purpose') or '').strip())
        normalized.append(item)
    return merge_entries(base,normalized,True)


def _rules(state,month):
    return {key:dict(vacation=bool(value.get('vacation')),exclude_overtime=bool(value.get('exclude_overtime')))
            for key,value in state.get('day_rules',{}).items() if key.startswith(month+'-')}


def _account(settings):return hashlib.sha256(settings['id'].encode()).hexdigest()


def _review(app,job):
    with app.file_lock('state'):state=app.load_json(app.STATE_FILE,{})
    review=state.get('trip_review') or {}
    if review.get('id')!=job.get('review_id') or review.get('consumed') or time.time()-review.get('created_at',0)>7200:
        raise ValueError('출장 일정을 새로 조회하세요. 조회 목록이 없거나 만료되었습니다.')
    settings=app.load_json(app.SETTINGS_FILE,{})
    if not settings.get('id') or _account(settings)!=review['account']:raise ValueError('계정이 바뀌었습니다. 다시 조회하세요.')
    if _rules(state,review['month'])!=review['rules']:raise ValueError('휴가·제외일 설정이 바뀌었습니다. 다시 조회하세요.')
    return state,review


def run_job(app,job):
    operation=job.get('operation')
    if operation=='export':
        from trip_export import export_site_records
        return export_site_records(app,job)
    if operation=='allocate':
        _,review=_review(app,job)
        rows=merge_entries(review['rows'],job.get('rows',[]))
        rows,summary=allocate(rows,money(job['total']),review['existing_amount'])
        return dict(ok=True,review_id=review['id'],rows=rows,summary=summary,message=summary['message'])
    if operation not in ('scan','inspect','submit'):raise ValueError('지원하지 않는 출장 작업입니다.')
    from monthly_reconcile import _settings,_connect,_read_month
    from trip_site import TripPage
    settings=_settings(app)
    review=None;chosen=[]
    if operation in ('inspect','submit'):
        _,review=_review(app,job)
        month=review['month']
        if operation=='inspect':
            rows=merge_entries(review['rows'],job.get('rows',[]))
            chosen=[r for r in rows if r['selected'] and not r['blocked']]
    if operation=='submit':
        if not review.get('existing_verified'):raise ValueError('선택 완료를 눌러 기존 출장 내역을 먼저 확인하세요.')
        rows=submission_rows(review['rows'],job.get('rows',[]))
        summary=summarize(rows,money(job['total']),review['existing_amount'])
        if summary['remaining_amount']<0 and any(r['selected'] and not r.get('is_existing') for r in rows):raise ValueError(summary['message']+' · 날짜/시간 선택을 줄이세요.')
        if any(r.get('conflict') for r in rows):raise ValueError('연장 제외일의 기존 출장 시간을 사이트에서 먼저 확인하세요.')
        chosen=[r for r in rows if r['selected'] and not r['blocked']]
        if not chosen:raise ValueError('등록할 출장 날짜를 선택하세요.')
        month=review['month']
    elif operation=='scan':
        month=job['month'];date.fromisoformat(month+'-01')
    money(job.get('total',0))
    with app.file_lock('action',timeout=120):
        driver,page=_connect(app,settings)
        submitted=[];attempted=False;active_date='';trips=None
        try:
            attendance=_read_month(page,month,date.today(),lambda day:True)
            with app.file_lock('state'):state=app.load_json(app.STATE_FILE,{})
            rules=_rules(state,month)
            if operation in ('submit','inspect'):
                if rules!=review['rules']:raise ValueError('달력 설정이 바뀌었습니다. 다시 조회하세요.')
                fresh={r['date']:r for r in attendance}
                for row in chosen:
                    if row['date'] not in fresh or any(row[k]!=fresh[row['date']][k] for k in ('checkin','checkout')):
                        raise ValueError(f'{row["date"]}: 출퇴근 기록이 바뀌었습니다. 다시 조회하세요.')
            if operation=='scan':
                # Read attendance first; a failed journal lookup must not erase it.
                existing=[];existing_amount=0;checked=False;warning=''
                try:
                    lookup=TripPage(driver);lookup.open();existing=lookup.existing(month)
                    existing_amount=sum(v['amount'] for v in existing_totals(existing).values());checked=True
                except Exception as error:
                    existing=[];existing_amount=0
                    detail=str(error).strip()
                    if not detail or detail in ('Message:','Message: None'):detail='사이트 응답 확인 실패'
                    warning=f'기등록 확인 안 됨 ({type(error).__name__}): {detail[:300]}'
                    app.log_event(warning)
                rows=make_rows(attendance,rules,existing,date.today())
                for row in rows:
                    row['existing_checked']=checked
                    if not checked:row['status']='기등록 확인 전 · 선택 완료 시 재확인'
                review=dict(id=uuid.uuid4().hex,month=month,created_at=time.time(),account=_account(settings),rules=rules,rows=rows,existing=existing,existing_amount=existing_amount,existing_verified=False,initial_existing_checked=checked)
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state['trip_review']=review;app.save_json(app.STATE_FILE,state)
                summary=summarize(rows,job.get('total',0),existing_amount)
                days=len(existing_totals(existing)) if checked else 0
                message=f'근태 날짜 조회 완료 · 기등록 {days}일 / {existing_amount:,}원 반영. 미등록 날짜를 추가 선택하세요. 기존 날짜는 수정 버튼으로 출발·복귀와 장소·목적을 변경합니다.' if checked else '근태 날짜는 조회했습니다. '+warning+' · 현재 금액은 임시 계산이며 선택 완료 시 반드시 확인합니다.'
                return dict(ok=True,review_id=review['id'],rows=rows,summary=summary,message=message,existing_checked=checked)
            trips=TripPage(driver);trips.open();existing=trips.existing(month);trips.check_options()
            existing_amount=sum(v['amount'] for v in existing_totals(existing).values())
            if operation=='inspect':
                fresh_rows=make_rows(attendance,rules,existing,date.today())
                previous={r['date']:r for r in rows}
                entries=[dict(previous[r['date']]) for r in fresh_rows if r['date'] in previous and not r['blocked'] and (not r.get('is_existing') or previous[r['date']].get('is_existing'))]
                rows=merge_entries(fresh_rows,entries)
                if job.get('edit_existing'):
                    for row in rows:row['selected']=False
                for row in rows:
                    if row.get('is_existing') and not row['blocked']:row['selected']=bool(job.get('edit_existing') or previous.get(row['date'],{}).get('selected'))
                for row in rows:
                    if state.get('trip_applications',{}).get(row['date'],{}).get('status') in ('sending','uncertain') and not row['existing_amount']:
                        row.update(blocked=True,selected=False,status='이전 등록 결과 확인 필요')
                review=dict(id=uuid.uuid4().hex,month=month,created_at=time.time(),account=_account(settings),rules=rules,rows=rows,existing=existing,existing_amount=existing_amount,existing_verified=True)
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state['trip_review']=review;app.save_json(app.STATE_FILE,state)
                summary=summarize(rows,job['total'],existing_amount)
                ready=any(r['selected'] and not r['blocked'] for r in rows) and (summary['remaining_amount']>=0 or not any(r['selected'] and not r.get('is_existing') for r in rows)) and not any(r.get('conflict') for r in rows)
                return dict(ok=True,review_id=review['id'],rows=rows,summary=summary,ready=ready,message='기존 출장 확인 완료. 선택 날짜의 장소·목적을 입력하세요.' if ready else '기존 출장 확인 완료. '+summary['message']+' · 날짜·시간 선택을 확인하세요.')
            if existing!=review['existing']:raise ValueError('기존 출장 내역이 바뀌었습니다. 다시 조회하세요.')
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{});state['trip_review']['consumed']=True;app.save_json(app.STATE_FILE,state)
            for row in sorted(chosen,key=lambda r:r['date']):
                key=row['date'];active_date=key;driver._workday_write_submitted=False;trips.phase='기존 출장 중복·변경 확인'
                matches=[e for e in trips.existing(month) if e['date']==key]
                if row.get('is_existing'):
                    expected=[e for e in review['existing'] if e['date']==key]
                    if len(matches)!=1 or matches!=expected:raise ValueError(f'{key}: 기존 출장 내용이 달라져 수정을 중단합니다.')
                    if all(' '.join(str(matches[0].get(field,CATEGORY if field=='category' else '')).split())==' '.join(str(row.get(field,CATEGORY if field=='category' else '')).split()) for field in ('location','purpose','start','end','category')):
                        row['status']='기존 내용 동일 · 유지';submitted.append(key)
                        with app.file_lock('state'):
                            state=app.load_json(app.STATE_FILE,{});state.setdefault('trip_applications',{})[key]=dict(status='success',row=row,source='기존 동일 내용 확인');app.save_json(app.STATE_FILE,state)
                        continue
                elif matches:raise ValueError(f'{key}: 기존 출장이 있어 중복 등록을 중단합니다.')
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state.setdefault('trip_applications',{})[key]=dict(status='sending',row=row,at=time.time());app.save_json(app.STATE_FILE,state)
                attempted=True
                app.log_event(f'{key} 출장 날짜별 등록 시작')
                trips.submit(row,month,update=True) if row.get('is_existing') else trips.submit(row,month)
                submitted.append(key);row['status']='수정 확인 완료' if row.get('is_existing') else '등록 확인 완료'
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state['trip_applications'][key]['status']='success';app.save_json(app.STATE_FILE,state)
                app.log_event(f'{key} 출장 등록 확인 완료')
            trips.phase='최종 출장 내역 합산 확인'
            final=trips.existing(month)
            final_amount=sum(v['amount'] for v in existing_totals(final).values())
            summary=summarize([],job['total'],final_amount)
            return dict(ok=True,rows=chosen,all_rows=make_rows(attendance,rules,final,date.today()),summary=summary,message=f'출장 {len(submitted)}일 등록·수정 확인 완료. '+summary['message'])
        except Exception as error:
            if operation!='submit' or not attempted:raise
            phase=getattr(trips,'phase','출장 처리')
            sent=getattr(driver,'_workday_write_submitted',True)
            stage='저장 요청 후 확인 실패' if sent else '저장 버튼 실행 전 중단'
            detail=app.user_job_error(error,f'{active_date or month} · {phase} · {stage}')
            app.log_event(detail)
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{})
                for item in chosen:
                    if item['date'] in submitted:item['status']=item.get('status','등록 확인 완료')
                    elif state.get('trip_applications',{}).get(item['date'],{}).get('status')=='sending':
                        sent=getattr(driver,'_workday_write_submitted',True)
                        state['trip_applications'][item['date']]['status']='uncertain' if sent else 'not_submitted'
                        item['status']='등록 결과 확인 필요' if sent else '저장 전 중단'
                    else:item['status']='미처리'
                app.save_json(app.STATE_FILE,state)
            return dict(ok=False,error=detail,rows=chosen,message=f'등록·수정 확인 {len(submitted)}일. 중단된 날짜를 확인하고 다시 조회하세요. 목표 미달이면 출장 추가가 필요합니다.')
        finally:driver.quit()
