"""Account CLI must hash passwords, avoid secret output, revoke old sessions."""
import sys
import pytest
from sqlalchemy import select
from app import manage
from app.models import User,LoginSession
from app.security import verify_password
from conftest import API

def invoke(monkeypatch,session,args,answers):
    monkeypatch.setattr(manage,'SessionLocal',session)
    monkeypatch.setattr(sys,'argv',['manage',*args])
    values=iter(answers)
    monkeypatch.setattr(manage.getpass,'getpass',lambda prompt:next(values))
    manage.main()

def test_cli_create_admin_and_hash(env,monkeypatch,capsys):
    invoke(monkeypatch,env,['create-admin','--username','newadmin','--name','Administrator'],['long-test-password','long-test-password'])
    with env() as db:
        u=db.scalar(select(User).where(User.username=='newadmin'))
        assert u.is_admin and verify_password('long-test-password',u.password_hash)
        assert u.password_hash!='long-test-password'
    assert 'long-test-password' not in capsys.readouterr().out

def test_cli_password_change_revokes_all_sessions(a,env,monkeypatch):
    invoke(monkeypatch,env,['change-password','--username','owner'],['changed-test-password','changed-test-password'])
    assert a.get('/auth/me').status_code==401
    with env() as db:assert not list(db.scalars(select(LoginSession)))
    assert API('owner','changed-test-password').get('/auth/me').status_code==200

@pytest.mark.parametrize('command,name,answers',[
 ('create-admin','owner',['same-test-password','same-test-password']),
 ('change-password','missing',['same-test-password','same-test-password']),
 ('create-admin','wrong username',[]),
 ('create-admin','mismatch',['same-test-password','different-password']),
])
def test_cli_rejects_invalid_account_operations(env,monkeypatch,command,name,answers):
    with pytest.raises(SystemExit) as error:invoke(monkeypatch,env,[command,'--username',name],answers)
    assert error.value.code==2

def test_backfilled_habit_is_included_in_history_and_streak(a):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today=datetime.now(ZoneInfo('Asia/Almaty')).date()
    h=a.make('/habits',{'title':'Backfilled','weekdays':[0,1,2,3,4,5,6]})
    for d in [today-timedelta(days=1),today]:
        assert a.put('/habits/'+h['id']+'/log',{'day':d.isoformat(),'value':1}).status_code==200
    row=a.get('/habits').json()[0]
    assert row['streak']==2
    assert row['completion_rate']==100
