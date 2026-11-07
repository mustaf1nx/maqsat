"""Real HTTP E2E runner, for the production Vite build. Uses a disposable SQLite DB.

Build frontend first. This suite is shipped for CI and local re-running; the
restricted authoring sandbox instead used a documented in-process bridge.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import pytest
from playwright.sync_api import sync_playwright
from journey import journey
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='session')
def server():
    if not (ROOT/'web_dist/index.html').is_file():
        pytest.fail('Run cd frontend && npm install && npm run build first')
    with tempfile.TemporaryDirectory(prefix='maqsat-e2e-') as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'DATABASE_URL':'sqlite:///'+str(Path(tmp)/'browser.db'),
             'PYTHONPATH':str(ROOT/'backend'),'APP_ENV':'development',
             'APP_ORIGIN':f'http://127.0.0.1:{port}',
             'WEB_DIST_DIR':str(ROOT/'web_dist')}
        subprocess.run([sys.executable,str(ROOT/'e2e/seed.py')],env=env,check=True)
        logfile=open(Path(tmp)/'server.log','w')
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT/'backend',env=env,stdout=logfile,stderr=logfile)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url+'/healthz',timeout=1) as r:
                        if r.status==200:break
                except Exception:time.sleep(.1)
            else:pytest.fail('Test API did not start')
            yield url
        finally:proc.terminate();proc.wait(timeout=10);logfile.close()

class Client:
    def __init__(self,page,url):self.page=page;self.url=url
    def get(self,path):return self.page.request.get(self.url+path)

class Harness:
    def __init__(self,browser,url,width=1440,touch=False):
        self.page=browser.new_page(viewport={'width':width,'height':1100 if width>760 else 844},has_touch=touch,is_mobile=touch)
        self.page.set_default_timeout(10000)
        self.errors=[];self.fail=None;self.client=Client(self.page,url)
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        def route(request):
            if self.fail and self.fail[0]==request.request.method and self.fail[1] in request.request.url:
                self.fail=None;request.fulfill(status=503,content_type='application/json',body=json.dumps({'detail':'Проверка сбоя сервера'}))
            else:request.continue_()
        self.page.route('**/api/v1/**',route)
        self.page.goto(url)
    def login(self):
        self.page.get_by_label('Логин',exact=True).fill('tester')
        self.page.get_by_label('Пароль',exact=True).fill('test-local-Only-82736')
        self.page.get_by_role('button',name='Войти',exact=True).click()
        self.page.locator('.app-shell').wait_for();self.page.wait_for_timeout(300)
    def nav(self,label):
        if self.page.viewport_size['width']<760:
            self.page.get_by_role('button',name='Открыть меню',exact=True).click()
        self.page.locator('.sidebar').get_by_role('button',name=label,exact=True).click()
        self.page.wait_for_timeout(250)

def test_full_user_journey(server):
    with sync_playwright() as p:
        browser=p.chromium.launch()
        h=Harness(browser,server);h.login()
        try:journey(h)
        finally:browser.close()

def test_mobile_pages_no_document_overflow(server):
    with sync_playwright() as p:
        browser=p.chromium.launch();h=Harness(browser,server,390);h.login()
        try:
            for label in ['Сегодня','Расписание','Задачи','Корзина идей','Фокус','Цели','Работа','Финансы','Тренировки','Привычки','Аналитика','Настройки']:
                h.nav(label)
                assert h.page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),label
                assert not h.errors,h.errors
        finally:browser.close()
