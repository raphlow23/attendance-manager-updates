"""Real Chrome + local HTTP POST/redirect/alert test, two dates in sequence."""
import sys,json,threading,tempfile,subprocess
from pathlib import Path
from datetime import date
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from lxml import html
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app')]
import main as app
from attendance_recovery import AttendancePage,parse_time
from monthly_reconcile import apply_plan
from site_access import check_page
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webelement import WebElement

records={'10001':dict(day=7,ci='08:50',co='19:20',note='기존 비고'),
         '10002':dict(day=13,ci='08:35',co=':',note='보존할 비고')}
events=[]
source=(ROOT/'tests/fixtures/attendance_edit_form.html').read_text(encoding='utf-8')

def render(edit=None):
    doc=html.fromstring(source)
    form=doc.xpath('//form')[0];form.getparent().remove(form)
    body=doc.find('body')
    if body is None:body=doc
    tbody=doc.xpath('//table/tbody')[0]
    for row in list(tbody):tbody.remove(row)
    for key,item in records.items():
        row=html.Element('tr')
        for text in (str(item['day'])+'일',item['ci'],item['co'],item['note']):
            cell=html.Element('td');cell.text=text;row.append(cell)
        cell=html.Element('td');link=html.Element('a',href=f'sappd_g4_edit.php?no={key}&m=10');link.text='수정';cell.append(link);row.append(cell);tbody.append(row)
    if edit:
        item=records[edit];form.set('action',f'sappd_g4_edit_pro.php?no={edit}&m=10')
        ci=item['ci'].split(':');co=item['co'].split(':')
        values=dict(zip(('culgun','culguna','tehgun','tehguna','huuga'),ci+co+[item['note']]))
        for element in form.xpath('.//input'):element.set('value',values[element.get('name')])
        body.append(form)
    return html.tostring(doc,encoding='utf-8')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        request=urlsplit(self.path);query=parse_qs(request.query)
        if request.path.endswith('/sappd_g4.php'):
            events.append(('GET_LIST',None));content=render()
        elif request.path.endswith('/sappd_g4_edit.php'):
            content=render(query['no'][0])
        else:self.send_response(404);self.end_headers();return
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(content)
    def do_POST(self):
        request=urlsplit(self.path);query=parse_qs(request.query)
        assert request.path.endswith('/sappd_g4_edit_pro.php')
        key=query['no'][0];fields=parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(),keep_blank_values=True)
        records[key].update(ci=f"{int(fields['culgun'][0]):02}:{int(fields['culguna'][0]):02}",
                            co=f"{int(fields['tehgun'][0]):02}:{int(fields['tehguna'][0]):02}",note=fields['huuga'][0])
        events.append(('POST',key))
        if key=='10001':
            self.send_response(303);self.send_header('Location','/sappd_g4.php?m=10');self.end_headers()
        else:
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
            self.wfile.write(b"<script>alert('saved');location.href='/sappd_g4.php?m=10';</script>")

server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
options=webdriver.ChromeOptions()
for arg in ('--headless=new','--window-size=1440,1000','--disable-background-networking','--no-first-run'):options.add_argument(arg)
options.set_capability('goog:loggingPrefs',{'performance':'ALL'})
driver=None
try:
    with tempfile.TemporaryDirectory(prefix='workday-real-post-') as folder:
        with patch.object(app,'DATA_DIR',folder),patch.object(app,'STATE_FILE',str(Path(folder)/'state.json')),patch.object(app,'LOG_FILE',str(Path(folder)/'events.log')),patch.object(app,'SITE_URL',base):
            driver=webdriver.Chrome(options=options,service=Service(str(ROOT/'app/driver/chromedriver.exe'),popen_kw={'creation_flags':subprocess.CREATE_NO_WINDOW}))
            driver._workday_check_response=lambda:check_page(app,driver)
            driver.get(base+'/sappd_g4.php?m=10');page=AttendancePage(driver,date(2026,10,27))
            changes=[]
            for day,after in ((date(2026,10,7),dict(checkin='09:00',checkout='18:00')),(date(2026,10,13),dict(checkout='19:10'))):
                record=page.record(day);changes.append(dict(date=str(day),before={k:record[k] for k in ('checkin','checkout','note')},after=after,reason='local sequential test'))
            original=WebElement.get_attribute
            def initial_value(element,name):return element.get_dom_attribute(name) if name=='value' else original(element,name)
            with patch.object(WebElement,'click',lambda self:None),patch.object(WebElement,'send_keys',lambda self,*values:None),patch.object(WebElement,'get_attribute',initial_value):
                completed=apply_plan(app,page,dict(changes=changes),'2026-10')
            assert len(completed)==2 and [item[1] for item in events if item[0]=='POST']==['10001','10002']
            first=events.index(('POST','10001'));second=events.index(('POST','10002'))
            assert ('GET_LIST',None) in events[first+1:second]
            assert records['10001']['ci']=='09:00' and records['10001']['co']=='18:00'
            assert records['10002']['ci']=='08:35' and records['10002']['co']=='19:10'
            assert records['10001']['note']=='기존 비고' and records['10002']['note']=='보존할 비고'
            assert driver._workday_post_seen is True
            state=json.loads(Path(folder,'state.json').read_text(encoding='utf-8'))
            assert all(item['status']=='verified' for item in state['monthly_reconcile_journal'])
            print('DAILY_POST_BROWSER_OK: date1 POST once -> fresh list verification -> date2 POST once; 303 and JS alert redirects; real Chrome with native WebDriver clicks/keys disabled; no target-site requests')
finally:
    if driver is not None:driver.quit()
    server.shutdown();server.server_close();thread.join()
