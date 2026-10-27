import sys,time,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app')]
import business_trips as trips
import main as app
import test_attendance as fixtures

def attendance(day,ci='08:35',co='18:00'):return dict(date=day,checkin=ci,checkout=co,note='')

class TripPlanning(unittest.TestCase):
    def rows(self):
        return trips.make_rows([attendance('2026-10-07'),attendance('2026-10-13'),attendance('2026-10-14')],{'2026-10-07':{'exclude_overtime':True}},[],date(2026,10,27))
    def test_exclusion_is_full_day_but_charged_four_hours(self):
        row=self.rows()[0]
        self.assertTrue(row['mandatory'] and row['selected'])
        self.assertEqual((row['start'],row['end'],row['hours'],row['amount']),('09:00','18:00',4,20000))
    def test_only_completed_attendance_days_are_shown(self):
        rows=[attendance('2026-10-01',':',':'),attendance('2026-10-02',co=':'),attendance('2026-10-03'),attendance('2026-10-30')]
        result=trips.make_rows(rows,{'2026-10-30':{'exclude_overtime':True}},[],date(2026,10,27))
        self.assertEqual([r['date'] for r in result],['2026-10-03'])
    def test_budget_allocation_uses_selected_dates_only(self):
        rows=self.rows();rows[1]['selected']=True
        result,summary=trips.allocate(rows,50000)
        self.assertFalse(result[2]['selected']);self.assertEqual(summary['remaining_amount'],10000)
        self.assertIn('출장 추가 필요',summary['message'])
    def test_two_selected_dates_can_mix_two_and_four_hours(self):
        rows=self.rows();rows[1]['selected']=rows[2]['selected']=True
        result,summary=trips.allocate(rows,50000)
        self.assertEqual(sorted(r['hours'] for r in result[1:]),[2,4]);self.assertEqual(summary['remaining_amount'],0)
        self.assertFalse(self.rows()[1]['selected'])
    def test_mandatory_dates_cannot_be_unchecked(self):
        with self.assertRaisesRegex(ValueError,'필수 포함'):
            trips.merge_entries(self.rows(),[dict(date='2026-10-07',selected=False)])
    def test_normal_trip_end_is_derived_and_cannot_exceed_attendance(self):
        row=self.rows()[1]
        self.assertEqual(trips.window(row,2,14)['end'],'16:00')
        with self.assertRaises(ValueError):trips.window(row,4,16)
        with self.assertRaises(ValueError):trips.window(row,2,8)
    def test_existing_day_is_capped_at_four_hours_and_not_selected(self):
        old=[dict(date='2026-10-07',start='09:00',end='18:00')]
        result=trips.make_rows([attendance('2026-10-07')],{'2026-10-07':{'exclude_overtime':True}},old,date(2026,10,27))
        self.assertEqual(result[0]['existing_amount'],20000);self.assertFalse(result[0]['selected']);self.assertTrue(result[0]['blocked'])
    def test_existing_two_hour_trip_is_not_displayed_as_four_hours(self):
        old=[dict(date='2026-10-13',start='09:00',end='11:00')]
        result=trips.make_rows([attendance('2026-10-13')],{},old,date(2026,10,27))
        self.assertEqual((result[0]['hours'],result[0]['amount'],result[0]['end']),(2,10000,'11:00'))
    def test_existing_overlap_and_unsupported_duration_are_not_guessed(self):
        for old in ([dict(date='2026-10-07',start='09:00',end='12:00')],
                    [dict(date='2026-10-07',start='09:00',end='11:00'),dict(date='2026-10-07',start='10:00',end='12:00')]):
            with self.assertRaises(ValueError):trips.existing_totals(old)
    def test_invalid_budget_and_blank_manual_details_are_rejected(self):
        for value in (15000,-10000,'30000',True):
            with self.assertRaises(ValueError):trips.money(value)
        with self.assertRaisesRegex(ValueError,'장소와 목적'):
            trips.merge_entries(self.rows(),[dict(date='2026-10-07',selected=True)],True)

class TripJobs(unittest.TestCase):
    setUp=fixtures.StateTests.setUp
    tearDown=fixtures.StateTests.tearDown
    def prepare(self):
        rows=TripPlanning().rows();rows[1]['selected']=True
        settings=app.load_json(app.SETTINGS_FILE,{})
        state={'day_rules':{'2026-10-07':{'exclude_overtime':True}}}
        review=dict(id='fixture',month='2026-10',created_at=time.time(),account=trips._account(settings),rules=trips._rules(state,'2026-10'),rows=rows,existing=[],existing_amount=0)
        state['trip_review']=review;app.save_json(app.STATE_FILE,state)
        return rows
    def test_allocate_is_local_and_never_opens_a_browser(self):
        rows=self.prepare()
        with patch.object(app,'create_driver') as driver:
            result=trips.run_job(app,dict(operation='allocate',review_id='fixture',total=30000,rows=rows))
        driver.assert_not_called();self.assertEqual(result['summary']['remaining_amount'],0)
    def test_changed_rules_invalidate_the_review(self):
        rows=self.prepare();state=app.load_json(app.STATE_FILE,{});state['day_rules']={};app.save_json(app.STATE_FILE,state)
        with patch.object(app,'create_driver') as driver:
            with self.assertRaisesRegex(ValueError,'제외일 설정'):
                trips.run_job(app,dict(operation='allocate',review_id='fixture',total=30000,rows=rows))
        driver.assert_not_called()
    def test_submit_wrong_total_never_connects(self):
        rows=self.prepare()
        for row in rows:row.update(location='직접 입력',purpose='직접 입력')
        with patch.object(app,'create_driver') as driver:
            with self.assertRaisesRegex(ValueError,'출장 추가 필요'):
                trips.run_job(app,dict(operation='submit',review_id='fixture',total=50000,rows=rows))
        driver.assert_not_called()

if __name__=='__main__':unittest.main()
