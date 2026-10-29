"""Semantic adapter for the user-supplied business-trip registration screen."""
import re
from datetime import date
from urllib.parse import urlsplit,urlunsplit
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select,WebDriverWait
from selenium.common.exceptions import NoAlertPresentException,UnexpectedAlertPresentException,StaleElementReferenceException,TimeoutException
from attendance_recovery import visible,one,label,input_value
from business_trips import CATEGORY,TRANSPORT,trip_category

# Explicit trip entry URL supplied by the user; do not infer it from menu labels.
TRIP_ENTRY_URL='http://sappd.kr/sappd_g6.php'

def norm(text):return re.sub(r'\s+','',text)


def history_date(text,month):
    """Parse a date cell, using only the already verified monthly view as context."""
    first=date.fromisoformat(month+'-01')
    value=re.sub(r'\s+','',text)
    value=re.sub(r'(?:\([월화수목금토일](?:요일)?\)|[월화수목금토일]요일)$','',value)
    match=re.fullmatch(r'(\d{4})[-./년](\d{1,2})[-./월](\d{1,2})(?:일|\.)?',value)
    if match:return date(*map(int,match.groups()))
    if re.fullmatch(r'\d{8}',value):return date(int(value[:4]),int(value[4:6]),int(value[6:]))
    match=re.fullmatch(r'(\d{1,2})[-./월](\d{1,2})(?:일|\.)?',value)
    if match:return date(first.year,*map(int,match.groups()))
    match=re.fullmatch(r'(\d{1,2})일',value)
    if match:return first.replace(day=int(match[1]))
    raise ValueError('지원하지 않는 출장일 표시')

def set_value(driver,element,value):
    driver.execute_script('''const e=arguments[0],v=arguments[1];
    if(e.disabled||e.readOnly)throw new Error('Field is not editable');
    const proto=e instanceof HTMLSelectElement?HTMLSelectElement.prototype:e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
    if(e instanceof HTMLSelectElement&&!Array.from(e.options).some(o=>o.value===v))throw new Error('Option not found');
    Object.getOwnPropertyDescriptor(proto,'value').set.call(e,v);
    e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));''',element,str(value))
    if input_value(element)!=str(value):raise RuntimeError('출장 입력값을 확인하지 못했습니다.')

def select_text(driver,element,text):
    option=one([o for o in Select(element).options if norm(o.text)==norm(text)],f'{text} 선택 항목')
    set_value(driver,element,option.get_attribute('value'))

def select_number(driver,element,number):
    matches=[o for o in Select(element).options if re.fullmatch(fr'0*{number}\s*[시분월일]?',o.text.strip())]
    # Edit pages can prepend the saved value before the normal option list.
    # Prefer a matching numeric value; identical duplicate values are equivalent.
    numeric=[o for o in matches if re.fullmatch(r'\d+',o.get_attribute('value') or '') and int(o.get_attribute('value'))==number]
    if numeric:
        exact=[o for o in numeric if o.get_attribute('value')==str(number)]
        option=(exact or numeric)[0]
    else:
        by_value={o.get_attribute('value'):o for o in matches}
        option=one(list(by_value.values()),f'{number} 선택 항목')
    set_value(driver,element,option.get_attribute('value'))
    if not re.fullmatch(fr'0*{number}\s*[시분월일]?',Select(element).first_selected_option.text.strip()):
        raise RuntimeError(f'{number} 선택 후 표시된 시간을 확인하지 못했습니다.')

class TripPage:
    def __init__(self,driver):self.driver=driver;self.wait=WebDriverWait(driver,20)
    def activate(self,control):
        href=control.get_attribute('href')
        if href and urlsplit(href).scheme in ('http','https') and not href.endswith('#'):
            source=urlsplit(self.driver.current_url);target=urlsplit(href)
            if (source.scheme,source.netloc)!=(target.scheme,target.netloc):raise RuntimeError('다른 사이트 링크는 열지 않습니다.')
            self.driver.get(href)
        else:self.driver.execute_script('arguments[0].click()',control)
    def open(self):
        source=urlsplit(self.driver.current_url);target=urlsplit(TRIP_ENTRY_URL)
        if source.hostname==target.hostname and source.port==target.port and source.scheme in ('http','https'):
            # Keep the authenticated origin (including HTTPS when available).
            entry=urlunsplit((source.scheme,source.netloc,target.path,target.query,''))
            self.driver.get(entry)
            current=urlsplit(self.driver.current_url)
            if (current.scheme,current.netloc)!=(source.scheme,source.netloc):raise RuntimeError('출장 입력 주소에서 다른 사이트로 이동하여 중단했습니다.')
            try:self.wait.until(lambda _:self.form())
            except TimeoutException as error:raise RuntimeError('출장 입력 주소(sappd_g6.php)를 열었지만 입력 폼을 확인하지 못했습니다. 로그인 상태·접근 권한을 확인하세요.') from error
            return
        self.activate(one(self.driver.find_elements(By.LINK_TEXT,'근무일지'),'근무일지 메뉴'))
        # The work-log tab may land directly on the trip form. Its active
        # tab can be a non-clickable label, so no second menu is required.
        def destination(_):
            if self.form():return ('form',None)
            control=self.entry_control()
            return ('menu',control) if control else False
        try:kind,control=self.wait.until(destination)
        except TimeoutException as error:raise RuntimeError('근무일지에서 출장 입력 화면이나 출장일지 바로가기를 찾지 못했습니다.') from error
        if kind=='form':return
        self.activate(control)
        self.wait.until(lambda _:self.form())
    def entry_control(self):
        selector="a, button, input[type='button'], input[type='submit']"
        controls=visible(self.driver.find_elements(By.CSS_SELECTOR,selector))
        matches=[c for c in controls if norm(label(c))=='출장일지']
        if not matches:
            titles=visible(self.driver.find_elements(By.XPATH,"//*[translate(normalize-space(.), ' \t\r\n', '')='출장일지']"))
            for title in titles:
                parent=title
                for _ in range(5):
                    parent=parent.find_element(By.XPATH,'..')
                    links=[c for c in visible(parent.find_elements(By.CSS_SELECTOR,selector)) if norm(label(c))=='바로가기']
                    if len(links)==1:
                        if links[0] not in matches:matches.append(links[0])
                        break
                    if len(links)>1:break
        return one(matches,'출장일지 메뉴') if matches else False
    def text_fields(self,form,keyword):
        return self.driver.execute_script('''const root=arguments[0],word=arguments[1],clean=s=>(s||'').replace(/\\s|:/g,'');
        const fields=Array.from(root.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),textarea')).filter(e=>e.getClientRects().length);
        const matches=fields.filter(e=>{
          if(clean(e.placeholder).includes(word)||clean(e.getAttribute('aria-label')).includes(word))return true;
          if(Array.from(e.labels||[]).some(l=>clean(l.textContent).includes(word)))return true;
          let p=e.parentElement;
          for(let i=0;p&&root.contains(p)&&i<4;i++,p=p.parentElement){
            if(p.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),textarea').length!==1)break;
            if(clean(p.textContent).includes(word))return true;
          }
          return false;
        });
        // Edit forms use a header row above a single row of inputs, often
        // without placeholders or label elements. Match the same table column.
        for(const table of root.querySelectorAll('table')){
          const header=Array.from(table.rows).find(r=>Array.from(r.cells).some(c=>c.tagName==='TH'));
          if(!header)continue;
          let column=0;
          for(const head of header.cells){
            const span=head.colSpan||1;
            if(span===1&&clean(head.textContent)===word){
              for(const row of table.rows){
                if(row===header)continue;
                let at=0;
                for(const cell of row.cells){
                  if(at===column&&(cell.colSpan||1)===1){
                    const candidates=fields.filter(e=>cell.contains(e));
                    if(candidates.length===1)matches.push(candidates[0]);
                  }
                  at+=cell.colSpan||1;
                }
              }
            }
            column+=span;
          }
        }
        return Array.from(new Set(matches));''',form,keyword)
    def form(self):
        forms=[f for f in visible(self.driver.find_elements(By.TAG_NAME,'form')) if self.text_fields(f,'출장장소') and self.text_fields(f,'출장목적')]
        if len(forms)>1:
            editing=[f for f in forms if any(norm(label(b)) in ('수정','수정하기','출장수정','출장수정하기','출장일지수정','수정완료') for b in visible(f.find_elements(By.CSS_SELECTOR,'button, input[type=submit]')))]
            if len(editing)==1:return editing[0]
        return one(forms,'출장 등록·수정 폼') if forms else False
    def fields(self):
        form=self.form()
        if not form:raise RuntimeError('출장 등록 폼을 찾지 못했습니다.')
        selects=visible(form.find_elements(By.TAG_NAME,'select'))
        texts=visible(form.find_elements(By.CSS_SELECTOR,"input:not([type='hidden']):not([type='submit']):not([type='button']), textarea"))
        place=one(self.text_fields(form,'출장장소'),'출장장소 입력칸')
        purpose=one(self.text_fields(form,'출장목적'),'출장목적 입력칸')
        dates=[i for i in texts if i not in (place,purpose)]
        if len(selects)!=6 or len(dates)!=3:raise RuntimeError('출장 등록 날짜·시간 입력칸 구조가 제공된 화면과 다릅니다. HTML 확인이 필요합니다.')
        submit=one([b for b in form.find_elements(By.CSS_SELECTOR,'button, input') if norm(label(b)) in ('확인','출장등록','수정','수정하기','출장수정','출장수정하기','출장일지수정','수정완료')],'출장 확인 버튼')
        return form,selects,dates,place,purpose,submit
    def check_options(self):
        _,selects,_,_,_,_=self.fields()
        if len([o for o in Select(selects[0]).options if norm(o.text)==CATEGORY])!=1:raise RuntimeError('출장 구분의 센터 항목을 확인하세요.')
        if len([o for o in Select(selects[1]).options if norm(o.text)==TRANSPORT])!=1:raise RuntimeError('이동수단의 대중교통 항목을 확인하세요.')
    def month(self,month):
        first=date.fromisoformat(month+'-01')
        if first.year!=date.today().year:raise ValueError('출장일지는 연도 선택이 확인된 당해 연도만 지원합니다.')
        body=self.driver.find_element(By.TAG_NAME,'body').text
        if re.search(fr'(?<!\d){first.month}\s*월\s*출장일지',body):return
        candidates=[]
        for select in visible(self.driver.find_elements(By.TAG_NAME,'select')):
            if sum(bool(re.fullmatch(r'\d{1,2}\s*월',o.text.strip())) for o in Select(select).options)>=2:candidates.append(select)
        select=one(candidates,'출장 조회 월');select_number(self.driver,select,first.month)
        form=select.find_element(By.XPATH,'ancestor::form[1]')
        control=one([c for c in form.find_elements(By.CSS_SELECTOR,'button, input') if label(c) in ('조회','확인')],'출장 월 조회 버튼')
        self.driver.execute_script('arguments[0].click()',control)
        self.wait.until(lambda _:re.search(fr'(?<!\d){first.month}\s*월\s*출장일지',self.driver.find_element(By.TAG_NAME,'body').text))
    def existing(self,month,include_elements=False):
        self.month(month);result=[];tables=0
        for table in visible(self.driver.find_elements(By.TAG_NAME,'table')):
            heads=[norm(e.text) for e in table.find_elements(By.XPATH,'.//tr[th][1]/th')]
            if heads[:8]!=['구분','출장일','출장장소','출장목적','이동수단','출발시간','복귀시간','출장시간']:continue
            tables+=1
            for row in table.find_elements(By.XPATH,'.//tr[td]'):
                cells=row.find_elements(By.XPATH,'./td')
                if len(cells)<8:continue
                text=cells[1].text
                try:day=history_date(text,month)
                except ValueError as error:
                    shown=re.sub(r'\s+',' ',text).strip()[:80] or '(빈 칸)'
                    raise RuntimeError(f'기존 출장 날짜 표시를 해석하지 못했습니다. 조회 월 {month} / 출장일 칸: {shown!r}. 중복 확인 전에는 추가 등록하지 않습니다.') from error
                if str(day)[:7]!=month:continue
                times=[]
                for cell in cells[5:7]:
                    clock=re.fullmatch(r'\s*(\d{1,2})\s*[:시]\s*(\d{1,2})\s*분?\s*',cell.text)
                    if not clock:raise RuntimeError('기존 출장 시각 표시를 해석하지 못했습니다.')
                    hour,minute=map(int,clock.groups())
                    if hour>23 or minute>59:raise RuntimeError('기존 출장 시각이 유효한 시간 범위를 벗어났습니다.')
                    times.append(f'{hour:02}:{minute:02}')
                result.append(dict(date=str(day),category=cells[0].text.strip(),location=cells[2].text.strip(),purpose=cells[3].text.strip(),transport=cells[4].text.strip(),start=times[0],end=times[1]))
                if include_elements:result[-1]['element']=row
        if tables!=1:raise RuntimeError('출장 내역 표를 하나로 확인하지 못했습니다. 중복 확인 전에는 등록하지 않습니다.')
        return result
    def delete(self,expected,month):
        self.driver._workday_write_submitted=False
        self.phase='삭제할 기등록 출장 확인'
        matches=[r for r in self.existing(month,True) if r['date']==expected['date']]
        element=one([r['element'] for r in matches],'삭제할 기존 출장')
        row=matches[0]
        if {k:v for k,v in row.items() if k!='element'}!=expected:
            raise RuntimeError('삭제 대상의 내용이 바뀌었습니다. 다시 조회하세요.')
        controls=visible(element.find_elements(By.CSS_SELECTOR,"a,button,input[type='button'],input[type='submit']"))
        button=one([c for c in controls if norm(label(c)) in ('삭제','삭제하기','출장삭제','출장삭제하기')],'해당 날짜 출장 삭제 버튼')
        href=button.get_attribute('href') or ''
        source=urlsplit(self.driver.current_url);target=urlsplit(href)
        if target.scheme in ('http','https') and (source.scheme,source.netloc)!=(target.scheme,target.netloc):
            raise RuntimeError('다른 사이트의 삭제 버튼은 실행하지 않습니다.')
        guard=getattr(self.driver,'_workday_before_write',None)
        if callable(guard):guard()
        self.phase='해당 날짜 삭제 버튼 실행'
        self.driver._workday_write_submitted=True
        try:self.driver.execute_script('arguments[0].click()',button)
        except UnexpectedAlertPresentException:pass
        self.phase='사이트 출장 삭제 결과 확인'
        def absent(_):
            try:self.driver.switch_to.alert.accept()
            except NoAlertPresentException:pass
            check=getattr(self.driver,'_workday_check_response',None)
            if callable(check):check()
            try:return not any(r['date']==expected['date'] for r in self.existing(month))
            except (StaleElementReferenceException,UnexpectedAlertPresentException):return False
        self.wait.until(absent)
    def submit(self,row,month,update=False):
        self.driver._workday_write_submitted=False
        self.phase='기존 출장 행 확인' if update else '신규 출장 입력 폼 확인'
        if update:
            matches=[r for r in self.existing(month,True) if r['date']==row['date']]
            record=one([r['element'] for r in matches],'수정할 기존 출장')
            original=matches[0]
            controls=visible(record.find_elements(By.CSS_SELECTOR,"a, button, input[type='button'], input[type='submit']"))
            edit=one([c for c in controls if norm(label(c)) in ('수정','수정하기','출장수정','출장수정하기')],'기존 출장 수정 버튼')
            self.phase='기존 출장 수정 입력 화면 열기'
            self.activate(edit)
            try:
                # The page may retain the new-entry form above the history.
                # Wait for the selected record, not merely any visible form.
                self.wait.until(lambda _:self.edit_matches(original))
            except TimeoutException as error:
                raise RuntimeError('기존 출장의 수정 버튼을 눌렀지만 해당 날짜의 수정 입력 화면을 확인하지 못했습니다. 신규 등록은 하지 않았습니다. 수정 화면 HTML 확인이 필요합니다.') from error
        self.phase='출장 입력값·저장 대상 확인'
        form,selects,dates,place,purpose,button=self.fields()
        action=form.get_attribute('action');source=urlsplit(self.driver.current_url);target=urlsplit(action)
        if (source.scheme,source.netloc)!=(target.scheme,target.netloc):raise RuntimeError('출장 저장 사이트가 다릅니다.')
        day=date.fromisoformat(row['date'])
        if update:
            if any(' '.join(input_value(field).split())!=' '.join(original[key].split()) for field,key in ((place,'location'),(purpose,'purpose'))):raise RuntimeError('수정 화면의 기존 장소·목적이 선택 내역과 다릅니다. 저장하지 않았습니다.')
            if [int(input_value(f)) for f in dates]!=[day.year,day.month,day.day]:raise RuntimeError('수정 화면 출장 날짜가 다릅니다.')
            if norm(Select(selects[0]).first_selected_option.text)!=norm(original['category']) or Select(selects[1]).first_selected_option.text.strip()!=TRANSPORT:raise RuntimeError('기존 출장 구분·이동수단을 확인하세요.')
            for field,value in zip(selects[2:],(int(original['start'][:2]),int(original['start'][3:]),int(original['end'][:2]),int(original['end'][3:]))):
                if not re.fullmatch(fr'0*{value}\s*[시분]?',Select(field).first_selected_option.text.strip()):raise RuntimeError('수정 화면 출장 시간이 다릅니다.')
        else:
            select_text(self.driver,selects[1],TRANSPORT)
            for element,value in zip(dates,(day.year,day.month,day.day)):set_value(self.driver,element,value)
        select_text(self.driver,selects[0],trip_category(row.get('category')))
        for element,value in zip(selects[2:],(int(row['start'][:2]),int(row['start'][3:]),int(row['end'][:2]),int(row['end'][3:]))):select_number(self.driver,element,value)
        set_value(self.driver,place,row['location']);set_value(self.driver,purpose,row['purpose'])
        if form.get_attribute('action')!=action:raise RuntimeError('출장 저장 대상이 바뀌었습니다.')
        guard=getattr(self.driver,'_workday_before_write',None)
        if callable(guard):guard()
        self.driver._workday_expected_save_url=action;self.driver._workday_post_seen=False;self.driver._workday_save_response_status=None
        self.phase='출장 저장 버튼 실행'
        self.driver._workday_write_submitted=True
        try:
            accepted=self.driver.execute_script('''const b=arguments[0],f=arguments[1];if(b.disabled||b.form!==f||!f.checkValidity())return false;b.click();return true;''',button,form)
            if accepted is False:
                self.driver._workday_write_submitted=False;raise RuntimeError('출장 등록 폼 검증에서 제출을 거절했습니다.')
        except UnexpectedAlertPresentException:pass
        self.phase='사이트 저장 결과 확인'
        def confirmed(_):
            try:self.driver.switch_to.alert.accept()
            except NoAlertPresentException:pass
            check=getattr(self.driver,'_workday_check_response',None)
            if callable(check):check()
            try:
                records=self.existing(month)
                return sum(all(' '.join(item[k].split())==' '.join(row[k].split()) for k in ('date','location','purpose','start','end')) and norm(item['category'])==trip_category(row.get('category')) and norm(item['transport'])==TRANSPORT for item in records)==1
            except StaleElementReferenceException:return False
        self.wait.until(confirmed)

    def edit_matches(self,original):
        try:
            form,selects,dates,place,purpose,button=self.fields()
            return (norm(label(button))!='확인' and
                    [int(input_value(f)) for f in dates]==list(map(int,original['date'].split('-'))) and
                    all(' '.join(input_value(f).split())==' '.join(original[k].split()) for f,k in ((place,'location'),(purpose,'purpose'))))
        except (StaleElementReferenceException,RuntimeError,ValueError):return False
