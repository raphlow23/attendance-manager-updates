import os
import base64
import sys
import tempfile
import threading
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import main as app
import attendance_recovery as recovery


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, key, value) for key, value in {
            'DATA_DIR': self.temp.name,
            'STATE_FILE': os.path.join(self.temp.name, 'state.json'),
            'SETTINGS_FILE': os.path.join(self.temp.name, 'settings.json'),
            'LOG_FILE': os.path.join(self.temp.name, 'events.log'),
        }.items()]
        for item in self.patches:
            item.start()
        app.save_json(app.SETTINGS_FILE, {'id': 'test-only', 'pw': 'not-a-real-password'})

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_month_has_ten_unique_nonholiday_weekdays(self):
        for month in range(1, 13):
            state = {'runs': {}}
            selected = app.get_overtime_dates(date(2026, month, 1), state)
            self.assertEqual(len(selected), 10)
            self.assertTrue(all(app.is_workday(date.fromisoformat(d)) for d in selected))

    def test_old_month_plan_survives_rollover(self):
        original = ['2026-09-01', '2026-09-02']
        state = {'overtime_month': '2026-09', 'overtime_dates': original, 'runs': {}}
        app.get_overtime_dates(date(2026, 10, 1), state)
        self.assertEqual(app.get_overtime_dates(date(2026, 9, 1), state), set(original))
        self.assertEqual(len(state['overtime_months']['2026-10']), 10)

    def test_normal_and_overtime_ranges_and_five_minute_steps(self):
        day = date(2026, 10, 26)
        for overtime in (False, True):
            for _ in range(30):
                state = {'runs': {}, 'overtime_months': {'2026-10': [day.isoformat()] if overtime else []}}
                target, _ = app.choose_target('checkout', day, state)
                self.assertEqual(target.hour, 19 if overtime else 18)
                self.assertIn(target.minute, range(0, 60, 5))

    def test_legacy_pending_checkout_targets_use_new_bounds(self):
        day=date(2026,10,26)
        state={'runs':{str(day):{'checkout':{'target':'2026-10-26T18:00'}}}}
        self.assertEqual(app.choose_target('checkout',day,state)[0].strftime('%H:%M'),'18:05')
        state={'runs':{str(day):{'checkout':{'target':'2026-10-26T19:30','daily_overtime_hours':2}}}}
        self.assertEqual(app.choose_target('checkout',day,state)[0].hour,20)
    def test_default_checkout_excludes_1800_and_completed_history_is_untouched(self):
        day=date(2026,10,26)
        self.assertEqual(app.time_settings({'checkout_start':'18:00'})[2],1085)
        state={'runs':{str(day):{'checkout':{'target':'2026-10-26T18:00','status':'success'}}}}
        self.assertIsNone(app.choose_target('checkout',day,state)[0])
        self.assertEqual(state['runs'][str(day)]['checkout']['target'],'2026-10-26T18:00')
    def test_two_hour_window_starts_at_2000(self):
        day=date(2026,10,26)
        app.save_json(app.SETTINGS_FILE,{'daily_overtime_hours':2})
        state={'runs':{},'overtime_months':{'2026-10':[str(day)]},'overtime_month_settings':{'2026-10':{'daily_hours':2}}}
        rng=Mock();rng.choice.side_effect=lambda v:min(v)
        with patch.object(app.random,'SystemRandom',return_value=rng):
            self.assertEqual(app.choose_target('checkout',day,state)[0].strftime('%H:%M'),'20:00')

    def test_normal_checkin_range_is_preserved(self):
        day = date(2026, 10, 26)
        for _ in range(20):
            target, _ = app.choose_target('checkin', day, {'runs': {}})
            self.assertEqual(target.hour, 8)
            self.assertIn(target.minute, range(30, 60, 5))

    def test_repair_reuses_exact_checkout_target(self):
        day = date(2026, 10, 23)
        state = {'runs': {day.isoformat(): {'checkout': {'target': '2026-10-23T19:35', 'status': 'in_progress'}}}}
        app.save_json(app.STATE_FILE, state)
        self.assertEqual(app.recovery_target(day), datetime(2026, 10, 23, 19, 35))

    def test_configured_time_windows_and_minute_intervals(self):
        day = date(2026, 10, 26)
        for step in (1, 5):
            settings = {'monthly_overtime_hours': 0, 'checkin_start': '08:32', 'checkin_end': '08:47',
                        'checkout_start': '17:41', 'checkout_end': '18:11', 'time_step_minutes': step}
            app.save_json(app.SETTINGS_FILE, settings)
            rng = Mock()
            rng.choice.side_effect = lambda values: max(values)
            with patch.object(app.random, 'SystemRandom', return_value=rng):
                for mode, expected in [('checkin', datetime(2026, 10, 26, 8, 47)),
                                       ('checkout', datetime(2026, 10, 26, 18, 11 if step==1 else 10))]:
                    target, _ = app.choose_target(mode, day, {'runs': {}, 'overtime_months': {'2026-10': []}})
                    self.assertEqual(target, expected)
                self.assertEqual(app.late_checkin_target(day), datetime(2026, 10, 26, 8, 47))

    def test_window_validation_and_saved_target_preservation(self):
        for fields in ({'checkin_start': '25:00'}, {'checkin_end': '08:00'}, {'time_step_minutes': 2},
                       {'time_step_minutes': True}, {'checkout_start': '08:00'}, {'checkout_end': '20:00'}):
            with self.assertRaises(ValueError):
                app.time_settings(fields)
        day = date(2026, 10, 26)
        state = {'runs': {str(day): {'checkout': {'target': '2026-10-26T18:35'}}}}
        app.save_json(app.SETTINGS_FILE, {'checkout_start': '17:00', 'checkout_end': '17:10'})
        self.assertEqual(app.choose_target('checkout', day, state)[0], datetime(2026, 10, 26, 18, 35))

    def test_one_minute_overtime_includes_non_five_minute_value(self):
        day = date(2026, 10, 26)
        app.save_json(app.SETTINGS_FILE, {'time_step_minutes': 1})
        state = {'runs': {}, 'overtime_months': {'2026-10': [str(day)]}}
        rng = Mock()
        rng.choice.side_effect = lambda values: list(values)[1]
        with patch.object(app.random, 'SystemRandom', return_value=rng):
            self.assertEqual(app.choose_target('checkout', day, state)[0], datetime(2026, 10, 26, 19, 1))

    def test_late_checkin_range_and_stability(self):
        day = date(2026, 10, 26)
        first = app.late_checkin_target(day)
        self.assertEqual(first.hour, 8)
        self.assertIn(first.minute, range(30, 51, 5))
        self.assertTrue(all(app.late_checkin_target(day) == first for _ in range(20)))

    def test_ten_hours_with_two_hour_setting_gives_five_days(self):
        app.save_json(app.SETTINGS_FILE, {'monthly_overtime_hours': 10, 'daily_overtime_hours': 2})
        state = {'runs': {}}
        days = app.get_overtime_dates(date(2026, 10, 1), state)
        self.assertEqual(len(days), 5)
        self.assertEqual(state['overtime_month_settings']['2026-10']['daily_hours'], 2)
        for day_key in days:
            target, _ = app.choose_target('checkout', date.fromisoformat(day_key), state)
            self.assertEqual(target.hour,20)
            self.assertIn(target.minute, range(0, 60, 5))

    def test_two_hour_window_can_reach_2055(self):
        day = date(2026, 10, 26)
        app.save_json(app.SETTINGS_FILE, {'monthly_overtime_hours': 10, 'daily_overtime_hours': 2})
        state = {'runs': {}, 'overtime_months': {'2026-10': [str(day)]},
                 'overtime_month_settings': {'2026-10': {'monthly_hours': 10, 'daily_hours': 2}}}
        rng = Mock()
        rng.choice.side_effect = lambda values: max(values)
        with patch.object(app.random, 'SystemRandom', return_value=rng):
            target, _ = app.choose_target('checkout', day, state)
        self.assertEqual(target, datetime(2026, 10, 26, 20, 55))

    def test_zero_monthly_hours_has_no_overtime_days(self):
        app.save_json(app.SETTINGS_FILE, {'monthly_overtime_hours': 0, 'daily_overtime_hours': 2})
        self.assertEqual(app.get_overtime_dates(date(2026, 10, 1), {'runs': {}}), set())

    def test_invalid_hour_budgets_are_rejected(self):
        for hours, daily in ((9, 2), (-1, 1), (10, 3), (10.5, 1), (True, 1)):
            with self.assertRaises(ValueError):
                app.overtime_settings({'monthly_overtime_hours': hours, 'daily_overtime_hours': daily})
        with self.assertRaises(ValueError):
            app.validate_overtime_capacity({'monthly_overtime_hours': 62, 'daily_overtime_hours': 1}, date(2026, 10, 1))

    def test_settings_changes_do_not_reroll_existing_month(self):
        state = {'runs': {}}
        original = app.get_overtime_dates(date(2026, 10, 1), state)
        app.save_json(app.SETTINGS_FILE, {'monthly_overtime_hours': 10, 'daily_overtime_hours': 2})
        self.assertEqual(app.get_overtime_dates(date(2026, 10, 1), state), original)
        self.assertEqual(state['overtime_month_settings']['2026-10']['daily_hours'], 1)
        self.assertEqual(len(app.get_overtime_dates(date(2026, 11, 1), state)), 5)

    def test_repair_uses_two_hour_plan_after_month_changes(self):
        app.save_json(app.SETTINGS_FILE, {'monthly_overtime_hours': 10, 'daily_overtime_hours': 2})
        state = {'runs': {}}
        selected = app.get_overtime_dates(date(2026, 10, 1), state)
        day = date.fromisoformat(sorted(selected)[0])
        target, _ = app.choose_target('checkout', day, state)
        app.save_json(app.SETTINGS_FILE, {'monthly_overtime_hours': 10, 'daily_overtime_hours': 1})
        app.get_overtime_dates(date(2026, 11, 1), state)
        self.assertEqual(app.recovery_target(day), target)

    def test_uncertain_without_target_can_be_planned_for_repair(self):
        day = date(2026, 10, 23)
        app.save_json(app.STATE_FILE, {'runs': {str(day): {'checkout': {'status': 'uncertain'}}}})
        target = app.recovery_target(day)
        self.assertIsInstance(target, datetime)
        self.assertEqual(app.load_json(app.STATE_FILE, {})['runs'][str(day)]['checkout']['status'], 'uncertain')

    def test_repair_success_preserves_other_runs_and_clears_queue(self):
        today = '2026-10-26'
        day = date(2026, 10, 23)
        app.save_json(app.STATE_FILE, {'runs': {today: {'checkin': {'status': 'in_progress'}}}})
        app.record_recovery(day, 'pending')
        app.record_recovery(day, 'success', datetime(2026, 10, 23, 19, 35))
        state = app.load_json(app.STATE_FILE, {})
        self.assertEqual(state['repair_pending'], [])
        self.assertEqual(state['runs'][today]['checkin']['status'], 'in_progress')
        self.assertEqual(state['runs'][str(day)]['checkout']['status'], 'success')

    def test_corrupt_state_fails_closed(self):
        Path(app.STATE_FILE).write_text('{broken', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            app.load_json(app.STATE_FILE, {'runs': {}})

    def test_pause_prevents_browser_action(self):
        app.save_json(app.SETTINGS_FILE, {'id': 'test', 'pw': 'test', 'enabled': False})
        with patch.object(app, 'perform_action') as action:
            self.assertFalse(app.run_scheduled('checkin', immediate=True))
            action.assert_not_called()

    def test_user_stop_flag_prevents_browser_action(self):
        Path(self.temp.name, 'automation.stop').write_text('intentional stop')
        with patch.object(app, 'perform_action') as action:
            self.assertFalse(app.run_scheduled('checkin', immediate=True))
            action.assert_not_called()

    def test_network_failure_before_login_submit_is_retryable(self):
        if not app.is_workday(date.today()):
            self.skipTest('Runs only on a real workday')
        with patch.object(app, 'create_driver', side_effect=ConnectionError('fixture offline')):
            self.assertFalse(app.run_scheduled('checkin', immediate=True))
        run = app.load_json(app.STATE_FILE, {})['runs'][str(date.today())]['checkin']
        self.assertEqual(run['status'], 'retryable')
        self.assertIn('retry_at', run)

    def test_failure_after_login_click_is_not_blindly_resubmitted(self):
        if not app.is_workday(date.today()):
            self.skipTest('Runs only on a real workday')
        driver = Mock()
        wait = Mock()
        wait.until.side_effect = [Mock(), app.TimeoutException('fixture response lost')]
        with patch.object(app, 'create_driver', return_value=driver), patch.object(app, 'WebDriverWait', return_value=wait):
            self.assertFalse(app.run_scheduled('checkin', immediate=True))
        run = app.load_json(app.STATE_FILE, {})['runs'][str(date.today())]['checkin']
        self.assertEqual(run['status'], 'uncertain')

    def test_logs_have_timestamp_and_redact_password(self):
        app._LOG_SECRETS.add('fixture-password-only')
        app.log_event('ConnectionError: failed, password=fixture-password-only')
        value = Path(app.LOG_FILE).read_text(encoding='utf-8')
        self.assertRegex(value, r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]')
        self.assertIn('ConnectionError', value)
        self.assertNotIn('fixture-password-only', value)

    def test_duplicate_checkin_and_state_update_during_browser(self):
        if not app.is_workday(date.today()):
            self.skipTest('Runs only on a real workday')
        previous = recovery.previous_workday(date.today(), app.is_workday)
        def action(*args):
            app.record_recovery(previous, 'success', datetime.combine(previous, datetime.min.time()).replace(hour=19, minute=35))
            return True
        with patch.object(app, 'perform_action', side_effect=action) as browser:
            self.assertTrue(app.run_scheduled('checkin', immediate=True))
            self.assertTrue(app.run_scheduled('checkin', immediate=True))
            self.assertEqual(browser.call_count, 1)
        state = app.load_json(app.STATE_FILE, {})
        self.assertEqual(state['runs'][str(previous)]['checkout']['status'], 'success')
        self.assertEqual(state['runs'][str(date.today())]['checkin']['status'], 'success')

    def test_file_lock_serializes_competing_workers(self):
        results = []
        def worker():
            with app.file_lock('test'):
                results.append('start')
                time.sleep(.05)
                results.append('end')
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results, ['start', 'end', 'start', 'end'])

    def test_task_definitions_include_daily_schedule_and_user_logon(self):
        with patch.object(app.subprocess, 'run', return_value=Mock(returncode=0, stdout='', stderr='')) as execute:
            app.register_tasks()
        commands = [base64.b64decode(call.args[0][-1]).decode('utf-16-le') for call in execute.call_args_list]
        self.assertEqual(len(commands), 1)
        self.assertIn("-At '08:30'", commands[0])
        self.assertIn("-At '18:05'", commands[0])
        self.assertIn('-AtLogOn -User $user', commands[0])
        self.assertIn("-Argument '--watchdog'", commands[0])
        self.assertEqual(commands[0].count('Register-ScheduledTask -TaskName'),4)
        self.assertTrue(all('-LogonType Interactive' in c for c in commands))
        self.assertIn('-EncodedCommand', execute.call_args.args[0])
        self.assertIn('GetCurrent().User.Value', commands[0])

    def test_registration_error_shows_cause_instead_of_full_command(self):
        result = Mock(returncode=1, stderr='예약 등록 실패 [자동출근]: 액세스가 거부되었습니다.', stdout='')
        with patch.object(app.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, '액세스가 거부') as caught:
                app.register_tasks()
        self.assertNotIn('EncodedCommand', str(caught.exception))
        self.assertLess(len(str(caught.exception)), 1200)

    def test_task_registration_preserves_non_ascii_path_and_apostrophe(self):
        root="C:\\Users\\한글 O'Name\\AppData\\Local\\AutoAttendance"
        with patch.object(app,'SOURCE_DIR',root), patch.object(app.subprocess,'run',return_value=Mock(returncode=0,stdout='',stderr='')) as execute:
            app.register_tasks()
        script=base64.b64decode(execute.call_args.args[0][-1]).decode('utf-16-le')
        self.assertIn("한글 O''Name",script)
        self.assertEqual(execute.call_args.kwargs['encoding'],'utf-8')

    def test_browser_driver_never_allocates_a_console(self):
        for bundled in (True, False):
            with patch.object(app.os.path, 'exists', return_value=bundled), \
                 patch.object(app, 'ChromeDriverManager') as manager, \
                 patch.object(app.webdriver, 'Chrome') as chrome, \
                 patch('site_access.reserve_session'):
                manager.return_value.install.return_value = 'fixture-driver.exe'
                app.create_driver()
                service = chrome.call_args.kwargs['service']
                self.assertEqual(service.creation_flags, app.subprocess.CREATE_NO_WINDOW)
                self.assertIn('--headless=new',chrome.call_args.kwargs['options'].arguments)

    def test_driver_version_probe_is_hidden_and_cached(self):
        probe = app.QuietChromeOSManager()
        with patch.object(app.subprocess, 'run', return_value=Mock(stdout='145.0.1234.5')) as execute:
            self.assertEqual(probe.get_browser_version_from_os(), '145.0.1234.5')
            self.assertEqual(probe.get_browser_version_from_os(), '145.0.1234.5')
            execute.assert_called_once()
            self.assertEqual(execute.call_args.kwargs['creationflags'], app.subprocess.CREATE_NO_WINDOW)
            self.assertFalse(execute.call_args.kwargs.get('shell', False))

    def test_known_mismatched_driver_is_skipped_before_launch(self):
        with patch.object(app.os.path,'exists',return_value=True),patch('site_access.reserve_session'), \
             patch.object(app,'QuietChromeOSManager') as version,patch.object(app.subprocess,'run',return_value=Mock(stdout='ChromeDriver 153.0.1')), \
             patch.object(app,'ChromeDriverManager') as manager,patch.object(app.webdriver,'Chrome') as chrome:
            version.return_value.get_browser_version_from_os.return_value='156.0.8078.48'
            manager.return_value.install.return_value='matching-driver.exe'
            app.create_driver()
        chrome.assert_called_once()
        self.assertEqual(chrome.call_args.kwargs['service'].path,'matching-driver.exe')


class RecoveryTests(unittest.TestCase):
    def test_time_parsing_and_blank_detection(self):
        self.assertEqual(recovery.parse_time('08 : 50'), (8, 50))
        for value in (':', ' : ', '', '--:--'):
            self.assertIsNone(recovery.parse_time(value))
            self.assertTrue(recovery.is_blank_time(value))
        self.assertIsNone(recovery.parse_time('25:99'))

    def test_previous_workday_skips_weekend_and_korean_holiday(self):
        self.assertEqual(recovery.previous_workday(date(2026, 10, 26), app.is_workday), date(2026, 10, 23))
        self.assertEqual(recovery.previous_workday(date(2026, 10, 12), app.is_workday), date(2026, 10, 8))

    def repair(self, row, edit_result=True, pending=()):
        page = Mock()
        page.record.return_value = row
        page.edit.return_value = edit_result
        status = Mock()
        target = Mock(return_value=datetime(2026, 10, 23, 19, 35))
        with patch.object(recovery, 'AttendancePage', return_value=page):
            recovery.repair_missing_checkouts(None, date(2026, 10, 26), app.is_workday, target, status, Mock(), pending)
        return page, status, target

    def test_only_missing_checkout_is_repaired(self):
        page, status, target = self.repair({'checkin': '08 : 50', 'checkout': ' : '})
        page.edit.assert_called_once_with(date(2026, 10, 23), 'checkout', target.return_value)
        status.assert_any_call(date(2026, 10, 23), 'success', target.return_value)

    def test_existing_checkout_is_not_overwritten(self):
        page, status, target = self.repair({'checkin': '08 : 50', 'checkout': '18 : 15'})
        page.edit.assert_not_called()
        target.assert_not_called()

    def test_no_checkin_means_no_fabricated_workday(self):
        page, status, target = self.repair({'checkin': ' : ', 'checkout': ' : '})
        page.edit.assert_not_called()
        target.assert_not_called()

    def test_unknown_checkout_format_is_not_overwritten(self):
        page, status, target = self.repair({'checkin': '08:50', 'checkout': '확인중'})
        page.edit.assert_not_called()
        target.assert_not_called()
        self.assertEqual(status.call_args_list, [unittest.mock.call(date(2026, 10, 23), 'pending')])

    def test_failed_repair_is_kept_pending(self):
        page = Mock()
        page.record.side_effect = RuntimeError('changed UI')
        status = Mock()
        with patch.object(recovery, 'AttendancePage', return_value=page):
            recovery.repair_missing_checkouts(None, date(2026, 10, 26), app.is_workday, Mock(), status, Mock())
        status.assert_called_once_with(date(2026, 10, 23), 'pending')

    def test_pending_days_are_retried_but_today_and_holidays_are_excluded(self):
        page, status, target = self.repair({'checkin': '08:50', 'checkout': '18:15'}, pending=['2026-10-22', '2026-10-26', '2026-10-09'])
        self.assertEqual([c.args[0] for c in page.record.call_args_list], [date(2026, 10, 22), date(2026, 10, 23)])

    def test_early_checkin_is_preserved(self):
        page = Mock()
        page.record.return_value = {'checkin': '08 : 55'}
        with patch.object(recovery, 'AttendancePage', return_value=page):
            recovery.correct_late_checkin(None, date(2026, 10, 26), Mock(), Mock())
        page.edit.assert_not_called()

    def test_late_checkin_is_corrected_without_targeting_checkout(self):
        page = Mock()
        page.record.return_value = {'checkin': '09 : 10'}
        target = datetime(2026, 10, 26, 8, 40)
        with patch.object(recovery, 'AttendancePage', return_value=page):
            recovery.correct_late_checkin(None, date(2026, 10, 26), Mock(return_value=target), Mock())
        page.edit.assert_called_once_with(date(2026, 10, 26), 'checkin', target)

    def test_yearless_page_does_not_guess_previous_year(self):
        page = recovery.AttendancePage(Mock(), date(2027, 1, 4))
        with patch.object(page, 'month_heading', return_value=(None, 1)):
            with self.assertRaisesRegex(RuntimeError, '전년도'):
                page.choose_month(date(2026, 12, 31))


if __name__ == '__main__':
    unittest.main()
