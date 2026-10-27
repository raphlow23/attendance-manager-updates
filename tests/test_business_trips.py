import sys,time,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch,Mock
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
        self.assertTrue(row['event_day']);self.assertFalse(row['mandatory'] or row['selected'])
        self.assertEqual((row['start'],row['end'],row['hours'],row['amount']),('09:00','18:00',4,20000))
    def test_only_completed_attendance_days_are_shown(self):
        rows=[attendance('2026-10-01',':',':'),attendance('2026-10-02',co=':'),attendance('2026-10-03'),attendance('2026-10-30')]
        result=trips.make_rows(rows,{'2026-10-30':{'exclude_overtime':True}},[],date(2026,10,27))
        self.assertEqual([r['date'] for r in result],['2026-10-03'])
    def test_budget_allocation_uses_selected_dates_only(self):
        rows=self.rows();rows[0]['selected']=rows[1]['selected']=True
        result,summary=trips.allocate(rows,50000)
        self.assertFalse(result[2]['selected']);self.assertEqual(summary['remaining_amount'],10000)
        self.assertIn('출장 추가 필요',summary['message'])
    def test_two_selected_dates_can_mix_two_and_four_hours(self):
        rows=self.rows();rows[0]['selected']=rows[1]['selected']=rows[2]['selected']=True
        result,summary=trips.allocate(rows,50000)
        self.assertEqual(sorted(r['hours'] for r in result[1:]),[2,4]);self.assertEqual(summary['remaining_amount'],0)
        self.assertFalse(self.rows()[1]['selected'])
    def test_event_can_be_unchecked_and_its_time_can_be_changed(self):
        rows=trips.merge_entries(self.rows(),[dict(date='2026-10-07',selected=False,hours=2,start_hour=10)])
        self.assertFalse(rows[0]['selected']);self.assertEqual((rows[0]['start'],rows[0]['end']),('10:00','12:00'))
    def test_vacation_is_hidden_and_general_default_is_1300_to_1700(self):
        rows=trips.make_rows([attendance('2026-10-07'),attendance('2026-10-13')],{'2026-10-07':{'vacation':True,'exclude_overtime':True}},[],date(2026,10,27))
        self.assertEqual([r['date'] for r in rows],['2026-10-13'])
        self.assertEqual((rows[0]['start'],rows[0]['end']),('13:00','17:00'))
    def test_event_changed_end_survives_review_round_trip(self):
        entry=dict(date='2026-10-07',selected=True,hours=4,start_hour=9,end='13:00')
        row=trips.merge_entries(self.rows(),[entry])[0]
        self.assertEqual(row['end'],'13:00')
        self.assertEqual(trips.merge_entries([row],[dict(row)])[0]['end'],'13:00')
    def test_normal_trip_end_is_derived_and_cannot_exceed_attendance(self):
        row=self.rows()[1]
        self.assertEqual(trips.window(row,2,14)['end'],'16:00')
        with self.assertRaises(ValueError):trips.window(row,4,16)
        with self.assertRaises(ValueError):trips.window(row,2,8)
    def test_existing_day_is_capped_at_four_hours_and_not_selected(self):
        old=[dict(date='2026-10-07',start='09:00',end='18:00')]
        result=trips.make_rows([attendance('2026-10-07')],{'2026-10-07':{'exclude_overtime':True}},old,date(2026,10,27))
        self.assertEqual(result[0]['existing_amount'],20000);self.assertFalse(result[0]['selected']);self.assertFalse(result[0]['blocked'])
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

    def test_submission_excludes_blank_purpose_unchecked_and_omitted_dates(self):
        rows=self.rows()
        for row in rows:row['selected']=True
        entries=[dict(rows[0],selected=True,purpose='   ',location='장소'),dict(rows[1],selected=False,purpose='작성한 목적',location='장소')]
        result=trips.submission_rows(rows,entries)
        self.assertFalse(any(r['selected'] for r in result))
    def test_submission_keeps_only_checked_purpose_and_requires_its_location(self):
        rows=self.rows();entry=dict(rows[0],selected=True,purpose='등록 목적',location='장소')
        result=trips.submission_rows(rows,[entry])
        self.assertEqual([r['date'] for r in result if r['selected']],[entry['date']])
        with self.assertRaisesRegex(ValueError,'장소와 목적'):
            trips.submission_rows(rows,[dict(entry,location='')])

    def test_existing_places_purposes_and_times_are_loaded_and_counted_once(self):
        old=[dict(date='2026-10-13',start='13:00',end='17:00',location='기존 장소',purpose='기존 목적')]
        rows=trips.make_rows([attendance('2026-10-13')],{},old,date(2026,10,27))
        self.assertEqual((rows[0]['location'],rows[0]['purpose']),('기존 장소','기존 목적'))
        self.assertTrue(rows[0]['is_existing']);rows[0]['selected']=True
        self.assertEqual(trips.summarize(rows,20000,20000)['remaining_amount'],0)
        edited=trips.submission_rows(rows,[dict(rows[0],location='새 장소',purpose='새 목적')])[0]
        self.assertEqual((edited['start'],edited['end']),('13:00','17:00'))
        with self.assertRaisesRegex(ValueError,'장소·목적만'):
            trips.submission_rows(rows,[dict(rows[0],start_hour=14)])
    def test_existing_morning_trip_is_editable_on_a_short_attendance_day(self):
        old=[dict(date='2026-10-13',start='09:00',end='11:00',location='오전 장소',purpose='오전 목적')]
        row=trips.make_rows([attendance('2026-10-13',co='12:00')],{},old,date(2026,10,27))[0]
        self.assertFalse(row['blocked']);self.assertEqual((row['start'],row['end']),('09:00','11:00'))
    def test_multiple_records_on_one_day_are_not_arbitrarily_edited(self):
        old=[dict(date='2026-10-13',start='09:00',end='11:00'),dict(date='2026-10-13',start='13:00',end='15:00')]
        row=trips.make_rows([attendance('2026-10-13')],{},old,date(2026,10,27))[0]
        self.assertTrue(row['blocked']);self.assertIn('여러 출장',row['status'])

class TripJobs(unittest.TestCase):
    setUp=fixtures.StateTests.setUp
    tearDown=fixtures.StateTests.tearDown
    def prepare(self):
        rows=TripPlanning().rows();rows[0]['selected']=rows[1]['selected']=True
        settings=app.load_json(app.SETTINGS_FILE,{})
        state={'day_rules':{'2026-10-07':{'exclude_overtime':True}}}
        review=dict(id='fixture',month='2026-10',created_at=time.time(),account=trips._account(settings),rules=trips._rules(state,'2026-10'),rows=rows,existing=[],existing_amount=0,existing_verified=True)
        state['trip_review']=review;app.save_json(app.STATE_FILE,state)
        return rows
    def test_allocate_is_local_and_never_opens_a_browser(self):
        rows=self.prepare()
        with patch.object(app,'create_driver') as driver:
            result=trips.run_job(app,dict(operation='allocate',review_id='fixture',total=30000,rows=rows))
        driver.assert_not_called();self.assertEqual(result['summary']['remaining_amount'],0)
    def test_scan_reads_attendance_without_opening_trip_page(self):
        self.prepare();driver=Mock()
        records=[attendance('2026-10-07','09:00','18:00'),attendance('2026-10-13'),attendance('2026-10-14',co=':')]
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=records),patch('trip_site.TripPage') as page:
            page.return_value.open.side_effect=RuntimeError('trip menu unavailable')
            result=trips.run_job(app,dict(operation='scan',month='2026-10',total=30000))
        self.assertEqual([r['date'] for r in result['rows']],['2026-10-07','2026-10-13'])
        page.assert_not_called();driver.quit.assert_called_once()
        self.assertFalse(app.load_json(app.STATE_FILE,{})['trip_review']['existing_verified'])

    def test_submit_without_existing_trip_check_never_connects(self):
        rows=self.prepare();state=app.load_json(app.STATE_FILE,{})
        state['trip_review']['existing_verified']=False;app.save_json(app.STATE_FILE,state)
        with patch('monthly_reconcile._connect') as connect:
            with self.assertRaisesRegex(ValueError,'기존 출장 내역'):
                trips.run_job(app,dict(operation='submit',review_id='fixture',total=30000,rows=rows))
        connect.assert_not_called()

    def test_failed_existing_check_keeps_attendance_review_for_retry(self):
        rows=self.prepare();driver=Mock()
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=rows),patch('trip_site.TripPage') as page:
            page.return_value.open.side_effect=RuntimeError('trip menu unavailable')
            with self.assertRaisesRegex(RuntimeError,'trip menu'):
                trips.run_job(app,dict(operation='inspect',review_id='fixture',total=30000,rows=rows))
        self.assertEqual(app.load_json(app.STATE_FILE,{})['trip_review']['id'],'fixture')
        page.return_value.submit.assert_not_called();driver.quit.assert_called_once()

    def test_existing_check_counts_registered_dates_without_posting(self):
        rows=self.prepare();driver=Mock()
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=rows),patch('trip_site.TripPage') as page:
            page.return_value.existing.return_value=[dict(date='2026-10-07',start='09:00',end='18:00')]
            result=trips.run_job(app,dict(operation='inspect',review_id='fixture',total=40000,rows=rows))
        self.assertTrue(result['ready']);self.assertEqual(result['summary']['existing_amount'],20000)
        self.assertTrue(result['rows'][0]['selected']);self.assertFalse(result['rows'][0]['blocked'])
        page.return_value.submit.assert_not_called()
        self.assertTrue(app.load_json(app.STATE_FILE,{})['trip_review']['existing_verified'])

    def test_load_existing_for_edit_does_not_select_new_dates(self):
        rows=self.prepare();driver=Mock()
        saved=dict(date='2026-10-07',start='09:00',end='18:00',location='기존 장소',purpose='기존 목적')
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=rows),patch('trip_site.TripPage') as page:
            page.return_value.existing.return_value=[saved]
            result=trips.run_job(app,dict(operation='inspect',review_id='fixture',total=40000,rows=rows,edit_existing=True))
        self.assertTrue(result['ready'])
        self.assertEqual([r['date'] for r in result['rows'] if r['selected']],['2026-10-07'])
        self.assertEqual(result['rows'][0]['location'],'기존 장소')
        page.return_value.submit.assert_not_called()
    def test_changed_rules_invalidate_the_review(self):
        rows=self.prepare();state=app.load_json(app.STATE_FILE,{});state['day_rules']={};app.save_json(app.STATE_FILE,state)
        with patch.object(app,'create_driver') as driver:
            with self.assertRaisesRegex(ValueError,'제외일 설정'):
                trips.run_job(app,dict(operation='allocate',review_id='fixture',total=30000,rows=rows))
        driver.assert_not_called()
    def test_all_excluded_dates_do_not_open_browser(self):
        rows=self.prepare()
        with patch('monthly_reconcile._connect') as connect:
            with self.assertRaisesRegex(ValueError,'등록할 출장 날짜'):
                trips.run_job(app,dict(operation='submit',review_id='fixture',total=30000,rows=[dict(r,purpose='') for r in rows]))
        connect.assert_not_called()
    def test_submit_wrong_total_never_connects(self):
        rows=self.prepare()
        for row in rows:row.update(location='직접 입력',purpose='직접 입력')
        with patch.object(app,'create_driver') as driver:
            with self.assertRaisesRegex(ValueError,'목표 초과'):
                trips.run_job(app,dict(operation='submit',review_id='fixture',total=10000,rows=rows))
        driver.assert_not_called()

if __name__=='__main__':unittest.main()
