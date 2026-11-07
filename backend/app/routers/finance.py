from datetime import date, datetime, timezone
from calendar import monthrange
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Transaction, RecurringPayment, Project, WorkEntry, Task
from ..schemas import MoneyIn,MoneyPatch,RecurringIn,RecurringPatch,ProjectIn,ProjectPatch,WorkIn,WorkPatch
from ..common import owned,records,serialize,add,change,remove,merge_validated,user_today,utcnow
from ..security import current_user,csrf_protected

router=APIRouter(prefix='/api/v1')

@router.get('/transactions')
def transactions(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Transaction).where(Transaction.user_id==user.id).order_by(Transaction.happened_at.desc()))]

@router.post('/transactions',status_code=201)
def tx_add(payload: MoneyIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    data=payload.model_dump();data['happened_at']=data['happened_at'] or utcnow()
    return add(db,Transaction,user,**data)

@router.patch('/transactions/{object_id}')
def tx_patch(object_id: str,payload: MoneyPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Transaction,user,object_id)
    data=merge_validated(obj,payload,MoneyIn)
    if not data['happened_at']:raise HTTPException(422,'Укажите дату операции')
    if obj.recurring_id and data['kind']!='expense':raise HTTPException(422,'Оплата подписки должна оставаться расходом')
    return change(db,obj,data)

@router.delete('/transactions/{object_id}')
def tx_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return remove(db,owned(db,Transaction,user,object_id))


def recurring_data(db,user):
    today=user_today(user);period=today.strftime('%Y-%m')
    paid={x.recurring_id:x for x in db.scalars(select(Transaction).where(Transaction.user_id==user.id,Transaction.period==period,Transaction.recurring_id.is_not(None)))}
    rows=[]
    for obj in records(db,RecurringPayment,user):
        due=today.replace(day=min(obj.day_of_month,monthrange(today.year,today.month)[1]))
        tx=paid.get(obj.id)
        rows.append({**serialize(obj),'due_date':due.isoformat(),'paid_this_month':bool(tx),
                     'transaction_id':tx.id if tx else None,'overdue':not tx and obj.active and due<today})
    return sorted(rows,key=lambda x:(not x['active'],x['paid_this_month'],x['due_date']))

@router.get('/recurring')
def recurring(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return recurring_data(db,user)

@router.post('/recurring',status_code=201)
def rec_add(payload: RecurringIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return add(db,RecurringPayment,user,**payload.model_dump())

@router.patch('/recurring/{object_id}')
def rec_patch(object_id: str,payload: RecurringPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,RecurringPayment,user,object_id)
    return change(db,obj,merge_validated(obj,payload,RecurringIn))

@router.post('/recurring/{object_id}/confirm')
def rec_confirm(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,RecurringPayment,user,object_id,lock=True)
    if not obj.active:raise HTTPException(409,'Платёж приостановлен')
    period=user_today(user).strftime('%Y-%m')
    query=select(Transaction).where(Transaction.user_id==user.id,Transaction.recurring_id==obj.id,Transaction.period==period)
    existing=db.scalar(query)
    if existing:return {'already_paid':True,'transaction':serialize(existing)}
    tx=Transaction(user_id=user.id,title=obj.title,amount=obj.amount,kind='expense',category='Регулярные платежи',recurring_id=obj.id,period=period)
    db.add(tx)
    try:db.commit()
    except IntegrityError:
        db.rollback();existing=db.scalar(query)
        if existing:return {'already_paid':True,'transaction':serialize(existing)}
        raise
    return {'already_paid':False,'transaction':serialize(tx)}

@router.delete('/recurring/{object_id}')
def rec_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,RecurringPayment,user,object_id)
    db.execute(update(Transaction).where(Transaction.user_id==user.id,Transaction.recurring_id==object_id).values(recurring_id=None))
    return remove(db,obj)

@router.get('/projects')
def projects(user: User=Depends(current_user),db: Session=Depends(get_db)):
    entries=records(db,WorkEntry,user);result=[]
    for p in records(db,Project,user):
        minutes=sum(x.minutes for x in entries if x.project_id==p.id)
        result.append({**serialize(p),'worked_minutes':minutes,'expected_income':format((Decimal(minutes)*p.hourly_rate/Decimal(60)).quantize(Decimal('0.01')),'.2f')})
    return result

@router.post('/projects',status_code=201)
def project_add(payload: ProjectIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return add(db,Project,user,**payload.model_dump())

@router.patch('/projects/{object_id}')
def project_patch(object_id: str,payload: ProjectPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Project,user,object_id)
    return change(db,obj,merge_validated(obj,payload,ProjectIn))

@router.delete('/projects/{object_id}')
def project_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Project,user,object_id)
    db.query(WorkEntry).filter(WorkEntry.user_id==user.id,WorkEntry.project_id==obj.id).delete(synchronize_session=False)
    db.execute(update(Task).where(Task.user_id==user.id,Task.project_id==obj.id).values(project_id=None))
    return remove(db,obj)

@router.get('/work-entries')
def work_entries(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in records(db,WorkEntry,user)]

@router.post('/work-entries',status_code=201)
def work_add(payload: WorkIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    owned(db,Project,user,payload.project_id)
    return add(db,WorkEntry,user,**payload.model_dump())

@router.patch('/work-entries/{object_id}')
def work_patch(object_id: str,payload: WorkPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,WorkEntry,user,object_id);data=merge_validated(obj,payload,WorkIn)
    owned(db,Project,user,data['project_id'])
    return change(db,obj,data)

@router.delete('/work-entries/{object_id}')
def work_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return remove(db,owned(db,WorkEntry,user,object_id))
