"""Monthly, user-confirmed overtime applications from actual attendance rows."""
import calendar
import re
from datetime import date
from urllib.parse import urlsplit

from selenium.common.exceptions import NoAlertPresentException, StaleElementReferenceException, TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from attendance_recovery import AttendancePage, label, one, parse_time, visible,activate_control,input_value
from trip_site import set_value,select_text

WEEKDAYS = '월화수목금토일'


def application_row(day, record):
    checkout = parse_time(record['checkout'])
    if not parse_time(record['checkin']) or not checkout or checkout[0] not in (19, 20):
        return None
    return {'date': str(day), 'weekday': WEEKDAYS[day.weekday()],
            'checkout': f'{checkout[0]:02d}:{checkout[1]:02d}',
            'start': '18:00', 'end': f'{checkout[0]:02d}:00', 'purpose': ''}


def collect_month(driver, month, today, is_workday):
    first = date.fromisoformat(month + '-01')
    if first > today:
        raise ValueError('미래 월은 조회할 수 없습니다.')
    page = AttendancePage(driver, today)
    page.open()
    rows = []
    for n in range(1, calendar.monthrange(first.year, first.month)[1] + 1):
        day = date(first.year, first.month, n)
        if day > today or not is_workday(day):
            continue
        row = application_row(day, page.record(day))
        if row:
            rows.append(row)
    return rows


def select_number(element, number,driver=None):
    options = Select(element).options
    matches = [o for o in options if re.fullmatch(fr'0*{number}\s*[월일시분]?', o.text.strip())]
    if len(matches) != 1:
        raise RuntimeError(f'선택값 {number}을 확인하지 못했습니다.')
    if driver is not None:set_value(driver,element,matches[0].get_attribute('value'))
    else:Select(element).select_by_value(matches[0].get_attribute('value'))


class OvertimePage:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)

    def open(self):
        activate_control(self.driver,one(self.driver.find_elements(By.LINK_TEXT, '근무일지'), '근무일지 메뉴'))
        if '시간외근무신청서' in re.sub(r'\s+','',self.driver.find_element(By.TAG_NAME,'body').text):
            self.page_url=self.driver.current_url;return
        try:
            control = self.wait.until(lambda _: self.entry_control())
        except TimeoutException as error:
            raise RuntimeError('근무일지에서 시간외근무 신청 바로가기를 찾지 못했습니다. 사이트 메뉴와 접근 권한을 확인하세요.') from error
        activate_control(self.driver,control)
        self.wait.until(lambda d: '시간외근무신청서' in re.sub(r'\s+', '', d.find_element(By.TAG_NAME, 'body').text))
        self.page_url=self.driver.current_url

    def entry_control(self):
        controls = visible(self.driver.find_elements(By.CSS_SELECTOR, "a, button, input[type='button'], input[type='submit']"))
        direct = [c for c in controls if '시간외근무신청' in re.sub(r'\s+', '', label(c))]
        if direct:
            return one(direct, '시간외근무 신청 메뉴')
        # Titles are often div/strong/span nodes and the link is a sibling in
        # a nested card. Walk only nearby parents; never guess a destination URL.
        titles = visible(self.driver.find_elements(By.XPATH, "//*[translate(normalize-space(.), ' \t\r\n', '')='시간외근무신청']"))
        matches = []
        for title in titles:
            parent = title
            for _ in range(5):
                parent = parent.find_element(By.XPATH, '..')
                choices = visible(parent.find_elements(By.CSS_SELECTOR, "a, button, input[type='button'], input[type='submit']"))
                choices = [c for c in choices if re.sub(r'\s+', '', label(c)) == '바로가기']
                if len(choices) == 1:
                    if choices[0] not in matches:
                        matches.append(choices[0])
                    break
                if len(choices) > 1:
                    break
        return one(matches, '시간외근무 신청 바로가기') if matches else False

    def purpose_fields(self,form):
        return visible(form.find_elements(By.XPATH,".//input[contains(@placeholder,'근무목적')] | .//tr[./td[string-length(normalize-space(.))<15 and contains(normalize-space(.),'근무목적')] or ./th[contains(normalize-space(.),'근무목적')]]//input[not(@type='hidden') and not(@type='submit') and not(@type='button')]"))

    def application_form(self):
        forms=[f for f in visible(self.driver.find_elements(By.TAG_NAME,'form')) if self.purpose_fields(f)]
        return one(forms,'시간외근무 신청·수정 화면') if forms else False

    def history(self,required=True):
        """Read only direct date/time cells in a recognizable application table."""
        tables=[];records=[]
        for table in visible(self.driver.find_elements(By.TAG_NAME,'table')):
            headings=' '.join(h.text for h in table.find_elements(By.TAG_NAME,'th'))
            if not re.search(r'근무.*(?:일|날짜)|근무일자|신청일|날짜',headings) or '시간' not in headings:continue
            tables.append(table)
            for record in table.find_elements(By.XPATH,'.//tr[td]'):
                cells=record.find_elements(By.XPATH,'./td')
                if any(c.find_elements(By.TAG_NAME,'table') for c in cells):continue
                dates=[];slots=[]
                for cell in cells:
                    text=cell.text.strip()
                    d=re.fullmatch(r'(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*일?\s*(?:\([월화수목금토일](?:요일)?\))?',text)
                    if d:dates.append(str(date(*map(int,d.groups()))))
                    t=re.fullmatch(r'(\d{1,2})\s*[:시]\s*(\d{2})\s*분?\s*[~～–—-]\s*(\d{1,2})\s*[:시]\s*(\d{2})\s*분?\s*(?:\([^)]*\))?',text)
                    if t:
                        sh,sm,eh,em=map(int,t.groups())
                        if sh<24 and eh<24 and sm<60 and em<60:slots.append((f'{sh:02}:{sm:02}',f'{eh:02}:{em:02}'))
                if len(dates)==1 and len(slots)!=1:raise RuntimeError(f'{dates[0]}: 기존 신청 시간 표시를 확인하지 못했습니다. 추가하지 않습니다.')
                if len(dates)==1 and len(slots)==1:records.append(dict(date=dates[0],start=slots[0][0],end=slots[0][1],element=record))
        if not tables and not required:return []
        if len(tables)!=1:raise RuntimeError('시간외근무 신청 내역 표를 하나로 확인하지 못했습니다. 중복 확인 전에는 저장하지 않습니다.')
        return records

    def existing(self,row,verify_details=False):
        matches=[r for r in self.history(False) if all(r[k]==row[k] for k in ('date','start','end'))]
        if verify_details:matches=[r for r in matches if ' '.join(row['purpose'].split()) in ' '.join(r['element'].text.split())]
        return bool(matches)

    def select_month(self,month):
        first=date.fromisoformat(month+'-01');candidates=[]
        for field in visible(self.driver.find_elements(By.TAG_NAME,'select')):
            parents=field.find_elements(By.XPATH,'ancestor::form[1]')
            if any(self.purpose_fields(f) for f in parents):continue
            opts=Select(field).options
            if {int(m.group(1)) for o in opts if (m:=re.fullmatch(r'(\d{1,2})\s*월',o.text.strip()))}==set(range(1,13)):candidates.append(field)
        if not candidates:return
        field=one(candidates,'시간외근무 내역 조회 월')
        # A month-only filter cannot safely query a different year.
        if first.year!=date.today().year:raise ValueError('연도 선택이 없는 신청 내역에서는 올해 월만 확인할 수 있습니다.')
        selected=Select(field).first_selected_option.text.strip()
        if re.fullmatch(fr'0*{first.month}\s*월',selected):return
        form=field.find_element(By.XPATH,'ancestor::form[1]')
        select_number(field,first.month,self.driver)
        buttons=[c for c in form.find_elements(By.CSS_SELECTOR,'button, input[type="submit"], input[type="button"]') if label(c).strip()=='조회']
        activate_control(self.driver,one(buttons,'시간외근무 월 조회 버튼'))
        self.wait.until(lambda _: bool(self.history()) or re.search(fr'{first.month}\s*월',self.driver.find_element(By.TAG_NAME,'body').text))
        self.page_url=self.driver.current_url

    def prepare(self,row):
        self.driver._workday_write_submitted=False
        self.select_month(row['date'][:7])
        matches=[r for r in self.history() if r['date']==row['date']]
        if len(matches)>1:raise RuntimeError(f"{row['date']}: 같은 날짜의 신청이 여러 건입니다. 사이트에서 중복 내역을 확인해 주세요.")
        self.editing=bool(matches)
        self.last_operation='update' if matches else 'create'
        if matches:
            controls=visible(matches[0]['element'].find_elements(By.CSS_SELECTOR,'a, button, input[type="button"], input[type="submit"]'))
            edit=one([c for c in controls if re.sub(r'\s+','',label(c)) in ('수정','수정하기','시간외근무수정','시간외근무수정하기')],'해당 날짜 신청 수정 버튼')
            activate_control(self.driver,edit)
        return self.fill(row)

    def fill(self, row):
        day = date.fromisoformat(row['date'])
        # Match the supplied form by its purpose placeholder and inspect only
        # visible controls inside that form. Ambiguity stops before submission.
        form = self.wait.until(lambda _: self.application_form())
        purpose = one(self.purpose_fields(form), '근무목적 입력칸')
        selects = visible(form.find_elements(By.TAG_NAME, 'select'))
        departments = [s for s in selects if any(o.text.strip() == '센터' for o in Select(s).options)]
        department = one(departments, '센터 부서 선택') if departments else None
        times = [s for s in selects if s != department]
        inputs = [i for i in visible(form.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']):not([type='submit']):not([type='button'])")) if i != purpose]
        if department is None:
            fixed=[i for i in inputs if input_value(i).strip()=='센터']
            one(fixed,'수정 화면 센터 부서');inputs=[i for i in inputs if i not in fixed]
        if len(times) != 7 or len(inputs) != 4:
            raise RuntimeError('신청서의 날짜/시간 입력칸 구조를 확인하지 못했습니다.')
        if getattr(self,'editing',False):
            selected_month=Select(times[0]).first_selected_option.text.strip()
            selected_day=Select(times[1]).first_selected_option.text.strip()
            if int(input_value(inputs[0]))!=day.year or not re.fullmatch(fr'0*{day.month}\s*월?',selected_month) or not re.fullmatch(fr'0*{day.day}\s*일?',selected_day):
                raise RuntimeError('수정 화면의 날짜가 선택 날짜와 다릅니다. 저장하지 않았습니다.')
        if department is not None:select_text(self.driver,department,'센터')
        set_value(self.driver,purpose,row['purpose'])
        # Main date year; footer year/month/day. Footer equals working date.
        for field, number in zip(inputs, (day.year, day.year, day.month, day.day)):
            set_value(self.driver,field,str(number))
        for field, number in zip((times[0], times[1], times[3], times[4], times[5], times[6]),
                                 (day.month, day.day, 18, 0, int(row['end'][:2]), 0)):
            select_number(field, number,self.driver)
        weekday = WEEKDAYS[day.weekday()]
        opts = [o for o in Select(times[2]).options if o.text.strip() in (weekday, weekday + '요일')]
        if len(opts) != 1:
            raise RuntimeError('요일 선택값을 확인하지 못했습니다.')
        set_value(self.driver,times[2],opts[0].get_attribute('value'))
        if input_value(purpose) != row['purpose']:
            raise RuntimeError('근무목적 입력 결과가 일치하지 않습니다.')
        if [int(input_value(i)) for i in inputs] != [day.year, day.year, day.month, day.day]:
            raise RuntimeError('신청 날짜 입력 결과가 일치하지 않습니다.')
        expected = [day.month, day.day, None, 18, 0, int(row['end'][:2]), 0]
        for element, number in zip(times, expected):
            text = Select(element).first_selected_option.text.strip()
            if number is not None and not re.fullmatch(fr'0*{number}\s*[월일시분]?', text):
                raise RuntimeError('신청 시간 입력 결과가 일치하지 않습니다.')
        buttons = form.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
        self.form=form;self.action=form.get_attribute('action')
        if not getattr(self,'page_url',None):self.page_url=self.driver.current_url
        wanted=('시간외근무수정','시간외근무수정하기','수정완료') if getattr(self,'editing',False) else ('시간외근무신청',)
        return one([b for b in buttons if re.sub(r'\s+','',label(b)) in wanted], '시간외근무 저장 버튼')

    def submit(self,button):
        self.driver._workday_write_submitted=False
        if self.form.get_attribute('action')!=self.action:raise RuntimeError('시간외근무 신청 대상이 바뀌었습니다.')
        source=urlsplit(self.driver.current_url);target=urlsplit(self.action)
        if (source.scheme,source.netloc)!=(target.scheme,target.netloc):raise RuntimeError('시간외근무 저장 사이트가 다릅니다.')
        guard=getattr(self.driver,'_workday_before_write',None)
        if callable(guard):guard()
        self.driver._workday_expected_save_url=self.action;self.driver._workday_post_seen=False;self.driver._workday_save_response_status=None;self.alert=''
        self.driver._workday_write_submitted=True
        try:
            accepted=self.driver.execute_script('const b=arguments[0],f=arguments[1];if(b.disabled||b.form!==f||!f.checkValidity())return false;b.click();return true;',button,self.form)
            if accepted is False:self.driver._workday_write_submitted=False;raise RuntimeError('신청 폼 검증에서 제출이 거절되었습니다.')
        except UnexpectedAlertPresentException as error:self.alert=str(error.alert_text or '')[:200]

    def verify(self, row):
        refreshed=False
        def found(_):
            nonlocal refreshed
            try:
                alert=self.driver.switch_to.alert;self.alert=str(alert.text)[:200];alert.accept()
            except NoAlertPresentException:
                pass
            check=getattr(self.driver,'_workday_check_response',None)
            if callable(check):check()
            try:
                # Match the saved slot in the list, then read the persisted
                # purpose/date/time from its edit screen without submitting.
                status=getattr(self.driver,'_workday_save_response_status',None)
                if isinstance(status,int) and status>=400:raise RuntimeError(f'신청 저장 응답 HTTP {status}')
                if self.driver.current_url==getattr(self,'page_url',None) and self.existing(row):
                    self.confirm_details(row);return True
                completed=isinstance(status,int) and 200<=status<400
                page_url=getattr(self,'page_url',None)
                if not completed and page_url and self.driver.current_url!=page_url:
                    try:self.form.is_enabled()
                    except StaleElementReferenceException:completed=True
                if completed and page_url and not refreshed:
                    refreshed=True
                    self.driver.get(page_url)
                    if callable(check):check()
                    if self.existing(row):
                        self.confirm_details(row);return True
                return False
            except StaleElementReferenceException:
                return False
        try:self.wait.until(found)
        except TimeoutException as error:raise RuntimeError(f'{row["date"]}: 신청 저장을 확인하지 못했습니다. 사이트 알림: {getattr(self,"alert","") or "없음"}') from error

    def confirm_details(self,row):
        matches=[r for r in self.history() if all(r[k]==row[k] for k in ('date','start','end'))]
        record=one([r['element'] for r in matches],'저장된 신청 내역')
        controls=visible(record.find_elements(By.CSS_SELECTOR,'a, button, input[type="button"], input[type="submit"]'))
        edit=one([c for c in controls if re.sub(r'\s+','',label(c)) in ('수정','수정하기','시간외근무수정','시간외근무수정하기')],'저장 내역 수정 확인 버튼')
        activate_control(self.driver,edit)
        form=self.wait.until(lambda _:self.application_form())
        purpose=one(self.purpose_fields(form),'저장된 근무목적')
        if input_value(purpose)!=row['purpose']:raise RuntimeError('저장된 근무목적이 입력한 내용과 다릅니다. 재제출하지 않았습니다.')
        day=date.fromisoformat(row['date'])
        selects=visible(form.find_elements(By.TAG_NAME,'select'))
        departments=[f for f in selects if any(o.text.strip()=='센터' for o in Select(f).options)]
        times=[f for f in selects if f not in departments]
        inputs=[f for f in visible(form.find_elements(By.CSS_SELECTOR,"input:not([type='hidden']):not([type='submit']):not([type='button'])")) if f!=purpose and input_value(f).strip()!='센터']
        if len(times)!=7 or len(inputs)!=4:raise RuntimeError('저장된 상세 화면 날짜·시간 구조가 다릅니다.')
        if [input_value(f) for f in inputs]!=[str(day.year),str(day.year),str(day.month),str(day.day)]:
            # Site may zero-pad footer values.
            if [int(input_value(f)) for f in inputs]!=[day.year,day.year,day.month,day.day]:raise RuntimeError('저장된 신청 날짜가 다릅니다.')
        for field,number in zip(times,(day.month,day.day,None,18,0,int(row['end'][:2]),0)):
            text=Select(field).first_selected_option.text.strip()
            if number is not None and not re.fullmatch(fr'0*{number}\s*[월일시분]?',text):raise RuntimeError('저장된 신청 시간이 다릅니다.')
        if not departments:
            fixed=[f for f in visible(form.find_elements(By.TAG_NAME,'input')) if input_value(f).strip()=='센터']
            one(fixed,'저장된 센터 부서')
        if departments and Select(one(departments,'저장 부서')).first_selected_option.text.strip()!='센터':raise RuntimeError('저장된 부서가 센터가 아닙니다.')
        self.driver.get(self.page_url)



def submit_rows(page, reviewed, current, statuses, persist):
    """Recheck real checkout and journal before each user-approved submission."""
    live = {r['date']: r for r in current}
    results = []
    seen = set()
    for item in reviewed:
        key = item['date']
        if key in seen:
            raise ValueError('같은 날짜가 중복 선택되었습니다.')
        seen.add(key)
        if not isinstance(item.get('purpose'), str) or not item['purpose'].strip():
            raise ValueError(f'{key}: 근무목적을 입력해 주세요.')
        if len(item['purpose']) > 1000:
            raise ValueError(f'{key}: 근무목적이 너무 깁니다.')
        if key not in live or any(item.get(k) != live[key][k] for k in ('checkout', 'start', 'end')):
            raise ValueError(f'{key}: 실제 퇴근 기록이 변경되었습니다. 다시 조회해 주세요.')
    for item in reviewed:
        key = item['date']
        row = dict(live[key], purpose=item['purpose'].strip())
        try:
            button = page.prepare(row)
            statuses[key] = {'status': 'sending', 'purpose': row['purpose'], 'checkout': row['checkout'], 'end': row['end']}
            persist(statuses)
            was_editing=page.editing
            page.submit(button)
            page.verify(row)
            statuses[key]['status'] = 'success'
            persist(statuses)
            results.append(dict(row, status='수정 확인 완료' if was_editing else '신청 확인 완료'))
        except Exception as error:
            if statuses.get(key, {}).get('status') == 'sending':
                sent=getattr(getattr(page,'driver',None),'_workday_write_submitted',True)
                statuses[key]['status'] = 'not_submitted' if sent is False else 'uncertain'
                persist(statuses)
            results.append(dict(row, status=f'확인 필요: {type(error).__name__}: {str(error)[:200]}'))
            # A changed form/ambiguous response must not blindly submit the rest.
            break
    return results


def run_job(app, job):
    month = job['month']
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('조회 월 형식이 잘못되었습니다.')
    operation = job['operation']
    if operation not in ('scan', 'submit'):
        raise ValueError('지원하지 않는 작업입니다.')
    settings = app.load_json(app.SETTINGS_FILE, {})
    if not settings.get('id') or not settings.get('pw'):
        raise ValueError('계정을 먼저 저장해 주세요.')
    app._LOG_SECRETS.add(settings['pw'])
    with app.file_lock('action', timeout=120):
        driver = app.create_driver()
        try:
            driver.set_page_load_timeout(45)
            driver.get(app.SITE_URL)
            app.check_site_response(driver)
            wait = WebDriverWait(driver, 20)
            wait.until(EC.visibility_of_element_located((By.NAME, 'iduser'))).send_keys(settings['id'])
            driver.find_element(By.NAME, 'pass').send_keys(settings['pw'])
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            wait.until(EC.element_to_be_clickable((By.LINK_TEXT, '근태관리')))
            rows = collect_month(driver, month, date.today(), app.is_workday)
            with app.file_lock('state'):
                statuses = app.load_json(app.STATE_FILE, {}).get('overtime_applications', {})
            if operation == 'scan':
                for row in rows:
                    prior = statuses.get(row['date'], {}).get('status')
                    row['selectable'] = True
                    row['status'] = ('이전 처리 기록 있음 · 선택 시 사이트 확인 후 수정/추가' if prior in ('success','sending','uncertain') else '선택 시 사이트 확인 후 수정/추가')
                    row['purpose']=statuses.get(row['date'],{}).get('purpose','')
                # Listing recorded overtime needs only attendance access. A
                # missing application menu must not discard the collected rows.
                return {'ok': True, 'rows': rows, 'message': '기존 신청 여부는 신청 직전에 사이트에서 다시 확인합니다.'}
            page = OvertimePage(driver)
            page.open()
            def persist(values):
                with app.file_lock('state'):
                    state = app.load_json(app.STATE_FILE, {})
                    state['overtime_applications'] = values
                    app.save_json(app.STATE_FILE, state)
            return {'ok': True, 'rows': submit_rows(page, job['rows'], rows, statuses, persist)}
        except Exception:
            app.check_site_response(driver)
            raise
        finally:
            driver.quit()
