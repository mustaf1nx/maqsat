from playwright.sync_api import expect
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
results=[]
def check(name,fn):
 try:
  fn();results.append({'name':name,'status':'passed'});print('PASS',name,flush=True)
 except Exception as e:
  results.append({'name':name,'status':'failed','error':str(e)});print('FAIL',name,e,flush=True);raise

def journey(h):
 page=h.page
 page.set_default_timeout(6000)
 def dialog():return page.locator('dialog[open]').last
 def save():dialog().get_by_role('button',name='Сохранить',exact=True).click();expect(page.locator('dialog[open]')).to_have_count(0);page.wait_for_timeout(150)
 def get(path):return h.client.get('/api/v1'+path).json()
 def row(title):return page.get_by_test_id('task-row').filter(has=page.get_by_text(title,exact=True))
 check('login and all pages',lambda:all_pages(h))
 def idea_regression():
  h.nav('Корзина идей');page.get_by_role('button',name='Записать идею',exact=True).click();dialog().get_by_label('Название',exact=True).fill('QA idea');save()
  card=page.locator('.idea-card').filter(has_text='QA idea');card.get_by_role('button',name='Сделать задачей').click();expect(card.get_by_text('В задачах',exact=True)).to_be_visible()
  first=[i for i in get('/ideas') if i['title']=='QA idea'][0]['converted_task_id']
  h.nav('Задачи');row('QA idea').get_by_role('button',name='Удалить',exact=True).click();dialog().get_by_role('button',name='Удалить',exact=True).click();expect(page.locator('dialog[open]')).to_have_count(0)
  h.nav('Корзина идей');card=page.locator('.idea-card').filter(has_text='QA idea');expect(card.get_by_role('button',name='Сделать задачей')).to_be_visible();card.get_by_role('button',name='Сделать задачей').click();page.wait_for_timeout(200)
  assert [i for i in get('/ideas') if i['title']=='QA idea'][0]['converted_task_id']!=first
 check('idea → task → delete → reconvert',idea_regression)
 def edit_task():
  h.nav('Задачи');row('QA idea').locator('.row-main').click();dialog().get_by_label('Название задачи').fill('QA edited task');dialog().get_by_label('Приоритет').select_option('high');dialog().get_by_role('button',name='Добавить шаг').click();dialog().get_by_label('Название шага 1').fill('First step');save()
  assert [t for t in get('/tasks') if t['title']=='QA edited task'][0]['checklist'][0]['title']=='First step'
  row('QA edited task').get_by_role('button',name='Выполнить задачу QA edited task').click();page.locator('.toast').get_by_role('button',name='Отменить',exact=True).click();page.wait_for_timeout(200)
  assert [t for t in get('/tasks') if t['title']=='QA edited task'][0]['completed'] is False
 check('task click edit, checklist, complete and undo',edit_task)
 def failed_save():
  h.nav('Задачи');row('QA edited task').locator('.row-main').click();dialog().get_by_label('Название задачи').fill('QA must survive failed save');h.fail=('PATCH','/tasks/')
  dialog().get_by_role('button',name='Сохранить',exact=True).click();expect(dialog().get_by_role('alert')).to_be_visible();expect(dialog().get_by_label('Название задачи')).to_have_value('QA must survive failed save')
  assert not any(t['title']=='QA must survive failed save' for t in get('/tasks'));save();assert any(t['title']=='QA must survive failed save' for t in get('/tasks'))
 check('failed save keeps form and supports retry',failed_save)
 def template():
  h.nav('Задачи');before=len(get('/tasks'));page.get_by_role('button',name='Шаблоны',exact=True).click();card=dialog().locator('.template-card').filter(has_text='Недельный обзор');card.get_by_role('button',name='Применить').click();expect(dialog().get_by_label('Название задачи')).to_have_value('Подвести итоги недели');assert len(get('/tasks'))==before;save();assert len(get('/tasks'))==before+1
 check('finished template opens form, saves only on confirm',template)
 def quick():
  page.keyboard.press('Control+k');expect(dialog()).to_be_visible();dialog().get_by_label('Глобальный поиск').fill('QA quick income');dialog().get_by_role('button',name='Доход',exact=True).click();expect(dialog().get_by_label('Название',exact=True)).to_have_value('QA quick income');expect(dialog().get_by_label('Тип операции')).to_have_value('income');dialog().get_by_label('Сумма, ₸').fill('1234.50');save();assert any(x['title']=='QA quick income' for x in get('/transactions'))
 check('Ctrl K quick add Russian income',quick)
 today=datetime.now(ZoneInfo('Asia/Almaty')).date();day=today+timedelta(days=(7-today.weekday())%7 or 7);datekey=day.isoformat()
 def calendar_create():
  h.nav('Расписание');page.get_by_label('Дата календаря').fill(datekey);page.get_by_role('button',name='Добавить событие',exact=True).click();dialog().get_by_label('Название события').fill('QA цикл');dialog().get_by_label('Начало',exact=True).fill(datekey+'T10:00');dialog().get_by_label('Окончание',exact=True).fill(datekey+'T11:00');dialog().get_by_label('Место',exact=True).fill('QA аудитория');dialog().get_by_label('Повторять',exact=True).select_option('weekly');dialog().get_by_label('Напомнить',exact=True).select_option('15');save();
  event=[e for e in get('/events') if e['title']=='QA цикл'][0];assert event['recurrence']['weekdays']==[0,2,4];assert event['location']=='QA аудитория';assert event['reminder_minutes']==15
  assert page.get_by_test_id('calendar-event').filter(has_text='QA цикл').count()==3
 check('recurring weekdays, place, reminder calendar',calendar_create)
 def drag_resize():
  block=page.get_by_test_id('calendar-event').filter(has_text='QA цикл').first;box=block.bounding_box();assert box
  page.mouse.move(box['x']+box['width']/2,box['y']+18);page.mouse.down();page.mouse.move(box['x']+box['width']/2,box['y']+82,steps=10);page.mouse.up();page.wait_for_timeout(400)
  assert page.locator('dialog[open]').count()==0
  expect(page.get_by_test_id('calendar-event').filter(has_text='QA цикл').first.locator('.event-time')).to_contain_text('11:00')
  page.locator('.toast').get_by_role('button',name='Отменить',exact=True).click();page.wait_for_timeout(250)
  expect(page.get_by_test_id('calendar-event').filter(has_text='QA цикл').first.locator('.event-time')).to_contain_text('10:00')
  block=page.get_by_test_id('calendar-event').filter(has_text='QA цикл').first;handle=block.locator('.resize-handle').bounding_box();assert handle
  page.mouse.move(handle['x']+handle['width']/2,handle['y']+4);page.mouse.down();page.mouse.move(handle['x']+handle['width']/2,handle['y']+36,steps=8);page.mouse.up();page.wait_for_timeout(350)
  expect(page.get_by_test_id('calendar-event').filter(has_text='QA цикл').first.locator('.event-time')).to_contain_text('11:30')
 check('drag event, undo and resize by 30 minutes',drag_resize)
 def series_edit():
  page.get_by_test_id('calendar-event').filter(has_text='QA цикл').first.click();dialog().get_by_role('button',name='Вся серия',exact=True).click();dialog().get_by_label('Место',exact=True).fill('Новый адрес серии');save();assert [e for e in get('/events') if e['title']=='QA цикл'][0]['location']=='Новый адрес серии'
 check('edit whole recurrence series from an occurrence',series_edit)
 def workout():
  h.nav('Тренировки');page.get_by_role('button',name='Добавить тренировку',exact=True).click();dialog().get_by_label('Что тренировали / планируете?').fill('QA тренировка');dialog().get_by_role('button',name='Первое упражнение').click();dialog().get_by_label('Упражнение 1',exact=True).fill('Моё упражнение');dialog().get_by_label('Подходы 1',exact=True).fill('3');dialog().get_by_label('Повторы 1',exact=True).fill('8 / 8 / 7');dialog().get_by_role('button',name='Сохранить шаблон',exact=True).click();page.wait_for_timeout(200);dialog().get_by_label('Статус',exact=True).select_option('done');save()
  log=[x for x in get('/workouts') if x['title']=='QA тренировка'][0];assert log['exercises'][0]['sets']==3;assert log['event_id'];assert any(x['title']=='QA тренировка' for x in get('/workout-templates'))
  page.get_by_role('button',name='Добавить тренировку',exact=True).click();template=[x for x in get('/workout-templates') if x['title']=='QA тренировка'][0];dialog().get_by_label('Взять сохранённый шаблон').select_option(template['id']);expect(dialog().get_by_label('Упражнение 1',exact=True)).to_have_value('Моё упражнение');dialog().get_by_role('button',name='Отмена',exact=True).click()
 check('workout table, calendar event and reusable template',workout)
 def habit():
  h.nav('Привычки');page.get_by_role('button',name='Новая привычка',exact=True).click();dialog().get_by_label('Название привычки').fill('QA читать');dialog().get_by_label('Цель на день').fill('2');dialog().get_by_label('Единица',exact=True).fill('страницы');save();card=page.locator('.habit-card').filter(has_text='QA читать');card.get_by_role('button',name='+1',exact=True).click();page.wait_for_timeout(200);card.get_by_role('button',name='+1',exact=True).click();page.wait_for_timeout(200)
  assert [x for x in get('/habits') if x['title']=='QA читать'][0]['checked_today'] is True
  card.get_by_role('button',name='Приостановить привычку').click();page.get_by_role('button',name='Архив',exact=True).click();card=page.locator('.habit-card').filter(has_text='QA читать');expect(card).to_be_visible();card.get_by_role('button',name='Вернуть привычку').click();page.get_by_role('button',name='Активные',exact=True).click();expect(page.locator('.habit-card').filter(has_text='QA читать')).to_be_visible()
 check('numeric habit, archive and preserved history',habit)
 def payment():
  h.nav('Финансы');card=page.locator('.payment-card').filter(has_text='Домашний интернет');card.get_by_role('button',name='Оплатил',exact=True).click();expect(card.get_by_text('Оплачено',exact=True)).to_be_visible();assert len([x for x in get('/transactions') if x['title']=='Домашний интернет'])==1
  page.locator('.toast').get_by_role('button',name='Отменить',exact=True).click();expect(card.get_by_role('button',name='Оплатил',exact=True)).to_be_visible();assert len([x for x in get('/transactions') if x['title']=='Домашний интернет'])==0
  assert 'expense' not in page.locator('body').inner_text();assert 'income' not in page.locator('body').inner_text().replace('QA quick income','')
 check('monthly payment, single charge, undo, Russian labels',payment)
 def focus():
  h.nav('Фокус');page.get_by_role('button',name='Секундомер',exact=True).click();page.get_by_label('Задача или краткая цель').fill('QA фокус');page.get_by_role('button',name='Начать',exact=True).click();page.evaluate('window.__oldNow=Date.now;Date.now=()=>window.__oldNow()+65000');page.wait_for_timeout(400);h.nav('Задачи');h.nav('Фокус');assert page.get_by_test_id('focus-clock').inner_text()>='01:05'
  page.get_by_role('button',name='Пауза',exact=True).click();before=len(get('/focus'));page.get_by_role('button',name='Завершить и сохранить').click();page.wait_for_timeout(350);assert len(get('/focus'))==before+1;assert get('/focus')[0]['minutes']==1
  page.evaluate('Date.now=window.__oldNow')
 check('focus persists across navigation and saves once',focus)
 def theme_search():
  page.get_by_role('button',name='Сменить тему').click();assert page.evaluate('document.documentElement.dataset.theme')=='light';assert page.evaluate('JSON.parse(localStorage.getItem("maqsat:theme"))')=='light';page.keyboard.press('Control+k');dialog().get_by_label('Глобальный поиск').fill('QA must survive');page.wait_for_timeout(350);expect(dialog().locator('.search-result')).to_have_count(1);dialog().locator('.search-result').click();expect(dialog().get_by_label('Название задачи')).to_have_value('QA must survive failed save');dialog().get_by_role('button',name='Отмена',exact=True).click();page.get_by_role('button',name='Сменить тему').click()
 check('theme saved and global search opens editor',theme_search)
 def no_errors():assert h.errors==[],h.errors
 check('no JavaScript errors during journey',no_errors)


def all_pages(h):
 page=h.page
 for label in ['Сегодня','Задачи','Расписание','Корзина идей','Фокус','Цели','Работа','Финансы','Тренировки','Привычки','Аналитика','Настройки']:
  h.nav(label);assert not h.errors,h.errors;assert page.locator('h1').count()==1
 assert 'Личное пространство' not in page.locator('body').inner_text()

