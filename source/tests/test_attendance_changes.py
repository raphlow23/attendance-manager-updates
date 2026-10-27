import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from attendance_changes import blocked, correct_reviewed, reviewed_targets, save_rule, summarize_month
from attendance_recovery import AttendancePage
import test_attendance as fixtures
from test_edit_form import FakeSite
import main as app


class ChangesTests(unittest.TestCase):
    def test_two_times_one_save_preserves_notes(self):
        site = FakeSite(checkin='08 : 50', checkout='19 : 55')
        page = AttendancePage(site, date(2026, 10, 26))
        before = page.record(date(2026, 10, 23))
        page.correct(date(2026, 10, 23), {
            'checkin': datetime(2026, 10, 23, 9), 'checkout': datetime(2026, 10, 23, 18)}, before)
        self.assertEqual(site.checkin.text, '09 : 00')
        self.assertEqual(site.checkout.text, '18 : 00')
        self.assertEqual(site.note.text, '원래 비고')

    def test_stale_snapshot_does_not_open_editor(self):
        site = FakeSite(checkout='18 : 00')
        page = AttendancePage(site, date(2026, 10, 26))
        before = dict(page.record(date(2026, 10, 23)), checkout='17 : 00')
        with self.assertRaisesRegex(RuntimeError, '변경'):
            page.correct(date(2026, 10, 23), {'checkout': datetime(2026, 10, 23, 18)}, before)
        self.assertFalse(site.editing)

    def test_actual_confirmation_reason_and_past_required(self):
        for data in ({}, {'confirmed_actual': True}, {'confirmed_actual': True, 'reason': '실제 퇴근 누락', 'checkout': '25:00'}):
            with self.assertRaises(ValueError):
                reviewed_targets(dict(date='2026-10-23', **data), date(2026, 10, 26))
        with self.assertRaises(ValueError):
            reviewed_targets(dict(date='2026-10-27', confirmed_actual=True, reason='x', checkout='18:00'), date(2026, 10, 26))


class RulesTests(unittest.TestCase):
    setUp = fixtures.StateTests.setUp
    tearDown = fixtures.StateTests.tearDown

    def test_bulk_rule_save_and_clear_keeps_history_and_site_records(self):
        days=['2026-10-23','2026-10-26','2026-11-02']
        app.save_json(app.STATE_FILE, {'runs': {days[0]: {'checkout': {'status':'success','target':'2026-10-23T19:15'}}}})
        save_rule(app, dict(dates=days, vacation=True, exclude_overtime=False))
        state=app.load_json(app.STATE_FILE,{})
        self.assertTrue(all(state['day_rules'][key]['vacation'] for key in days))
        self.assertEqual(state['runs'][days[0]]['checkout']['target'],'2026-10-23T19:15')
        save_rule(app, dict(dates=days[:2], vacation=False, exclude_overtime=True))
        state=app.load_json(app.STATE_FILE,{})
        self.assertTrue(state['day_rules'][days[2]]['vacation'])
        self.assertTrue(all(state['day_rules'][key]['exclude_overtime'] for key in days[:2]))

    def test_bulk_invalid_date_is_atomic(self):
        before={'day_rules':{'2026-10-01':{'vacation':True}}}
        app.save_json(app.STATE_FILE,before)
        with self.assertRaises(ValueError):
            save_rule(app, dict(dates=['2026-10-23','invalid'],vacation=True,exclude_overtime=False))
        self.assertEqual(app.load_json(app.STATE_FILE,{}),before)

    def test_summary_counts_existing_records_without_changing_dates(self):
        rows=[dict(date='2026-10-23',checkin='08:30',checkout='19:55',rule={'vacation':True}),
              dict(date='2026-10-26',checkin='09:00',checkout='18:00',rule={}),
              dict(date='2026-10-27',checkin=':',checkout='20:00',rule={})]
        summary=summarize_month(rows,{},lambda day:True)
        self.assertEqual(summary['recorded_days'],1)
        self.assertEqual(summary['remaining_days'],9)
        self.assertEqual(summary['excluded_record_days'],1)
        self.assertEqual(rows[0]['checkout'],'19:55')
        self.assertEqual(summarize_month(rows,{'monthly_overtime_hours':10,'daily_overtime_hours':2},lambda day:True)['target_days'],5)
    def test_vacation_blocks_cached_target_and_both_modes(self):
        day = date(2026, 10, 23)
        state = {'day_rules': {str(day): {'vacation': True}}, 'runs': {str(day): {'checkout': {'target': '2026-10-23T19:55'}}}}
        for mode in ('checkin', 'checkout'):
            self.assertIsNone(app.choose_target(mode, day, state)[0])

    def test_exclude_cancels_pending_target_without_moving_other_days(self):
        day = date(2026, 10, 23)
        state = {'overtime_months': {'2026-10': [str(day), '2026-10-22']}, 'runs': {str(day): {'checkout': {'target': '2026-10-23T19:55'}}}}
        app.save_json(app.STATE_FILE, state)
        save_rule(app, dict(date=str(day), vacation=False, exclude_overtime=True))
        state = app.load_json(app.STATE_FILE, {})
        self.assertEqual(app.get_overtime_dates(day, state), {'2026-10-22'})
        target, _ = app.choose_target('checkout', day, state)
        self.assertLess(target.hour, 19)
        self.assertEqual(state['overtime_months']['2026-10'], [str(day), '2026-10-22'])

    def test_uncertain_correction_holds_automation(self):
        day = date(2026, 10, 23)
        page = Mock()
        page.record.return_value = dict(checkin='08:50', checkout='18:15', note='keep')
        job = dict(date=str(day), confirmed_actual=True, reason='실제 퇴근 기록 정정', checkout='18:00', before=page.record.return_value)
        page.correct.side_effect = RuntimeError('network disconnected after save')
        with self.assertRaises(RuntimeError):
            correct_reviewed(app, page, job, date(2026, 10, 26))
        self.assertTrue(blocked(app.load_json(app.STATE_FILE, {}), day))
        page.correct.side_effect = None
        correct_reviewed(app, page, job, date(2026, 10, 26))
        state = app.load_json(app.STATE_FILE, {})
        self.assertFalse(blocked(state, day))
        self.assertEqual(state['runs'][str(day)]['checkout']['status'], 'success')
        self.assertIsNone(app.choose_target('checkout', day, state)[0])

    def test_submitted_overtime_prevents_silent_change(self):
        day = date(2026, 10, 23)
        app.save_json(app.STATE_FILE, {'overtime_applications': {str(day): {'status': 'success'}}})
        page = Mock()
        page.record.return_value = dict(checkin='08:50', checkout='19:15', note='keep')
        job = dict(date=str(day), confirmed_actual=True, reason='정정', checkout='18:00', before=page.record.return_value)
        with self.assertRaisesRegex(ValueError, '신청'):
            correct_reviewed(app, page, job, date(2026, 10, 26))
        page.correct.assert_not_called()


if __name__ == '__main__':
    unittest.main()
