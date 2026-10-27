"""Offline DOM model: screenshot structure, not a live-site integration test."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from attendance_recovery import AttendancePage
from selenium.common.exceptions import NoAlertPresentException
from selenium.common.exceptions import TimeoutException
from unittest.mock import patch
from selenium.webdriver.common.by import By


class Element:
    def __init__(self, text='', value='', children=None, click=None):
        self.text = text
        self.value = value
        self.children = children or {}
        self.click_handler = click
        self.change_handler = None

    def is_displayed(self):
        return True

    def get_attribute(self, name):
        return self.value if name == 'value' else None

    def find_elements(self, by, selector):
        return self.children.get((by, selector), [])

    def click(self):
        if self.click_handler:
            self.click_handler()

    def clear(self):
        self.value = ''

    def send_keys(self, value):
        self.value += value
        if self.change_handler:
            self.change_handler()


class NoAlert:
    @property
    def alert(self):
        raise NoAlertPresentException()


class FakeSite:
    """A single visible attendance row and the four-column inline edit form."""
    def __init__(self, checkin='08 : 50', checkout=' : ', note='원래 비고'):
        self.checkin = Element(checkin)
        self.checkout = Element(checkout)
        self.note = Element(note)
        self.editing = False
        self.saved = False
        self.switch_to = NoAlert()
        edit_link = Element('수정', click=self.open_edit)
        edit_cell = Element(children={(By.CSS_SELECTOR, 'a, button, input'): [edit_link]})
        row = Element(children={(By.XPATH, './td'): [Element('23일'), self.checkin, self.checkout, self.note, edit_cell]})
        self.table = Element(children={
            (By.XPATH, './/tr[th][1]/th'): [Element(s) for s in ['근무일', '출근시간', '퇴근시간', '비고', '수정']],
            (By.XPATH, './/tr[td]'): [row],
        })

    def open_edit(self):
        self.editing = True
        cin = [s.strip() for s in self.checkin.text.split(':')]
        cout = [s.strip() for s in self.checkout.text.split(':')]
        self.fields = [Element(value=v) for v in cin + cout]
        self.note_field = Element(value=self.note.text)
        input_cells = [Element(children={(By.CSS_SELECTOR, "input:not([type='hidden'])"): self.fields[:2]}),
                       Element(children={(By.CSS_SELECTOR, "input:not([type='hidden'])"): self.fields[2:]})]
        save = Element('수정완료', click=self.save)
        row = Element(children={
            (By.TAG_NAME, 'input'): self.fields + [self.note_field],
            (By.CSS_SELECTOR, 'input, textarea, select'): self.fields + [self.note_field],
            (By.XPATH, './td'): input_cells + [Element(), Element(children={(By.CSS_SELECTOR, 'button, a, input'): [save]})],
        })
        self.editor = Element(children={
            (By.XPATH, './/tr[th][1]/th'): [Element(s) for s in ['출근시간', '퇴근시간', '비고', '수정']],
            (By.XPATH, './/tr[td]'): [row],
        })

    def save(self):
        self.saved = True
        self.checkin.text = ' : '.join(f.value for f in self.fields[:2])
        self.checkout.text = ' : '.join(f.value for f in self.fields[2:])
        self.note.text = self.note_field.value
        self.editing = False

    def find_element(self, by, selector):
        if (by, selector) == (By.TAG_NAME, 'body'):
            return Element('10월 근태현황 (연장근무: 0시간 0분)')
        raise AssertionError((by, selector))

    def find_elements(self, by, selector):
        if (by, selector) == (By.TAG_NAME, 'table'):
            return [self.table] + ([self.editor] if self.editing else [])
        raise AssertionError((by, selector))


class EditFormTests(unittest.TestCase):
    def test_td_or_mixed_editor_heading_is_accepted(self):
        for variant in ('td','mixed'):
            with self.subTest(variant=variant):
                site=FakeSite();original=site.open_edit
                def open_edit():
                    original()
                    heads=site.editor.children.pop((By.XPATH,'.//tr[th][1]/th'))
                    site.editor.children[(By.XPATH,'.//tr[th or td][1]/*[self::th or self::td]')]=heads
                link=site.table.children[(By.XPATH,'.//tr[td]')][0].children[(By.XPATH,'./td')][4].children[(By.CSS_SELECTOR,'a, button, input')][0]
                link.click_handler=open_edit
                page=AttendancePage(site,date(2026,10,26))
                page.correct(date(2026,10,23),{'checkout':datetime(2026,10,23,19,35)},page.record(date(2026,10,23)))
                self.assertTrue(site.saved);self.assertEqual(site.checkout.text,'19 : 35')

    def test_editor_timeout_identifies_date_and_no_submission(self):
        site=FakeSite();page=AttendancePage(site,date(2026,10,26))
        with patch.object(page.wait,'until',side_effect=TimeoutException()):
            with self.assertRaisesRegex(RuntimeError,'2026-10-23: 출퇴근 수정 입력 화면 찾기') as caught:
                page.correct(date(2026,10,23),{'checkout':datetime(2026,10,23,19,35)},page.record(date(2026,10,23)))
        self.assertIn('저장 버튼을 누르기 전에',str(caught.exception))
        self.assertFalse(site.saved)

    def test_unverified_save_is_never_reported_complete(self):
        site=FakeSite();page=AttendancePage(site,date(2026,10,26))
        calls=[0]
        def wait_for(condition):
            calls[0]+=1
            if calls[0]==1:return condition(site)
            raise TimeoutException()
        with patch.object(page.wait,'until',side_effect=wait_for):
            with self.assertRaisesRegex(RuntimeError,'저장된 출퇴근 시간 재확인') as caught:
                page.correct(date(2026,10,23),{'checkout':datetime(2026,10,23,19,35)},page.record(date(2026,10,23)))
        self.assertIn('저장 요청 이후',str(caught.exception))

    def test_checkout_edit_preserves_checkin_and_note(self):
        site = FakeSite()
        page = AttendancePage(site, date(2026, 10, 26))
        self.assertTrue(page.edit(date(2026, 10, 23), 'checkout', datetime(2026, 10, 23, 20, 55)))
        self.assertTrue(site.saved)
        self.assertEqual(site.checkin.text, '08 : 50')
        self.assertEqual(site.checkout.text, '20 : 55')
        self.assertEqual(site.note.text, '원래 비고')

    def test_checkin_edit_preserves_checkout_and_note(self):
        site = FakeSite(checkin='09 : 20', checkout='19 : 35')
        page = AttendancePage(site, date(2026, 10, 26))
        self.assertTrue(page.edit(date(2026, 10, 23), 'checkin', datetime(2026, 10, 23, 8, 30)))
        self.assertEqual(site.checkin.text, '08 : 30')
        self.assertEqual(site.checkout.text, '19 : 35')
        self.assertEqual(site.note.text, '원래 비고')

    def test_existing_checkout_skips_edit_form(self):
        site = FakeSite(checkout='18 : 15')
        page = AttendancePage(site, date(2026, 10, 26))
        self.assertFalse(page.edit(date(2026, 10, 23), 'checkout', datetime(2026, 10, 23, 19, 35)))
        self.assertFalse(site.editing)
        self.assertFalse(site.saved)

    def test_early_checkin_skips_edit_form(self):
        site = FakeSite(checkin='08 : 55')
        page = AttendancePage(site, date(2026, 10, 26))
        self.assertFalse(page.edit(date(2026, 10, 23), 'checkin', datetime(2026, 10, 23, 8, 30)))
        self.assertFalse(site.saved)

    def test_changed_note_is_detected_before_save(self):
        site = FakeSite()
        original = site.open_edit
        def open_corrupt_edit():
            original()
            site.fields[2].change_handler = lambda: setattr(site.note_field, 'value', 'unexpected change')
        # Replace the original link action with an editor that changes a field
        # in response to input, exercising the pre-submission preservation guard.
        link = site.table.children[(By.XPATH, './/tr[td]')][0].children[(By.XPATH, './td')][4].children[(By.CSS_SELECTOR, 'a, button, input')][0]
        link.click_handler = open_corrupt_edit
        page = AttendancePage(site, date(2026, 10, 26))
        with self.assertRaisesRegex(RuntimeError, '대상 외 입력값'):
            page.edit(date(2026, 10, 23), 'checkout', datetime(2026, 10, 23, 19, 35))
        self.assertFalse(site.saved)


if __name__ == '__main__':
    unittest.main()
