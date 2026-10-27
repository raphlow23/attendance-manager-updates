"""Shared session budget and backoff; never bypass a site's access limits."""
import json
import os
import time
from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime


class SiteAccessPaused(RuntimeError):
    pass


def _read(app):
    path = os.path.join(app.DATA_DIR, 'site-access.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8-sig') as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError('invalid state')
        return value
    except Exception as error:
        raise SiteAccessPaused('접속 간격 상태를 읽지 못해 추가 접속을 보류합니다.') from error


def check_pause(app):
    with app.file_lock('site_access'):
        state = _read(app)
        ready = float(state.get('cooldown_until',0))
    if ready > time.time():
        raise SiteAccessPaused(f'사이트 보호를 위해 접속 대기 중입니다. 약 {max(1,int(ready-time.time()))}초 후 다시 확인하세요. {state.get("reason", "단시간 접속 횟수 제한")}')


def reserve_session(app):
    """No fixed delay: throttle only a measured burst or site-imposed pause."""
    while True:
        check_pause(app)
        with app.file_lock('site_access'):
            now=time.time()
            requests=sorted(float(t) for t in _read(app).get('requests',[]) if now-1<float(t)<=now+1)
        if len(requests)<8:
            return
        time.sleep(min(1,max(0.01,requests[-8]+1.01-now)))


def reserve_write(app):
    reserve_session(app)


def record_requests(app, timestamps):
    if not timestamps:
        return
    with app.file_lock('site_access'):
        state=_read(app);now=time.time()
        values=[float(t) for t in state.get('requests',[]) if now-10<float(t)<=now+1]
        values.extend(t for t in timestamps if now-10<t<=now+1)
        state['requests']=sorted(values)
        storm=sum(t>now-1 for t in values)>24
        if storm:
            state.update(cooldown_until=now+10,reason='비정상적인 반복 요청 감지')
        app.save_json(os.path.join(app.DATA_DIR,'site-access.json'),state)
    if storm:
        raise SiteAccessPaused('짧은 시간에 반복 요청이 감지되어 해당 작업을 중단했습니다. 자동 반복하지 않습니다.')


def pause(app, status, retry_after=None):
    seconds = {403:1800,429:900,503:300}.get(status,300)
    if retry_after:
        try:
            seconds = max(seconds, int(retry_after))
        except (ValueError, TypeError):
            try:
                seconds = max(seconds, int(parsedate_to_datetime(retry_after).timestamp()-time.time()))
            except (ValueError, TypeError, OverflowError):
                pass
    seconds = min(max(60,seconds),2147483647)
    with app.file_lock('site_access'):
        state = _read(app)
        state.update(cooldown_until=max(float(state.get('cooldown_until',0)),time.time()+seconds),
                     reason=f'사이트 응답 {status}: 추가 요청 중단')
        app.save_json(os.path.join(app.DATA_DIR,'site-access.json'),state)
    app.log_event(f'사이트 응답 {status}: 최소 {seconds}초 접속 보류')
    raise SiteAccessPaused(f'사이트가 요청 초과 또는 접근 제한({status})을 표시해 자동 접속을 멈췄습니다. 최소 {seconds//60}분 뒤 다시 확인하세요.')


def check_page(app, driver):
    # Read only document response status. Do not persist browser headers/cookies.
    try:
        entries=driver.get_log('performance')
        requests=[]
        for entry in entries:
            message=json.loads(entry['message'])['message']
            params=message.get('params',{})
            expected=getattr(driver,'_workday_expected_save_url',None)
            if isinstance(expected,str) and expected:
                request=params.get('request',{})
                if message.get('method')=='Network.requestWillBeSent' and request.get('method')=='POST' and request.get('url')==expected:
                    driver._workday_post_seen=True
                response=params.get('response',{}) if message.get('method')=='Network.responseReceived' else params.get('redirectResponse',{})
                if response.get('url')==expected:
                    driver._workday_save_response_status=int(response.get('status',0))
            if message.get('method')=='Network.requestWillBeSent' and params.get('type') in ('Document','XHR','Fetch'):
                if urlsplit(params.get('request',{}).get('url','')).hostname==urlsplit(app.SITE_URL).hostname:
                    requests.append(float(params.get('wallTime',time.time())))
            if message.get('method')=='Network.responseReceived' and params.get('type')=='Document':
                response=params.get('response',{})
                status=int(response.get('status',0))
                if status in (403,429,503):
                    headers={k.lower():v for k,v in response.get('headers',{}).items()}
                    pause(app,status,headers.get('retry-after'))
        record_requests(app,requests)
    except SiteAccessPaused:
        raise
    except Exception:
        pass
    try:
        body=str(driver.find_element('tag name','body').text).lower()
    except Exception:
        return
    if any(t in body for t in ('too many requests','요청 횟수를 초과','접속 횟수를 초과')):
        pause(app,429)
    if '403 forbidden' in body or 'access denied' in body:
        pause(app,403)
    if '503 service unavailable' in body:
        pause(app,503)
