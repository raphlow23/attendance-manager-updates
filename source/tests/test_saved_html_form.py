"""Run the real adapter against parsed HTML, with local-only form submission."""
import re
import sys
import unittest
from pathlib import Path
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit, parse_qs
from lxml import html

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'app')]
from attendance_recovery import AttendancePage
from selenium.webdriver.common.by import By
from test_edit_form import NoAlert

FIXTURE=Path(__file__).parent/'fixtures'/'attendance_edit_form.html'


class Node:
    def __init__(self,site,node):self.site,self.node=site,node
    @property
    def text(self):return ''.join(self.node.itertext()).strip()
    def is_displayed(self):return True
    def get_attribute(self,name):
        value=self.node.get(name)
        return urljoin('http://sappd.kr/',value) if value and name in ('href','action') else value
    def find_elements(self,by,selector):return self.site.select(self.node,by,selector)
    def clear(self):self.node.set('value','')
    def send_keys(self,value):self.node.set('value',(self.node.get('value') or '')+value)
    def click(self):
        if self.node.tag=='a':return
        form=self.node.xpath('ancestor::form[1]')[0]
        query=parse_qs(urlsplit(form.get('action')).query)
        links=self.site.doc.xpath('//a[contains(@href,"sappd_g4_edit.php")]')
        link=next(a for a in links if parse_qs(urlsplit(a.get('href')).query)==query)
        row=link.xpath('ancestor::tr[1]')[0];cells=row.xpath('./td')
        for index,names in ((1,('culgun','culguna')),(2,('tehgun','tehguna'))):
            cells[index].text=' : '.join(form.xpath(f'.//input[@name="{n}"]')[0].get('value') for n in names)
        cells[3].text=form.xpath('.//input[@name="huuga"]')[0].get('value')
        self.site.saved+=1


class ParsedSite:
    def __init__(self,source):
        self.doc=html.fromstring(source);self.cache={};self.saved=0;self.switch_to=NoAlert()
        self.current_url='http://sappd.kr/sappd_g4.php?m=10';self.navigations=[];self.edit_source=None
    def get(self,url):
        self.navigations.append(url);self.current_url=url
        if self.edit_source:self.doc=html.fromstring(self.edit_source);self.cache={}
    def wrap(self,node):
        if node not in self.cache:self.cache[node]=Node(self,node)
        return self.cache[node]
    def select(self,node,by,selector):
        if by==By.TAG_NAME:xpath='.//'+selector
        elif by==By.XPATH:xpath=selector
        elif by==By.CSS_SELECTOR:
            match=re.fullmatch(r'input\[name="([a-z]+)"\]',selector)
            if match:xpath=f'.//input[@name="{match[1]}"]'
            elif selector=="input:not([type='hidden'])":xpath='.//input[not(@type="hidden")]'
            elif selector in ('a, button, input','button, a, input'):xpath='.//a | .//button | .//input'
            elif selector=='input, textarea, select':xpath='.//input | .//textarea | .//select'
            else:raise AssertionError(selector)
        else:raise AssertionError((by,selector))
        return [self.wrap(n) for n in node.xpath(xpath)]
    def find_elements(self,by,selector):return self.select(self.doc,by,selector)
    def find_element(self,by,selector):return self.find_elements(by,selector)[0]


def verify_source(source):
    site=ParsedSite(source)
    form=site.doc.xpath('//form[.//input[@name="culgun"]]')[0]
    query=parse_qs(urlsplit(form.get('action')).query)
    link=next(a for a in site.doc.xpath('//a[contains(@href,"sappd_g4_edit.php")]') if parse_qs(urlsplit(a.get('href')).query)==query)
    n=int(re.search(r'\d+',link.xpath('ancestor::tr[1]/td[1]')[0].text_content()).group())
    day=date(2026,int(query['m'][0]),n);page=AttendancePage(site,date(2026,10,27))
    before=page.record(day)
    assert page.correct(day,{'checkin':datetime.combine(day,datetime.min.time()).replace(hour=9),'checkout':datetime.combine(day,datetime.min.time()).replace(hour=18)},before)
    after=page.record(day)
    assert after['checkin']=='09 : 00' and after['checkout']=='18 : 00' and after['note']==before['note'] and site.saved==1
    return site


class SavedFormTests(unittest.TestCase):
    def test_source_derived_form_saves_and_preserves_note(self):verify_source(FIXTURE.read_text(encoding='utf-8'))
    def test_opening_editor_from_list_uses_observed_link_once(self):
        source=FIXTURE.read_text(encoding='utf-8');site=ParsedSite(source)
        form=site.doc.xpath('//form[.//input[@name="culgun"]]')[0];form.getparent().remove(form)
        site.edit_source=source
        self.assertEqual(len(site.doc.xpath('//input[@name="culgun"]')),0)
        page=AttendancePage(site,date(2026,10,27));day=date(2026,10,7)
        page.correct(day,{'checkout':datetime(2026,10,7,18)},page.record(day))
        self.assertEqual(site.navigations,['http://sappd.kr/sappd_g4_edit.php?no=10001&m=10'])
        self.assertEqual(site.saved,1)

    def test_redirect_to_list_is_reported_before_any_save(self):
        site=ParsedSite(FIXTURE.read_text(encoding='utf-8'))
        def redirect(url):site.navigations.append(url);site.current_url='http://sappd.kr/sappd_g4.php?m=10'
        site.get=redirect
        page=AttendancePage(site,date(2026,10,27));day=date(2026,10,7)
        with self.assertRaisesRegex(RuntimeError,'사이트가 다른 화면'):
            page.correct(day,{'checkout':datetime(2026,10,7,18)},page.record(day))
        self.assertEqual(site.saved,0);self.assertEqual(len(site.navigations),1)
    def test_wrong_record_month_or_site_never_submits(self):
        source=FIXTURE.read_text(encoding='utf-8')
        for action in ('sappd_g4_edit_pro.php?no=99999&m=10','sappd_g4_edit_pro.php?no=10001&m=9','http://other.invalid/sappd_g4_edit_pro.php?no=10001&m=10'):
            site=ParsedSite(source);form=site.doc.xpath('//form[.//input[@name="culgun"]]')[0];form.set('action',action)
            page=AttendancePage(site,date(2026,10,27));day=date(2026,10,7)
            with self.assertRaisesRegex(RuntimeError,'기록 번호'):
                page.correct(day,{'checkout':datetime(2026,10,7,18)},page.record(day))
            self.assertEqual(site.saved,0)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1].endswith('.html'):
        data=Path(sys.argv[1]).read_bytes()
        try:source=data.decode('utf-8-sig')
        except UnicodeDecodeError:source=data.decode('cp949')
        verify_source(source)
        print('SAVED_HTML_ADAPTER_OK: supplied HTML parsed; local edit/save/verification; no network or real submission')
    else:unittest.main()
