"""Semantic adapters for the attendance table and edit form in the supplied UI.

No field names or private endpoint URLs are guessed. An ambiguous table/form
raises an error before submission and leaves the record for a later attempt.
"""
import re
from urllib.parse import urlsplit, parse_qs
from datetime import date, datetime, timedelta

from selenium.common.exceptions import NoAlertPresentException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait


def parse_time(text):
    match = re.fullmatch(r"\s*(\d{1,2})\s*:\s*(\d{1,2})\s*", text)
    if not match:
        return None
    hour, minute = map(int, match.groups())
    return (hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None


def is_blank_time(text):
    return re.sub(r"\s", "", text) in {"", ":", "-", "--:--"}


def previous_workday(today, is_workday):
    day = today - timedelta(days=1)
    for _ in range(370):
        if is_workday(day):
            return day
        day -= timedelta(days=1)
    raise RuntimeError("이전 근무일을 찾을 수 없습니다.")


def visible(elements):
    return [item for item in elements if item.is_displayed()]


def label(element):
    return (element.text or element.get_attribute("value") or "").strip()


def one(elements, description):
    elements = visible(elements)
    if len(elements) != 1:
        raise RuntimeError(f"{description}: 후보가 {len(elements)}개여서 처리를 중단합니다.")
    return elements[0]


def input_value(element):
    """Read live input state, not its initial HTML value attribute."""
    getter=getattr(element,'get_property',None)
    return str((getter('value') if callable(getter) else element.get_attribute('value')) or '')


SET_TIME_INPUTS = '''
const inputs=arguments[0], values=arguments[1];
if(inputs.length!==2 || values.length!==2) throw new Error('Invalid time input pair');
for(const input of inputs){
  if(!(input instanceof HTMLInputElement) || input.disabled || input.readOnly)
    throw new Error('Time input is not editable');
}
const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
for(let i=0;i<inputs.length;i++) setter.call(inputs[i],values[i]);
for(const input of inputs){
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.dispatchEvent(new Event('change',{bubbles:true}));
  input.focus({preventScroll:true});input.blur();
}
return inputs.map(input=>input.value);
'''


class AttendancePage:
    def __init__(self, driver, today):
        self.driver = driver
        self.today = today
        self.wait = WebDriverWait(driver, 20)

    def open(self):
        one(self.driver.find_elements(By.LINK_TEXT, "근태관리"), "근태관리 메뉴").click()
        self.wait.until(lambda _: self.month_heading() is not None)

    def month_heading(self):
        text = self.driver.find_element(By.TAG_NAME, "body").text
        match = re.search(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*근태현황", text)
        if not match:
            return None
        year, month = match.groups()
        return (int(year) if year else None, int(month))

    def choose_month(self, day):
        heading = self.month_heading()
        if not heading:
            raise RuntimeError("근태현황의 조회 월을 확인할 수 없습니다.")
        # The screenshot has a month selector but no year selector. Never
        # assume that selecting December in January means the previous year.
        if heading[0] is None and day.year != self.today.year:
            raise RuntimeError("연도 선택이 확인되지 않아 전년도 기록은 자동 수정하지 않습니다.")
        if heading == (day.year, day.month) or (heading[0] is None and heading[1] == day.month):
            return
        selectors = visible(self.driver.find_elements(By.TAG_NAME, "select"))
        month_selects = []
        year_selects = []
        for element in selectors:
            options = Select(element).options
            months = [o for o in options if re.fullmatch(r"0?\d{1,2}\s*월", o.text.strip())]
            years = [o for o in options if re.fullmatch(r"\d{4}\s*년?", o.text.strip())]
            if len(months) >= 2:
                month_selects.append(element)
            if years:
                year_selects.append(element)
        if heading[0] is not None and heading[0] != day.year:
            year_select = one(year_selects, "연도 선택")
            option = one([o for o in Select(year_select).options if re.fullmatch(fr"{day.year}\s*년?", o.text.strip())], "조회 연도")
            Select(year_select).select_by_value(option.get_attribute("value"))
        month_select = one(month_selects, "월 선택")
        option = one([o for o in Select(month_select).options if re.fullmatch(fr"0?{day.month}\s*월", o.text.strip())], "조회 월")
        Select(month_select).select_by_value(option.get_attribute("value"))
        controls = self.driver.find_elements(By.CSS_SELECTOR, "button, a, input[type='submit'], input[type='button']")
        one([c for c in controls if label(c) == "조회"], "월 조회 버튼").click()
        self.wait.until(lambda _: self.month_heading() in {(None, day.month), (day.year, day.month)})

    def record(self, day):
        self.choose_month(day)
        records = []
        for table in visible(self.driver.find_elements(By.TAG_NAME, "table")):
            headers = table.find_elements(By.XPATH, ".//tr[th][1]/th")
            names = [re.sub(r"\s", "", h.text) for h in headers]
            for start, name in enumerate(names):
                if names[start:start + 5] != ["근무일", "출근시간", "퇴근시간", "비고", "수정"]:
                    continue
                for row in table.find_elements(By.XPATH, ".//tr[td]"):
                    cells = row.find_elements(By.XPATH, "./td")
                    if len(cells) < start + 5:
                        continue
                    if re.fullmatch(fr"\s*0?{day.day}\s*일\s*", cells[start].text):
                        records.append({"checkin": cells[start + 1].text, "checkout": cells[start + 2].text,
                                        "note": cells[start + 3].text, "edit_cell": cells[start + 4]})
        if len(records) != 1:
            raise RuntimeError(f"{day.isoformat()} 근태 행을 하나로 확인하지 못했습니다.")
        return records[0]

    def edit(self, day, field, target):
        before = self.record(day)
        if field == "checkout":
            if not parse_time(before["checkin"]) or not is_blank_time(before["checkout"]):
                return False
        elif field == "checkin":
            value = parse_time(before["checkin"])
            if value is None or value < (9, 0):
                return False
        else:
            raise ValueError("Unknown attendance field")
        return self.correct(day, {field: target}, before)

    def correct(self, day, targets, expected):
        self.driver._workday_phase = '수정 전 기록 확인'
        try:
            return self._correct(day, targets, expected)
        except Exception as error:
            phase = self.driver._workday_phase
            detail = '제한 시간 안에 화면 또는 저장 결과를 확인하지 못했습니다.' if isinstance(error, TimeoutException) else str(error).strip() or type(error).__name__
            if isinstance(error, TimeoutException) and phase == '출퇴근 수정 입력 화면 찾기':
                detail += ' ' + str(getattr(self.driver, '_workday_editor_diagnostic', ''))
            submitted = bool(getattr(self.driver, '_workday_write_submitted', False))
            outcome = '저장 요청 이후이므로 사이트에서 결과를 다시 확인하세요.' if submitted else '저장 버튼을 누르기 전에 중단했습니다.'
            raise RuntimeError(f'{day}: {phase} 실패 · {detail} {outcome}') from error

    def _correct(self, day, targets, expected):
        """User-reviewed correction; preserve notes and reject stale snapshots."""
        self.driver._workday_write_submitted = False
        if not targets or set(targets) - {'checkin', 'checkout'}:
            raise ValueError('정정할 출퇴근 시간을 확인하세요.')
        before = self.record(day)
        if any(before[k] != expected[k] for k in ('checkin', 'checkout', 'note')):
            raise RuntimeError('조회 후 기록이 변경되었습니다. 다시 조회하세요.')
        controls = before["edit_cell"].find_elements(By.CSS_SELECTOR, "a, button, input")
        edit = one([c for c in controls if label(c) == "수정"], "해당 날짜의 수정 버튼")
        edit_href = edit.get_attribute('href') or ''
        guard = getattr(self.driver, '_workday_before_write', None)
        if guard:
            guard()
        self.driver._workday_phase = '해당 날짜 수정 버튼 열기'
        if edit_href:
            # Follow the exact observed link once. Do not depend on a click
            # navigating the current tab (or retry a navigation in a loop).
            source=urlsplit(edit_href);query=parse_qs(source.query)
            if (source.path.rsplit('/',1)[-1]!='sappd_g4_edit.php'
                    or len(query.get('no',[]))!=1 or not query['no'][0].isdigit()
                    or query.get('m')!=[str(day.month)]):
                raise RuntimeError('선택한 날짜의 수정 주소와 기록 번호·월을 확인하지 못했습니다.')
            current_url=getattr(self.driver,'current_url','')
            if isinstance(current_url,str) and current_url:
                current=urlsplit(current_url)
                if (source.scheme,source.netloc)!=(current.scheme,current.netloc):
                    raise RuntimeError('수정 링크가 현재 사이트와 달라 이동을 중단합니다.')
            self.driver.get(edit_href)
            final_url=getattr(self.driver,'current_url','')
            if isinstance(final_url,str) and final_url:
                final=urlsplit(final_url);final_query=parse_qs(final.query)
                if ((source.scheme,source.netloc,source.path)!=(final.scheme,final.netloc,final.path)
                        or any(query.get(k)!=final_query.get(k) for k in ('no','m'))):
                    raise RuntimeError(f'수정 주소로 이동했지만 사이트가 다른 화면({final.path.rsplit("/",1)[-1] or "/"})을 반환했습니다. 수정 페이지 접근·로그인 상태를 확인하세요.')
        else:
            edit.click()
        response_check = getattr(self.driver, '_workday_check_response', None)
        if response_check:
            response_check()

        def named_editor():
            candidates=[]
            for form in visible(self.driver.find_elements(By.TAG_NAME,'form')):
                fields={name:visible(form.find_elements(By.CSS_SELECTOR,f'input[name="{name}"]'))
                        for name in ('culgun','culguna','tehgun','tehguna','huuga')}
                if all(len(values)==1 for values in fields.values()):
                    candidates.append((form,fields))
            if len(candidates)>1:
                raise RuntimeError('동일한 출퇴근 수정 폼이 여러 개여서 저장을 중단합니다.')
            if not candidates:return None
            form,fields=candidates[0]
            source=urlsplit(edit_href);action=urlsplit(form.get_attribute('action') or '')
            source_query=parse_qs(source.query);action_query=parse_qs(action.query)
            if (action.path.rsplit('/',1)[-1]!='sappd_g4_edit_pro.php'
                    or not source_query.get('no') or not source_query.get('m')
                    or any(source_query.get(k)!=action_query.get(k) for k in ('no','m'))
                    or (source.netloc and (source.scheme,source.netloc)!=(action.scheme,action.netloc))):
                raise RuntimeError('선택 날짜의 수정 링크와 저장 폼의 기록 번호·월·사이트가 다릅니다.')
            return form,fields

        def edit_table(_):
            named=named_editor()
            if named:return ('named',named)
            candidates = []
            tables = visible(self.driver.find_elements(By.TAG_NAME, "table"))
            for table in tables:
                # Descendant searches also matched layout tables containing the
                # actual editor, turning one editor into several candidates.
                own_rows = table.find_elements(By.XPATH, './tr | ./thead/tr | ./tbody/tr | ./tfoot/tr')
                matching = any([re.sub(r'\s', '', h.text) for h in row.find_elements(By.XPATH, './th | ./td')]
                               == ['출근시간', '퇴근시간', '비고', '수정'] for row in own_rows)
                if matching:
                    candidates.append(table)
            all_forms=self.driver.find_elements(By.TAG_NAME,'form')
            field_count=len(self.driver.find_elements(By.CSS_SELECTOR,'input[name="culgun"]'))
            current_url=getattr(self.driver,'current_url','')
            path=urlsplit(current_url).path.rsplit('/',1)[-1] if isinstance(current_url,str) else ''
            self.driver._workday_editor_diagnostic = f'현재 페이지 {path or "확인 불가"} / 표시 테이블 {len(tables)}개 / 입력표 후보 {len(candidates)}개 / 폼 {len(all_forms)}개 / 출근 입력 DOM {field_count}개.'
            return ('table',candidates[0]) if len(candidates) == 1 else False

        self.driver._workday_phase = '출퇴근 수정 입력 화면 찾기'
        kind,editor = self.wait.until(edit_table)
        self.driver._workday_phase = '수정 입력값 확인'
        if kind=='named':
            form,fields=editor
            row=form
            pairs=[[fields[name][0] for name in names] for names in (('culgun','culguna'),('tehgun','tehguna'))]
            save=one([c for c in form.find_elements(By.CSS_SELECTOR,'button, a, input') if label(c)=='수정완료'],'수정완료 버튼')
            expected_action=form.get_attribute('action')
        else:
            table=editor
            rows = [r for r in table.find_elements(By.XPATH, './tr | ./thead/tr | ./tbody/tr | ./tfoot/tr') if visible(r.find_elements(By.TAG_NAME, "input"))]
            row = one(rows, "시간 수정 입력 행")
            cells = row.find_elements(By.XPATH, "./td")
            if len(cells) != 4:
                raise RuntimeError("수정 입력칸 구조가 예상과 다릅니다.")
            pairs = [visible(c.find_elements(By.CSS_SELECTOR, "input:not([type='hidden'])")) for c in cells[:2]]
            save = one([c for c in cells[3].find_elements(By.CSS_SELECTOR, 'button, a, input') if label(c)=='수정완료'],'수정완료 버튼')
        if [len(pair) for pair in pairs] != [2, 2]:
            raise RuntimeError("출퇴근 시/분 입력칸을 확인하지 못했습니다.")
        # Confirm we opened the correct row before touching any input.
        displayed_checkin = parse_time(":".join(input_value(i) for i in pairs[0]))
        if displayed_checkin != parse_time(before["checkin"]):
            raise RuntimeError("선택한 날짜와 수정 화면의 출근 시간이 다릅니다.")
        displayed_checkout = parse_time(":".join(input_value(i) for i in pairs[1]))
        if displayed_checkout != parse_time(before["checkout"]):
            raise RuntimeError("선택한 날짜와 수정 화면의 퇴근 시간이 다릅니다.")
        target_inputs = [i for field in targets for i in pairs[0 if field == 'checkin' else 1]]
        untouched = [i for i in row.find_elements(By.CSS_SELECTOR, "input, textarea, select") if i not in target_inputs]
        values = [(i, input_value(i)) for i in untouched]
        for field, target in targets.items():
            inputs = pairs[0 if field == 'checkin' else 1]
            execute=getattr(self.driver,'execute_script',None)
            if callable(execute):
                execute(SET_TIME_INPUTS,inputs,[f'{target.hour:02d}',f'{target.minute:02d}'])
            else:
                for element, value in zip(inputs, (target.hour, target.minute)):
                    element.click()
                    element.send_keys(Keys.CONTROL, 'a')
                    element.send_keys(Keys.BACKSPACE)
                    element.send_keys(f"{value:02d}")
                    element.send_keys(Keys.TAB)
            def input_matches(_):
                return parse_time(':'.join(input_value(i).strip() for i in inputs))==(target.hour,target.minute)
            try:
                WebDriverWait(self.driver,3,poll_frequency=0.1).until(input_matches)
            except TimeoutException as error:
                actual=':'.join(re.sub(r'[^0-9\s]', '?',input_value(i))[:8] for i in inputs)
                name='출근' if field=='checkin' else '퇴근'
                raise RuntimeError(f'{name} 입력값이 다릅니다: 예정 {target:%H:%M} / 입력칸 {actual}. 저장하지 않았습니다.') from error
        if any(input_value(i) != value for i, value in values):
            raise RuntimeError("대상 외 입력값이 바뀌어 저장을 중단합니다.")
        current = self.record(day)
        if any(current[key] != before[key] for key in ("checkin", "checkout", "note")):
            raise RuntimeError("다른 곳에서 근태 기록이 변경되어 저장을 중단합니다.")
        if kind=='named' and form.get_attribute('action')!=expected_action:
            raise RuntimeError('입력 중 저장 대상이 변경되어 저장을 중단합니다.')
        self.driver._workday_phase = '수정완료 버튼 저장'
        self.driver._workday_write_submitted = True
        save.click()
        if response_check:
            response_check()

        self.driver._workday_phase = '사이트에 저장된 출퇴근 시간 재확인'
        def verified(_):
            try:
                self.driver.switch_to.alert.accept()
            except NoAlertPresentException:
                pass
            try:
                after = self.record(day)
                return (all(parse_time(after[field]) == (target.hour, target.minute) for field, target in targets.items())
                        and all(after[field] == before[field] for field in ('checkin', 'checkout') if field not in targets)
                        and after['note'] == before['note'])
            except StaleElementReferenceException:
                return False

        self.wait.until(verified)
        return True


def repair_missing_checkouts(driver, today, is_workday, target_for, record_status, log, pending=()):
    days = {previous_workday(today, is_workday)}
    for value in pending:
        day = date.fromisoformat(value)
        if day < today and is_workday(day):
            days.add(day)
    # Queue before navigation so a broken menu/network does not lose recovery.
    for day in days:
        record_status(day, "pending")
    page = AttendancePage(driver, today)
    page.open()
    for day in sorted(days):
        try:
            row = page.record(day)
            if parse_time(row["checkout"]):
                record_status(day, "present")
                log(f"{day} 기존 퇴근 기록 유지")
                continue
            if not parse_time(row["checkin"]):
                record_status(day, "no_checkin")
                log(f"{day} 출근 기록이 없어 퇴근 보완 생략")
                continue
            if not is_blank_time(row["checkout"]):
                raise RuntimeError("퇴근 표시를 해석할 수 없습니다.")
            target = target_for(day)
            if page.edit(day, "checkout", target):
                record_status(day, "success", target)
                log(f"{day} 퇴근 누락 보완 확인: {target:%H:%M}")
        except Exception as error:
            log(f"{day} 퇴근 누락 보완 보류: {type(error).__name__} / {error}")


def correct_late_checkin(driver, today, target_for, log, late_from=(9, 0)):
    page = AttendancePage(driver, today)
    page.open()
    row = page.record(today)
    value = parse_time(row["checkin"])
    if value is None or value < late_from:
        log(f"{today} 출근 보정 대상이 아니므로 기존 시간 유지")
        return
    target = target_for(today)
    if page.edit(today, "checkin", target):
        log(f"{today} 늦은 출근 시간 보정 확인: {target:%H:%M}")
