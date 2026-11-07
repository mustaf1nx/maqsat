from playwright.sync_api import expect

def mobile_calendar_journey(h):
    page=h.page;results=[]
    for theme in ['dark','light']:
        if page.evaluate('document.documentElement.dataset.theme')!=theme:page.get_by_role('button',name='Сменить тему',exact=True).click()
        for label in ['Сегодня','Расписание','Задачи','Корзина идей','Фокус','Цели','Работа','Финансы','Тренировки','Привычки','Аналитика','Настройки']:
            h.nav(label);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(theme,label)
            assert not h.errors,h.errors
            results.append(theme+': '+label)
    h.nav('Расписание');page.get_by_label('Дата календаря',exact=True).fill('2031-01-06');page.get_by_label('Вид календаря',exact=True).select_option('day');page.wait_for_timeout(200)
    col=page.locator('[data-time-day="2031-01-06"]');r=col.bounding_box();x=r['x']+r['width']/2;y=r['y']+10*64
    page.touchscreen.tap(x,y);expect(page.locator('dialog[open]')).to_have_count(1)
    expect(page.get_by_test_id('selection-summary')).to_contain_text('10:00 — 11:00');page.locator('dialog[open]').get_by_role('button',name='Закрыть',exact=True).click()
    results.append('Touch tap opens default-duration draft')
    for view in ['week','workweek','month','year','list','day']:
        page.get_by_label('Вид календаря',exact=True).select_option(view);page.wait_for_timeout(160)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),view
        results.append('calendar '+view+' no document overflow')
    assert not h.errors,h.errors
    return results
