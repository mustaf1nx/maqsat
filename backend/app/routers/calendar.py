from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Event, EventOverride, Workout, WorkoutTemplate
from ..schemas import EventIn, EventPatch, OccurrencePatch
from ..common import owned, records, serialize, change, remove, merge_validated, aware, utcnow
from ..recurrence import expand, resolve_occurrence
from ..security import current_user, csrf_protected

router=APIRouter(prefix='/api/v1')


def is_workout(event):
    return event.category.lower() in {'тренировка','спорт','зал','здоровье'} or event.title.strip().lower() in {'зал','спортзал','gym','тренировка'}


def normalized(data):
    if data.get('recurrence'):
        rule=dict(data['recurrence'])
        if rule.get('until') and not isinstance(rule['until'],str): rule['until']=rule['until'].isoformat()
        data['recurrence']=rule
    return data


def validate_template(db,user,data):
    if data.get('workout_template_id'): owned(db,WorkoutTemplate,user,data['workout_template_id'])


def all_occurrences(db,user,start,end):
    if end<=start or end-start>timedelta(days=367):
        raise HTTPException(422,'Выберите диапазон до 366 дней')
    overrides=records(db,EventOverride,user)
    logs={(x.event_id,x.event_key):x for x in records(db,Workout,user) if x.event_id}
    result=[]
    for event in records(db,Event,user):
        own_overrides=[x for x in overrides if x.event_id==event.id]
        for row in expand(event,start,end,own_overrides):
            log=logs.get((event.id,row['occurrence_key']))
            row.update({'is_workout':is_workout(event),'workout_id':log.id if log else None,
                        'workout_status':log.status if log else None})
            result.append(row)
    return sorted(result,key=lambda x:x['starts_at'])


def get_occurrence(db,user,event_id,key,lock=False):
    event=owned(db,Event,user,event_id,lock=lock)
    override=db.scalar(select(EventOverride).where(EventOverride.event_id==event.id,EventOverride.user_id==user.id,EventOverride.occurrence_key==key))
    occurrence=resolve_occurrence(event,key,override)
    if not occurrence: raise HTTPException(404,'Событие в выбранную дату не найдено')
    return event,override,occurrence


def sync_workouts(db,user,event):
    """Retain journal content. Re-scheduling syncs date; deleted days are detached."""
    overrides={x.occurrence_key:x for x in db.scalars(select(EventOverride).where(EventOverride.event_id==event.id,EventOverride.user_id==user.id))}
    for log in db.scalars(select(Workout).where(Workout.user_id==user.id,Workout.event_id==event.id)):
        row=resolve_occurrence(event,log.event_key,overrides.get(log.event_key))
        if row:
            log.happened_at=datetime.fromisoformat(row['starts_at'])
            if log.status=='planned':
                log.minutes=max(1,int((datetime.fromisoformat(row['ends_at'])-log.happened_at).total_seconds()/60))
        else:
            log.event_id=None;log.event_key=None

@router.get('/events')
def events(start: AwareDatetime|None=None,end: AwareDatetime|None=None,user: User=Depends(current_user),db: Session=Depends(get_db)):
    if bool(start)!=bool(end): raise HTTPException(422,'Нужны начало и конец диапазона')
    if start and end: return all_occurrences(db,user,start,end)
    return [serialize(x) for x in sorted(records(db,Event,user),key=lambda x:x.starts_at)]

@router.post('/events',status_code=201)
def event_add(payload: EventIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    data=normalized(payload.model_dump());validate_template(db,user,data)
    event=Event(user_id=user.id,**data);db.add(event);db.commit();db.refresh(event)
    return serialize(event)

@router.patch('/events/{object_id}')
def event_patch(object_id: str,payload: EventPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    event=owned(db,Event,user,object_id,lock=True)
    data=normalized(merge_validated(event,payload,EventIn));validate_template(db,user,data)
    for k,v in data.items():setattr(event,k,v)
    db.flush();sync_workouts(db,user,event);db.commit()
    return serialize(event)

@router.patch('/events/{object_id}/occurrences/{key}')
def occurrence_patch(object_id: str,key: str,payload: OccurrencePatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    event,override,row=get_occurrence(db,user,object_id,key,lock=True)
    if payload.version is not None and event.version!=payload.version:
        raise HTTPException(409,'Событие уже изменилось. Обновите расписание.')
    values=payload.model_dump(exclude_unset=True,exclude={'version','cancelled'})
    if any(v is None for v in values.values()): raise HTTPException(422,'Поля события не могут быть пустыми')
    proposed={**row,**values}
    start=proposed['starts_at'];end=proposed['ends_at']
    if isinstance(start,str):start=datetime.fromisoformat(start)
    if isinstance(end,str):end=datetime.fromisoformat(end)
    if end<=start or end-start>timedelta(days=7):raise HTTPException(422,'Проверьте длительность события')
    if not event.recurrence:
        if payload.cancelled:
            for log in db.scalars(select(Workout).where(Workout.user_id==user.id,Workout.event_id==event.id)):
                log.event_id=None;log.event_key=None
            return remove(db,event)
        for k,v in values.items():setattr(event,k,v)
    else:
        if not override:
            override=EventOverride(user_id=user.id,event_id=event.id,occurrence_key=key,data={})
            db.add(override)
        override.data={**(override.data or {}),**{k:v.isoformat() if isinstance(v,datetime) else v for k,v in values.items()}}
        override.cancelled=payload.cancelled
    event.version+=1
    db.flush();sync_workouts(db,user,event);db.commit()
    return {'ok':True,'version':event.version}

@router.delete('/events/{object_id}')
def event_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    event=owned(db,Event,user,object_id)
    for log in db.scalars(select(Workout).where(Workout.user_id==user.id,Workout.event_id==event.id)):
        log.event_id=None;log.event_key=None
    db.execute(delete(EventOverride).where(EventOverride.user_id==user.id,EventOverride.event_id==event.id))
    return remove(db,event)

@router.get('/reminders')
def reminders(user: User=Depends(current_user),db: Session=Depends(get_db)):
    now=utcnow();result=[]
    for row in all_occurrences(db,user,now-timedelta(hours=1),now+timedelta(days=8)):
        minutes=row['reminder_minutes']
        if minutes is None:continue
        start=datetime.fromisoformat(row['starts_at'])
        due=start-timedelta(minutes=minutes)
        if now-timedelta(hours=24)<=due<=now+timedelta(hours=24):
            result.append({'id':f"{row['occurrence_id']}:{start.isoformat()}:{minutes}",
                           'title':row['title'],'starts_at':row['starts_at'],'due_at':due.isoformat(),
                           'location':row['location'],'is_due':due<=now,'event_id':row['event_id']})
    return sorted(result,key=lambda x:x['due_at'])
