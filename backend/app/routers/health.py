from datetime import datetime,timedelta,date
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select,delete,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User,Workout,WorkoutTemplate,Event,Habit,HabitCheck,FocusSession
from ..schemas import WorkoutIn,WorkoutPatch,WorkoutTemplateIn,WorkoutTemplatePatch,HabitIn,HabitPatch,HabitLogIn,FocusIn
from ..common import owned,records,serialize,add,change,remove,merge_validated,user_today,utcnow,aware
from ..security import current_user,csrf_protected
from .calendar import all_occurrences,get_occurrence,is_workout

router=APIRouter(prefix='/api/v1')

@router.get('/workout-templates')
def workout_templates(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in records(db,WorkoutTemplate,user)]

@router.post('/workout-templates',status_code=201)
def template_add(payload: WorkoutTemplateIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return add(db,WorkoutTemplate,user,**payload.model_dump())

@router.patch('/workout-templates/{object_id}')
def template_patch(object_id: str,payload: WorkoutTemplatePatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,WorkoutTemplate,user,object_id)
    return change(db,obj,merge_validated(obj,payload,WorkoutTemplateIn))

@router.delete('/workout-templates/{object_id}')
def template_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,WorkoutTemplate,user,object_id)
    db.execute(update(Event).where(Event.user_id==user.id,Event.workout_template_id==obj.id).values(workout_template_id=None))
    return remove(db,obj)

@router.get('/workouts/upcoming')
def upcoming(user: User=Depends(current_user),db: Session=Depends(get_db)):
    now=utcnow()
    return [x for x in all_occurrences(db,user,now-timedelta(days=1),now+timedelta(days=31)) if x['is_workout'] and x['workout_status']!='done']

@router.get('/workouts')
def workouts(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Workout).where(Workout.user_id==user.id).order_by(Workout.happened_at.desc()))]


def workout_link(db,user,data,existing=None):
    if data['event_id']:
        event,_,row=get_occurrence(db,user,data['event_id'],data['event_key'],lock=True)
        if not is_workout(event):raise HTTPException(422,'Выберите событие категории «Тренировка»')
        duplicate=db.scalar(select(Workout).where(Workout.user_id==user.id,Workout.event_id==event.id,Workout.event_key==data['event_key']))
        if duplicate and (not existing or duplicate.id!=existing.id):
            return duplicate
        data['happened_at']=datetime.fromisoformat(row['starts_at'])
    else:
        data['happened_at']=data['happened_at'] or utcnow()
        event=Event(user_id=user.id,title=data['title'],starts_at=data['happened_at'],
                    ends_at=data['happened_at']+timedelta(minutes=data['minutes']),category='Тренировка',timezone=user.timezone)
        db.add(event);db.flush();data['event_id']=event.id;data['event_key']='single'
    return None

@router.post('/workouts',status_code=201)
def workout_add(payload: WorkoutIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    data=payload.model_dump();existing=workout_link(db,user,data)
    # An accidental double click on the same planned session never creates two logs.
    if existing:return serialize(existing)
    return add(db,Workout,user,**data)

@router.patch('/workouts/{object_id}')
def workout_patch(object_id: str,payload: WorkoutPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Workout,user,object_id,lock=True);data=merge_validated(obj,payload,WorkoutIn)
    if data['event_id']:
        if workout_link(db,user,data,obj):raise HTTPException(409,'Для этого события уже есть тренировка')
    else:
        # A detached historical log remains historical; editing it must not recreate
        # a deliberately deleted calendar event.
        if data['happened_at'] is None:raise HTTPException(422,'Укажите дату тренировки')
    return change(db,obj,data)

@router.delete('/workouts/{object_id}')
def workout_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return remove(db,owned(db,Workout,user,object_id))


def habit_data(db,user):
    today=user_today(user);checks=records(db,HabitCheck,user);result=[]
    for obj in records(db,Habit,user):
        by_day={x.day:x.value for x in checks if x.habit_id==obj.id}
        current=by_day.get(today.isoformat(),0)
        # Count only scheduled days. Today does not break an unfinished streak.
        streak=0;cursor=today
        earliest=aware(obj.created_at).astimezone(__import__('zoneinfo').ZoneInfo(user.timezone)).date()
        if by_day:earliest=min(earliest,date.fromisoformat(min(by_day)))
        while cursor>=earliest and (today-cursor).days<=3660:
            if cursor.weekday() in obj.weekdays:
                if by_day.get(cursor.isoformat(),0)>=obj.target:streak+=1
                elif cursor!=today:break
            cursor-=timedelta(days=1)
        last=[today-timedelta(days=i) for i in reversed(range(28))]
        planned=[d for d in last if d>=earliest and d.weekday() in obj.weekdays]
        done=sum(by_day.get(d.isoformat(),0)>=obj.target for d in planned)
        result.append({**serialize(obj),'value_today':current,'checked_today':current>=obj.target,
                       'scheduled_today':today.weekday() in obj.weekdays,'streak':streak,
                       'completion_rate':round(done/len(planned)*100) if planned else 0,
                       'history':[{'day':d.isoformat(),'value':by_day.get(d.isoformat(),0),'scheduled':d in planned} for d in last]})
    return result

@router.get('/habits')
def habits(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return habit_data(db,user)

@router.post('/habits',status_code=201)
def habit_add(payload: HabitIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return add(db,Habit,user,**payload.model_dump())

@router.patch('/habits/{object_id}')
def habit_patch(object_id: str,payload: HabitPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Habit,user,object_id)
    return change(db,obj,merge_validated(obj,payload,HabitIn))


def save_habit_log(db,user,obj,day,value):
    today=user_today(user)
    if obj.archived:raise HTTPException(409,'Сначала верните привычку из архива')
    if day>today:raise HTTPException(422,'Будущий день ещё нельзя отметить')
    if day<today-timedelta(days=3660):raise HTTPException(422,'Дата слишком далеко в прошлом')
    if day.weekday() not in obj.weekdays:raise HTTPException(422,'Этот день не входит в расписание привычки')
    query=select(HabitCheck).where(HabitCheck.user_id==user.id,HabitCheck.habit_id==obj.id,HabitCheck.day==day.isoformat())
    check=db.scalar(query)
    if value==0:
        if check:db.delete(check)
    elif check:check.value=value
    else:db.add(HabitCheck(user_id=user.id,habit_id=obj.id,day=day.isoformat(),value=value))
    db.commit()
    return {'day':day.isoformat(),'value':value,'checked_today':value>=obj.target}

@router.put('/habits/{object_id}/log')
def habit_log(object_id: str,payload: HabitLogIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Habit,user,object_id,lock=True)
    return save_habit_log(db,user,obj,payload.day,payload.value)

@router.post('/habits/{object_id}/toggle')
def habit_toggle(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Habit,user,object_id,lock=True);today=user_today(user)
    check=db.scalar(select(HabitCheck).where(HabitCheck.user_id==user.id,HabitCheck.habit_id==obj.id,HabitCheck.day==today.isoformat()))
    return save_habit_log(db,user,obj,today,0 if check and check.value>=obj.target else obj.target)

@router.delete('/habits/{object_id}')
def habit_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Habit,user,object_id)
    db.execute(delete(HabitCheck).where(HabitCheck.user_id==user.id,HabitCheck.habit_id==obj.id))
    return remove(db,obj)

@router.get('/focus')
def focus(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(FocusSession).where(FocusSession.user_id==user.id).order_by(FocusSession.created_at.desc()).limit(500))]

@router.post('/focus',status_code=201)
def focus_add(payload: FocusIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    query=select(FocusSession).where(FocusSession.user_id==user.id,FocusSession.client_id==payload.client_id)
    if payload.client_id:
        existing=db.scalar(query)
        if existing:return serialize(existing)
    obj=FocusSession(user_id=user.id,**payload.model_dump());db.add(obj)
    try:db.commit()
    except IntegrityError:
        db.rollback();existing=db.scalar(query)
        if existing:return serialize(existing)
        raise
    return serialize(obj)

@router.delete('/focus/{object_id}')
def focus_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return remove(db,owned(db,FocusSession,user,object_id))
