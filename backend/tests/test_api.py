"""Core API checks: auth, CSRF, data isolation, idempotency, input validation."""
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db import Base, get_db
from app import models
from app.security import hash_password

def sign_in(client, username='owner', password='strongpassword123'):
    res = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200, res.text
    return res.json()['csrf']

def write(client, method, path, csrf, payload=None):
    return client.request(method, '/api/v1'+path, headers={'X-CSRF-Token':csrf}, json=payload)

def test_login_csrf_and_isolation(env):
    a = TestClient(app)
    b = TestClient(app)
    a_csrf = sign_in(a)
    b_csrf = sign_in(b, 'other', 'strongpassword234')
    assert a.post('/api/v1/tasks', json={'title':'No CSRF'}).status_code == 403
    made = write(a, 'POST', '/tasks', a_csrf, {'title':'Private task','area':'Учёба'})
    assert made.status_code == 201, made.text
    id = made.json()['id']
    assert len(a.get('/api/v1/tasks').json()) == 1
    assert b.get('/api/v1/tasks').json() == []
    assert write(b, 'PATCH', f'/tasks/{id}', b_csrf, {'completed':True}).status_code == 404
    assert write(b, 'DELETE', f'/tasks/{id}', b_csrf).status_code == 404
    assert write(a, 'PATCH', f'/tasks/{id}', a_csrf, {'completed': True}).json()['completed'] is True
    assert a.get('/api/v1/dashboard').json()['tasks_done'] == 1
    assert b.get('/api/v1/dashboard').json()['tasks_done'] == 0
    assert write(b,'POST','/admin/users',b_csrf,{'username':'someone','display_name':'Someone','password':'somepassword123'}).status_code == 403

def test_finances_recurring_idempotency_and_decimal(env):
    client = TestClient(app)
    csrf = sign_in(client)
    rec = write(client,'POST','/recurring',csrf,{'title':'Интернет','amount':'3490.00','day_of_month':12})
    assert rec.status_code==201,rec.text
    r_id=rec.json()['id']
    first=write(client,'POST',f'/recurring/{r_id}/confirm',csrf)
    second=write(client,'POST',f'/recurring/{r_id}/confirm',csrf)
    assert first.status_code==200 and first.json()['already_paid'] is False
    assert second.status_code==200 and second.json()['already_paid'] is True
    tx=client.get('/api/v1/transactions').json()
    assert len(tx)==1 and tx[0]['amount']=='3490.00'
    assert client.get('/api/v1/dashboard').json()['net_flow']=='-3490.00'
    bad=write(client,'POST','/transactions',csrf,{'title':'bad','amount':'-5.00','kind':'expense'})
    assert bad.status_code==422

def test_ideas_conversion_and_event_validations(env):
    client=TestClient(app)
    csrf=sign_in(client)
    idea=write(client,'POST','/ideas',csrf,{'title':'Создать сайт'})
    assert idea.status_code==201
    id=idea.json()['id']
    first=write(client,'POST',f'/ideas/{id}/to-task',csrf)
    second=write(client,'POST',f'/ideas/{id}/to-task',csrf)
    assert first.json()['id']==second.json()['id']
    assert len(client.get('/api/v1/tasks').json())==1
    event=write(client,'POST','/events',csrf,{'title':'bad','starts_at':'2026-11-01T15:00:00Z','ends_at':'2026-11-01T14:00:00Z'})
    assert event.status_code==422
    goal=write(client,'POST','/goals',csrf,{'title':'Good goal','progress':150})
    assert goal.status_code==422

def test_password_change_revokes_other_sessions(env):
    a=TestClient(app)
    b=TestClient(app)
    ca=sign_in(a)
    cb=sign_in(b)
    result=write(a,'PATCH','/auth/password',ca,{'old_password':'strongpassword123','new_password':'newstrongpassword123'})
    assert result.status_code==200
    assert a.get('/api/v1/auth/me').status_code==200
    assert b.get('/api/v1/auth/me').status_code==401
    assert b.post('/api/v1/auth/login',json={'username':'owner','password':'newstrongpassword123'}).status_code==200

def test_admin_create_other_user_account(env):
    client=TestClient(app)
    csrf=sign_in(client)
    result=write(client,'POST','/admin/users',csrf,{'username':'newuser','display_name':'New User','password':'strongpassword999'})
    assert result.status_code==201
    assert result.json()['is_admin'] is False
    assert 'password_hash' not in str(result.json())
    assert len(client.get('/api/v1/admin/users').json())==3
    assert TestClient(app).post('/api/v1/auth/login',json={'username':'newuser','password':'strongpassword999'}).status_code==200
