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
TRANSPORT='대중교통'
RATE=5000


def money(value):
    if type(value) is not int or value<0 or value>10000000 or value%10000:
        raise ValueError('목표 금액은 0~1,000만원 범위의 1만원 단위로 입력하세요.')
    return value


def minutes(value):
    parsed=parse_time(value)
    return parsed[0]*60+parsed[1] if parsed else None


def window(row,hours=None,start_hour=None):
    if row['mandatory']:
        return dict(hours=4,start_hour=9,start='09:00',end='18:00',amount=20000)
    hours=row.get('hours',4) if hours is None else hours
    if type(hours) is not int or hours not in (2,4):raise ValueError('출장 인정시간은 2시간 또는 4시간입니다.')
    ci=minutes(row['checkin']);co=minutes(row['checkout'])
    start_hour=(ci+59)//60 if start_hour is None else start_hour
    if type(start_hour) is not int or not 0<=start_hour<=23 or start_hour+hours>23:
        raise ValueError('출발 시각과 복귀 시각을 확인하세요.')
    if ci is None or co is None or start_hour*60<ci or (start_hour+hours)*60>co:
        raise ValueError(f'{row["date"]}: 출퇴근 시간 안에서 출발 시각을 선택하세요.')
    return dict(hours=hours,start_hour=start_hour,start=f'{start_hour:02}:00',end=f'{start_hour+hours:02}:00',amount=hours*RATE)


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
        mandatory=bool(rule.get('exclude_overtime') and not rule.get('vacation'))
        ci=minutes(record.get('checkin',''));co=minutes(record.get('checkout',''))
        valid=ci is not None and co is not None and ci<co and date.fromisoformat(key)<=today
        if not valid:continue
        registered=totals.get(key)
        row=dict(date=key,weekday='월화수목금토일'[date.fromisoformat(key).weekday()],checkin=record.get('checkin',''),checkout=record.get('checkout',''),
                 mandatory=mandatory,selected=mandatory and valid and not registered,blocked=not valid or bool(registered) or bool(rule.get('vacation')),
                 location='',purpose='',existing_hours=registered['hours'] if registered else 0,existing_amount=registered['amount'] if registered else 0)
        row['status']='등록 완료 · 중복 제외' if registered else '출퇴근 기록 확인 필요' if not valid else '휴가 · 기본 제외' if rule.get('vacation') else '필수 포함' if mandatory else '선택 가능'
        if mandatory and registered and not any(r['start']=='09:00' and r['end']=='18:00' for r in registered['records']):
            row['status']='기존 출장 확인 필요 · 제외일 09~18시와 다름';row['conflict']=True
        try:row.update(window(row,4))
        except (ValueError,TypeError):
            try:row.update(window(row,2))
            except (ValueError,TypeError):row.update(hours=2,start_hour=9,start='09:00',end='11:00',amount=10000,blocked=True,selected=False,status='출퇴근 구간에 2시간 출장 불가')
        if registered:
            ordered=sorted(registered['records'],key=lambda item:item['start'])
            row.update(hours=registered['hours'],amount=registered['amount'],start=ordered[0]['start'],end=ordered[-1]['end'],start_hour=minutes(ordered[0]['start'])//60)
        rows.append(row)
    return rows


def summarize(rows,total,existing_amount=0):
    money(total)
    planned=sum(r['amount'] for r in rows if r.get('selected') and not r.get('blocked'))
    remaining=total-existing_amount-planned
    message=(f'출장 추가 필요: {remaining//RATE}시간 / {remaining:,}원 부족' if remaining>0 else
             f'목표 초과: {-remaining//RATE}시간 / {-remaining:,}원' if remaining<0 else '목표 금액·인정시간 일치')
    return dict(target_amount=total,target_hours=total//RATE,existing_amount=existing_amount,planned_amount=planned,
                recognized_hours=(existing_amount+planned)//RATE,remaining_amount=remaining,message=message)


def allocate(rows,total,existing_amount=0,preferred_hours=4):
    money(total)
    if preferred_hours not in (2,4):raise ValueError('기본 출장 시간을 선택하세요.')
    result=deepcopy(rows)
    remaining=total-existing_amount-sum(r['amount'] for r in result if r['selected'] and r['mandatory'] and not r['blocked'])
    candidates=[r for r in result if r.get('selected') and not r['mandatory'] and not r['blocked']]
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
        if row['mandatory'] and not row['blocked'] and not selected:raise ValueError(f'{key}: 연장 제외일은 필수 포함입니다.')
        if row['blocked'] and selected:raise ValueError(f'{key}: {row["status"]}')
        row.update(selected=selected,location=str(entry.get('location','')).strip(),purpose=str(entry.get('purpose','')).strip())
        if not row['blocked']:row.update(window(row,entry.get('hours',row['hours']),entry.get('start_hour',row['start_hour'])))
        if selected and require_details and (not row['location'] or not row['purpose']):raise ValueError(f'{key}: 출장 장소와 목적을 직접 입력하세요.')
        if len(row['location'])>500 or len(row['purpose'])>1000:raise ValueError('출장 장소 또는 목적이 너무 깁니다.')
    if require_details and any(r['mandatory'] and not r['existing_amount'] and (r['blocked'] or r['date'] not in seen or not r['selected']) for r in result):
        raise ValueError('연장 제외일의 출퇴근 기록과 출장 선택을 먼저 확인하세요.')
    return result


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
        rows=merge_entries(review['rows'],job.get('rows',[]),True)
        summary=summarize(rows,money(job['total']),review['existing_amount'])
        if summary['remaining_amount']!=0:raise ValueError(summary['message']+' · 날짜/시간 선택을 완료하세요.')
        if any(r.get('conflict') for r in rows):raise ValueError('연장 제외일의 기존 출장 시간을 사이트에서 먼저 확인하세요.')
        chosen=[r for r in rows if r['selected'] and not r['blocked']]
        if not chosen:raise ValueError('등록할 출장 날짜를 선택하세요.')
        month=review['month']
    elif operation=='scan':
        month=job['month'];date.fromisoformat(month+'-01')
    money(job.get('total',0))
    with app.file_lock('action',timeout=120):
        driver,page=_connect(app,settings)
        submitted=[];attempted=False
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
                # Attendance lookup must not depend on finding the trip menu.
                rows=make_rows(attendance,rules,[],date.today())
                review=dict(id=uuid.uuid4().hex,month=month,created_at=time.time(),account=_account(settings),rules=rules,rows=rows,existing=[],existing_amount=0,existing_verified=False)
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state['trip_review']=review;app.save_json(app.STATE_FILE,state)
                summary=summarize(rows,job.get('total',0),0)
                return dict(ok=True,review_id=review['id'],rows=rows,summary=summary,message='근태관리의 출퇴근 등록 날짜를 조회했습니다. 날짜·시간을 선택하세요. 기존 출장은 선택 완료 시 확인합니다.')
            trips=TripPage(driver);trips.open();existing=trips.existing(month);trips.check_options()
            existing_amount=sum(v['amount'] for v in existing_totals(existing).values())
            if operation=='inspect':
                fresh_rows=make_rows(attendance,rules,existing,date.today())
                previous={r['date']:r for r in rows}
                entries=[dict(previous[r['date']]) for r in fresh_rows if r['date'] in previous and not r['blocked']]
                rows=merge_entries(fresh_rows,entries)
                for row in rows:
                    if state.get('trip_applications',{}).get(row['date'],{}).get('status') in ('sending','uncertain') and not row['existing_amount']:
                        row.update(blocked=True,selected=False,status='이전 등록 결과 확인 필요')
                review=dict(id=uuid.uuid4().hex,month=month,created_at=time.time(),account=_account(settings),rules=rules,rows=rows,existing=existing,existing_amount=existing_amount,existing_verified=True)
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state['trip_review']=review;app.save_json(app.STATE_FILE,state)
                summary=summarize(rows,job['total'],existing_amount)
                ready=summary['remaining_amount']==0 and any(r['selected'] and not r['blocked'] for r in rows) and not any(r.get('conflict') for r in rows)
                return dict(ok=True,review_id=review['id'],rows=rows,summary=summary,ready=ready,message='기존 출장 확인 완료. 선택 날짜의 장소·목적을 입력하세요.' if ready else '기존 출장 확인 완료. '+summary['message']+' · 날짜·시간 선택을 확인하세요.')
            if existing!=review['existing']:raise ValueError('기존 출장 내역이 바뀌었습니다. 다시 조회하세요.')
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{});state['trip_review']['consumed']=True;app.save_json(app.STATE_FILE,state)
            for row in sorted(chosen,key=lambda r:r['date']):
                key=row['date']
                if any(e['date']==key for e in trips.existing(month)):raise ValueError(f'{key}: 기존 출장이 있어 중복 등록을 중단합니다.')
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state.setdefault('trip_applications',{})[key]=dict(status='sending',row=row,at=time.time());app.save_json(app.STATE_FILE,state)
                attempted=True
                app.log_event(f'{key} 출장 날짜별 등록 시작')
                trips.submit(row,month)
                submitted.append(key);row['status']='등록 확인 완료'
                with app.file_lock('state'):
                    state=app.load_json(app.STATE_FILE,{});state['trip_applications'][key]['status']='success';app.save_json(app.STATE_FILE,state)
                app.log_event(f'{key} 출장 등록 확인 완료')
            final=trips.existing(month)
            final_amount=sum(v['amount'] for v in existing_totals(final).values())
            summary=summarize([],job['total'],final_amount)
            return dict(ok=True,rows=chosen,all_rows=make_rows(attendance,rules,final,date.today()),summary=summary,message=f'출장 {len(submitted)}일 등록 확인 완료. '+summary['message'])
        except Exception as error:
            if operation!='submit' or not attempted:raise
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{})
                for item in chosen:
                    if item['date'] in submitted:item['status']='등록 확인 완료'
                    elif state.get('trip_applications',{}).get(item['date'],{}).get('status')=='sending':
                        sent=getattr(driver,'_workday_write_submitted',True)
                        state['trip_applications'][item['date']]['status']='uncertain' if sent else 'not_submitted'
                        item['status']='등록 결과 확인 필요' if sent else '저장 전 중단'
                    else:item['status']='미처리'
                app.save_json(app.STATE_FILE,state)
            return dict(ok=False,error=str(error),rows=chosen,message=f'등록 확인 {len(submitted)}일. 중단된 날짜를 확인하고 다시 조회하세요. 목표 미달이면 출장 추가가 필요합니다.')
        finally:driver.quit()
