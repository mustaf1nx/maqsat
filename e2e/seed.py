import os
assert 'maqsat-e2e-' in os.environ.get('DATABASE_URL',''), 'Only the generated E2E database is allowed'
os.environ['APP_ENV']='development'
from app.db import Base,engine,SessionLocal
from app.models import User,Task,Event,Goal,RecurringPayment,Transaction,Habit,Idea
from app.security import hash_password
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
with SessionLocal() as s:
 u=User(username='tester',display_name='Азамат',password_hash=hash_password('test-local-Only-82736'),is_admin=True)
 s.add(u);s.flush()
 s.add(User(username='second',display_name='Второй',password_hash=hash_password('test-local-Only-82736')))
 today=datetime.now(ZoneInfo('Asia/Almaty')).replace(hour=9,minute=0,second=0,microsecond=0)
 for title,hr,area in [('Подготовить материал к уроку',9,'Работа'),('Разобрать задачи по алгоритмам',12,'Учёба'),('Запланировать следующую неделю',18,'Личное')]:
  s.add(Task(user_id=u.id,title=title,due_at=today.replace(hour=hr).astimezone(timezone.utc),area=area))
 s.add(Goal(user_id=u.id,title='Запустить MAQSAT',progress=65))
 for title,hr,cat,loc in [('Пары в университете',9,'Учёба','Аудитория 203'),('Работа над проектом',13,'Работа','Дома'),('Зал',18,'Тренировка','Спортивный зал')]:
  s.add(Event(user_id=u.id,title=title,starts_at=today.replace(hour=hr).astimezone(timezone.utc),ends_at=today.replace(hour=hr+1).astimezone(timezone.utc),category=cat,location=loc,timezone='Asia/Almaty'))
 s.add(RecurringPayment(user_id=u.id,title='Домашний интернет',amount=Decimal('4990'),day_of_month=10))
 s.add(RecurringPayment(user_id=u.id,title='Мобильная связь',amount=Decimal('2990'),day_of_month=15))
 s.add(Transaction(user_id=u.id,title='Кофе и перекус',amount=Decimal('1900'),kind='expense',category='Еда'))
 s.add(Habit(user_id=u.id,title='Читать',target=10,unit='страниц'))
 s.add(Habit(user_id=u.id,title='Подвести итоги дня',target=1))
 s.add(Idea(user_id=u.id,title='Новый формат урока',note='Сделать интерактивную игру по Python.'))
 s.commit()
