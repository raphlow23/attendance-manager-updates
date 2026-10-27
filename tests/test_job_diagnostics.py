import sys
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import Mock,patch
from selenium.common.exceptions import TimeoutException

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import main as app
from monthly_reconcile import _read_month


class JobDiagnostics(unittest.TestCase):
    def test_empty_selenium_message_has_type_and_explanation(self):
        text=app.user_job_error(TimeoutException(),'출장 일정 조회 2026-09')
        self.assertIn('TimeoutException',text);self.assertIn('화면 응답',text);self.assertIn('2026-09',text)

    def test_month_read_failure_reports_date_and_type(self):
        page=Mock();page.record.side_effect=TimeoutException()
        with self.assertRaisesRegex(RuntimeError,r'2026-09-01.*TimeoutException'):
            _read_month(page,'2026-09',date(2026,10,27),lambda day:True)
        page.record.assert_called_once()

    def test_diagnostic_redacts_password(self):
        with patch.object(app,'_LOG_SECRETS',{'fixture-private-password'}):
            text=app.user_job_error(RuntimeError('fixture-private-password failed'))
        self.assertNotIn('fixture-private-password',text);self.assertIn('[숨김]',text)


if __name__=='__main__':unittest.main()
