"""Verify duplicate saved time options in real Chrome without target-site access."""
import sys
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.test-libs'),str(ROOT/'app')]
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from trip_site import select_number
options=webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--no-first-run')
options.add_argument('--disable-background-networking')
driver=webdriver.Chrome(service=Service(str(ROOT/'app/driver/chromedriver.exe')),options=options)
try:
    driver.get('data:text/html;charset=utf-8,'+quote('<select id="hour"><option value="13" selected>13</option><option value="12">12</option><option value="13">13시</option></select><select id="minute"><option value="00" selected>00</option><option value="0">0분</option><option value="15">15</option></select>'))
    hour=driver.find_element(By.ID,'hour');minute=driver.find_element(By.ID,'minute')
    select_number(driver,hour,13);select_number(driver,minute,0)
    assert hour.get_attribute('value')=='13' and minute.get_attribute('value')=='0'
    select_number(driver,minute,15)
    assert Select(minute).first_selected_option.text=='15'
    print('DUPLICATE_TIME_CHROME_OK: duplicate saved hour/minute options selected and verified; no target-site requests')
finally:driver.quit()
