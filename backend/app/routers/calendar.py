from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from hashlib import sha256
from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..db import get_db
from ..models import User, Event, EventOverride, Workout, WorkoutTemplate, CalendarCollection
from ..schemas import EventIn, EventPatch, OccurrencePatch, CalendarIn, CalendarPatch, CalendarImport
from ..common import owned, records, serialize, change, remove, merge_validated, aware, utcnow
from ..recurrence import expand, resolve_occurrence, base_occurrence, occurrence_number, matches_day
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
    if data.get('calendar_id'): owned(db,CalendarCollection,user,data['calendar_id'])


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
            row.update({'is_workout':is_workout(type('Occurrence',(),row)),'workout_id':log.id if log else None,
                        'workout_status':log.status if log else None})
            result.append(row)
    return sorted(result,key=lambda x:x['starts_at'])


def get_occurrence(db,user,event_id,key,lock=False,include_cancelled=False):
    event=owned(db,Event,user,event_id,lock=lock)
    override=db.scalar(select(EventOverride).where(EventOverride.event_id==event.id,EventOverride.user_id==user.id,EventOverride.occurrence_key==key))
    occurrence=resolve_occurrence(event,key,override)
    if occurrence is None and include_cancelled and override and override.cancelled:
        occurrence=base_occurrence(event,key)
        if occurrence:occurrence.update(override.data or {})
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
    event,override,row=get_occurrence(db,user,object_id,key,lock=True,include_cancelled=True)
    if payload.version is not None and event.version!=payload.version:
        raise HTTPException(409,'Событие уже изменилось. Обновите расписание.')
    values=payload.model_dump(exclude_unset=True,exclude={'version','cancelled'})
    proposed={name:row.get(name) for name in EventIn.model_fields}
    proposed.update(values)
    proposed['recurrence']=None  # one moved occurrence may be outside the series end
    try:
        validated=EventIn.model_validate(proposed).model_dump()
    except ValidationError:
        raise HTTPException(422,'Проверьте поля и длительность события') from None
    validate_template(db,user,validated)
    values={name:validated[name] for name in values}
    if not event.recurrence:
        if payload.cancelled:
            for log in db.scalars(select(Workout).where(Workout.user_id==user.id,Workout.event_id==event.id)):
                log.event_id=None;log.event_key=None
            event.deleted_at=utcnow();event.version+=1;db.commit();return {'ok':True}
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
    event.deleted_at=utcnow();event.version+=1;db.commit()
    return {'ok':True,'undo_id':event.id}

@router.get('/reminders')
def reminders(user: User=Depends(current_user),db: Session=Depends(get_db)):
    now=utcnow();result=[]
    for row in all_occurrences(db,user,now-timedelta(hours=1),now+timedelta(days=8)):
        for minutes in row.get('reminders') or ([row['reminder_minutes']] if row['reminder_minutes'] is not None else []):
            start=datetime.fromisoformat(row['starts_at'])
            due=start-timedelta(minutes=minutes)
            if now-timedelta(hours=24)<=due<=now+timedelta(hours=24):
                result.append({'id':f"{row['occurrence_id']}:{start.isoformat()}:{minutes}",
                               'title':row['title'],'starts_at':row['starts_at'],'due_at':due.isoformat(),
                               'location':row['location'],'is_due':due<=now,'event_id':row['event_id']})
    return sorted(result,key=lambda x:x['due_at'])


@router.get('/calendars')
def calendars(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in sorted(records(db,CalendarCollection,user),key=lambda x:x.created_at)]


@router.post('/calendars',status_code=201)
def calendar_add(payload: CalendarIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=CalendarCollection(user_id=user.id,**payload.model_dump());db.add(obj);db.commit();return serialize(obj)


@router.patch('/calendars/{object_id}')
def calendar_edit(object_id: str,payload: CalendarPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,CalendarCollection,user,object_id,lock=True)
    return change(db,obj,merge_validated(obj,payload,CalendarIn))


@router.delete('/calendars/{object_id}')
def calendar_remove(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,CalendarCollection,user,object_id,lock=True)
    # Keep all events; deleting a grouping is not deleting the user's schedule.
    for ev in db.scalars(select(Event).where(Event.user_id==user.id,Event.calendar_id==obj.id)):
        ev.calendar_id=None;ev.version+=1
    for override in records(db,EventOverride,user):
        if override.data.get('calendar_id')==obj.id:override.data={**override.data,'calendar_id':None}
    return remove(db,obj)


@router.get('/calendar-trash')
def trash(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Event).where(Event.user_id==user.id,Event.deleted_at.is_not(None)).order_by(Event.deleted_at.desc()))]


def trashed(db,user,object_id):
    obj=db.scalar(select(Event).where(Event.id==object_id,Event.user_id==user.id,Event.deleted_at.is_not(None)).with_for_update())
    if obj is None:raise HTTPException(404,'Удалённое событие не найдено')
    return obj


@router.post('/calendar-trash/{object_id}/restore')
def restore(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=trashed(db,user,object_id);obj.deleted_at=None;obj.version+=1;db.commit();return serialize(obj)


@router.delete('/calendar-trash/{object_id}')
def purge(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=trashed(db,user,object_id)
    return remove(db,obj)


@router.patch('/events/{object_id}/following/{key}')
def edit_following(object_id: str,key: str,payload: EventPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    """Split a series atomically; never rewrite its earlier occurrences."""
    event,override,row=get_occurrence(db,user,object_id,key,lock=True)
    if not event.recurrence or key=='single':raise HTTPException(422,'Это не повторяющаяся серия')
    incoming=payload.model_dump(exclude_unset=True);version=incoming.pop('version',None)
    if version is not None and version!=event.version:raise HTTPException(409,'Серия уже изменена. Обновите расписание.')
    base=base_occurrence(event,key);number=occurrence_number(event,date.fromisoformat(key))
    values={name:getattr(event,name) for name in EventIn.model_fields}
    values.update(starts_at=datetime.fromisoformat(base['starts_at']),ends_at=datetime.fromisoformat(base['ends_at']))
    values.update(incoming)
    rule=values.get('recurrence')
    # An omitted rule inherits the remaining COUNT. An explicit rule is respected.
    if rule and rule.get('count') and 'recurrence' not in incoming:
        rule={**rule,'count':max(1,rule['count']-number+1)};values['recurrence']=rule
    try:values=normalized(EventIn.model_validate(values).model_dump())
    except ValidationError:raise HTTPException(422,'Проверьте поля новой части серии') from None
    validate_template(db,user,values)
    if number==1:
        for name,value in values.items():setattr(event,name,value)
        event.version+=1;db.flush();sync_workouts(db,user,event);db.commit();return serialize(event)
    old_rule={**event.recurrence,'until':(date.fromisoformat(key)-timedelta(days=1)).isoformat(),'count':None}
    event.recurrence=old_rule;event.version+=1
    new=Event(user_id=user.id,**values);db.add(new);db.flush()
    for ex in list(db.scalars(select(EventOverride).where(EventOverride.event_id==event.id,EventOverride.user_id==user.id))):
        if ex.occurrence_key>=key:
            if new.recurrence and matches_day(new,date.fromisoformat(ex.occurrence_key)):
                ex.event_id=new.id
            else:db.delete(ex)
    for log in db.scalars(select(Workout).where(Workout.user_id==user.id,Workout.event_id==event.id)):
        if log.event_key and log.event_key>=key:
            if new.recurrence and matches_day(new,date.fromisoformat(log.event_key)):log.event_id=new.id
            else:log.event_id=None;log.event_key=None
    db.flush();sync_workouts(db,user,event);sync_workouts(db,user,new);db.commit()
    return serialize(new)


@router.delete('/events/{object_id}/following/{key}')
def delete_following(object_id: str,key: str,version: int|None=None,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    event,_,_=get_occurrence(db,user,object_id,key,lock=True)
    if not event.recurrence or key=='single':raise HTTPException(422,'Это не серия')
    if version is not None and event.version!=version:raise HTTPException(409,'Серия уже изменена')
    if occurrence_number(event,date.fromisoformat(key))==1:return event_delete(object_id,user,db)
    event.recurrence={**event.recurrence,'until':(date.fromisoformat(key)-timedelta(days=1)).isoformat(),'count':None};event.version+=1
    for ex in list(db.scalars(select(EventOverride).where(EventOverride.event_id==event.id,EventOverride.user_id==user.id))):
        if ex.occurrence_key>=key:db.delete(ex)
    db.flush();sync_workouts(db,user,event);db.commit();return {'ok':True}


@router.get('/calendar-transfer/export')
def calendar_export(start: AwareDatetime,end: AwareDatetime,calendar_id: str|None=None,user: User=Depends(current_user),db: Session=Depends(get_db)):
    from ..calendar_transfer import export_snapshot
    if calendar_id and calendar_id!='default':owned(db,CalendarCollection,user,calendar_id)
    rows=all_occurrences(db,user,start,end)
    if calendar_id:rows=[x for x in rows if (x['calendar_id'] or 'default')==calendar_id]
    if len(rows)>5000:raise HTTPException(422,'Слишком много событий. Выберите меньший диапазон.')
    return {'filename':'maqsat-calendar.ics','content':export_snapshot(rows),'count':len(rows),'mode':'occurrences_snapshot'}


@router.post('/calendar-transfer/import')
def calendar_import(payload: CalendarImport,preview: bool=False,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    try:
        return import_calendar_records(payload,preview,user,db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Календарь изменился во время импорта. Проверьте файл и повторите импорт; дубликаты будут пропущены.') from None


def import_calendar_records(payload,preview,user,db):
    from ..calendar_transfer import parse_import
    if payload.calendar_id:owned(db,CalendarCollection,user,payload.calendar_id)
    try:items,warnings=parse_import(payload.content,user.timezone)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    existing={x.import_uid for x in db.scalars(select(Event).where(Event.user_id==user.id)) if x.import_uid}
    pending=[];seen=set(existing);skipped=0;exceptions=[]
    for item in items:
        if item['recurrence_id']:
            exceptions.append(item);continue
        if item['cancelled']:skipped+=1;continue
        uid=item['uid'] or sha256(str(item['data']).encode()).hexdigest()
        if uid in seen:skipped+=1;continue
        seen.add(uid);pending.append((uid,item))
    if preview:return {'created':len(pending),'skipped':skipped,'warnings':warnings,'titles':[x[1]['data']['title'] for x in pending]}
    imported={}
    for uid,item in pending:
        data=normalized(EventIn.model_validate(item['data']).model_dump());data['calendar_id']=payload.calendar_id
        event=Event(user_id=user.id,import_uid=uid,**data);db.add(event);db.flush();imported[uid]=event
        for key in set(item['exceptions']):
            if event.recurrence and matches_day(event,date.fromisoformat(key)):
                db.add(EventOverride(user_id=user.id,event_id=event.id,occurrence_key=key,data={},cancelled=True))
    for item in exceptions:
        ev=imported.get(item['uid'])
        if not ev:
            if item['uid'] not in existing:warnings.append('Исключение повторения пропущено: исходная серия не импортирована')
            continue
        key=datetime.fromisoformat(item['recurrence_id']).astimezone(ZoneInfo(ev.timezone)).date().isoformat()
        if not matches_day(ev,date.fromisoformat(key)):
            warnings.append('Исключение повторения не соответствует серии');continue
        db.flush()
        ex=db.scalar(select(EventOverride).where(EventOverride.event_id==ev.id,EventOverride.occurrence_key==key))
        if not ex:ex=EventOverride(user_id=user.id,event_id=ev.id,occurrence_key=key);db.add(ex)
        ex.cancelled=item['cancelled'];ex.data={k:v for k,v in item['data'].items() if k in {'title','starts_at','ends_at','note','location','meeting_url','all_day','reminders','availability'}}
    db.commit();return {'created':len(pending),'skipped':skipped,'warnings':warnings}
