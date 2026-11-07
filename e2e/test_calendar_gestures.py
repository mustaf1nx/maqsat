from playwright.sync_api import sync_playwright
from test_browser import Harness,server
from calendar_journey import calendar_journey

def test_calendar_mouse_range_and_management(server):
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            h=Harness(browser,server);h.login();assert len(calendar_journey(h))>=15
        finally:browser.close()

def test_calendar_touch_and_mobile_views(server):
    from calendar_mobile import mobile_calendar_journey
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            h=Harness(browser,server,390,touch=True);h.login();assert len(mobile_calendar_journey(h))==31
        finally:browser.close()
