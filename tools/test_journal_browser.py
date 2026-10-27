"""Real Chrome workflows against a local trip/overtime form+POST server."""
import sys,threading,tempfile
from pathlib import Path
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'.test-libs'),str(ROOT/'app')]
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webelement import WebElement
import main as app
import business_trips as trips
import overtime_requests as overtime

trip_records=[];ot_records=[];posts=[];ignore_ot_update=False;direct_trip_landing=False
NAV='<a href="/attendance">근태관리</a><a href="/work">근무일지</a>'
def inp(name,value='',placeholder=''):return f'<input name="{name}" value="{escape(str(value),quote=True)}" placeholder="{placeholder}">'
def sel(name,options):return '<select name="'+name+'">'+''.join(f'<option value="{v}">{label}</option>' for v,label in options)+'</select>'
def numbers(name,limit,unit):return sel(name,[(str(n),str(n)+unit) for n in range(limit)])
def trip_page():
    form='<form method="post" action="/trip-save">'+inp('nonce','fixture-token') .replace('<input ','<input type="hidden" ',1)
    form+=sel('kind',[('x','선택'),('center','센터')])+inp('y',2026)+inp('m',10)+inp('d',27)+inp('place','','출장장소')+inp('purpose','','출장목적을 구체적으로 입력하세요')
    form+=sel('transport',[('x','선택'),('public','대중교통')])+numbers('sh',24,'시')+numbers('sm',60,'분')+numbers('eh',24,'시')+numbers('em',60,'분')+'<button type="submit">확인</button></form>'
    heads=''.join('<th>'+t+'</th>' for t in ('구분','출장일','출장장소','출장목적','이동수단','출발시간','복귀시간','출장시간'))
    body=''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in ('센터',r['date'],r['location'],r['purpose'],'대중교통',r['start'],r['end'],'시간'))+'</tr>' for r in trip_records)
    return NAV+'<h2>출장 등록하기</h2>'+form+'<h2>사용자님의 10월 출장일지</h2><table><thead><tr>'+heads+'</tr></thead><tbody>'+body+'</tbody></table>'
def overtime_page(edit=None):
    r=ot_records[edit] if edit is not None else None
    form='<form method="post" action="'+('/ot-update?index='+str(edit) if r else '/ot-save')+'">'
    form+=(inp('dept','센터') if r else sel('dept',[('x','선택'),('center','센터')]))+inp('purpose',r['purpose'] if r else '','근무목적을 구체적으로 입력하세요')+inp('year',2026)
    form+=numbers('month',13,'월')+numbers('day',32,'일')+sel('weekday',[(v,v+'요일') for v in '월화수목금토일'])
    form+=numbers('sh',24,'시')+numbers('sm',60,'분')+numbers('eh',24,'시')+numbers('em',60,'분')
    form+=inp('fy',2026)+inp('fm',int(r['date'][5:7]) if r else 10)+inp('fd',int(r['date'][8:]) if r else 27)+'<button type="submit">'+('시간외근무 수정하기' if r else '시간외근무 신청')+'</button></form>'
    if r:
        for name,value in dict(month=int(r['date'][5:7]),day=int(r['date'][8:]),sh=int(r['start'][:2]),sm=int(r['start'][3:]),eh=int(r['end'][:2]),em=int(r['end'][3:])).items():
            marker='<select name="'+name+'">';a=form.index(marker);b=form.index('</select>',a)
            form=form[:a]+form[a:b].replace('value="'+str(value)+'"','value="'+str(value)+'" selected')+form[b:]
    if r:form=form.replace(inp('purpose',r['purpose'],'근무목적을 구체적으로 입력하세요'),'<table><tr><td>근무목적 :</td><td>'+inp('purpose',r['purpose'])+'</td></tr></table>')
    body=''.join('<tr><td>'+escape(r['date']+' (목)')+'</td><td>'+escape(r['start']+' ~ '+r['end']+' (1시간 00분)')+'</td><td><a href="/ot-edit?index='+str(i)+'">수정하기</a></td></tr>' for i,r in enumerate(ot_records))
    return NAV+'<h2>시간외근무 '+('수정' if r else '신청서')+'</h2>'+form+'<table><thead><tr><th>근무일</th><th>근무시간</th><th>수정</th></tr></thead><tbody>'+body+'</tbody></table>'
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/work' and direct_trip_landing:content=trip_page()
        elif path=='/work':content=NAV+'<div><span><h3>출장일지</h3></span><a href="/trips">바로가기</a></div><div><span><h3>시간외근무신청</h3></span><a href="/overtime">바로가기</a></div>'
        elif path in ('/trips','/sappd_g6.php'):content=trip_page()
        elif path=='/overtime':content=overtime_page()
        elif path=='/ot-edit':content=overtime_page(int(parse_qs(urlsplit(self.path).query)['index'][0]))
        elif path=='/ot-success':content=NAV+'<h2>신청 저장 완료</h2>'
        elif path=='/attendance':content=NAV
        else:self.send_response(404);self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(('<meta charset="utf-8">'+content).encode())
    def do_POST(self):
        fields={k:v[0] for k,v in parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(),keep_blank_values=True).items()}
        if self.path=='/trip-save':
            assert fields['kind']=='center' and fields['transport']=='public' and fields['nonce']=='fixture-token'
            row=dict(date=f"{int(fields['y']):04}-{int(fields['m']):02}-{int(fields['d']):02}",location=fields['place'],purpose=fields['purpose'],start=f"{int(fields['sh']):02}:{int(fields['sm']):02}",end=f"{int(fields['eh']):02}:{int(fields['em']):02}")
            trip_records.append(row);posts.append(('trip',row['date']));target='/trips'
        elif urlsplit(self.path).path in ('/ot-save','/ot-update'):
            updating=urlsplit(self.path).path=='/ot-update'
            assert fields['dept']==('센터' if updating else 'center') and fields['year']==fields['fy'] and fields['month']==fields['fm'] and fields['day']==fields['fd']
            row=dict(date=f"{int(fields['year']):04}-{int(fields['month']):02}-{int(fields['day']):02}",purpose=fields['purpose'],start=f"{int(fields['sh']):02}:{int(fields['sm']):02}",end=f"{int(fields['eh']):02}:{int(fields['em']):02}")
            if updating:
                if not ignore_ot_update:ot_records[int(parse_qs(urlsplit(self.path).query)['index'][0])]=row
            else:ot_records.append(row)
            posts.append(('overtime-update' if updating else 'overtime',row['date']));target='/ot-success'
        else:self.send_response(404);self.end_headers();return
        self.send_response(303);self.send_header('Location',target);self.end_headers()
class Server(ThreadingHTTPServer):
    def handle_error(self,request,address):
        if not isinstance(sys.exc_info()[1],(ConnectionResetError,BrokenPipeError)):super().handle_error(request,address)
server=Server(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
def connect(*args):
    options=webdriver.ChromeOptions()
    for arg in ('--headless=new','--window-size=1440,1000','--disable-background-networking','--no-first-run'):options.add_argument(arg)
    driver=webdriver.Chrome(options=options,service=Service(str(ROOT/'app/driver/chromedriver.exe'),popen_kw={'creation_flags':app.subprocess.CREATE_NO_WINDOW}))
    driver.get(base+'/attendance');return driver,Mock()
try:
 with tempfile.TemporaryDirectory(prefix='workday-journal-') as folder:
  with patch.object(app,'DATA_DIR',folder),patch.object(app,'STATE_FILE',str(Path(folder)/'state.json')),patch.object(app,'SETTINGS_FILE',str(Path(folder)/'settings.json')),patch.object(app,'LOG_FILE',str(Path(folder)/'events.log')):
   app.save_json(app.SETTINGS_FILE,{'id':'fixture','pw':'fixture'});app.save_json(app.STATE_FILE,{'day_rules':{'2026-10-07':{'exclude_overtime':True}}})
   attendance=[dict(date='2026-10-07',checkin='09:00',checkout='18:00',note=''),dict(date='2026-10-13',checkin='08:35',checkout='18:00',note='')]
   original=WebElement.get_attribute
   def initial_value(element,name):return element.get_dom_attribute(name) if name=='value' else original(element,name)
   with patch.object(WebElement,'click',lambda self:None),patch.object(WebElement,'send_keys',lambda self,*args:None),patch.object(WebElement,'get_attribute',initial_value),patch('monthly_reconcile._connect',side_effect=connect),patch('monthly_reconcile._read_month',return_value=attendance):
    review=trips.run_job(app,dict(operation='scan',month='2026-10',total=30000))
    chosen=[]
    for row in review['rows']:chosen.append(dict(date=row['date'],selected=True,hours=4 if row.get('event_day') else 2,start_hour=9,location='장소 '+row['date'],purpose='직접  입력한 출장 목적'))
    review=trips.run_job(app,dict(operation='inspect',review_id=review['review_id'],total=30000,rows=chosen))
    assert review['ready']
    result=trips.run_job(app,dict(operation='submit',review_id=review['review_id'],total=30000,rows=chosen))
    assert result['ok'] and result['summary']['remaining_amount']==0
    assert posts==[('trip','2026-10-07'),('trip','2026-10-13')]
    assert trip_records[0]['start']=='09:00' and trip_records[0]['end']=='18:00' and trip_records[1]['end']=='11:00'
    try:trips.run_job(app,dict(operation='submit',review_id=review['review_id'],total=30000,rows=chosen));raise AssertionError('Review replay allowed')
    except ValueError:pass
    driver,_=connect()
    try:
     direct_trip_landing=True
     from trip_site import TripPage
     TripPage(driver).open()
     assert driver.current_url==base+'/work' and TripPage(driver).form()
     direct_trip_landing=False
     with patch('trip_site.TRIP_ENTRY_URL',base+'/sappd_g6.php'):
      TripPage(driver).open()
      assert driver.current_url==base+'/sappd_g6.php' and TripPage(driver).form()
     page=overtime.OvertimePage(driver);page.open();rows=[]
     for d,checkout in ((1,'19:55'),(7,'20:30')):rows.append(dict(overtime.application_row(date(2026,10,d),{'checkin':'08:35','checkout':checkout}),purpose='직접  입력한 시간외 목적'))
     statuses={};result=overtime.submit_rows(page,rows,rows,statuses,lambda values:None)
     assert all(row['status']=='신청 확인 완료' for row in result),result
     changed=[dict(rows[0],purpose='수정한 새 근무목적')]
     updated=overtime.submit_rows(page,changed,rows,statuses,lambda values:None)
     assert updated[0]['status']=='수정 확인 완료',updated
     assert len(ot_records)==2 and ot_records[0]['end']=='19:00' and ot_records[1]['end']=='20:00'
     assert [p for p in posts if p[0]=='overtime']==[('overtime','2026-10-01'),('overtime','2026-10-07')]
     assert ot_records[0]['purpose']=='수정한 새 근무목적' and ot_records[1]['purpose']=='직접  입력한 시간외 목적'
     assert len([p for p in posts if p[0]=='overtime-update'])==1
     missing=dict(overtime.application_row(date(2026,10,6),{'checkin':'08:35','checkout':'19:15'}),purpose='이전 확인 실패지만 실제 미등록')
     statuses[missing['date']]={'status':'uncertain'}
     added=overtime.submit_rows(page,[missing],rows+[missing],statuses,lambda values:None)
     assert added[0]['status']=='신청 확인 완료' and len(ot_records)==3,added
     assert page.existing(rows[0]) and not page.existing(rows[0],True)
     ignore_ot_update=True
     rejected=overtime.submit_rows(page,[dict(rows[0],purpose='저장되지 않는 목적'),rows[1]],rows,statuses,lambda values:None)
     assert len(rejected)==1 and rejected[0]['status'].startswith('확인 필요:') and statuses[rows[0]['date']]['status']=='uncertain',rejected
     assert len(ot_records)==3 and ot_records[0]['purpose']=='수정한 새 근무목적'
    finally:driver.quit()
   print('JOURNAL_BROWSER_OK: trip workflow + work-log direct form + user-supplied direct URL without menu links; overtime purpose absent from list / success page without history / observed-page refresh / two sequential POSTs / existing date purpose updated once / uncertain missing date added / detail purpose verified / no duplicate dates; no target-site requests')
finally:server.shutdown();server.server_close();thread.join()
