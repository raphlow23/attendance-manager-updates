"""Delete one explicitly confirmed recorded trip, then rebuild the available row."""
import copy,time,uuid
from datetime import date
from business_trips import _review,_account,_rules,make_rows,merge_entries,center_totals,summarize,money

def confirm_absent_deletions(app,month,records):
    present={r['date'] for r in records}
    with app.file_lock('state'):
        state=app.load_json(app.STATE_FILE,{})
        changed=False
        for key,entry in state.get('trip_deletions',{}).items():
            if key.startswith(month+'-') and entry.get('status') in ('sending','uncertain') and key not in present:
                entry['status']='verified_after_requery'
                state.setdefault('trip_applications',{})[key]=dict(status='deleted',source='삭제 후 재조회로 부재 확인')
                changed=True
        if changed:app.save_json(app.STATE_FILE,state)

def rebuild_rows(attendance,rules,existing,previous,deleted_key,today):
    rows=make_rows(attendance,rules,existing,today)
    drafts={r['date']:r for r in previous}
    for index,row in enumerate(rows):
        draft=drafts.get(row['date'])
        if draft and not row['blocked']:
            same_source=draft.get('site_record')==row.get('site_record')
            if row['date']==deleted_key or same_source:
                proposed=dict(draft,selected=False if row['date']==deleted_key else bool(draft.get('selected')))
                try:rows[index]=row=merge_entries([row],[proposed])[0]
                except ValueError:
                    row.update(selected=False,location=str(draft.get('location','')),purpose=str(draft.get('purpose','')))
        if row['date']==deleted_key:
            row.update(selected=False,status='삭제 확인 완료 · 미등록 · 다시 선택 가능')
    return rows

def delete_trip(app,job):
    from monthly_reconcile import _settings,_connect,_read_month
    from trip_site import TripPage
    state,review=_review(app,job)
    keys=job.get('dates')
    if job.get('confirmed') is not True or not isinstance(keys,list) or len(keys)!=1:
        raise ValueError('삭제할 기등록 날짜 한 건을 확인한 뒤 삭제하세요.')
    key=keys[0];month=review['month']
    candidates=[r for r in review['rows'] if r['date']==key and r.get('is_existing') and not r.get('blocked')]
    originals=[r for r in review['existing'] if r['date']==key]
    if len(candidates)!=1 or len(originals)!=1:raise ValueError('삭제할 기등록 한 건을 확인하지 못했습니다. 다시 조회하세요.')
    expected=originals[0];settings=_settings(app)
    if _account(settings)!=review['account']:raise ValueError('계정이 바뀌었습니다. 다시 조회하세요.')
    total=money(job.get('total',0));attempted=False
    with app.file_lock('action',timeout=120):
        driver,page=_connect(app,settings)
        try:
            attendance=_read_month(page,month,date.today(),lambda day:True)
            with app.file_lock('state'):state=app.load_json(app.STATE_FILE,{})
            rules=_rules(state,month)
            if rules!=review['rules']:raise ValueError('휴가·제외일 설정이 바뀌었습니다. 다시 조회하세요.')
            site=TripPage(driver);site.open();existing=site.existing(month)
            if [r for r in existing if r['date']==key]!=[expected]:raise ValueError('삭제 대상 기록이 바뀌었습니다. 다시 조회하세요.')
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{})
                if (state.get('trip_review') or {}).get('id')!=review['id'] or state['trip_review'].get('consumed'):raise ValueError('조회 목록이 바뀌었습니다. 다시 조회하세요.')
                state['trip_review']['consumed']=True
                state.setdefault('trip_deletions',{})[key]=dict(status='sending',before=expected,at=time.time())
                app.save_json(app.STATE_FILE,state)
            attempted=True;app.log_event(f'{key} 사용자 확인 후 출장 삭제 시작')
            site.delete(expected,month)
            final=site.existing(month)
            if any(r['date']==key for r in final):raise RuntimeError('삭제 후 같은 날짜의 기록이 확인되어 재조회가 필요합니다.')
            prior={r['date']:r for r in review['rows']}
            previous=[dict(prior[r['date']],**r) for r in job.get('rows',review['rows']) if r.get('date') in prior]
            rows=rebuild_rows(attendance,rules,final,previous,key,date.today())
            amount=sum(v['amount'] for v in center_totals(final).values())
            fresh=dict(id=uuid.uuid4().hex,month=month,created_at=time.time(),account=review['account'],rules=rules,rows=rows,existing=final,existing_amount=amount,existing_verified=False,initial_existing_checked=True)
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{})
                state.setdefault('trip_deletions',{})[key].update(status='success')
                state.setdefault('trip_applications',{})[key]=dict(status='deleted',source='사용자 삭제 후 사이트 부재 확인')
                state['trip_review']=fresh;app.save_json(app.STATE_FILE,state)
            app.log_event(f'{key} 출장 삭제 확인 완료 · 재등록 가능')
            return dict(ok=True,review_id=fresh['id'],rows=rows,summary=summarize(rows,total,amount),deleted_dates=[key],message=f'{key} 출장 삭제 확인 완료. 해당 날짜가 미등록으로 돌아왔습니다. 다시 선택하여 등록할 수 있습니다.')
        except Exception as error:
            if not attempted:raise
            sent=getattr(driver,'_workday_write_submitted',False)
            with app.file_lock('state'):
                state=app.load_json(app.STATE_FILE,{})
                state.setdefault('trip_deletions',{})[key].update(status='uncertain' if sent else 'not_submitted')
                app.save_json(app.STATE_FILE,state)
            detail=app.user_job_error(error,f'{key} 출장 삭제 결과 확인 필요' if sent else f'{key} 출장 삭제 실행 전 중단')
            app.log_event(detail)
            rows=copy.deepcopy(review['rows'])
            for row in rows:
                if row['date']==key:row.update(selected=False,blocked=True,status='삭제 결과 확인 필요 · 사이트 확인 후 재조회')
            return dict(ok=False,error=detail,rows=rows,message='삭제 결과가 확인되지 않아 미등록으로 바꾸지 않았습니다. 사이트를 확인한 뒤 다시 조회하세요.')
        finally:driver.quit()
