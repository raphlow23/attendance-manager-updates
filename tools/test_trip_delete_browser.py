"""Local-only deletion dialogs and stale history verification regression."""
import sys,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'.test-libs')]
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from trip_site import TripPage
from subprocess import CREATE_NO_WINDOW

mode='native';present=True;deletes=0
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        global present,deletes
        if urlsplit(self.path).path=='/delete':
            deletes+=1
            if mode!='refused':present=False
            if mode in ('stale','html'):
                self.send_response(200);self.end_headers();self.wfile.write(b'OK');return
            self.send_response(303);self.send_header('Location','/list');self.end_headers();return
        heads=''.join('<th>'+s+'</th>' for s in ('구분','출장일','출장장소','출장목적','이동수단','출발시간','복귀시간','출장시간','삭제'))
        row='<tr><td>센터</td><td>10-23</td><td>장소</td><td>목적</td><td>대중교통</td><td>13:00</td><td>17:00</td><td>4시간</td><td>'
        if mode=='html':
            control='<button onclick="document.querySelector(\'dialog\').showModal()">삭제</button>'
        elif mode=='stale':
            control='<a href="/delete" onclick="if(confirm(\'삭제할까요?\'))fetch(this.href);return false">삭제</a>'
        else:control='<a href="/delete" onclick="return confirm(\'삭제할까요?\')">삭제</a>'
        body='<h2>10월 출장일지</h2><table><tr>'+heads+'</tr>'+(row+control+'</td></tr>' if present else '')+'</table>'
        body+='<dialog><p>삭제할까요?</p><button onclick="fetch(\'/delete\').then(()=>location.href=\'/list\')">확인</button><button onclick="this.parentNode.close()">취소</button></dialog>'
        self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.end_headers();self.wfile.write(body.encode())

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
options=webdriver.ChromeOptions();options.add_argument('--headless=new');options.add_argument('--no-first-run');options.set_capability('unhandledPromptBehavior','ignore')
driver=webdriver.Chrome(options=options,service=Service(str(ROOT/'app/driver/chromedriver.exe'),popen_kw={'creation_flags':CREATE_NO_WINDOW}))
try:
    for mode in ('native','html','stale','refused'):
        present=True;deletes=0;driver.get(f'http://127.0.0.1:{server.server_port}/list')
        page=TripPage(driver);page.wait=WebDriverWait(driver,3,poll_frequency=.2)
        page.form=lambda:bool(driver.find_elements(By.TAG_NAME,'table'))
        expected=page.existing('2026-10')[0]
        try:
            page.delete(expected,'2026-10')
            assert mode!='refused' and not present,mode
        except RuntimeError as error:
            assert mode=='refused' and '기록이 남아' in str(error),(mode,str(error))
        assert deletes==1,(mode,deletes)
        print('DELETE_BROWSER_OK: '+mode,flush=True)
finally:
    driver.quit();server.shutdown();server.server_close();thread.join()
