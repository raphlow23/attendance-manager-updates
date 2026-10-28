import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from trip_site import TripPage,select_number


class DuplicateTimeOptions(unittest.TestCase):
    def option(self,text,value):
        return Mock(text=text,get_attribute=Mock(return_value=value))
    def choose(self,options,expected):
        select=Mock(options=options,first_selected_option=options[0])
        with patch('trip_site.Select',return_value=select),patch('trip_site.set_value') as write:
            select_number(Mock(),Mock(),13)
            self.assertEqual(write.call_args.args[2],expected)
    def test_saved_hour_prepended_to_generated_list(self):
        self.choose([self.option('13','13'),self.option('13시','13')],'13')
    def test_saved_hour_with_zero_padding(self):
        self.choose([self.option('13','013'),self.option('13','13')],'13')
    def test_identical_non_numeric_option_values(self):
        self.choose([self.option('13','hour13'),self.option('13','hour13')],'hour13')
    def test_different_opaque_values_are_still_rejected(self):
        with patch('trip_site.Select',return_value=Mock(options=[self.option('13','a'),self.option('13','b')])),patch('trip_site.set_value') as write:
            with self.assertRaises(RuntimeError):select_number(Mock(),Mock(),13)
            write.assert_not_called()
    def test_selected_label_is_checked_after_setting(self):
        select=Mock(options=[self.option('13','13')],first_selected_option=self.option('14','14'))
        with patch('trip_site.Select',return_value=select),patch('trip_site.set_value'):
            with self.assertRaisesRegex(RuntimeError,'선택 후'):select_number(Mock(),Mock(),13)


class TripNavigation(unittest.TestCase):
    def test_user_supplied_trip_url_does_not_require_work_log_or_trip_links(self):
        driver=Mock(current_url='http://sappd.kr/sappd_g4.php?m=10')
        driver.get.side_effect=lambda url:setattr(driver,'current_url',url)
        page=TripPage(driver);page.form=Mock(return_value=Mock());page.entry_control=Mock()
        page.open()
        driver.get.assert_called_once_with('http://sappd.kr/sappd_g6.php')
        driver.find_elements.assert_not_called();page.entry_control.assert_not_called()

    def test_javascript_edit_control_is_clicked_without_navigation(self):
        driver=Mock(current_url='http://sappd.kr/sappd_g6.php');control=Mock()
        control.get_attribute.return_value='javascript:editTrip(1)'
        TripPage(driver).activate(control)
        driver.get.assert_not_called();driver.execute_script.assert_called_once()

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
