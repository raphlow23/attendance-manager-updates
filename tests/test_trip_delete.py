import sys,time,unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock,patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app')]
import main as app
import business_trips as trips
import trip_delete as deletion
import test_attendance as fixtures

def saved():return dict(date='2026-10-13',category='센터',start='13:00',end='17:00',location='기존 장소',purpose='기존 목적',transport='대중교통')
def attendance():return [dict(date='2026-10-13',checkin='08:35',checkout='18:35',note='')]

class DeleteJobs(unittest.TestCase):
    setUp=fixtures.StateTests.setUp
    tearDown=fixtures.StateTests.tearDown
    def test_reregistration_draft_preserves_nonzero_start_minute(self):
        previous=trips.make_rows(attendance(),{},[dict(saved(),start='12:30',end='14:30')],date(2026,10,29))
        self.assertEqual(previous[0]['start_minute'],30)
        row=deletion.rebuild_rows(attendance(),{},[],previous,'2026-10-13',date(2026,10,29))[0]
        self.assertEqual((row['start'],row['end'],row['hours']),('12:30','14:30',2))
        self.assertFalse(row['is_existing'])
    def prepare(self):
        rows=trips.make_rows(attendance(),{},[saved()],date(2026,10,29))
        settings=app.load_json(app.SETTINGS_FILE,{})
        review=dict(id='delete-test',month='2026-10',created_at=time.time(),account=trips._account(settings),rules={},rows=rows,existing=[saved()],existing_amount=20000,existing_verified=False)
        app.save_json(app.STATE_FILE,dict(trip_review=review,trip_applications={'2026-10-13':{'status':'uncertain'}}))
        return dict(operation='delete',review_id='delete-test',dates=['2026-10-13'],confirmed=True,total=20000,rows=[dict(rows[0],selected=True)])
    def run_delete(self,job,records=None,error=None):
        driver=Mock();driver._workday_write_submitted=False
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=attendance()),patch('trip_site.TripPage') as page:
            page.return_value.existing.side_effect=records or [[saved()],[]]
            if error:
                def fail(*a):driver._workday_write_submitted=True;raise error
                page.return_value.delete.side_effect=fail
            result=trips.run_job(app,job)
            return result,page,driver
    def test_delete_is_verified_and_same_date_is_available_for_reregistration(self):
        job=self.prepare();result,page,driver=self.run_delete(job)
        self.assertTrue(result['ok']);page.return_value.delete.assert_called_once_with(saved(),'2026-10')
        row=result['rows'][0]
        self.assertEqual(row['date'],'2026-10-13');self.assertFalse(row['is_existing']);self.assertFalse(row['selected']);self.assertFalse(row['blocked'])
        self.assertEqual(row['existing_amount'],0);self.assertEqual(row['location'],'기존 장소');self.assertEqual(row['purpose'],'기존 목적')
        self.assertEqual(result['summary']['remaining_amount'],20000)
        state=app.load_json(app.STATE_FILE,{})
        self.assertEqual(state['trip_applications']['2026-10-13']['status'],'deleted')
        self.assertFalse(state['trip_review']['existing_verified']);driver.quit.assert_called_once()
        rows=trips.merge_entries(result['rows'],[dict(row,selected=True)])
        self.assertTrue(rows[0]['selected']);self.assertFalse(rows[0]['is_existing'])
    def test_confirmation_and_existing_status_are_required_before_connect(self):
        job=self.prepare()
        with patch('monthly_reconcile._connect') as connect:
            for change in ({'confirmed':False},{'dates':[]},{'dates':['2026-10-14']},{'dates':['2026-10-13','2026-10-14']}):
                with self.assertRaises(ValueError):trips.run_job(app,dict(job,**change))
            connect.assert_not_called()
    def test_changed_site_record_is_not_deleted(self):
        job=self.prepare();changed=dict(saved(),purpose='다른 내용')
        driver=Mock()
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=attendance()),patch('trip_site.TripPage') as page:
            page.return_value.existing.return_value=[changed]
            with self.assertRaisesRegex(ValueError,'바뀌었습니다'):trips.run_job(app,job)
            page.return_value.delete.assert_not_called();driver.quit.assert_called_once()
    def test_uncertain_delete_does_not_change_registered_to_unregistered(self):
        job=self.prepare();result,page,driver=self.run_delete(job,error=RuntimeError('응답 확인 실패'))
        self.assertFalse(result['ok']);self.assertTrue(result['rows'][0]['is_existing']);self.assertTrue(result['rows'][0]['blocked'])
        state=app.load_json(app.STATE_FILE,{})
        self.assertEqual(state['trip_deletions']['2026-10-13']['status'],'uncertain')
        self.assertTrue(state['trip_review']['consumed'])
        deletion.confirm_absent_deletions(app,'2026-10',[])
        state=app.load_json(app.STATE_FILE,{})
        self.assertEqual(state['trip_applications']['2026-10-13']['status'],'deleted')
    def test_record_still_present_after_delete_is_not_marked_absent(self):
        job=self.prepare();result,_,_=self.run_delete(job,records=[[saved()],[saved()]])
        self.assertFalse(result['ok']);self.assertTrue(result['rows'][0]['is_existing'])

if __name__=='__main__':unittest.main()
