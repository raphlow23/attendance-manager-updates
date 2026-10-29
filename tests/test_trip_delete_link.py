import unittest
from trip_site import confirmed_delete_link

class ObservedDeleteLink(unittest.TestCase):
    source='https://example.test/sappd_g6.php'
    handler="return confirm('해당 출장일지를 삭제하시겠습니까?');"
    def test_resolves_actual_relative_link_without_guessing_record_id(self):
        self.assertEqual(confirmed_delete_link(self.source,'sappd_g6_d.php?no=7&m=10',self.handler),'https://example.test/sappd_g6_d.php?no=7&m=10')
    def test_never_executes_other_handler_logic_or_non_delete_confirm(self):
        for handler in (None,'',"return confirm('저장할까요?');",self.handler+'otherAction();',"confirm('해당 출장일지를 삭제하시겠습니까?');"):
            self.assertIsNone(confirmed_delete_link(self.source,'/action',handler))
        self.assertIsNone(confirmed_delete_link(self.source,'#',self.handler))
    def test_cross_origin_and_script_links_are_rejected(self):
        for href in ('https://other.test/delete','//other.test/delete','javascript:danger()','http://example.test/delete'):
            with self.assertRaises(RuntimeError):confirmed_delete_link(self.source,href,self.handler)
