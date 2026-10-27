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

    def test_missing_regular_checkout_reuses_saved_time(self):
        key='2026-10-13'
        plan=monthly.build_plan([row(key,':')],{}, {'monthly_overtime_hours':0},date(2026,10,27),lambda d:True,saved_targets={key:'2026-10-13T18:40'})
        self.assertEqual(plan['changes'][0]['after'],{'checkout':'18:40'})

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
        self.assertEqual(len(plan['changes']), 2)
        self.assertEqual(plan['remaining_days'], 8)

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

    def test_exclusion_reconfirms_orphan_hold_and_overrides_other_times(self):
        key='2026-10-07'
        rows=[row(key,'17:25','09:35')]
        app.save_json(app.STATE_FILE,{'day_rules':{key:{'manual_hold':True,'exclude_overtime':True}}})
        self.assertEqual(monthly.resolve_holds(app,rows,date(2026,10,27)),[key])
        state=app.load_json(app.STATE_FILE,{})
        plan=monthly.build_plan(rows,state['day_rules'],{},date(2026,10,27),lambda d:True)
        self.assertEqual(plan['changes'][0]['after'],{'checkin':'09:00','checkout':'18:00'})

    def test_verified_after_requery_hold_is_resolved_without_site_write(self):
        key='2026-10-07';before=row(key,'19:35')
        app.save_json(app.STATE_FILE,{'day_rules':{key:{'manual_hold':True}},'monthly_reconcile_journal':[dict(date=key,before=before,after={'checkout':'18:00'},status='uncertain')]})
        self.assertEqual(monthly.resolve_holds(app,[row(key,'18:00')],date(2026,10,27)),[key])
        self.assertEqual(app.load_json(app.STATE_FILE,{})['monthly_reconcile_journal'][0]['status'],'verified_after_requery')

    def test_unapplied_goal_is_retained_for_retry(self):
        key='2026-10-07';before=row(key)
        app.save_json(app.STATE_FILE,{'day_rules':{key:{'manual_hold':True}},'monthly_reconcile_journal':[dict(date=key,before=before,after={'checkout':'19:45'},status='uncertain')]})
        monthly.resolve_holds(app,[before],date(2026,10,27))
        state=app.load_json(app.STATE_FILE,{})
        targets={key:state['runs'][key]['checkout']['target']}
        plan=monthly.build_plan([before],state['day_rules'],{},date(2026,10,27),lambda d:True,saved_targets=targets)
        self.assertEqual(plan['changes'][0]['after']['checkout'],'19:45')

    def test_mutually_exclusive_rule_is_rejected_without_write(self):
        app.save_json(app.STATE_FILE,{'day_rules':{}})
        with self.assertRaises(ValueError):
            changes.save_rule(app,dict(date='2026-10-07',vacation=True,exclude_overtime=True))
        self.assertEqual(app.load_json(app.STATE_FILE,{}),{'day_rules':{}})

    def test_preview_never_saves_even_when_edit_form_would_fail(self):
        page=MemoryPage([row(f'2026-09-{d:02}') for d in range(1,31)],fail=True)
        with patch.object(app,'create_driver'),patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            result=monthly.run(app,['2026-09'])
        self.assertTrue(result['ok']);self.assertTrue(result['rows']);self.assertEqual(len(result['all_rows']),30)
        self.assertEqual(page.saved,[])

    def test_empty_past_hold_is_cleared_without_creating_a_workday(self):
        key='2026-10-01'
        app.save_json(app.STATE_FILE, {'day_rules': {key: {'manual_hold': True, 'vacation': True}},
                                      'monthly_reconcile_journal': [{'date':key,'status':'uncertain'}]})
        rows=[row(key, ' : ', ' : ')]
        cleared=monthly.clear_empty_holds(app, rows, date(2026,10,27))
        self.assertEqual(cleared,[key])
        state=app.load_json(app.STATE_FILE,{})
        self.assertFalse(state['day_rules'][key]['manual_hold'])
        self.assertTrue(state['day_rules'][key]['vacation'])
        self.assertEqual(state['monthly_reconcile_journal'][0]['status'],'empty_record_confirmed')
        self.assertNotIn('runs',state)
        plan=monthly.build_plan(rows,state['day_rules'],{},date(2026,10,27),lambda d:True)
        self.assertEqual(plan['changes'],[])

    def test_present_or_unknown_or_today_records_keep_their_hold(self):
        rows=[row('2026-10-01','18:00'),row('2026-10-02','확인중',':'),row('2026-10-27',':',':')]
        app.save_json(app.STATE_FILE, {'day_rules':{r['date']:{'manual_hold':True} for r in rows}})
        self.assertEqual(monthly.clear_empty_holds(app,rows,date(2026,10,27)),[])
        self.assertTrue(all(r['manual_hold'] for r in app.load_json(app.STATE_FILE,{})['day_rules'].values()))

    def test_startup_runs_only_checkin_then_checkout(self):
        calls=[]
        def scheduled(mode,**kw):
            calls.append(mode);return True
        with patch.object(app,'choose_target'),patch.object(app,'run_scheduled',side_effect=scheduled):
            self.assertTrue(app.run_startup())
        self.assertEqual(calls,['checkin','checkout'])

    def test_failed_startup_checkin_does_not_checkout(self):
        with patch.object(app,'choose_target'),patch.object(app,'run_scheduled',return_value=False) as scheduled:
            self.assertFalse(app.run_startup())
        scheduled.assert_called_once_with('checkin',immediate=True)

    def test_preview_then_apply_all_and_second_preview_is_noop(self):
        rows=[row(f'2026-09-{d:02}') for d in range(1,31)];page=MemoryPage(rows)
        app.save_json(app.SETTINGS_FILE,{'id':'fixture','pw':'fixture','monthly_overtime_hours':10})
        app.save_json(app.STATE_FILE,{'day_rules':{'2026-09-01':{'exclude_overtime':True}},'overtime_month_settings':{'2026-09':{'monthly_hours':4,'daily_hours':2}}})
        driver=Mock()
        with patch.object(app,'create_driver',return_value=driver),patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            first=monthly.run(app,['2026-09'])
            self.assertEqual(page.saved,[])
            requested=[dict(date=e['date'],**e['after']) for e in first['rows'] if e['selectable']]
            result=monthly.apply_reviewed(app,{'plan_id':first['plan_id'],'rows':requested})
            second=monthly.run(app,['2026-09'])
        self.assertTrue(result['ok']);self.assertEqual(len(page.saved),3)
        self.assertEqual(second['rows'],[]);self.assertEqual(first['target_days'],2)
        self.assertEqual(driver.quit.call_count,3)

    def test_user_can_uncheck_a_date_and_edit_proposed_time(self):
        page=MemoryPage([row(f'2026-09-{d:02}') for d in range(1,31)])
        app.save_json(app.SETTINGS_FILE,{'id':'fixture','pw':'fixture','monthly_overtime_hours':2})
        with patch.object(app,'create_driver'),patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            preview=monthly.run(app,['2026-09'])
            selected=preview['rows'][0]
            monthly.apply_reviewed(app,{'plan_id':preview['plan_id'],'rows':[dict(date=selected['date'],checkin='09:15',checkout='19:35')]})
            with self.assertRaises(ValueError):
                monthly.apply_reviewed(app,{'plan_id':preview['plan_id'],'rows':[dict(date=selected['date'],checkin='09:15',checkout='19:35')]})
        self.assertEqual(page.saved,[selected['date']])
        self.assertEqual(page.rows[selected['date']]['checkin'],'09:15')
        self.assertEqual(page.rows[selected['date']]['checkout'],'19:35')

    def test_background_month_processing_is_disabled(self):
        with patch.object(app,'create_driver') as driver:
            result=monthly.run(app,['2026-09'],background=True)
        self.assertFalse(result['ok']);driver.assert_not_called()

    def test_partial_apply_reports_saved_failed_and_unprocessed_dates(self):
        page=MemoryPage([row(f'2026-09-{d:02}') for d in range(1,31)])
        original=page.correct
        def fail_second(day,targets,before):
            if len(page.saved)==1:raise RuntimeError('수정 입력 화면 찾기 실패')
            return original(day,targets,before)
        with patch.object(app,'create_driver'),patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            preview=monthly.run(app,['2026-09'])
            with patch.object(page,'correct',side_effect=fail_second):
                result=monthly.apply_reviewed(app,{'plan_id':preview['plan_id'],'rows':[dict(date=e['date'],**e['after']) for e in preview['rows'][:3]]})
        self.assertFalse(result['ok']);self.assertEqual(len(page.saved),1)
        self.assertIn('개별 저장 확인',result['rows'][0]['status'])
        self.assertIn('저장 실패',result['rows'][1]['status'])
        self.assertIn('미처리',result['rows'][2]['status'])
        self.assertIn('전체 정리가 완료되지 않았습니다',result['error'])

    def test_final_month_mismatch_is_not_a_success(self):
        page=MemoryPage([row(f'2026-09-{d:02}') for d in range(1,31)])
        original=monthly._read_month
        def changed_month(*args):
            result=original(*args)
            for entry in result:
                if entry['date'] in page.saved:entry['checkout']='18:00'
            return result
        with patch.object(app,'create_driver'),patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            preview=monthly.run(app,['2026-09']);entry=preview['rows'][0]
            with patch.object(monthly,'_read_month',side_effect=changed_month):
                result=monthly.apply_reviewed(app,{'plan_id':preview['plan_id'],'rows':[dict(date=entry['date'],**entry['after'])]})
        self.assertFalse(result['ok']);self.assertIn('최종 월 조회 값',result['error'])

    def test_review_rejects_changed_calendar_before_connecting(self):
        page=MemoryPage([row(f'2026-09-{d:02}') for d in range(1,31)])
        with patch.object(app,'create_driver') as driver,patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            preview=monthly.run(app,['2026-09']);entry=preview['rows'][0]
            state=app.load_json(app.STATE_FILE,{})
            state.setdefault('day_rules',{})[entry['date']]={'vacation':True}
            app.save_json(app.STATE_FILE,state)
            with self.assertRaisesRegex(ValueError,'달력 설정'):
                monthly.apply_reviewed(app,{'plan_id':preview['plan_id'],'rows':[dict(date=entry['date'],**entry['after'])]})
            self.assertEqual(driver.call_count,1)
        self.assertEqual(page.saved,[])

    def test_review_rechecks_site_before_any_write(self):
        page=MemoryPage([row(f'2026-09-{d:02}') for d in range(1,31)])
        with patch.object(app,'create_driver'),patch.object(monthly,'WebDriverWait'),patch.object(monthly,'AttendancePage',return_value=page):
            preview=monthly.run(app,['2026-09'])
            entries=preview['rows'][:2]
            page.rows[entries[-1]['date']]['note']='외부 수정'
            with self.assertRaisesRegex(ValueError,'기록이 바뀌었습니다'):
                monthly.apply_reviewed(app,{'plan_id':preview['plan_id'],'rows':[dict(date=e['date'],**e['after']) for e in entries]})
        self.assertEqual(page.saved,[])

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

    def test_failure_before_submit_does_not_create_site_confirmation_hold(self):
        rows=[row('2026-10-01')]
        page=MemoryPage(rows,fail=True)
        page.driver=Mock(_workday_write_submitted=False)
        plan=monthly.build_plan(rows,{}, {},date(2026,10,27),lambda d:True)
        with self.assertRaises(RuntimeError):monthly.apply_plan(app,page,plan,'2026-10')
        state=app.load_json(app.STATE_FILE,{})
        self.assertFalse(state['day_rules']['2026-10-01']['manual_hold'])
        self.assertEqual(state['monthly_reconcile_journal'][0]['status'],'not_submitted')

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

    def test_rule_save_never_connects_or_starts_month_processing(self):
        job=dict(operation='rules',dates=['2026-10-01'],vacation=False,exclude_overtime=True)
        with patch.object(monthly,'run') as sync,patch.object(app,'create_driver') as driver:
            result=changes.run_job(app,job)
        self.assertTrue(result['ok']);sync.assert_not_called();driver.assert_not_called()
        self.assertTrue(app.load_json(app.STATE_FILE,{})['day_rules']['2026-10-01']['exclude_overtime'])


if __name__ == '__main__':
    unittest.main()
