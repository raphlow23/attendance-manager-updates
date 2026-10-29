import time,unittest
from unittest.mock import Mock,patch
from datetime import date
from test_trip_delete import attendance,saved
import test_attendance as fixtures
import main as app
import business_trips as trips

class BatchTrips(unittest.TestCase):
    setUp=fixtures.StateTests.setUp
    tearDown=fixtures.StateTests.tearDown
    def prepare(self):
        rows=trips.make_rows(attendance(),{},[saved()],date(2026,10,29))
        settings=app.load_json(app.SETTINGS_FILE,{})
        review=dict(id='batch',month='2026-10',created_at=time.time(),account=trips._account(settings),rules={},rows=rows,existing=[saved()],existing_amount=20000,existing_verified=True)
        app.save_json(app.STATE_FILE,dict(trip_review=review))
        return review
    def test_pending_delete_reduces_budget_and_can_be_undone_without_connecting(self):
        review=self.prepare();rows=trips.merge_entries(review['rows'],[dict(review['rows'][0],pending_delete=True)])
        self.assertFalse(rows[0]['selected'])
        self.assertEqual(trips.summarize(rows,20000,20000)['remaining_amount'],20000)
        rows=trips.merge_entries(rows,[dict(rows[0],pending_delete=False)])
        self.assertEqual(trips.summarize(rows,20000,20000)['remaining_amount'],0)
        with patch('monthly_reconcile._connect') as connect:
            result=trips.run_job(app,dict(operation='allocate',review_id='batch',total=20000,rows=[dict(review['rows'][0],pending_delete=True)]))
            self.assertEqual(result['summary']['existing_amount'],0);connect.assert_not_called()
    def test_inspect_only_does_not_delete_and_allows_delete_only_batch(self):
        review=self.prepare();driver=Mock()
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=attendance()),patch('trip_site.TripPage') as site:
            site.return_value.existing.return_value=[saved()]
            result=trips.run_job(app,dict(operation='inspect',review_id='batch',total=20000,rows=[dict(review['rows'][0],pending_delete=True)]))
            self.assertTrue(result['ready']);site.return_value.delete.assert_not_called();site.return_value.submit.assert_not_called()
            self.assertTrue(result['rows'][0]['pending_delete'])
    def test_final_submit_deletes_without_requiring_purpose_and_marks_absence(self):
        review=self.prepare();driver=Mock()
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=attendance()),patch('trip_site.TripPage') as site:
            site.return_value.existing.side_effect=[[saved()],[saved()],[],[]]
            result=trips.run_job(app,dict(operation='submit',review_id='batch',total=20000,rows=[dict(review['rows'][0],pending_delete=True,purpose='')]))
            self.assertTrue(result['ok']);self.assertEqual(result['rows'][0]['status'],'삭제 확인 완료')
            site.return_value.delete.assert_called_once_with(saved(),'2026-10');site.return_value.submit.assert_not_called()
            self.assertFalse(result['all_rows'][0]['is_existing'])
            self.assertEqual(app.load_json(app.STATE_FILE,{})['trip_deletions']['2026-10-13']['status'],'success')
    def test_unconfirmed_delete_stops_batch_and_retains_uncertainty(self):
        review=self.prepare();driver=Mock();driver._workday_write_submitted=True
        with patch('monthly_reconcile._connect',return_value=(driver,Mock())),patch('monthly_reconcile._read_month',return_value=attendance()),patch('trip_site.TripPage') as site:
            site.return_value.existing.return_value=[saved()]
            def fail(*args):driver._workday_write_submitted=True;raise RuntimeError('삭제 결과 불명')
            site.return_value.delete.side_effect=fail
            result=trips.run_job(app,dict(operation='submit',review_id='batch',total=20000,rows=[dict(review['rows'][0],pending_delete=True)]))
            self.assertFalse(result['ok']);self.assertEqual(result['rows'][0]['status'],'삭제 결과 확인 필요')
            self.assertEqual(app.load_json(app.STATE_FILE,{})['trip_deletions']['2026-10-13']['status'],'uncertain')
            site.return_value.submit.assert_not_called()
