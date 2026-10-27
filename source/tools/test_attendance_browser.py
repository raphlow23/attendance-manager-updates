"""Real headless Chrome test against a local fixture, never the target site."""
import subprocess
import sys
import tempfile
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import date, datetime
from unittest.mock import patch
from selenium.webdriver.remote.webelement import WebElement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from attendance_recovery import AttendancePage, parse_time

HTML = '''<!doctype html><meta charset="utf-8"><h2>10월 근태현황</h2>
<table><tr><th>근무일</th><th>출근시간</th><th>퇴근시간</th><th>비고</th><th>수정</th></tr>
<tr><td>23일</td><td id="ci">08 : 50</td><td id="co"> : </td><td>원래 비고</td>
<td><button onclick="document.getElementById('editor').hidden=false">수정</button></td></tr></table>
<section id="editor" hidden><h3>근태 기록 수정하기</h3><table>
<tr><td>출근시간</td><td>퇴근시간</td><td>비고</td><td>수정</td></tr>
<tr><td><input id="ih" value="08"><input id="im" value="50"></td>
<td><input id="oh" value=""><input id="om" value=""></td>
<td><input value="원래 비고"></td><td><button onclick="save()">수정완료</button></td></tr></table></section>
<script>function save(){for(const [dest,h,m] of [['ci','ih','im'],['co','oh','om']]){
document.getElementById(dest).textContent=document.getElementById(h).value+' : '+document.getElementById(m).value;}
document.getElementById('editor').hidden=true;alert('수정완료');}</script>'''

options = webdriver.ChromeOptions()
for value in ('--headless=new', '--window-size=1440,1000', '--disable-background-networking', '--no-first-run', '--disable-default-apps'):
    options.add_argument(value)
driver_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'app/driver/chromedriver.exe'
service = Service(str(driver_path), popen_kw={'creation_flags': subprocess.CREATE_NO_WINDOW})
with tempfile.TemporaryDirectory(prefix='workday-local-dom-') as folder:
    fixture = Path(folder) / 'attendance.html'
    fixture.write_text(HTML, encoding='utf-8')
    driver = webdriver.Chrome(options=options, service=service)
    try:
        driver.get(fixture.as_uri())
        page = AttendancePage(driver, date(2026, 10, 27))
        day = date(2026, 10, 23)
        before = page.record(day)
        assert page.correct(day, {'checkin': datetime(2026,10,23,9), 'checkout': datetime(2026,10,23,18)}, before)
        after = page.record(day)
        assert after['checkin'] == '09 : 00' and after['checkout'] == '18 : 00'
        assert after['note'] == '원래 비고'
        print('ATTENDANCE_BROWSER_OK: local td-header form; click/edit/save/alert/verify; no target site access')
        source=(ROOT/'tests/fixtures/attendance_edit_form.html').read_text(encoding='utf-8')
        script='''<script>const form=document.querySelector('form');
        for(const input of form.querySelectorAll('input:not([name="huuga"])')){
          input.addEventListener('blur',()=>{if(input.value.trim())input.value=' '+Number(input.value)+' ';});
        }
        form.addEventListener('submit',event=>{event.preventDefault();
          const values=new FormData(form),cells=document.querySelector('table tbody tr').cells;
          cells[1].textContent=values.get('culgun')+':'+values.get('culguna');
          cells[2].textContent=values.get('tehgun')+':'+values.get('tehguna');
          form.remove();alert('수정완료');});</script>'''
        pages={'/sappd_g4.php':re.sub(r'<form\b[\s\S]*?</form>','',source),'/sappd_g4_edit.php':source+script}
        class Handler(BaseHTTPRequestHandler):
            posts=0
            def log_message(self,*args):pass
            def do_GET(self):
                content=pages.get(self.path.split('?')[0])
                self.send_response(200 if content else 404);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
                self.wfile.write((content or '').encode('utf-8'))
            def do_POST(self):
                Handler.posts+=1;self.send_response(500);self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            driver.get(f'http://127.0.0.1:{server.server_port}/sappd_g4.php?m=10')
            page=AttendancePage(driver,date(2026,10,27));day=date(2026,10,7)
            original_attribute=WebElement.get_attribute
            def initial_attribute(element,name):
                return element.get_dom_attribute(name) if name=='value' else original_attribute(element,name)
            with patch.object(WebElement,'send_keys',lambda self,*values:None),patch.object(WebElement,'get_attribute',initial_attribute):
                assert page.correct(day,{'checkin':datetime(2026,10,7,9),'checkout':datetime(2026,10,7,18)},page.record(day))
            after=page.record(day)
            assert parse_time(after['checkin'])==(9,0) and parse_time(after['checkout'])==(18,0)
            assert after['note']=='기존 비고' and Handler.posts==0
            print('NAMED_FORM_BROWSER_OK: real Chrome list/navigation/native value/blur/local submit/verification with no-op keyboard and stale HTML attributes; no target site requests')
        finally:
            server.shutdown();server.server_close();thread.join()
    finally:
        driver.quit()
