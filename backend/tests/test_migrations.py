"""Upgrade the frozen old schema with real legacy rows, never the live DB."""
import os,sys,subprocess
from datetime import datetime,timezone,timedelta
from pathlib import Path
from decimal import Decimal
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app.db import Base
from app.security import hash_password,verify_password
ROOT=Path(__file__).resolve().parents[1]

def migrate(url,*args):
    env={**os.environ,'DATABASE_URL':url,'APP_ENV':'development','PYTHONPATH':str(ROOT)}
    r=subprocess.run([sys.executable,'-m','alembic',*args],cwd=ROOT,env=env,text=True,capture_output=True,timeout=30)
    assert r.returncode==0,r.stderr

def test_old_schema_upgrade_preserves_accounts_links_and_history(tmp_path):
    url='sqlite:///'+str(tmp_path/'upgrade.db');migrate(url,'upgrade','0001_initial')
    engine=sa.create_engine(url);meta=sa.MetaData();meta.reflect(engine)
    now=datetime(2026,11,7,10,tzinfo=timezone.utc);password=hash_password('legacy-Password-123')
    with engine.begin() as c:
        c.execute(meta.tables['users'].insert(),{'id':'owner','username':'legacy','display_name':'Legacy','password_hash':password,'is_admin':True,'created_at':now})
        c.execute(meta.tables['tasks'].insert(),{'id':'task','user_id':'owner','title':'Legacy task','note':'note','area':'Work','priority':'normal','due_at':now,'completed':True,'created_at':now,'updated_at':now})
        for id,linked in [('linked','task'),('orphan','deleted-task')]:
            c.execute(meta.tables['ideas'].insert(),{'id':id,'user_id':'owner','title':id,'note':'note','converted_task_id':linked,'created_at':now})
        c.execute(meta.tables['events'].insert(),{'id':'event','user_id':'owner','title':'Legacy event','starts_at':now,'ends_at':now+timedelta(hours=1),'category':'Работа','note':'old note','created_at':now})
        c.execute(meta.tables['habits'].insert(),{'id':'habit','user_id':'owner','title':'Habit','created_at':now})
        c.execute(meta.tables['habit_checks'].insert(),{'id':'check','user_id':'owner','habit_id':'habit','day':'2026-11-07'})
        c.execute(meta.tables['workouts'].insert(),{'id':'workout','user_id':'owner','title':'Old session','minutes':40,'note':'Keep this note','happened_at':now,'created_at':now})
        c.execute(meta.tables['focus_sessions'].insert(),{'id':'focus','user_id':'owner','minutes':25,'task_label':'Legacy focus','created_at':now})
        c.execute(meta.tables['finance_transactions'].insert(),{'id':'tx','user_id':'owner','title':'Old payment','amount':Decimal('1234.50'),'kind':'expense','category':'Subscriptions','happened_at':now,'recurring_id':'missing','period':'2026-11','created_at':now})
    migrate(url,'upgrade','head');migrate(url,'upgrade','head')
    meta=sa.MetaData();meta.reflect(engine)
    with engine.connect() as c:
        user=c.execute(sa.select(meta.tables['users'])).mappings().one();assert user['id']=='owner';assert verify_password('legacy-Password-123',user['password_hash']);assert user['timezone']=='Asia/Almaty'
        ideas={r['id']:r['converted_task_id'] for r in c.execute(sa.select(meta.tables['ideas'])).mappings()};assert ideas=={'linked':'task','orphan':None}
        task=c.execute(sa.select(meta.tables['tasks'])).mappings().one();assert task['completed'];assert task['completed_at'] is None;assert task['checklist']==[]
        habit=c.execute(sa.select(meta.tables['habits'])).mappings().one();assert habit['archived'] is False;assert habit['weekdays']==list(range(7));assert habit['target']==1
        check=c.execute(sa.select(meta.tables['habit_checks'])).mappings().one();assert check['value']==1
        workout=c.execute(sa.select(meta.tables['workouts'])).mappings().one();assert workout['note']=='Keep this note';assert workout['exercises']==[];assert workout['status']=='done'
        tx=c.execute(sa.select(meta.tables['finance_transactions'])).mappings().one();assert tx['amount']==Decimal('1234.50');assert tx['recurring_id'] is None
        assert c.execute(sa.text('PRAGMA foreign_key_check')).all()==[]
        context=MigrationContext.configure(c,opts={'compare_type':True})
        differences=compare_metadata(context,Base.metadata)
        assert not differences,differences
    engine.dispose()

def test_fresh_upgrade_and_empty_downgrade(tmp_path):
    url='sqlite:///'+str(tmp_path/'fresh.db')
    migrate(url,'upgrade','head')
    migrate(url,'downgrade','0001_initial')
    migrate(url,'upgrade','head')
    engine=sa.create_engine(url)
    with engine.connect() as c:
        assert c.execute(sa.text('SELECT version_num FROM alembic_version')).scalar()=='0002_daily_flow'
        assert len(sa.inspect(c).get_table_names())==18
    engine.dispose()
