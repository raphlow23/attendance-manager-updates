import unittest
from datetime import date,datetime
from unittest.mock import Mock,patch
import test_attendance as fixtures
import main as app
import attendance_recovery as recovery

class EventSchedule(unittest.TestCase):
    setUp=fixtures.StateTests.setUp
    tearDown=fixtures.StateTests.tearDown
    def test_event_overrides_both_cached_targets_and_recovery(self):
        day=date(2026,11,2);key=str(day)
        state=dict(day_rules={key:{'exclude_overtime':True}},runs={key:dict(checkin={'target':key+'T08:45'},checkout={'target':key+'T20:30'})})
        for mode,clock in (('checkin','09:00'),('checkout','18:05')):
            target,_=app.choose_target(mode,day,state)
            self.assertEqual(target.strftime('%H:%M'),clock)
        self.assertEqual(app.recovery_target(day).strftime('%H:%M'),'18:05')
    def test_vacation_does_not_open_browser_in_either_mode(self):
        day=date.today();app.save_json(app.STATE_FILE,{'day_rules':{str(day):{'vacation':True}}})
        with patch.object(app,'is_workday',return_value=True),patch.object(app,'perform_action') as action:
            self.assertTrue(app.run_scheduled('checkin',immediate=True))
            self.assertTrue(app.run_scheduled('checkout'))
            action.assert_not_called()
    def test_logon_immediate_does_not_replace_event_target_with_current_time(self):
        day=date.today()
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return cls.combine(day,datetime.min.time()).replace(hour=9,minute=30)
        app.save_json(app.STATE_FILE,{'day_rules':{str(day):{'exclude_overtime':True}}})
        with patch.object(app,'datetime',Clock),patch.object(app,'is_workday',return_value=True),patch.object(app,'perform_action',return_value=True):
            self.assertTrue(app.run_scheduled('checkin',immediate=True))
        self.assertEqual(app.load_json(app.STATE_FILE,{})['runs'][str(day)]['checkin']['target'],str(day)+'T09:00')
    def test_event_matching_times_are_not_written_again(self):
        with patch.object(recovery,'AttendancePage') as page:
            page.return_value.record.return_value=dict(checkin='09:00',checkout='18:05',note='유지')
            recovery.enforce_event_times(Mock(),date(2026,11,2),'checkout',Mock())
            page.return_value.correct.assert_not_called()
    def test_event_registration_corrects_only_needed_fields(self):
        day=date(2026,11,2);before=dict(checkin='08:40',checkout='19:30',note='유지')
        with patch.object(recovery,'AttendancePage') as page:
            page.return_value.record.return_value=before
            recovery.enforce_event_times(Mock(),day,'checkin',Mock())
            page.return_value.correct.assert_called_once_with(day,{'checkin':datetime(2026,11,2,9)},before)
            page.return_value.correct.reset_mock()
            recovery.enforce_event_times(Mock(),day,'checkout',Mock())
            page.return_value.correct.assert_called_once_with(day,dict(checkin=datetime(2026,11,2,9),checkout=datetime(2026,11,2,18,5)),before)
    def test_replacement_overtime_excludes_vacation_event_and_keeps_completed_day(self):
        state=dict(overtime_months={'2026-11':['2026-11-02','2026-11-03']},overtime_month_settings={'2026-11':dict(monthly_hours=2,daily_hours=1)},
                   day_rules={'2026-11-02':{'exclude_overtime':True},'2026-11-05':{'vacation':True}},
                   runs={'2026-11-03':{'checkout':{'status':'success','target':'2026-11-03T19:20'}},'2026-11-04':{'checkout':{'target':'2026-11-04T18:10'}}})
        with patch.object(app.random.SystemRandom,'sample',side_effect=lambda candidates,n:candidates[:n]):
            selected=app.get_overtime_dates(date(2026,11,1),state)
        self.assertEqual(selected,{'2026-11-03','2026-11-04'})
        self.assertNotIn('target',state['runs']['2026-11-04']['checkout'])
        self.assertEqual(state['runs']['2026-11-03']['checkout']['target'],'2026-11-03T19:20')
