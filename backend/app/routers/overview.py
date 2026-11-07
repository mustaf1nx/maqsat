from collections import defaultdict
from datetime import datetime,timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import ValidationError,Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User,Task,Transaction,FocusSession,Workout,Idea,Project,SavedTemplate
from ..schemas import TemplateIn,TaskIn,IdeaIn,EventIn,GoalIn,MoneyIn,RecurringIn,ProjectIn,HabitIn
from ..common import Input,records,serialize,user_today,aware,utcnow,owned,add,remove
from ..security import current_user,csrf_protected,public_user
from .planning import goal_data
from .finance import recurring_data
from .calendar import all_occurrences
from .health import habit_data

router=APIRouter(prefix='/api/v1')

@router.get('/dashboard')
def dashboard(user: User=Depends(current_user),db: Session=Depends(get_db)):
    today=user_today(user);zone=ZoneInfo(user.timezone)
    first=today.replace(day=1)
    tasks=records(db,Task,user);goals=goal_data(db,user);finance=records(db,Transaction,user)
    focus=records(db,FocusSession,user);workouts=records(db,Workout,user)
    month=[x for x in finance if aware(x.happened_at).astimezone(zone).date()>=first and aware(x.happened_at).astimezone(zone).date()<=today]
    expenses=defaultdict(Decimal)
    for tx in month:
        if tx.kind=='expense':expenses[tx.category]+=tx.amount
    task_today=[x for x in tasks if x.due_at and aware(x.due_at).astimezone(zone).date()==today]
    overdue=[x for x in tasks if not x.completed and x.due_at and aware(x.due_at).astimezone(zone).date()<today]
    start=datetime.combine(today,datetime.min.time(),zone)
    series=[]
    for i in reversed(range(7)):
        day=today-timedelta(days=i)
        series.append({'day':day.isoformat(),
                       'focus_minutes':sum(x.minutes for x in focus if aware(x.created_at).astimezone(zone).date()==day),
                       'tasks_done':sum(1 for x in tasks if x.completed_at and aware(x.completed_at).astimezone(zone).date()==day)})
    income=sum((x.amount for x in month if x.kind=='income'),Decimal(0))
    expense=sum((x.amount for x in month if x.kind=='expense'),Decimal(0))
    total_net=sum((x.amount if x.kind=='income' else -x.amount for x in finance),Decimal(0))
    return {'tasks_total':len(tasks),'tasks_done':sum(x.completed for x in tasks),'goals_count':len(goals),
            'goals_average':round(sum(x['progress'] for x in goals)/len(goals)) if goals else 0,
            'focus_minutes':sum(x.minutes for x in focus),'focus_today':series[-1]['focus_minutes'],
            'net_flow':format(total_net,'.2f'),'income_total':format(income,'.2f'),'expense_total':format(expense,'.2f'),
            'month_net':format(income-expense,'.2f'),'period':today.strftime('%Y-%m'),
            'expense_categories':[{'name':k,'amount':format(v,'.2f')} for k,v in sorted(expenses.items(),key=lambda x:x[1],reverse=True)],
            'workouts_count':sum(x.status=='done' for x in workouts),'today':today.isoformat(),
            'today_tasks':[serialize(x) for x in task_today],'overdue_tasks':[serialize(x) for x in overdue],
            'today_events':all_occurrences(db,user,start,start+timedelta(days=1)),
            'recurring':recurring_data(db,user),'habits':habit_data(db,user),'week':series}

@router.get('/search')
def search(q: str=Query(min_length=1,max_length=120),user: User=Depends(current_user),db: Session=Depends(get_db)):
    needle=q.casefold().strip();result=[]
    if not needle:return []
    for cls,kind in [(Task,'task'),(Idea,'idea'),(Project,'project')]:
        for obj in records(db,cls,user):
            if needle in obj.title.casefold():result.append({'id':obj.id,'kind':kind,'title':obj.title})
    return result[:30]

TEMPLATE_SCHEMAS={'task':TaskIn,'idea':IdeaIn,'event':EventIn,'goal':GoalIn,'transaction':MoneyIn,'recurring':RecurringIn,'project':ProjectIn,'habit':HabitIn}

@router.get('/templates')
def templates(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in records(db,SavedTemplate,user)]

@router.post('/templates',status_code=201)
def template_add(payload: TemplateIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    try:validated=TEMPLATE_SCHEMAS[payload.kind].model_validate(payload.data)
    except ValidationError:raise HTTPException(422,'Проверьте содержимое шаблона') from None
    data=validated.model_dump(mode='json')
    # User-specific links and completion state should not accidentally be copied.
    for key in ['goal_id','project_id','workout_template_id']:data.pop(key,None)
    if payload.kind=='task':
        data['completed']=False;data['due_at']=None
        for item in data['checklist']:item['completed']=False
    return add(db,SavedTemplate,user,title=payload.title,kind=payload.kind,data=data)

@router.delete('/templates/{object_id}')
def template_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return remove(db,owned(db,SavedTemplate,user,object_id))

class ProfileIn(Input):
    display_name: str=Field(min_length=1,max_length=100)
    timezone: str='Asia/Almaty'

@router.patch('/auth/profile')
def profile(payload: ProfileIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    user.display_name=payload.display_name;user.timezone=payload.timezone;db.commit()
    return public_user(user)

@router.get('/admin/diagnostics')
def diagnostics(user: User=Depends(current_user),db: Session=Depends(get_db)):
    if not user.is_admin:raise HTTPException(403,'Недостаточно прав')
    db.execute(text('SELECT 1'))
    # No host, credentials, user data or environment dump in diagnostics.
    return {'database':'ok','app_version':'0.3.0','checked_at':utcnow().isoformat(),
            'reminders':'В открытом браузере; фоновые push не подключены',
            'login_limit':'В памяти одного процесса'}

@router.get('/export')
def export_personal(user: User=Depends(current_user),db: Session=Depends(get_db)):
    from ..models import Goal,Event,EventOverride,RecurringPayment,WorkEntry,Habit,HabitCheck,WorkoutTemplate
    classes=[Task,Idea,Goal,Event,EventOverride,Transaction,RecurringPayment,Project,WorkEntry,FocusSession,Workout,WorkoutTemplate,Habit,HabitCheck,SavedTemplate]
    return {'schema_version':'0.3.0','exported_at':utcnow().isoformat(),'profile':public_user(user),
            'data':{cls.__tablename__:[serialize(x) for x in records(db,cls,user)] for cls in classes}}
