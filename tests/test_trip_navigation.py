import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from selenium.webdriver.common.by import By

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from trip_site import TripPage


class TripNavigation(unittest.TestCase):
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
