"""Isolated databases only. PostgreSQL CI uses maqsat_test; never a live URL."""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,get_db
from app.models import User
from app.security import hash_password,FAILED_LOGINS

@pytest.fixture()
def env():
    url=os.environ.get('TEST_DATABASE_URL','sqlite://')
    if url!='sqlite://' and 'maqsat_test' not in url.rsplit('/',1)[-1]:
        raise RuntimeError('Refusing tests on a non-test database')
    engine=create_engine(url,**({'connect_args':{'check_same_thread':False},'poolclass':StaticPool} if url=='sqlite://' else {}))
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    Session=sessionmaker(engine,autoflush=False,expire_on_commit=False)
    def session():
        with Session() as db:yield db
    app.dependency_overrides[get_db]=session;FAILED_LOGINS.clear()
    with Session() as db:
        db.add(User(username='owner',display_name='Owner',password_hash=hash_password('strongpassword123'),is_admin=True))
        db.add(User(username='other',display_name='Other',password_hash=hash_password('strongpassword234')))
        db.commit()
    yield Session
    app.dependency_overrides.clear();FAILED_LOGINS.clear()
    Base.metadata.drop_all(engine);engine.dispose()

class API:
    def __init__(self,name='owner',password='strongpassword123'):
        self.client=TestClient(app)
        r=self.client.post('/api/v1/auth/login',json={'username':name,'password':password})
        assert r.status_code==200,r.text
        self.csrf=r.json()['csrf'];self.user=r.json()['user']
    def request(self,method,path,data=None):
        return self.client.request(method,'/api/v1'+path,headers={'X-CSRF-Token':self.csrf},json=data)
    def get(self,path):return self.request('GET',path)
    def post(self,path,data=None):return self.request('POST',path,data)
    def patch(self,path,data):return self.request('PATCH',path,data)
    def put(self,path,data):return self.request('PUT',path,data)
    def delete(self,path):return self.request('DELETE',path)
    def make(self,path,data):
        r=self.post(path,data);assert r.status_code==201,r.text;return r.json()

@pytest.fixture()
def a(env):return API()
@pytest.fixture()
def b(env):return API('other','strongpassword234')
