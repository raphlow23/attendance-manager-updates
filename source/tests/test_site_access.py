import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from urllib.error import HTTPError
from email.message import Message

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import main as app
import site_access as access
from resident import Health
import test_attendance as fixtures


class AccessTests(unittest.TestCase):
    setUp=fixtures.StateTests.setUp
    tearDown=fixtures.StateTests.tearDown

    def test_normal_sessions_and_edits_have_no_fixed_delay(self):
        with patch.object(access.time,'sleep') as sleep:
            access.reserve_session(app);access.reserve_session(app);access.reserve_write(app)
        sleep.assert_not_called()

    def test_only_measured_request_burst_causes_brief_wait(self):
        app.save_json(os.path.join(app.DATA_DIR,'site-access.json'),{'requests':[1000+.01*n for n in range(8)]})
        clock=[1000.1]
        with patch.object(access.time,'time',side_effect=lambda:clock[0]),patch.object(access.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            access.reserve_session(app)
        self.assertGreaterEqual(clock[0],1001)
        self.assertLess(clock[0],1002)

    def test_runaway_requests_are_stopped(self):
        with patch.object(access.time,'time',return_value=1000):
            with self.assertRaises(access.SiteAccessPaused):access.record_requests(app,[1000]*25)
            with self.assertRaises(access.SiteAccessPaused):access.check_pause(app)

    def test_rate_limit_is_persisted_and_private_headers_not_saved(self):
        driver=Mock()
        driver.get_log.return_value=[{'message':json.dumps({'message':{'method':'Network.responseReceived','params':{'type':'Document','response':{'status':429,'headers':{'Retry-After':'1800','Cookie':'do-not-store'}}}}})}]
        with patch.object(access.time,'time',return_value=1000):
            with self.assertRaises(access.SiteAccessPaused):access.check_page(app,driver)
            with self.assertRaises(access.SiteAccessPaused):access.check_pause(app)
        text=Path(app.DATA_DIR,'site-access.json').read_text(encoding='utf-8')
        self.assertNotIn('do-not-store',text)
        self.assertGreaterEqual(json.loads(text)['cooldown_until'],2800)

    def test_normal_connectivity_probe_uses_head_and_long_interval(self):
        response=MagicMock()
        with patch('resident.urlopen',return_value=response) as request:
            health=Health(app)
            self.assertTrue(health.probe())
        self.assertEqual(request.call_args.args[0].get_method(),'HEAD')
        self.assertEqual(health.probe_interval,1800)

    def test_probe_honors_server_rate_limit(self):
        headers=Message();headers['Retry-After']='900'
        with patch('resident.urlopen',side_effect=HTTPError('http://test.invalid',429,'limited',headers,None)):
            health=Health(app)
            self.assertFalse(health.probe())
        with self.assertRaises(access.SiteAccessPaused):access.check_pause(app)

    def test_probe_fallback_get_still_honors_rate_limit(self):
        headers=Message();headers['Retry-After']='900'
        errors=[HTTPError('http://test.invalid',405,'no HEAD',headers,None),HTTPError('http://test.invalid',429,'limited',headers,None)]
        with patch('resident.urlopen',side_effect=errors):
            self.assertFalse(Health(app).probe())
        with self.assertRaises(access.SiteAccessPaused):access.check_pause(app)
