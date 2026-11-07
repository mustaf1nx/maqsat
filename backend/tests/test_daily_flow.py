from datetime import datetime,timedelta,timezone,date
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import select,delete
from fastapi.testclient import TestClient
import pytest
from app.main import app
from app import models,common
from app.security import COOKIE_NAME,token_digest
from app.routers import calendar,finance,health,overview,planning

EVENT={'title':'Зал','starts_at':'2026-11-09T10:00:00+05:00','ends_at':'2026-11-09T11:00:00+05:00','category':'Тренировка','timezone':'Asia/Almaty','location':'Зал 2'}
RULE={'frequency':'weekly','interval':1,'weekdays':[0,2,4],'until':'2026-11-20'}

def rows(a,start='2026-11-09',end='2026-11-23'):
    r=a.get(f'/events?start={start}T00:00:00Z&end={end}T00:00:00Z');assert r.status_code==200,r.text;return r.json()

def test_idea_deleted_task_becomes_convertible_and_can_be_recreated(a):
    idea=a.make('/ideas',{'title':'Idea'})
    task=a.post(f"/ideas/{idea['id']}/to-task").json()
    assert a.get('/ideas').json()[0]['converted_task_id']==task['id']
    assert a.delete('/tasks/'+task['id']).status_code==200
    assert a.get('/ideas').json()[0]['converted_task_id'] is None
    second=a.post(f"/ideas/{idea['id']}/to-task").json()
    assert second['id']!=task['id'];assert len(a.get('/tasks').json())==1

def test_idea_conversion_is_idempotent_and_live_completed_state(a):
    idea=a.make('/ideas',{'title':'idea','note':'Note'})
    first=a.post('/ideas/'+idea['id']+'/to-task').json()
    second=a.post('/ideas/'+idea['id']+'/to-task').json()
    assert first['id']==second['id']
    a.patch('/tasks/'+first['id'],{'completed':True})
    assert a.get('/ideas').json()[0]['task_completed'] is True
    a.delete('/ideas/'+idea['id'])
    assert len(a.get('/tasks').json())==1

def test_foreign_key_clears_idea_even_direct_sql_delete(a,env):
    idea=a.make('/ideas',{'title':'fk'})
    task=a.post('/ideas/'+idea['id']+'/to-task').json()
    with env() as db:db.execute(delete(models.Task).where(models.Task.id==task['id']));db.commit()
    assert a.get('/ideas').json()[0]['converted_task_id'] is None

def test_task_edit_checklist_version_and_rollback(a):
    t=a.make('/tasks',{'title':'before','checklist':[{'id':'one','title':'step'}]})
    r=a.patch('/tasks/'+t['id'],{'title':'after','version':t['version'],'checklist':[{'id':'one','title':'step','completed':True}]})
    assert r.status_code==200;assert r.json()['version']==t['version']+1
    assert r.json()['checklist'][0]['completed'] is True
    assert a.patch('/tasks/'+t['id'],{'title':'stale','version':t['version']}).status_code==409
    assert a.get('/tasks').json()[0]['title']=='after'
    assert a.patch('/tasks/'+t['id'],{'title':None}).status_code==422
    assert a.patch('/tasks/'+t['id'],{'checklist':[{'id':'a','title':'1'},{'id':'a','title':'2'}]}).status_code==422

def test_task_completed_at_roundtrip(a):
    t=a.make('/tasks',{'title':'complete'})
    done=a.patch('/tasks/'+t['id'],{'completed':True}).json();assert done['completed_at']
    assert a.patch('/tasks/'+t['id'],{'completed':False}).json()['completed_at'] is None

def test_linked_goal_progress_and_delete_goal(a):
    g=a.make('/goals',{'title':'goal','mode':'tasks','progress':99})
    t1=a.make('/tasks',{'title':'one','goal_id':g['id']})
    t2=a.make('/tasks',{'title':'two','goal_id':g['id']})
    assert a.get('/goals').json()[0]['progress']==0
    a.patch('/tasks/'+t1['id'],{'completed':True})
    assert a.get('/goals').json()[0]['progress']==50
    a.delete('/tasks/'+t2['id']);assert a.get('/goals').json()[0]['progress']==100
    a.delete('/goals/'+g['id']);assert a.get('/tasks').json()[0]['goal_id'] is None

def test_weekly_repeat_selected_days_and_inclusive_until(a):
    e=a.make('/events',{**EVENT,'recurrence':RULE})
    found=rows(a)
    assert [r['occurrence_key'] for r in found]==['2026-11-09','2026-11-11','2026-11-13','2026-11-16','2026-11-18','2026-11-20']
    assert len(set(r['occurrence_id'] for r in found))==6
    assert all(r['event_id']==e['id'] for r in found)

def test_two_week_cycle_and_daily_cycle(a):
    a.make('/events',{**EVENT,'recurrence':{**RULE,'interval':2,'until':'2026-11-30'}})
    assert [r['occurrence_key'] for r in rows(a,'2026-11-09','2026-11-30')]==['2026-11-09','2026-11-11','2026-11-13','2026-11-23','2026-11-25','2026-11-27']
    a.make('/events',{**EVENT,'title':'Daily','recurrence':{'frequency':'daily','interval':3,'until':'2026-11-16'}})
    assert [r['occurrence_key'] for r in rows(a) if r['title']=='Daily']==['2026-11-09','2026-11-12','2026-11-15']

def test_move_one_occurrence_outside_range_no_duplicate_and_undo(a):
    e=a.make('/events',{**EVENT,'recurrence':RULE})
    endpoint=f"/events/{e['id']}/occurrences/2026-11-09"
    r=a.patch(endpoint,{'starts_at':'2026-12-01T05:00:00Z','ends_at':'2026-12-01T06:30:00Z','version':1})
    assert r.status_code==200
    assert len(rows(a))==5
    december=rows(a,'2026-12-01','2026-12-02');assert len(december)==1
    assert december[0]['occurrence_key']=='2026-11-09'
    assert a.patch(endpoint,{'title':'stale','version':1}).status_code==409
    assert a.patch(endpoint,{'starts_at':EVENT['starts_at'],'ends_at':EVENT['ends_at'],'version':r.json()['version']}).status_code==200
    assert len(rows(a))==6;assert not rows(a,'2026-12-01','2026-12-02')

def test_resize_one_cancel_and_edit_series(a):
    e=a.make('/events',{**EVENT,'recurrence':RULE})
    path=f"/events/{e['id']}/occurrences/2026-11-11"
    assert a.patch(path,{'ends_at':'2026-11-11T07:00:00Z'}).status_code==200
    found=rows(a);assert found[1]['ends_at'].startswith('2026-11-11T07:00')
    assert a.patch(path,{'cancelled':True}).status_code==200
    assert len(rows(a))==5
    assert a.patch('/events/'+e['id'],{'title':'Новый зал','location':'Другой адрес'}).status_code==200
    assert all(x['title']=='Новый зал' for x in rows(a))
    assert a.patch(f"/events/{e['id']}/occurrences/2026-11-10",{'title':'bad'}).status_code==404

def test_dst_series_keeps_wall_clock(a):
    a.make('/events',{'title':'DST','starts_at':'2026-03-02T10:00:00-05:00','ends_at':'2026-03-02T11:00:00-05:00','timezone':'America/New_York','recurrence':{'frequency':'weekly','weekdays':[0],'until':'2026-03-16'}})
    found=rows(a,'2026-03-01','2026-03-18')
    assert [x['starts_at'][11:16] for x in found]==['15:00','14:00','14:00']
    assert all(datetime.fromisoformat(x['starts_at']).astimezone(ZoneInfo('America/New_York')).hour==10 for x in found)

def test_midnight_overlap_and_range_boundaries(a):
    a.make('/events',{'title':'overnight','starts_at':'2026-11-09T23:00:00Z','ends_at':'2026-11-10T02:00:00Z'})
    assert len(rows(a,'2026-11-10','2026-11-11'))==1
    assert len(rows(a,'2026-11-11','2026-11-12'))==0
    assert a.get('/events?start=2026-11-10T02:00:00Z&end=2026-11-10T03:00:00Z').json()==[]
    assert a.get('/events?start=2026-11-10T00:00:00Z').status_code==422
    assert a.get('/events?start=2026-11-10T00:00:00Z&end=2028-11-10T00:00:00Z').status_code==422

@pytest.mark.parametrize('data',[{'ends_at':'2026-11-08T05:00:00Z'},{'ends_at':'2026-11-19T05:00:00Z'},{'starts_at':'2026-11-09T10:00:00'},{'timezone':'Invalid/Timezone'},{'recurrence':{'frequency':'weekly','weekdays':[]}},{'recurrence':{'frequency':'weekly','weekdays':[7]}},{'recurrence':{'frequency':'daily','interval':0}},{'recurrence':{'frequency':'daily','until':'2026-11-08'}},{'reminder_minutes':-1},{'reminder_minutes':10081}])
def test_invalid_events_rejected(a,data):assert a.post('/events',{**EVENT,**data}).status_code==422

def test_workout_calendar_connection_move_delete_history(a):
    e=a.make('/events',{**EVENT,'recurrence':RULE})
    w=a.make('/workouts',{'title':'Спина','event_id':e['id'],'event_key':'2026-11-09','status':'planned','exercises':[{'name':'Упражнение пользователя','sets':3,'reps':'8, 8, 7'}]})
    dup=a.make('/workouts',{'title':'duplicate','event_id':e['id'],'event_key':'2026-11-09'})
    assert dup['id']==w['id'];assert len(a.get('/workouts').json())==1
    a.patch(f"/events/{e['id']}/occurrences/2026-11-09",{'starts_at':'2026-11-10T08:00:00Z','ends_at':'2026-11-10T09:30:00Z'})
    updated=a.get('/workouts').json()[0]
    assert updated['happened_at'].startswith('2026-11-10T08:00');assert updated['minutes']==90;assert updated['exercises']==w['exercises']
    a.delete('/events/'+e['id']);historic=a.get('/workouts').json()[0]
    assert historic['event_id'] is None;assert historic['exercises']==w['exercises']
    assert a.patch('/workouts/'+w['id'],{'status':'done'}).status_code==200
    assert a.get('/events').json()==[]

def test_standalone_workout_creates_event_and_template_is_snapshot(a):
    template=a.make('/workout-templates',{'title':'Мой план','exercises':[{'name':'A','sets':2,'reps':'10'}]})
    w=a.make('/workouts',{'title':'Journal','exercises':template['exercises'],'status':'done'})
    assert len(a.get('/events').json())==1;assert w['event_key']=='single'
    a.patch('/workout-templates/'+template['id'],{'exercises':[{'name':'B','sets':4}]})
    assert a.get('/workouts').json()[0]['exercises'][0]['name']=='A'
    a.delete('/workout-templates/'+template['id']);assert len(a.get('/workouts').json())==1
    a.delete('/workouts/'+w['id']);assert len(a.get('/events').json())==1

def test_gym_in_calendar_appears_in_workout_plan_without_log(a):
    start=datetime.now(timezone.utc)+timedelta(hours=2)
    a.make('/events',{'title':'Зал','starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=1)).isoformat()})
    assert len(a.get('/workouts/upcoming').json())==1
    assert a.get('/workouts').json()==[]

def test_deleting_workout_template_detaches_event_not_journal(a):
    t=a.make('/workout-templates',{'title':'Template'})
    a.make('/events',{**EVENT,'workout_template_id':t['id']})
    a.delete('/workout-templates/'+t['id'])
    assert a.get('/events').json()[0]['workout_template_id'] is None

def test_ordinary_meeting_not_accepted_as_workout(a):
    e=a.make('/events',{**EVENT,'title':'Встреча','category':'Работа'})
    assert a.post('/workouts',{'title':'No','event_id':e['id'],'event_key':'single'}).status_code==422

def test_recurring_payment_roundtrip_and_delete_transaction(a):
    rec=a.make('/recurring',{'title':'Интернет','amount':'4990.50','day_of_month':31})
    paid=a.post('/recurring/'+rec['id']+'/confirm').json()
    tx=paid['transaction'];assert tx['amount']=='4990.50'
    assert a.get('/recurring').json()[0]['paid_this_month'] is True
    assert a.patch('/transactions/'+tx['id'],{'kind':'income'}).status_code==422
    a.delete('/transactions/'+tx['id']);assert a.get('/recurring').json()[0]['paid_this_month'] is False
    assert a.post('/recurring/'+rec['id']+'/confirm').json()['already_paid'] is False
    a.delete('/recurring/'+rec['id']);assert a.get('/transactions').json()[0]['recurring_id'] is None

def test_month_end_day31_leap_year_and_paused_payment(a,monkeypatch):
    rec=a.make('/recurring',{'title':'31','amount':'100','day_of_month':31})
    monkeypatch.setattr(common,'utcnow',lambda:datetime(2028,2,20,10,tzinfo=timezone.utc))
    assert a.get('/recurring').json()[0]['due_date']=='2028-02-29'
    monkeypatch.setattr(common,'utcnow',lambda:datetime(2027,2,20,10,tzinfo=timezone.utc))
    assert a.get('/recurring').json()[0]['due_date']=='2027-02-28'
    a.patch('/recurring/'+rec['id'],{'active':False})
    assert a.post('/recurring/'+rec['id']+'/confirm').status_code==409

@pytest.mark.parametrize('amount',['0','-1','1.001','nan','Infinity','1000000000000.00'])
def test_invalid_money(a,amount):assert a.post('/transactions',{'title':'bad','kind':'income','amount':amount}).status_code==422

def test_finance_exact_decimal_and_month_filter(a):
    now=datetime.now(timezone.utc)
    a.make('/transactions',{'title':'income','amount':'0.30','kind':'income'})
    a.make('/transactions',{'title':'expense','amount':'0.10','kind':'expense'})
    a.make('/transactions',{'title':'old','amount':'100.00','kind':'expense','happened_at':'2020-01-01T12:00:00Z'})
    d=a.get('/dashboard').json();assert d['month_net']=='0.20';assert d['net_flow']=='-99.80';assert d['expense_total']=='0.10'

def test_work_hours_expected_not_received_income_and_delete_project(a):
    p=a.make('/projects',{'title':'project','hourly_rate':'2500.00'})
    t=a.make('/tasks',{'title':'work','project_id':p['id']})
    entry=a.make('/work-entries',{'project_id':p['id'],'minutes':90})
    assert a.get('/projects').json()[0]['expected_income']=='3750.00'
    assert a.get('/transactions').json()==[]
    assert a.patch('/work-entries/'+entry['id'],{'minutes':120}).status_code==200
    assert a.get('/projects').json()[0]['expected_income']=='5000.00'
    a.delete('/projects/'+p['id']);assert a.get('/work-entries').json()==[];assert a.get('/tasks').json()[0]['project_id'] is None

def test_habit_numeric_value_idempotent_and_archive(a):
    h=a.make('/habits',{'title':'Read','target':10,'unit':'страниц'})
    today=datetime.now(ZoneInfo('Asia/Almaty')).date().isoformat()
    for _ in range(2):assert a.put('/habits/'+h['id']+'/log',{'day':today,'value':5}).status_code==200
    data=a.get('/habits').json()[0];assert data['value_today']==5;assert not data['checked_today']
    a.put('/habits/'+h['id']+'/log',{'day':today,'value':10});assert a.get('/habits').json()[0]['checked_today']
    a.patch('/habits/'+h['id'],{'archived':True});assert a.put('/habits/'+h['id']+'/log',{'day':today,'value':11}).status_code==409
    a.patch('/habits/'+h['id'],{'archived':False});assert a.get('/habits').json()[0]['value_today']==10
    a.put('/habits/'+h['id']+'/log',{'day':today,'value':0});assert a.get('/habits').json()[0]['value_today']==0
    a.delete('/habits/'+h['id']);assert a.get('/habits').json()==[]

def test_habit_schedule_future_and_streak_skips_offdays(a,env,monkeypatch):
    monkeypatch.setattr(common,'utcnow',lambda:datetime(2026,11,13,10,tzinfo=timezone.utc))
    h=a.make('/habits',{'title':'MWF','weekdays':[0,2,4]})
    with env() as db:
        obj=db.get(models.Habit,h['id']);obj.created_at=datetime(2026,11,9,tzinfo=timezone.utc);db.commit()
    for d in ['2026-11-09','2026-11-11']:assert a.put('/habits/'+h['id']+'/log',{'day':d,'value':1}).status_code==200
    assert a.get('/habits').json()[0]['streak']==2
    assert a.put('/habits/'+h['id']+'/log',{'day':'2026-11-10','value':1}).status_code==422
    assert a.put('/habits/'+h['id']+'/log',{'day':'2026-11-16','value':1}).status_code==422
    a.put('/habits/'+h['id']+'/log',{'day':'2026-11-13','value':1});assert a.get('/habits').json()[0]['streak']==3
    assert a.get('/habits').json()[0]['completion_rate']==100

@pytest.mark.parametrize('method',['pomodoro','long','custom','stopwatch'])
def test_focus_methods_idempotency_and_delete(a,method):
    x=a.make('/focus',{'minutes':25,'method':method,'client_id':'same'})
    y=a.make('/focus',{'minutes':25,'method':method,'client_id':'same'})
    assert x['id']==y['id'];assert a.get('/dashboard').json()['focus_minutes']==25
    a.delete('/focus/'+x['id']);assert a.get('/dashboard').json()['focus_minutes']==0

@pytest.mark.parametrize('path,payload',[
 ('tasks',{'title':'Task'}),('ideas',{'title':'Idea'}),('goals',{'title':'Goal'}),('events',EVENT),
 ('transactions',{'title':'Private','amount':'100','kind':'income'}),('recurring',{'title':'Subscription','amount':'100','day_of_month':1}),
 ('projects',{'title':'Project'}),('habits',{'title':'Habit'}),('workout-templates',{'title':'Template'}),('workouts',{'title':'Log'}),
 ('focus',{'minutes':5,'client_id':'private'}),('templates',{'title':'Template','kind':'task','data':{'title':'Hi'}})
])
def test_all_domains_owner_isolation(a,b,path,payload):
    x=a.make('/'+path,payload)
    assert b.get('/'+path).json()==[]
    assert b.delete('/'+path+'/'+x['id']).status_code==404
    if path not in ['focus','templates']:
        assert b.patch('/'+path+'/'+x['id'],{'title':'stolen'}).status_code==404
    assert len(a.get('/'+path).json())==1

def test_cross_owner_foreign_keys_rejected(a,b):
    goal=b.make('/goals',{'title':'Secret'})
    project=b.make('/projects',{'title':'Secret'})
    template=b.make('/workout-templates',{'title':'Secret'})
    event=b.make('/events',EVENT)
    for field,id in [('goal_id',goal['id']),('project_id',project['id'])]:
        assert a.post('/tasks',{'title':'steal',field:id}).status_code==404
    assert a.post('/work-entries',{'project_id':project['id'],'minutes':15}).status_code==404
    assert a.post('/events',{**EVENT,'workout_template_id':template['id']}).status_code==404
    assert a.post('/workouts',{'title':'steal','event_id':event['id'],'event_key':'single'}).status_code==404
    assert a.patch('/events/'+event['id']+'/occurrences/single',{'title':'steal'}).status_code==404

def test_templates_real_data_no_record_until_apply(a):
    template=a.make('/templates',{'title':'Review','kind':'task','data':{'title':'Week','completed':True,'due_at':'2026-11-09T10:00:00Z'}})
    assert a.get('/tasks').json()==[]
    assert template['data'].get('completed',False) is False
    assert template['data'].get('due_at') is None
    task=a.make('/tasks',template['data']);assert task['title']=='Week'
    assert a.post('/templates',{'title':'bad','kind':'task','data':{'title':''}}).status_code==422
    a.delete('/templates/'+template['id']);assert len(a.get('/tasks').json())==1

def test_search_and_export_private_no_secrets(a,b):
    a.make('/tasks',{'title':'Проект MAQSAT'});b.make('/ideas',{'title':'Secret MAQSAT'})
    result=a.get('/search?q=MAQSAT').json();assert len(result)==1
    exported=a.get('/export');assert exported.status_code==200
    assert 'Проект MAQSAT' in exported.text
    assert 'Secret' not in exported.text;assert 'password_hash' not in exported.text;assert 'token_hash' not in exported.text

def test_profile_timezone_changes_today(a,monkeypatch):
    monkeypatch.setattr(common,'utcnow',lambda:datetime(2026,11,9,21,tzinfo=timezone.utc))
    assert a.get('/dashboard').json()['today']=='2026-11-10'
    r=a.patch('/auth/profile',{'display_name':'New name','timezone':'UTC'});assert r.status_code==200
    assert a.get('/dashboard').json()['today']=='2026-11-09'
    assert a.patch('/auth/profile',{'timezone':'Mars/City'}).status_code==422

def test_today_dashboard_excludes_future_and_undated(a,monkeypatch):
    monkeypatch.setattr(common,'utcnow',lambda:datetime(2026,11,9,21,tzinfo=timezone.utc))
    for name,dt in [('today','2026-11-09T22:00:00Z'),('past','2026-11-08T12:00:00Z'),('future','2026-11-11T12:00:00Z'),('none',None)]:a.make('/tasks',{'title':name,'due_at':dt})
    d=a.get('/dashboard').json();assert [x['title'] for x in d['today_tasks']]==['today'];assert [x['title'] for x in d['overdue_tasks']]==['past']

def test_reminder_boundaries_and_location(a,monkeypatch):
    monkeypatch.setattr(calendar,'utcnow',lambda:datetime(2026,11,9,4,46,tzinfo=timezone.utc))
    e=a.make('/events',{**EVENT,'reminder_minutes':15})
    r=a.get('/reminders').json();assert len(r)==1;assert r[0]['is_due'];assert r[0]['location']=='Зал 2'
    a.patch('/events/'+e['id'],{'reminder_minutes':None});assert a.get('/reminders').json()==[]

@pytest.mark.parametrize('path',['/tasks','/ideas','/events','/goals','/transactions','/recurring','/projects','/work-entries','/focus','/workouts','/workout-templates','/habits','/templates','/dashboard','/search?q=abc','/export','/reminders'])
def test_every_private_collection_requires_login(env,path):assert TestClient(app).get('/api/v1'+path).status_code==401

@pytest.mark.parametrize('origin',['https://evil.example','null'])
def test_cross_site_origin_rejected(a,origin):
    r=a.client.post('/api/v1/tasks',headers={'Origin':origin,'X-CSRF-Token':a.csrf},json={'title':'bad'})
    assert r.status_code==403

def test_auth_logout_expiry_security_headers_and_no_secret_echo(a,env):
    response=a.client.get('/healthz');assert response.status_code==200;assert response.headers['x-content-type-options']=='nosniff'
    invalid=a.client.post('/api/v1/auth/login',json={'username':'x','password':'SUPER_SECRET_DO_NOT_ECHO'});assert invalid.status_code==422;assert 'SUPER_SECRET' not in invalid.text
    assert a.post('/auth/logout').status_code==200;assert a.get('/auth/me').status_code==401

def test_expired_session_rejected(a,env):
    with env() as db:
        row=db.scalar(select(models.LoginSession).where(models.LoginSession.user_id==a.user['id']));row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert a.get('/auth/me').status_code==401

def test_login_rate_limit_and_admin_permissions(a,b):
    assert b.get('/admin/diagnostics').status_code==403
    assert a.get('/admin/diagnostics').status_code==200
    assert b.get('/admin/users').status_code==403
    for _ in range(6):assert a.client.post('/api/v1/auth/login',json={'username':'missing','password':'wrong'}).status_code==401
    assert a.client.post('/api/v1/auth/login',json={'username':'missing','password':'wrong'}).status_code==429

@pytest.mark.parametrize('path,data',[
 ('/tasks',{'title':'   '}),('/tasks',{'title':'bad','user_id':'other'}),('/habits',{'title':'bad','weekdays':[]}),('/habits',{'title':'bad','target':0}),('/habits',{'title':'bad','unit':''}),('/focus',{'minutes':0}),('/focus',{'minutes':241}),('/focus',{'minutes':1,'method':'invalid'}),('/workouts',{'title':'bad','exercises':[{'name':'','sets':3}]}),('/workouts',{'title':'bad','exercises':[{'name':'x','sets':0}]}),('/workouts',{'title':'bad','event_id':'abc'}),('/recurring',{'title':'bad','amount':'1','day_of_month':32}),('/projects',{'title':'bad','hourly_rate':'-1'})])
def test_invalid_inputs_do_not_mutate(a,path,data):
    before=a.get(path).json();assert a.post(path,data).status_code==422;assert a.get(path).json()==before
