"""Real headless Chrome test against a local fixture, never the target site."""
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from attendance_recovery import AttendancePage

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
    finally:
        driver.quit()
