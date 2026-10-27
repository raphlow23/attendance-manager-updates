import sys
import unittest
from pathlib import Path
from datetime import date

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from trip_site import history_date


class TripDates(unittest.TestCase):
    def test_full_date_formats_and_weekday(self):
        for text in ('2026-10-07','2026.10.7. (수)','2026 / 10 / 07','2026년 10월 7일\n(수요일)','20261007'):
            with self.subTest(text=text):self.assertEqual(history_date(text,'2026-10'),date(2026,10,7))

    def test_monthly_short_dates_use_verified_view_year(self):
        for text in ('10월 7일','10/07(수)','10.7.','7일(수)'):
            with self.subTest(text=text):self.assertEqual(history_date(text,'2026-10'),date(2026,10,7))
        self.assertEqual(history_date('9월 7일','2026-09'),date(2026,9,7))

    def test_missing_year_does_not_force_another_month_to_requested_month(self):
        self.assertEqual(history_date('9/7','2026-10'),date(2026,9,7))

    def test_invalid_ambiguous_or_nondate_cells_are_not_guessed(self):
        for text in ('','선택','7','기간 2026-10-07부터','10/7 ~ 10/8','2026-02-30','13/07','0일'):
            with self.subTest(text=text),self.assertRaises(ValueError):history_date(text,'2026-10')


if __name__=='__main__':unittest.main()
