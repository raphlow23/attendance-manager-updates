import sys
from contextlib import nullcontext
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from selenium.webdriver.common.by import By

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import overtime_requests as overtime
import resident


class OvertimeTests(unittest.TestCase):
    def test_open_follows_observed_menu_and_application_links(self):
        driver=Mock(current_url='https://test.invalid/attendance')
        work=Mock(text='근무일지',is_displayed=Mock(return_value=True));work.get_attribute.return_value='https://test.invalid/work'
        entry=Mock(text='시간외근무 신청',is_displayed=Mock(return_value=True));entry.get_attribute.return_value='https://test.invalid/overtime'
        driver.get.side_effect=lambda url:setattr(driver,'current_url',url)
        driver.find_elements.side_effect=lambda by,selector:[work] if by==By.LINK_TEXT else [entry] if by==By.CSS_SELECTOR else []
        driver.find_element.side_effect=lambda *a:Mock(text='시간외근무신청서' if driver.current_url.endswith('/overtime') else '근무일지')
        overtime.OvertimePage(driver).open()
        self.assertEqual([call.args[0] for call in driver.get.call_args_list],['https://test.invalid/work','https://test.invalid/overtime'])
        work.click.assert_not_called();entry.click.assert_not_called()
    def test_scan_succeeds_without_application_menu_and_protects_prior_submissions(self):
        driver=Mock()
        app=Mock(SETTINGS_FILE='settings',STATE_FILE='state',SITE_URL='https://test.invalid')
        app.file_lock.side_effect=lambda *a,**kw:nullcontext()
        app.create_driver.return_value=driver
        app.load_json.side_effect=[{'id':'test-only','pw':'test-only'},
                                  {'overtime_applications':{'2026-09-04':{'status':'uncertain'}}}]
        rows=[self.row(),dict(self.row(),date='2026-09-07')]
        with patch.object(overtime,'collect_month',return_value=rows),patch.object(overtime,'WebDriverWait'),patch.object(overtime,'OvertimePage') as page:
            page.return_value.open.side_effect=RuntimeError('no application menu')
            result=overtime.run_job(app,{'operation':'scan','month':'2026-09'})
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['rows']),2)
        self.assertFalse(result['rows'][0]['selectable'])
        self.assertTrue(result['rows'][1]['selectable'])
        page.assert_not_called()
        driver.quit.assert_called_once()

    def test_submit_still_checks_remote_duplicates_before_writing(self):
        app=Mock(SETTINGS_FILE='settings',STATE_FILE='state',SITE_URL='https://test.invalid')
        app.file_lock.side_effect=lambda *a,**kw:nullcontext()
        app.load_json.side_effect=[{'id':'test-only','pw':'test-only'},{},{}]
        row=self.row()
        with patch.object(overtime,'collect_month',return_value=[row]),patch.object(overtime,'WebDriverWait'),patch.object(overtime,'OvertimePage') as page:
            page.return_value.existing.return_value=True
            result=overtime.run_job(app,{'operation':'submit','month':'2026-09','rows':[dict(row,purpose='직접 입력') ]})
        page.return_value.open.assert_called_once()
        page.return_value.existing.assert_called_once()
        page.return_value.fill.assert_not_called()
        self.assertEqual(result['rows'][0]['status'],'기존 신청 유지')

    def test_entry_link_accepts_spacing_and_button(self):
        control=Mock(text='시간외근무 신청',is_displayed=Mock(return_value=True))
        driver=Mock()
        driver.find_elements.return_value=[control]
        self.assertIs(overtime.OvertimePage(driver).entry_control(),control)

    def test_entry_link_finds_nested_sibling_card(self):
        link=Mock(text='바로가기',is_displayed=Mock(return_value=True))
        card=Mock()
        card.find_elements.return_value=[link]
        inner=Mock()
        inner.find_elements.return_value=[]
        inner.find_element.return_value=card
        title=Mock(is_displayed=Mock(return_value=True))
        title.find_element.return_value=inner
        driver=Mock()
        driver.find_elements.side_effect=lambda by,selector: [title] if by==By.XPATH else [link]
        self.assertIs(overtime.OvertimePage(driver).entry_control(),link)

    def test_ambiguous_entry_links_are_not_clicked(self):
        links=[Mock(text='시간외근무 신청',is_displayed=Mock(return_value=True)) for _ in range(2)]
        driver=Mock();driver.find_elements.return_value=links
        with self.assertRaises(RuntimeError):
            overtime.OvertimePage(driver).entry_control()
        for link in links:
            link.click.assert_not_called()

    def row(self, checkout='19:55'):
        return overtime.application_row(date(2026, 9, 4), {'checkin': '08:50', 'checkout': checkout})

    def test_floor_to_1900_or_2000_and_preserve_selected_month(self):
        self.assertEqual(self.row()['end'], '19:00')
        self.assertEqual(self.row('20:55')['end'], '20:00')
        self.assertEqual(self.row()['date'], '2026-09-04')
        self.assertEqual(self.row()['weekday'], '금')
        self.assertEqual(self.row()['start'], '18:00')

    def test_non_overtime_and_no_checkin_are_excluded(self):
        for value in ('18:55', ':', '21:00'):
            self.assertIsNone(self.row(value))
        self.assertIsNone(overtime.application_row(date(2026, 9, 4), {'checkin': ':', 'checkout': '19:55'}))

    def test_scan_september_when_current_month_is_october(self):
        page = Mock()
        page.record.return_value = {'checkin': '08:50', 'checkout': '19:55'}
        with patch.object(overtime, 'AttendancePage', return_value=page):
            rows = overtime.collect_month(None, '2026-09', date(2026, 10, 26), lambda d: d.weekday() < 5)
        self.assertTrue(rows)
        self.assertTrue(all(row['date'].startswith('2026-09-') for row in rows))
        self.assertTrue(all(call.args[0].month == 9 for call in page.record.call_args_list))

    def submit(self, status=None, fail_verify=False):
        row = self.row()
        reviewed = dict(row, purpose='직접 입력한 업무 목적')
        page = Mock()
        page.existing.return_value = False
        if fail_verify:
            page.verify.side_effect = RuntimeError('unknown result')
        statuses = status or {}
        persist = Mock()
        result = overtime.submit_rows(page, [reviewed], [row], statuses, persist)
        return page, statuses, persist, result

    def test_confirmed_submission_uses_user_purpose_and_journals_success(self):
        page, state, persist, result = self.submit()
        self.assertEqual(page.fill.call_args.args[0]['purpose'], '직접 입력한 업무 목적')
        self.assertEqual(state['2026-09-04']['status'], 'success')
        self.assertEqual(result[0]['status'], '신청 확인 완료')
        self.assertEqual(persist.call_count, 2)

    def test_uncertain_submission_is_not_retried(self):
        page, state, persist, result = self.submit(fail_verify=True)
        self.assertEqual(state['2026-09-04']['status'], 'uncertain')
        page, _, _, _ = self.submit(status=state)
        page.fill.assert_not_called()

    def test_changed_real_checkout_blocks_submission(self):
        page = Mock()
        reviewed = dict(self.row(), purpose='확인')
        with self.assertRaisesRegex(ValueError, '퇴근 기록이 변경'):
            overtime.submit_rows(page, [reviewed], [self.row('20:55')], {}, Mock())
        page.fill.assert_not_called()

    def test_blank_purpose_and_duplicate_date_are_rejected(self):
        row = self.row()
        with self.assertRaises(ValueError):
            overtime.submit_rows(Mock(), [row], [row], {}, Mock())
        reviewed = dict(row, purpose='업무')
        with self.assertRaises(ValueError):
            overtime.submit_rows(Mock(), [reviewed, reviewed], [row], {}, Mock())

    def test_existing_remote_application_is_preserved(self):
        row = dict(self.row(), purpose='업무')
        page = Mock()
        page.existing.return_value = True
        overtime.submit_rows(page, [row], [self.row()], {}, Mock())
        page.fill.assert_not_called()


class HealthTests(unittest.TestCase):
    def test_heartbeat_and_connectivity_do_not_claim_login_success(self):
        health = resident.Health(Mock())
        health.network_online = True
        data = health.snapshot()
        self.assertTrue(data['network_online'])
        self.assertIsNone(data['last_login_verified_utc'])
        health.login_verified()
        self.assertIsNotNone(health.snapshot()['last_login_verified_utc'])

    def test_automation_deadline_detects_stall_even_with_fresh_heartbeat(self):
        health = resident.Health(Mock())
        health.phase('checkin', 'login_submit', seconds=-1)
        self.assertTrue(health.snapshot()['stalled'])
        health.phase('checkin', 'waiting')
        self.assertFalse(health.snapshot()['stalled'])


if __name__ == '__main__':
    unittest.main()
