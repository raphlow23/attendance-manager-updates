import sys,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import business_trips as trips

class CenterBudget(unittest.TestCase):
    def rows(self):
        attendance=[dict(date=f'2026-10-{d:02}',checkin='08:30',checkout='18:30') for d in (1,2,5)]
        existing=[dict(date=f'2026-10-{d:02}',start='13:00',end='17:00',category=category,location='장소',purpose='목적',transport='대중교통') for d,category in ((1,'센터'),(2,'협회'))]
        return trips.make_rows(attendance,{},existing,date(2026,10,29)),existing
    def test_existing_association_is_visible_but_not_in_center_total(self):
        rows,existing=self.rows()
        self.assertTrue(rows[1]['is_existing']);self.assertEqual(rows[1]['existing_amount'],20000)
        self.assertEqual(rows[1]['existing_center_amount'],0)
        self.assertEqual(sum(v['amount'] for v in trips.center_totals(existing).values()),20000)
        rows[2]['selected']=True
        self.assertEqual(trips.summarize(rows,40000,20000)['remaining_amount'],0)
    def test_new_association_and_deleting_association_do_not_change_budget(self):
        rows,_=self.rows();rows[1]['pending_delete']=True;rows[2].update(selected=True,category='협회')
        summary=trips.summarize(rows,40000,20000)
        self.assertEqual((summary['existing_amount'],summary['planned_amount'],summary['remaining_amount']),(20000,0,20000))
    def test_category_edits_add_and_remove_center_amount(self):
        rows,_=self.rows();rows[0].update(selected=True,category='협회');rows[1].update(selected=True,category='센터')
        self.assertEqual(trips.budget_delta(rows[0]),-20000);self.assertEqual(trips.budget_delta(rows[1]),20000)
        self.assertEqual(trips.summarize(rows,20000,20000)['remaining_amount'],0)
        rows[1]['selected']=False
        self.assertEqual(trips.summarize(rows,20000,20000)['remaining_amount'],20000)
    def test_allocator_ignores_association_and_uses_released_center_budget(self):
        rows,_=self.rows();rows[0].update(selected=True,category='협회');rows[2]['selected']=True
        allocated,summary=trips.allocate(rows,20000,20000)
        self.assertEqual(allocated[2]['hours'],4);self.assertEqual(summary['remaining_amount'],0)
        rows[2]['category']='협회'
        allocated,summary=trips.allocate(rows,20000,20000)
        self.assertEqual(allocated[2]['hours'],4);self.assertEqual(summary['remaining_amount'],20000)
