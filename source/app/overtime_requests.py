"""Monthly, user-confirmed overtime applications from actual attendance rows."""
import calendar
import re
from datetime import date

from selenium.common.exceptions import NoAlertPresentException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from attendance_recovery import AttendancePage, label, one, parse_time, visible

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


def select_number(element, number):
    options = Select(element).options
    matches = [o for o in options if re.fullmatch(fr'0*{number}\s*[월일시분]?', o.text.strip())]
    if len(matches) != 1:
        raise RuntimeError(f'선택값 {number}을 확인하지 못했습니다.')
    Select(element).select_by_value(matches[0].get_attribute('value'))


class OvertimePage:
    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)

    def open(self):
        one(self.driver.find_elements(By.LINK_TEXT, '근무일지'), '근무일지 메뉴').click()
        try:
            control = self.wait.until(lambda _: self.entry_control())
        except TimeoutException as error:
            raise RuntimeError('근무일지에서 시간외근무 신청 바로가기를 찾지 못했습니다. 사이트 메뉴와 접근 권한을 확인하세요.') from error
        control.click()
        self.wait.until(lambda d: '시간외근무신청서' in re.sub(r'\s+', '', d.find_element(By.TAG_NAME, 'body').text))

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

    def existing(self, row):
        day = date.fromisoformat(row['date'])
        date_pattern = fr'{day.year}\s*[-./년]\s*0?{day.month}\s*[-./월]\s*0?{day.day}(?:\D|$)'
        start = r'18\s*(?::|시)\s*00'
        end = fr"{int(row['end'][:2])}\s*(?::|시)\s*00"
        for table in visible(self.driver.find_elements(By.TAG_NAME, 'table')):
            for record in table.find_elements(By.XPATH, './/tr[td]'):
                text = record.text
                if re.search(date_pattern, text) and re.search(start, text) and re.search(end, text):
                    return True
        return False

    def fill(self, row):
        day = date.fromisoformat(row['date'])
        # Match the supplied form by its purpose placeholder and inspect only
        # visible controls inside that form. Ambiguity stops before submission.
        form = one(self.driver.find_elements(By.XPATH, "//form[.//input[contains(@placeholder,'근무목적')]]"), '시간외근무 신청서')
        purpose = one(form.find_elements(By.CSS_SELECTOR, "input[placeholder*='근무목적']"), '근무목적 입력칸')
        selects = visible(form.find_elements(By.TAG_NAME, 'select'))
        departments = [s for s in selects if any(o.text.strip() == '센터' for o in Select(s).options)]
        department = one(departments, '센터 부서 선택')
        times = [s for s in selects if s != department]
        inputs = [i for i in visible(form.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']):not([type='submit']):not([type='button'])")) if i != purpose]
        if len(times) != 7 or len(inputs) != 4:
            raise RuntimeError('신청서의 날짜/시간 입력칸 구조를 확인하지 못했습니다.')
        Select(department).select_by_visible_text('센터')
        purpose.clear()
        purpose.send_keys(row['purpose'])
        # Main date year; footer year/month/day. Footer equals working date.
        for field, number in zip(inputs, (day.year, day.year, day.month, day.day)):
            field.clear()
            field.send_keys(str(number))
        for field, number in zip((times[0], times[1], times[3], times[4], times[5], times[6]),
                                 (day.month, day.day, 18, 0, int(row['end'][:2]), 0)):
            select_number(field, number)
        weekday = WEEKDAYS[day.weekday()]
        opts = [o for o in Select(times[2]).options if o.text.strip() in (weekday, weekday + '요일')]
        if len(opts) != 1:
            raise RuntimeError('요일 선택값을 확인하지 못했습니다.')
        Select(times[2]).select_by_value(opts[0].get_attribute('value'))
        if purpose.get_attribute('value') != row['purpose']:
            raise RuntimeError('근무목적 입력 결과가 일치하지 않습니다.')
        if [int(i.get_attribute('value')) for i in inputs] != [day.year, day.year, day.month, day.day]:
            raise RuntimeError('신청 날짜 입력 결과가 일치하지 않습니다.')
        expected = [day.month, day.day, None, 18, 0, int(row['end'][:2]), 0]
        for element, number in zip(times, expected):
            text = Select(element).first_selected_option.text.strip()
            if number is not None and not re.fullmatch(fr'0*{number}\s*[월일시분]?', text):
                raise RuntimeError('신청 시간 입력 결과가 일치하지 않습니다.')
        buttons = form.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
        return one([b for b in buttons if label(b).replace(' ', '') == '시간외근무신청'], '시간외근무 신청 버튼')

    def verify(self, row):
        def found(_):
            try:
                self.driver.switch_to.alert.accept()
            except NoAlertPresentException:
                pass
            try:
                return self.existing(row)
            except StaleElementReferenceException:
                return False
        self.wait.until(found)


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
        if page.existing(row):
            statuses[key] = {'status': 'success', 'source': '사이트 기존 신청'}
            persist(statuses)
            results.append(dict(row, status='기존 신청 유지'))
            continue
        if statuses.get(key, {}).get('status') in ('success', 'sending', 'uncertain'):
            results.append(dict(row, status='재신청 보류 — 사이트 확인 필요'))
            continue
        try:
            button = page.fill(row)
            statuses[key] = {'status': 'sending', 'purpose': row['purpose'], 'checkout': row['checkout'], 'end': row['end']}
            persist(statuses)
            button.click()
            page.verify(row)
            statuses[key]['status'] = 'success'
            persist(statuses)
            results.append(dict(row, status='신청 확인 완료'))
        except Exception as error:
            if statuses.get(key, {}).get('status') == 'sending':
                statuses[key]['status'] = 'uncertain'
                persist(statuses)
            results.append(dict(row, status=f'확인 필요: {type(error).__name__}'))
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
    with app.file_lock('action', timeout=120):
        driver = app.create_driver()
        try:
            driver.set_page_load_timeout(45)
            driver.get(app.SITE_URL)
            wait = WebDriverWait(driver, 20)
            wait.until(EC.visibility_of_element_located((By.NAME, 'iduser'))).send_keys(settings['id'])
            driver.find_element(By.NAME, 'pass').send_keys(settings['pw'])
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
            wait.until(EC.element_to_be_clickable((By.LINK_TEXT, '근무일지')))
            rows = collect_month(driver, month, date.today(), app.is_workday)
            page = OvertimePage(driver)
            page.open()
            with app.file_lock('state'):
                statuses = app.load_json(app.STATE_FILE, {}).get('overtime_applications', {})
            if operation == 'scan':
                for row in rows:
                    row['status'] = ('기존 신청 있음' if page.existing(row) else
                                     '확인 필요' if statuses.get(row['date'], {}).get('status') in ('success', 'sending', 'uncertain') else '신청 가능')
                return {'ok': True, 'rows': rows}
            def persist(values):
                with app.file_lock('state'):
                    state = app.load_json(app.STATE_FILE, {})
                    state['overtime_applications'] = values
                    app.save_json(app.STATE_FILE, state)
            return {'ok': True, 'rows': submit_rows(page, job['rows'], rows, statuses, persist)}
        finally:
            driver.quit()
