"""Mouse/touch calendar scenarios. Runs against an isolated API; no screenshots."""
from datetime import datetime, timedelta
from playwright.sync_api import expect


def calendar_journey(h):
    page=h.page;checks=[]
    def done(name):
        assert not h.errors,h.errors
        checks.append(name);print('PASS',name,flush=True)
    def get(path):return h.client.get('/api/v1'+path).json()
    def masters():return get('/events')
    def event(title):return next(e for e in masters() if e['title']==title)
    def dlg():return page.locator('dialog[open]').last
    def cancel():
        dlg().get_by_role('button',name='Закрыть',exact=True).click();expect(page.locator('dialog[open]')).to_have_count(0);page.wait_for_timeout(280)
    def save():
        dlg().get_by_role('button',name='Сохранить',exact=True).click();expect(page.locator('dialog[open]')).to_have_count(0);page.wait_for_timeout(250)
    def setup(day='2030-01-07',view='day',scroll_hour=8):
        h.nav('Расписание');page.get_by_label('Дата календаря',exact=True).fill(day)
        page.get_by_label('Вид календаря',exact=True).select_option(view);page.wait_for_timeout(220)
        if view in ['day','week','workweek']:page.locator('.calendar-scroll').evaluate('(e,v)=>e.scrollTop=v',scroll_hour*64)
    def point(day,minute,fraction=.5):
        r=page.locator(f'[data-time-day="{day}"]').bounding_box();assert r
        return (r['x']+r['width']*fraction,r['y']+minute/60*64)
    def drag(day,a,b,other_day=None):
        x,y=point(day,a);xx,yy=point(other_day or day,b)
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(xx,yy,steps=7)
    def create(title):
        dlg().get_by_label('Название события',exact=True).fill(title);save()
    def block(title):return page.get_by_test_id('calendar-event').filter(has_text=title).first
    def timeassert(title,start,end):
        e=event(title);assert e['starts_at'].startswith(start),(title,e['starts_at'],start)
        assert e['ends_at'].startswith(end),(title,e['ends_at'],end)
    setup()
    before=len(masters());drag('2030-01-07',600,690)
    expect(page.get_by_test_id('selection-preview')).to_have_count(1)
    assert len(masters())==before
    page.mouse.up();expect(dlg().get_by_test_id('selection-summary')).to_contain_text('10:00 — 11:30')
    assert len(masters())==before
    create('Gesture forward');assert len(masters())==before+1
    timeassert('Gesture forward','2030-01-07T05:00','2030-01-07T06:30')
    done('Forward drag previews without saving; release opens one timed draft; save creates one record')

    drag('2030-01-07',840,750);page.mouse.up()
    expect(dlg().get_by_test_id('selection-summary')).to_contain_text('12:30 — 14:00');create('Gesture reverse')
    timeassert('Gesture reverse','2030-01-07T07:30','2030-01-07T09:00')
    done('Reverse drag normalizes chronological start and end')

    before=len(masters());drag('2030-01-07',900,945);page.keyboard.press('Escape');page.mouse.up();page.wait_for_timeout(300)
    expect(page.locator('dialog[open]')).to_have_count(0);expect(page.get_by_test_id('selection-preview')).to_have_count(0)
    assert len(masters())==before
    drag('2030-01-07',900,945);page.evaluate('window.dispatchEvent(new Event("blur"))');page.mouse.up();page.wait_for_timeout(300)
    expect(page.locator('dialog[open]')).to_have_count(0);assert len(masters())==before
    done('Escape and window blur cancel without orphan or duplicate events')

    x,y=point('2030-01-07',900);page.mouse.click(x,y,button='right');page.wait_for_timeout(300)
    expect(page.locator('dialog[open]')).to_have_count(0)
    page.mouse.click(x,y);expect(dlg().get_by_test_id('selection-summary')).to_contain_text('15:00 — 16:00');cancel()
    done('Right button does not create; ordinary click preserves the default duration')

    # Existing event manipulation must never start a new draft.
    r=block('Gesture forward').bounding_box();page.mouse.move(r['x']+r['width']/2,r['y']+17);page.mouse.down();page.mouse.move(r['x']+r['width']/2,r['y']+81,steps=8);page.mouse.up();page.wait_for_timeout(300)
    expect(page.locator('dialog[open]')).to_have_count(0)
    timeassert('Gesture forward','2030-01-07T06:00','2030-01-07T07:30')
    page.locator('.toast').get_by_role('button',name='Отменить',exact=True).click();page.wait_for_timeout(300)
    timeassert('Gesture forward','2030-01-07T05:00','2030-01-07T06:30')
    done('Move existing event and undo retain duration without accidental creation')

    handle=block('Gesture forward').locator('.resize-handle.bottom').bounding_box()
    page.mouse.move(handle['x']+handle['width']/2,handle['y']+3);page.mouse.down();page.mouse.move(handle['x']+handle['width']/2,handle['y']+35,steps=8);page.mouse.up();page.wait_for_timeout(300)
    timeassert('Gesture forward','2030-01-07T05:00','2030-01-07T07:00')
    handle=block('Gesture forward').locator('.resize-handle.top').bounding_box()
    page.mouse.move(handle['x']+handle['width']/2,handle['y']+3);page.mouse.down();page.mouse.move(handle['x']+handle['width']/2,handle['y']-13,steps=8);page.mouse.up();page.wait_for_timeout(300)
    timeassert('Gesture forward','2030-01-07T04:45','2030-01-07T07:00')
    done('Both resize handles modify only the intended boundary')

    old=event('Gesture forward');h.fail=('PATCH','/events/')
    r=block('Gesture forward').bounding_box();page.mouse.move(r['x']+r['width']/2,r['y']+17);page.mouse.down();page.mouse.move(r['x']+r['width']/2,r['y']+81,steps=8);page.mouse.up();page.wait_for_timeout(250)
    assert event('Gesture forward')['starts_at']==old['starts_at']
    expect(block('Gesture forward').locator('.event-time')).to_contain_text('09:45')
    done('Server rejection rolls back the visual event and leaves stored time unchanged')

    block('Gesture forward').click();expect(dlg().get_by_role('heading',name='Gesture forward',exact=True)).to_be_visible()
    before=len(masters());dlg().get_by_role('button',name='Создать копию события',exact=True).click()
    expect(dlg().get_by_label('Название события',exact=True)).to_have_value('Gesture forward (копия)');assert len(masters())==before
    cancel();block('Gesture forward').click();dlg().get_by_role('button',name='Редактировать',exact=True).click()
    dlg().get_by_label('Место',exact=True).fill('Room 203');dlg().get_by_label('Ссылка на видеовстречу',exact=True).fill('https://meet.example.org/room')
    dlg().get_by_label('Доступность',exact=True).select_option('free');dlg().get_by_role('button',name='Добавить напоминание',exact=True).click();save()
    assert event('Gesture forward')['location']=='Room 203';assert event('Gesture forward')['reminders']==[15]
    done('Details, safe meeting link, editing, multiple reminders and duplicate draft')

    # Failed save retains title and selected interval, then supports retry.
    drag('2030-01-07',900,930);page.mouse.up();dlg().get_by_label('Название события',exact=True).fill('Gesture retry')
    before=len(masters());h.fail=('POST','/events');dlg().get_by_role('button',name='Сохранить',exact=True).click()
    expect(dlg().get_by_role('alert')).to_be_visible();expect(dlg().get_by_label('Название события',exact=True)).to_have_value('Gesture retry');assert len(masters())==before
    save();assert len(masters())==before+1
    done('Failed creation preserves the draft and retries once')

    setup(view='week');before=len(masters());drag('2030-01-11',600,660,'2030-01-12');page.mouse.up()
    expect(dlg().get_by_test_id('selection-summary')).to_contain_text('1500 мин');expect(dlg().get_by_role('button',name='Задача',exact=True)).to_be_disabled();create('Gesture multi-day')
    timeassert('Gesture multi-day','2030-01-11T05:00','2030-01-12T06:00');assert len(masters())==before+1
    done('Cross-column selection creates one multi-day event, not several duplicates')

    # Autoscroll operates while dragging and stops after cancellation.
    setup('2030-01-08');page.locator('.calendar-scroll').evaluate('(e)=>e.scrollTop=512')
    r=page.locator('.calendar-scroll').bounding_box();x,_=point('2030-01-08',900)
    page.mouse.move(x,r['y']+r['height']-80);page.mouse.down();page.mouse.move(x,r['y']+r['height']-4,steps=5);page.wait_for_timeout(220)
    assert page.locator('.calendar-scroll').evaluate('(e)=>e.scrollTop')>512
    page.keyboard.press('Escape');page.mouse.up();s=page.locator('.calendar-scroll').evaluate('(e)=>e.scrollTop');page.wait_for_timeout(150)
    assert page.locator('.calendar-scroll').evaluate('(e)=>e.scrollTop')==s
    done('Edge autoscroll works and stops on cancel')

    # Full-day selection across two columns, with the selected end day included.
    setup('2030-01-07','week')
    a=page.locator('.all-day-cell[data-select-day="2030-01-07"]').bounding_box();z=page.locator('.all-day-cell[data-select-day="2030-01-09"]').bounding_box()
    page.mouse.move(a['x']+a['width']/2,a['y']+20);page.mouse.down();page.mouse.move(z['x']+z['width']/2,z['y']+20,steps=6);page.mouse.up()
    expect(dlg().get_by_test_id('selection-summary')).to_contain_text('Весь день');create('Gesture all day')
    e=event('Gesture all day');assert e['all_day'];assert e['starts_at'].startswith('2030-01-06T19:00');assert e['ends_at'].startswith('2030-01-09T19:00')
    expect(page.locator('.all-day-strip .calendar-date-event').filter(has_text='Gesture all day')).to_have_count(3)
    done('All-day strip selects inclusive dates and stores exclusive end')

    setup('2030-01-07','month')
    a=page.locator('.month-day[data-select-day="2030-01-14"]').bounding_box();z=page.locator('.month-day[data-select-day="2030-01-16"]').bounding_box()
    # use the blank lower area, not the clickable date label
    page.mouse.move(a['x']+a['width']/2,a['y']+70);page.mouse.down();page.mouse.move(z['x']+z['width']/2,z['y']+70,steps=6);page.mouse.up();create('Gesture month')
    assert event('Gesture month')['all_day'];assert event('Gesture month')['ends_at'].startswith('2030-01-16T19:00')
    done('Month-grid date dragging creates a multi-day all-day event')

    # Calendar grouping and filter persistence.
    if page.get_by_role('button',name='Управление календарями',exact=True).count()==0:page.get_by_role('button',name='Показать панель календарей').click()
    page.get_by_role('button',name='Управление календарями',exact=True).click();dlg().get_by_label('Новый календарь').fill('Calendar QA');dlg().get_by_role('button',name='Создать календарь',exact=True).click();page.wait_for_timeout(150)
    assert any(c['title']=='Calendar QA' for c in get('/calendars'));cancel()
    setup('2030-01-07');block('Gesture forward').click();dlg().get_by_role('button',name='Редактировать',exact=True).click();c=next(c for c in get('/calendars') if c['title']=='Calendar QA');dlg().get_by_label('Календарь',exact=True).select_option(c['id']);save()
    page.get_by_label('Calendar QA',exact=True).uncheck();expect(block('Gesture forward')).to_have_count(0)
    page.get_by_label('Calendar QA',exact=True).check();expect(block('Gesture forward')).to_have_count(1)
    page.get_by_label('Поиск по текущему периоду',exact=True).fill('Room 203');expect(page.get_by_test_id('calendar-event')).to_have_count(1);page.get_by_label('Поиск по текущему периоду',exact=True).fill('')
    done('Private calendar creation, assignment, visibility and search')

    block('Gesture retry').click();dlg().get_by_role('button',name='Удалить событие',exact=True).click();dlg().get_by_role('button',name='Удалить',exact=True).click();page.wait_for_timeout(250)
    assert not any(e['title']=='Gesture retry' for e in masters())
    page.get_by_role('button',name='Корзина событий',exact=True).click();row=dlg().locator('.trash-row').filter(has_text='Gesture retry');row.get_by_role('button',name='Восстановить',exact=True).click();page.wait_for_timeout(220);assert event('Gesture retry');cancel()
    done('Deletion moves a record to trash; restore preserves its data')

    # User-selected grid density and time interval are live, not decorative.
    page.get_by_role('button',name='Настройки календаря',exact=True).click();dlg().get_by_label('Шаг выделения').select_option('5');dlg().get_by_label('Плотность сетки').select_option('88');dlg().get_by_label('Дополнительный часовой пояс').fill('Europe/London');save()
    assert page.locator('.calendar-timeline').evaluate('(e)=>e.offsetHeight')==24*88
    expect(page.locator('.time-labels small')).to_have_count(24)
    page.get_by_role('button',name='Настройки календаря',exact=True).click();dlg().get_by_label('Шаг выделения').select_option('15');dlg().get_by_label('Плотность сетки').select_option('64');dlg().get_by_label('Дополнительный часовой пояс').fill('');save()
    done('Preferences change actual grid geometry and secondary timezone labels')

    for mode in ['workweek','month','year','list','week','day']:
        page.get_by_label('Вид календаря',exact=True).select_option(mode);page.wait_for_timeout(150)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),mode
    expect(page.locator('.calendar-shell')).to_be_visible()
    page.locator('h1').click();page.keyboard.press('c');expect(dlg()).to_be_visible();cancel()
    page.keyboard.press('y');expect(page.locator('.year-calendar .mini-calendar')).to_have_count(12)
    page.get_by_label('Поиск по текущему периоду',exact=True).fill('w');expect(page.get_by_label('Вид календаря',exact=True)).to_have_value('year');page.get_by_label('Поиск по текущему периоду',exact=True).fill('')
    done('All six views render without page overflow; keyboard shortcuts ignore text inputs')
    return checks
