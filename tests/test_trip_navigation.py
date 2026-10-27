import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from trip_site import TripPage


class TripNavigation(unittest.TestCase):
    def test_user_supplied_trip_url_does_not_require_work_log_or_trip_links(self):
        driver=Mock(current_url='http://sappd.kr/sappd_g4.php?m=10')
        driver.get.side_effect=lambda url:setattr(driver,'current_url',url)
        page=TripPage(driver);page.form=Mock(return_value=Mock());page.entry_control=Mock()
        page.open()
        driver.get.assert_called_once_with('http://sappd.kr/sappd_g6.php')
        driver.find_elements.assert_not_called();page.entry_control.assert_not_called()

    def test_https_session_is_not_downgraded_for_direct_trip_entry(self):
        driver=Mock(current_url='https://sappd.kr/sappd_g4.php')
        driver.get.side_effect=lambda url:setattr(driver,'current_url',url)
        page=TripPage(driver);page.form=Mock(return_value=Mock());page.open()
        driver.get.assert_called_once_with('https://sappd.kr/sappd_g6.php')

    def test_direct_entry_without_form_stops_without_trying_other_menus(self):
        driver=Mock(current_url='http://sappd.kr/sappd_g4.php')
        driver.get.side_effect=lambda url:setattr(driver,'current_url',url)
        page=TripPage(driver);page.wait=Mock();page.wait.until.side_effect=TimeoutException()
        with self.assertRaisesRegex(RuntimeError,'입력 폼'):page.open()
        driver.get.assert_called_once_with('http://sappd.kr/sappd_g6.php')
        driver.find_elements.assert_not_called()

    def test_cross_site_redirect_does_not_continue_to_fill_or_submit(self):
        driver=Mock(current_url='http://sappd.kr/sappd_g4.php')
        driver.get.side_effect=lambda url:setattr(driver,'current_url','https://other.invalid/login')
        page=TripPage(driver);page.form=Mock()
        with self.assertRaisesRegex(RuntimeError,'다른 사이트'):page.open()
        page.form.assert_not_called()

    def page(self):
        driver=Mock(current_url='https://test.invalid/attendance')
        work=Mock(text='근무일지',is_displayed=Mock(return_value=True))
        work.get_attribute.return_value='https://test.invalid/work'
        driver.find_elements.side_effect=lambda by,selector:[work] if by==By.LINK_TEXT else []
        page=TripPage(driver)
        page.wait=Mock();page.wait.until.side_effect=lambda check:check(driver)
        return page

    def test_direct_trip_form_does_not_require_a_clickable_active_tab(self):
        page=self.page();page.form=Mock(return_value=Mock());page.entry_control=Mock()
        page.open()
        page.entry_control.assert_not_called()
        page.driver.get.assert_called_once_with('https://test.invalid/work')

    def test_menu_path_follows_observed_link_then_waits_for_form(self):
        page=self.page();page.form=Mock(side_effect=[False,Mock()])
        link=Mock();link.get_attribute.return_value='https://test.invalid/trips'
        page.entry_control=Mock(return_value=link)
        page.open()
        self.assertEqual([c.args[0] for c in page.driver.get.call_args_list],['https://test.invalid/work','https://test.invalid/trips'])

    def test_spaced_trip_title_with_nested_sibling_shortcut(self):
        page=TripPage(Mock())
        link=Mock(text='바로 가기',is_displayed=Mock(return_value=True))
        card=Mock();card.find_elements.return_value=[link]
        title=Mock(is_displayed=Mock(return_value=True));title.find_element.return_value=card
        page.driver.find_elements.side_effect=lambda by,selector:[title] if by==By.XPATH else []
        self.assertIs(page.entry_control(),link)

    def test_two_trip_links_are_not_arbitrarily_selected(self):
        page=TripPage(Mock())
        links=[Mock(text='출장 일지',is_displayed=Mock(return_value=True)) for _ in range(2)]
        page.driver.find_elements.return_value=links
        with self.assertRaises(RuntimeError):page.entry_control()
        page.driver.get.assert_not_called()

    def test_other_cards_shortcut_is_not_selected_without_trip_title(self):
        page=TripPage(Mock());link=Mock(text='바로가기',is_displayed=Mock(return_value=True))
        page.driver.find_elements.side_effect=lambda by,selector:[] if by==By.XPATH else [link]
        self.assertFalse(page.entry_control())
        page.driver.get.assert_not_called()


if __name__=='__main__':unittest.main()
