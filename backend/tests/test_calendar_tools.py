"""Calendar 0.4 regressions. Uses only isolated fixtures, no external services."""
from datetime import datetime, date
import pytest
from app.calendar_transfer import escape,unescape,fold,parse_import,parse_rule,properties
from test_daily_flow import EVENT,rows

def make(a,**extra):return a.make('/events',{**EVENT,'title':'Встреча','category':'Личное',**extra})
def ic(*lines):return '\r\n'.join(['BEGIN:VCALENDAR','VERSION:2.0',*lines,'END:VCALENDAR',''])
def ve(uid='test',**fields):
    items={'UID':uid,'DTSTART':'20261109T050000Z','DTEND':'20261109T060000Z','SUMMARY':'Запись',**fields}
    return ['BEGIN:VEVENT',*(f'{k}:{v}' for k,v in items.items()),'END:VEVENT']

def test_calendar_owner_crud_and_delete_preserves_events(a,b):
    c=a.make('/calendars',{'title':'Работа','color':'#3b82f6'})
    e=make(a,calendar_id=c['id'])
    assert b.get('/calendars').json()==[]
    assert b.patch('/calendars/'+c['id'],{'title':'bad'}).status_code==404
    assert b.delete('/calendars/'+c['id']).status_code==404
    assert b.post('/events',{**EVENT,'calendar_id':c['id']}).status_code==404
    assert a.patch('/calendars/'+c['id'],{'title':'Учёба','color':'#abcdef'}).json()['title']=='Учёба'
    assert a.delete('/calendars/'+c['id']).status_code==200
    assert a.get('/events').json()[0]['calendar_id'] is None
    assert a.get('/events').json()[0]['id']==e['id']

@pytest.mark.parametrize('value',['red','#fff','#ff00ff;bad','url(javascript:1)'])
def test_calendar_color_rejects_css_injection(a,value):
    assert a.post('/calendars',{'title':'X','color':value}).status_code==422

@pytest.mark.parametrize('value',['javascript:alert(1)','http://example.com','https://user:pass@example.com','https://x.com\nscript'])
def test_meeting_link_rejects_unsafe_url(a,value):
    assert a.post('/events',{**EVENT,'meeting_url':value}).status_code==422

def test_trash_restore_purge_is_private_and_hides_schedule(a,b):
    e=make(a,meeting_url='https://meet.example.org/room',reminders=[30,0,15,15],availability='free')
    assert e['reminders']==[0,15,30]
    assert a.delete('/events/'+e['id']).status_code==200
    assert rows(a)==[];assert a.get('/events').json()==[]
    assert b.get('/calendar-trash').json()==[]
    assert b.post('/calendar-trash/'+e['id']+'/restore').status_code==404
    assert b.delete('/calendar-trash/'+e['id']).status_code==404
    assert a.patch('/events/'+e['id'],{'title':'bad'}).status_code==404
    restored=a.post('/calendar-trash/'+e['id']+'/restore');assert restored.status_code==200
    assert len(rows(a))==1;assert not a.get('/calendar-trash').json()
    assert a.delete('/events/'+e['id']).status_code==200
    assert a.delete('/calendar-trash/'+e['id']).status_code==200
    assert a.post('/calendar-trash/'+e['id']+'/restore').status_code==404

def test_recurring_cancel_can_be_undone_and_metadata_updated(a):
    c=a.make('/calendars',{'title':'Личное','color':'#ffffff'})
    e=make(a,recurrence={'frequency':'daily','count':3})
    path=f"/events/{e['id']}/occurrences/2026-11-10"
    cancel=a.patch(path,{'cancelled':True,'version':e['version']});assert cancel.status_code==200
    assert [x['occurrence_key'] for x in rows(a)]==['2026-11-09','2026-11-11']
    restore=a.patch(path,{'cancelled':False,'version':cancel.json()['version'],'calendar_id':c['id'],'color':'#abcdef','meeting_url':'https://example.org/meeting','reminders':[5,60],'availability':'free'})
    assert restore.status_code==200,restore.text
    found=rows(a);assert len(found)==3
    assert found[1]['calendar_id']==c['id'];assert found[1]['reminders']==[5,60]
    assert found[0]['reminders']==[];assert found[1]['availability']=='free'
    assert a.delete('/calendars/'+c['id']).status_code==200
    assert rows(a)[1]['calendar_id'] is None

@pytest.mark.parametrize('data',[{'reminders':[-1]},{'reminders':[10081]},{'reminders':[0,1,2,3,4,5]},{'all_day':True},{'recurrence':{'frequency':'weekly','weekdays':[]}},{'recurrence':{'frequency':'daily','count':0}},{'recurrence':{'frequency':'daily','count':3,'until':'2027-01-01'}}])
def test_calendar_new_invalid_inputs(a,data):
    assert a.post('/events',{**EVENT,**data}).status_code==422

def test_all_day_recurrence_keeps_midnight_through_dst(a):
    make(a,starts_at='2026-03-07T00:00:00-05:00',ends_at='2026-03-08T00:00:00-05:00',timezone='America/New_York',all_day=True,recurrence={'frequency':'daily','count':3})
    found=rows(a,'2026-03-07','2026-03-11');assert len(found)==3
    spans=[(datetime.fromisoformat(x['ends_at'])-datetime.fromisoformat(x['starts_at'])).total_seconds()/3600 for x in found]
    assert spans==[24,23,24]
    assert [x['start_date'] for x in found]==['2026-03-07','2026-03-08','2026-03-09']

def test_monthly_31_skips_missing_days_and_counts_valid_instances(a):
    make(a,starts_at='2026-01-31T10:00:00Z',ends_at='2026-01-31T11:00:00Z',timezone='UTC',recurrence={'frequency':'monthly','count':4})
    assert [x['occurrence_key'] for x in rows(a,'2026-01-01','2026-08-01')]==['2026-01-31','2026-03-31','2026-05-31','2026-07-31']

@pytest.mark.parametrize('mode,expected',[('weekday',['2026-11-09','2026-12-14','2027-01-11']),('last_weekday',['2026-11-30','2026-12-28','2027-01-25'])])
def test_monthly_nth_and_last_weekday(a,mode,expected):
    make(a,recurrence={'frequency':'monthly','monthly_mode':mode,'count':3})
    assert [x['occurrence_key'] for x in rows(a,'2026-11-01','2027-02-01')]==expected

def test_yearly_leap_day_skips_non_leap_years(a):
    make(a,starts_at='2024-02-29T10:00:00Z',ends_at='2024-02-29T11:00:00Z',timezone='UTC',recurrence={'frequency':'yearly','count':2})
    assert rows(a,'2027-01-01','2028-01-01')==[]
    assert [x['occurrence_key'] for x in rows(a,'2028-01-01','2029-01-01')]==['2028-02-29']
    assert rows(a,'2032-01-01','2033-01-01')==[]

def test_weekly_count_across_partial_first_week(a):
    make(a,starts_at='2026-11-11T10:00:00+05:00',ends_at='2026-11-11T11:00:00+05:00',recurrence={'frequency':'weekly','weekdays':[0,2,4],'interval':2,'count':4})
    assert [x['occurrence_key'] for x in rows(a,'2026-11-01','2026-12-01')]==['2026-11-11','2026-11-13','2026-11-23','2026-11-25']

def test_following_split_preserves_past_and_remaining_count(a):
    e=make(a,recurrence={'frequency':'daily','count':5})
    path=f"/events/{e['id']}/following/2026-11-11"
    assert a.patch(path,{'title':'bad','version':999}).status_code==409
    r=a.patch(path,{'title':'Новая часть','version':e['version']});assert r.status_code==200,r.text
    found=rows(a);assert len(found)==5
    assert [x['title'] for x in found]==['Встреча','Встреча','Новая часть','Новая часть','Новая часть']
    assert found[0]['event_id']==e['id'];assert found[2]['event_id']!=e['id']
    assert r.json()['recurrence']['count']==3

def test_following_preserves_future_exception(a):
    e=make(a,recurrence={'frequency':'daily','count':5})
    patch=a.patch(f"/events/{e['id']}/occurrences/2026-11-12",{'location':'Перенесённая комната'}).json()
    r=a.patch(f"/events/{e['id']}/following/2026-11-11",{'title':'New','version':patch['version']});assert r.status_code==200
    assert next(x for x in rows(a) if x['occurrence_key']=='2026-11-12')['location']=='Перенесённая комната'

def test_following_delete_preserves_past_and_first_goes_to_trash(a,b):
    e=make(a,recurrence={'frequency':'daily','count':5})
    assert b.delete(f"/events/{e['id']}/following/2026-11-11").status_code==404
    assert a.delete(f"/events/{e['id']}/following/2026-11-11").status_code==200
    assert len(rows(a))==2
    assert a.delete(f"/events/{e['id']}/following/2026-11-09").status_code==200
    assert rows(a)==[];assert len(a.get('/calendar-trash').json())==1

def test_calendar_export_private_snapshot_excludes_trash(a,b):
    c=a.make('/calendars',{'title':'Family'})
    e=make(a,calendar_id=c['id'],title='Қазақша, встреча; '+'длинный '*25,note='Строка 1\nСтрока 2',reminders=[0,30],recurrence={'frequency':'daily','count':2})
    make(b,title='PRIVATE')
    path='/calendar-transfer/export?start=2026-11-01T00:00:00Z&end=2026-12-01T00:00:00Z'
    result=a.get(path).json();assert result['count']==2;assert 'PRIVATE' not in result['content'];assert 'RRULE:' not in result['content']
    assert all(len(x.encode())<=75 for x in result['content'].split('\r\n'))
    parsed,warnings=parse_import(result['content'],'Asia/Almaty');assert len(parsed)==2;assert not warnings
    assert parsed[0]['data']['note']=='Строка 1\nСтрока 2';assert parsed[0]['data']['title']==e['title'];assert parsed[0]['data']['reminders']==[0,30]
    assert b.get(path+'&calendar_id='+c['id']).status_code==404
    a.delete('/events/'+e['id']);assert a.get(path).json()['count']==0

def test_ics_dryrun_duplicate_owner_and_deleted_uid(a,b):
    data={'content':ic(*ve())}
    assert a.post('/calendar-transfer/import?preview=true',data).json()['created']==1
    assert a.get('/events').json()==[]
    assert a.post('/calendar-transfer/import',data).json()['created']==1
    assert a.post('/calendar-transfer/import',data).json()['skipped']==1
    assert b.post('/calendar-transfer/import',data).json()['created']==1
    a.delete('/events/'+a.get('/events').json()[0]['id'])
    assert a.post('/calendar-transfer/import',data).json()['skipped']==1


def test_ics_recurrence_exdate_and_changed_occurrence(a):
    data={'content':ic(*ve(RRULE='FREQ=DAILY;COUNT=4',EXDATE='20261110T050000Z'),*ve(**{'RECURRENCE-ID':'20261111T050000Z','DTSTART':'20261111T080000Z','DTEND':'20261111T090000Z','SUMMARY':'Перенос'}))}
    r=a.post('/calendar-transfer/import',data);assert r.status_code==200,r.text
    result=rows(a);assert len(result)==3;assert [x['occurrence_key'] for x in result]==['2026-11-09','2026-11-11','2026-11-12']
    assert result[1]['title']=='Перенос';assert result[1]['starts_at'].startswith('2026-11-11T08:00')


def test_ics_all_day_exclusive_end_roundtrip(a):
    content=ic('BEGIN:VEVENT','UID:holiday','DTSTART;VALUE=DATE:20261109','DTEND;VALUE=DATE:20261112','SUMMARY:Отдых','END:VEVENT')
    assert a.post('/calendar-transfer/import',{'content':content}).json()['created']==1
    result=rows(a);assert len(result)==1;assert result[0]['all_day'];assert result[0]['start_date']=='2026-11-09';assert result[0]['end_date']=='2026-11-12'
    out=a.get('/calendar-transfer/export?start=2026-11-01T00:00:00Z&end=2026-12-01T00:00:00Z').json()['content']
    assert 'DTEND;VALUE=DATE:20261112' in out

@pytest.mark.parametrize('rule',['FREQ=HOURLY','FREQ=MONTHLY;BYSETPOS=1','FREQ=WEEKLY;BYDAY=2MO','FREQ=DAILY;INTERVAL=0','FREQ=DAILY;COUNT=2000'])
def test_ics_unsupported_rule_not_silently_changed(a,rule):
    r=a.post('/calendar-transfer/import',{'content':ic(*ve(RRULE=rule))});assert r.status_code==200
    assert r.json()['created']==0;assert r.json()['warnings'];assert a.get('/events').json()==[]

def test_ics_attendee_warned_and_url_not_fetched(a):
    r=a.post('/calendar-transfer/import',{'content':ic(*ve(ATTENDEE='mailto:private@example.com',URL='javascript:alert(1)'))}).json()
    assert r['created']==1;assert len(r['warnings'])==2
    assert a.get('/events').json()[0]['meeting_url']==''

@pytest.mark.parametrize('content',['not ics','BEGIN:VCALENDAR\nBEGIN:VEVENT','BEGIN:VCALENDAR\nEND:VEVENT'])
def test_ics_invalid_document(a,content):assert a.post('/calendar-transfer/import',{'content':content}).status_code==422

def test_ics_import_foreign_calendar(a,b):
    c=b.make('/calendars',{'title':'Private'})
    assert a.post('/calendar-transfer/import',{'content':ic(*ve()),'calendar_id':c['id']}).status_code==404

def test_ics_duplicate_within_one_file(a):
    r=a.post('/calendar-transfer/import',{'content':ic(*ve(),*ve())}).json();assert r['created']==1;assert r['skipped']==1

def test_ics_unicode_escaping_and_folding():
    text='Қазақша 🧭, ; \\ newline\n'*30
    assert unescape(escape(text))==text
    folded=fold('SUMMARY:'+escape(text))
    assert all(len(x.encode())<=75 for x in folded.split('\r\n'))
    assert folded.replace('\r\n ','')=='SUMMARY:'+escape(text)

def test_ics_limit_count():
    with pytest.raises(ValueError):properties(ic(*[x for n in range(501) for x in ve(str(n))]))

def test_following_explicit_count_is_not_confused_with_inherited_count(a):
    e=make(a,recurrence={'frequency':'daily','count':5})
    result=a.patch(f"/events/{e['id']}/following/2026-11-11",{'title':'Five new','recurrence':{'frequency':'daily','count':5}})
    assert result.status_code==200,result.text
    assert len(rows(a))==7
    assert rows(a)[2]['occurrence_index']==1


def test_personal_export_preserves_calendar_groups_and_trashed_events(a,b):
    c=a.make('/calendars',{'title':'Mine'});b.make('/calendars',{'title':'Not mine'})
    ev=make(a,calendar_id=c['id']);a.delete('/events/'+ev['id'])
    result=a.get('/export').json();assert result['schema_version']=='0.4.0'
    assert len(result['data']['calendars'])==1
    assert result['data']['events'][0]['deleted_at'] is not None
    assert result['data']['events'][0]['calendar_id']==c['id']


def test_saved_event_template_does_not_keep_dangling_calendar_id(a):
    c=a.make('/calendars',{'title':'Temp'})
    template=a.make('/templates',{'title':'Example','kind':'event','data':{**EVENT,'calendar_id':c['id']}})
    a.delete('/calendars/'+c['id'])
    assert 'calendar_id' not in template['data']
    assert a.post('/events',template['data']).status_code==201


def test_import_integrity_conflict_is_rolled_back_and_reported(a,env,monkeypatch):
    from sqlalchemy.exc import IntegrityError
    def conflict(*args,**kwargs):raise IntegrityError('test',{},Exception('simulated concurrent UID'))
    with monkeypatch.context() as m:
        m.setattr(env.class_,'flush',conflict)
        r=a.post('/calendar-transfer/import',{'content':ic(*ve())})
    assert r.status_code==409
    assert a.get('/events').json()==[]
