import calendar
import random
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'app')]
import main as app
import attendance_changes as changes
import monthly_reconcile as monthly
from resident import MonthlyPass
import test_attendance as fixtures


def row(key, checkout='18:15', checkin='08:35'):
    return dict(date=key, checkin=checkin, checkout=checkout, note='비고 보존')


class MemoryPage:
    def __init__(self, rows, fail=False):
        self.rows = {r['date']: dict(r) for r in rows}
        self.fail = fail
        self.saved = []

    def open(self):
        pass

    def record(self, day):
        return dict(self.rows[str(day)])

    def correct(self, day, targets, before):
        if self.fail:
            raise RuntimeError('test: response lost')
        current = self.rows[str(day)]
        if any(current[k] != before[k] for k in monthly.FIELDS):
            raise RuntimeError('changed row')
        for key, value in targets.items():
            current[key] = value.strftime('%H:%M')
        self.saved.append(str(day))
        return True


class PlannerTests(unittest.TestCase):
    def test_daily_pass_is_bounded_and_checkout_can_trigger_second_pass(self):
        state = MonthlyPass()
        day = date(2026, 10, 27)
        self.assertTrue(state.ready(day, 'checkin', 0))
        state.begin(0);state.result={'ok':False}
        self.assertFalse(state.ready(day, 'checkin', 59))
        self.assertTrue(state.ready(day, 'checkin', 60))
        state.begin(60);state.result={'ok':False}
        self.assertTrue(state.ready(day, 'checkin', 120))
        state.begin(120);state.result={'ok':False}
        self.assertFalse(state.ready(day, 'checkin', 180))
        self.assertTrue(state.ready(day, 'checkout', 181))
        state.begin(181);state.result={'ok':True}
        self.assertFalse(state.ready(day, 'checkout', 300))
        self.assertTrue(state.ready(date(2026, 10, 28), 'checkin', 301))

    def workday(self, day):
        return day.weekday() < 5 and day != date(2026, 10, 9)

    def rows(self):
        return [row(f'2026-10-{day:02}') for day in range(1, 32)]

    def plan(self, rows, rules=None, settings=None):
        return monthly.build_plan(rows, rules or {}, settings or {}, date(2026, 10, 27), self.workday, random.Random(7))

    def test_ten_days_reallocated_around_vacation_and_exclusion(self):
        rows = self.rows()
        rows[1]['checkout'] = '18:45'
        rules = {'2026-10-01': {'exclude_overtime': True}, '2026-10-02': {'vacation': True}}
        plan = self.plan(rows, rules)
        self.assertEqual(plan['target_days'], 10)
        self.assertEqual(plan['overtime_days'], 10)
        changes = {c['date']: c for c in plan['changes']}
        self.assertEqual(changes['2026-10-01']['after'], {'checkin': '09:00', 'checkout': '18:00'})
        self.assertNotIn('2026-10-02', changes)
        overtime = [c for c in plan['changes'] if c['after'].get('checkout', '') >= '19:00']
        self.assertEqual(len(overtime), 10)
        for c in overtime:
            self.assertTrue(self.workday(date.fromisoformat(c['date'])))
            self.assertLessEqual(c['date'], '2026-10-27')
            self.assertLessEqual(c['after']['checkout'], '19:55')
            self.assertEqual(int(c['after']['checkout'][3:]) % 5, 0)

    def test_vacation_before_19_is_unchanged_even_if_both_flags(self):
        plan = self.plan([row('2026-10-02', '18:45')], {'2026-10-02': {'vacation': True, 'exclude_overtime': True}})
        self.assertEqual(plan['changes'], [])

    def test_vacation_after_19_preserves_checkin_and_note(self):
        plan = self.plan([row('2026-10-02', '20:55')], {'2026-10-02': {'vacation': True}})
        self.assertEqual(plan['changes'][0]['after'], {'checkout': '18:00'})
        self.assertEqual(plan['changes'][0]['before']['note'], '비고 보존')

    def test_excluded_past_day_with_checkin_can_fill_missing_checkout(self):
        plan = self.plan([row('2026-10-02', ':')], {'2026-10-02': {'exclude_overtime': True}})
        self.assertEqual(plan['changes'][0]['after'], {'checkin': '09:00', 'checkout': '18:00'})

    def test_missing_today_checkout_and_unknown_time_are_not_filled(self):
        rows = [row('2026-10-27', ':'), row('2026-10-02', '확인중'), row('2026-10-06', ':', ':')]
        rules = {r['date']: {'exclude_overtime': True} for r in rows}
        self.assertEqual(self.plan(rows, rules)['changes'], [])

    def test_two_hour_setting_gives_five_days_and_stays_within_window(self):
        plan = self.plan(self.rows(), settings={'monthly_overtime_hours': 10, 'daily_overtime_hours': 2, 'time_step_minutes': 1})
        self.assertEqual(plan['target_days'], 5)
        self.assertEqual(plan['overtime_days'], 5)
        self.assertTrue(all('19:00' <= c['after']['checkout'] <= '20:55' for c in plan['changes']))

    def test_not_enough_completed_days_does_not_create_absent_records(self):
        plan = self.plan([row('2026-10-01'), row('2026-10-02', ':'), row('2026-10-06', ':', ':')])
        self.assertEqual(len(plan['changes']), 1)
        self.assertEqual(plan['remaining_days'], 9)

    def test_existing_overtime_kept_and_excess_reduced(self):
        plan = self.plan([row(f'2026-10-{d:02}', '19:35') for d in (1, 2, 6)], settings={'monthly_overtime_hours': 2})
        self.assertEqual(plan['overtime_days'], 2)
        self.assertEqual(plan['changes'][0]['date'], '2026-10-06')
        self.assertEqual(plan['changes'][0]['after']['checkout'], '18:00')

    def test_uncertain_day_blocks_new_month_plan(self):
        with self.assertRaisesRegex(RuntimeError, '불확실'):
            self.plan(self.rows(), {'2026-10-02': {'manual_hold': True}})

    def test_other_origin_is_rejected(self):
        with self.assertRaises(ValueError):
            monthly.require_site(Mock(SITE_URL='https://different.invalid'))


class ApplyTests(unittest.TestCase):
    setUp = fixtures.StateTests.setUp
    tearDown = fixtures.StateTests.tearDown

    def test_startup_runs_checkin_then_month_sync_then_checkout(self):
        calls = []
        def scheduled(mode, **kw):
            calls.append(mode)
            return True
        with patch.object(app, 'choose_target'), patch.object(app, 'run_scheduled', side_effect=scheduled), patch.object(app, 'run_monthly_reconcile', side_effect=lambda: calls.append('monthly')):
            self.assertTrue(app.run_startup())
        self.assertEqual(calls, ['checkin', 'monthly', 'checkout'])

    def test_failed_startup_checkin_does_not_checkout_or_mutate_month(self):
        with patch.object(app, 'choose_target'), patch.object(app, 'run_scheduled', return_value=False) as scheduled, patch.object(app, 'run_monthly_reconcile') as sync:
            self.assertFalse(app.run_startup())
        scheduled.assert_called_once_with('checkin', immediate=True)
        sync.assert_not_called()

    def test_full_month_run_verifies_server_rows_and_second_pass_is_noop(self):
        rows = [row(f'2026-09-{day:02}') for day in range(1, 31)]
        page = MemoryPage(rows)
        app.save_json(app.SETTINGS_FILE, {'id': 'fixture', 'pw': 'fixture', 'monthly_overtime_hours': 10})
        app.save_json(app.STATE_FILE, {'day_rules': {'2026-09-01': {'exclude_overtime': True}}, 'reconcile_pending_months': ['2026-09'],
                                      'overtime_month_settings': {'2026-09': {'monthly_hours': 4, 'daily_hours': 2}}})
        driver = Mock()
        with patch.object(app, 'create_driver', return_value=driver), patch.object(monthly, 'WebDriverWait'), patch.object(monthly, 'AttendancePage', return_value=page):
            first = monthly.run(app, ['2026-09'])
            second = monthly.run(app, ['2026-09'])
        self.assertEqual(first['months'][0]['changed'], 3)
        self.assertEqual(second['months'][0]['changed'], 0)
        self.assertEqual(second['summary']['recorded_days'], 2)
        self.assertEqual(second['summary']['target_days'], 2)
        self.assertEqual(driver.quit.call_count, 2)
        self.assertEqual(app.load_json(app.STATE_FILE, {})['reconcile_pending_months'], [])

    def test_background_recovery_error_is_not_reported_as_all_success(self):
        page = MemoryPage([row(f'2026-09-{day:02}') for day in range(1,31)])
        app.save_json(app.SETTINGS_FILE, {'id': 'fixture', 'pw': 'fixture', 'monthly_overtime_hours': 0})
        with patch.object(app, 'create_driver'), patch.object(monthly, 'WebDriverWait'), patch.object(monthly, 'AttendancePage', return_value=page), patch.object(app, 'recover_previous_days', side_effect=RuntimeError('fixture recovery error')):
            result = monthly.run(app, ['2026-09'], background=True)
        self.assertTrue(result['warnings'])
        self.assertIn('누락 퇴근 보완 확인 필요', result['message'])

    def test_repeated_reconcile_is_idempotent_and_preserves_notes(self):
        rows = [row('2026-10-01'), row('2026-10-02'), row('2026-10-06')]
        rules = {'2026-10-01': {'exclude_overtime': True}}
        app.save_json(app.STATE_FILE, {'day_rules': rules})
        page = MemoryPage(rows)
        settings = {'monthly_overtime_hours': 2}
        plan = monthly.build_plan(rows, rules, settings, date(2026, 10, 27), lambda d: True, random.Random(1))
        monthly.apply_plan(app, page, plan, '2026-10')
        again = monthly.build_plan(list(page.rows.values()), rules, settings, date(2026, 10, 27), lambda d: True)
        self.assertEqual(again['changes'], [])
        self.assertTrue(all(r['note'] == '비고 보존' for r in page.rows.values()))
        state = app.load_json(app.STATE_FILE, {})
        self.assertTrue(all(j['status'] == 'verified' for j in state['monthly_reconcile_journal']))

    def test_unknown_remote_result_leaves_hold_and_uncertain_journal(self):
        rows = [row('2026-10-01')]
        plan = monthly.build_plan(rows, {}, {}, date(2026, 10, 27), lambda d: True)
        with self.assertRaises(RuntimeError):
            monthly.apply_plan(app, MemoryPage(rows, fail=True), plan, '2026-10')
        state = app.load_json(app.STATE_FILE, {})
        self.assertTrue(state['day_rules']['2026-10-01']['manual_hold'])
        self.assertEqual(state['monthly_reconcile_journal'][0]['status'], 'uncertain')

    def test_preflight_conflict_prevents_all_writes(self):
        rows = [row('2026-10-01'), row('2026-10-02')]
        plan = monthly.build_plan(rows, {}, {}, date(2026, 10, 27), lambda d: True)
        page = MemoryPage(rows)
        page.rows['2026-10-02']['note'] = '다른 곳에서 수정'
        with self.assertRaises(RuntimeError):
            monthly.apply_plan(app, page, plan, '2026-10')
        self.assertEqual(page.saved, [])

    def test_submitted_application_is_not_silently_changed(self):
        rows = [row('2026-10-01')]
        app.save_json(app.STATE_FILE, {'overtime_applications': {'2026-10-01': {'status': 'success'}}})
        page = MemoryPage(rows)
        plan = monthly.build_plan(rows, {}, {}, date(2026, 10, 27), lambda d: True)
        with self.assertRaises(ValueError):
            monthly.apply_plan(app, page, plan, '2026-10')
        self.assertEqual(page.saved, [])

    def test_rule_save_is_preserved_when_remote_reconcile_fails(self):
        job = dict(operation='rules', dates=['2026-10-01'], vacation=False, exclude_overtime=True)
        with patch.object(monthly, 'run', side_effect=RuntimeError('fixture offline')):
            result = changes.run_job(app, job)
        self.assertTrue(result['ok'])
        self.assertFalse(result['reconcile_ok'])
        state = app.load_json(app.STATE_FILE, {})
        self.assertIn('2026-10', state['reconcile_pending_months'])
        self.assertTrue(state['day_rules']['2026-10-01']['exclude_overtime'])


if __name__ == '__main__':
    unittest.main()
