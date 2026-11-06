"""MAQSAT web MVP API. Owner-scoped data access throughout.

This is a tested starter, not a security audit or finished SaaS release.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import os
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, func, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import (User, LoginSession, Task, Idea, Event, Goal, Transaction, RecurringPayment,
                     Project, WorkEntry, FocusSession, Workout, Habit, HabitCheck, now)
from .security import (public_user, hash_password, verify_password, current_user, csrf_protected,
                       admin_user, check_origin, guard_login, failed_login, successful_login,
                       attach_session, token_digest, csrf_token, COOKIE_NAME, USERNAME_RE)

app = FastAPI(title='MAQSAT API', version='0.2.0', docs_url=None, redoc_url=None)

@app.middleware('http')
async def security_headers(request: Request, call_next):
    try:
        check_origin(request)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response

@app.get('/healthz')
def health(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok'}

def serialize(obj):
    data = {}
    for column in inspect(obj).mapper.column_attrs:
        value = getattr(obj, column.key)
        if isinstance(value, Decimal): value = str(value)
        elif isinstance(value, datetime): value = value.isoformat()
        data[column.key] = value
    return data

def owned(db: Session, cls, user: User, object_id: str):
    obj = db.scalar(select(cls).where(cls.id == object_id, cls.user_id == user.id))
    if obj is None:
        raise HTTPException(404, 'Запись не найдена')
    return obj

def create(db: Session, cls, user: User, **kwargs):
    record = cls(user_id=user.id, **kwargs)
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize(record)

def update(db: Session, obj, data: BaseModel):
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, name, value)
    db.commit()
    db.refresh(obj)
    return serialize(obj)

def delete(db: Session, obj):
    db.delete(obj)
    db.commit()
    return {'ok': True}

class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class UserCreate(BaseModel):
    username: str = Field(pattern=r'^[a-z0-9_\-]{3,32}$')
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=256)

class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=10, max_length=256)

@app.post('/api/v1/auth/login')
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    # Never trust forwarded IP headers; an in-memory limiter is a first-line MVP precaution only.
    ip = request.client.host if request.client else 'unknown'
    guard_login(ip)
    username = payload.username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(payload.password, user.password_hash):
        failed_login(ip)
        raise HTTPException(401, 'Неверный логин или пароль')
    successful_login(ip)
    csrf = attach_session(response, db, user)
    return {'user': public_user(user), 'csrf': csrf}

@app.get('/api/v1/auth/me')
def me(request: Request, user: User = Depends(current_user)):
    return {'user': public_user(user), 'csrf': csrf_token(request.cookies[COOKIE_NAME])}

@app.post('/api/v1/auth/logout')
def logout(request: Request, response: Response, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_digest(token)))
    if session:
        db.delete(session); db.commit()
    response.delete_cookie(COOKIE_NAME, path='/', samesite='lax')
    return {'ok': True}

@app.patch('/api/v1/auth/password')
def password_change(payload: PasswordChange, request: Request, response: Response, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, 'Текущий пароль неверный')
    user.password_hash = hash_password(payload.new_password)
    # Invalidate all OTHER sessions to prevent continued access from old sessions.
    current = token_digest(request.cookies[COOKIE_NAME])
    db.query(LoginSession).filter(LoginSession.user_id == user.id, LoginSession.token_hash != current).delete(synchronize_session=False)
    db.commit()
    return {'ok': True}

@app.get('/api/v1/admin/users')
def admin_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, 'Недостаточно прав')
    return [public_user(x) for x in db.scalars(select(User).order_by(User.created_at)).all()]

@app.post('/api/v1/admin/users', status_code=201)
def admin_create(payload: UserCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    username = payload.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, 'Логин уже занят')
    new_user = User(username=username, display_name=payload.display_name.strip(),
                    password_hash=hash_password(payload.password), is_admin=False)
    db.add(new_user)
    db.commit()
    return public_user(new_user)

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    note: str = Field(default='', max_length=5000)
    area: str = Field(default='Личное', min_length=1, max_length=48)
    priority: Literal['low', 'normal', 'high'] = 'normal'
    due_at: datetime | None = None

class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    note: str | None = Field(default=None, max_length=5000)
    area: str | None = Field(default=None, min_length=1, max_length=48)
    priority: Literal['low', 'normal', 'high'] | None = None
    due_at: datetime | None = None
    completed: bool | None = None

@app.get('/api/v1/tasks')
def tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.completed, Task.created_at.desc())).all()]

@app.post('/api/v1/tasks', status_code=201)
def task_add(payload: TaskIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Task, user, **payload.model_dump())

@app.patch('/api/v1/tasks/{object_id}')
def task_patch(object_id: str, payload: TaskPatch, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    obj = owned(db, Task, user, object_id)
    if any(v is None for k, v in payload.model_dump(exclude_unset=True).items() if k != 'due_at'):
        raise HTTPException(422, 'Недопустимое значение')
    return update(db, obj, payload)

@app.delete('/api/v1/tasks/{object_id}')
def task_delete(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return delete(db, owned(db, Task, user, object_id))

class IdeaIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    note: str = Field(default='', max_length=5000)

@app.get('/api/v1/ideas')
def ideas(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Idea).where(Idea.user_id == user.id).order_by(Idea.created_at.desc())).all()]

@app.post('/api/v1/ideas', status_code=201)
def idea_add(payload: IdeaIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Idea, user, **payload.model_dump())

@app.post('/api/v1/ideas/{object_id}/to-task')
def idea_to_task(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    idea = owned(db, Idea, user, object_id)
    if idea.converted_task_id:
        task = db.scalar(select(Task).where(Task.id == idea.converted_task_id, Task.user_id == user.id))
        if task: return serialize(task)
    task = Task(user_id=user.id, title=idea.title, note=idea.note)
    db.add(task)
    db.flush()
    idea.converted_task_id = task.id
    db.commit()
    return serialize(task)

@app.delete('/api/v1/ideas/{object_id}')
def idea_delete(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return delete(db, owned(db, Idea, user, object_id))

class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    starts_at: datetime
    ends_at: datetime
    category: str = Field(default='Личное', min_length=1, max_length=48)
    note: str = Field(default='', max_length=5000)
    @model_validator(mode='after')
    def check_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('Время окончания должно быть после начала')
        return self

@app.get('/api/v1/events')
def events(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Event).where(Event.user_id == user.id).order_by(Event.starts_at)).all()]

@app.post('/api/v1/events', status_code=201)
def event_add(payload: EventIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Event, user, **payload.model_dump())

@app.delete('/api/v1/events/{object_id}')
def event_delete(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return delete(db, owned(db, Event, user, object_id))

class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    detail: str = Field(default='', max_length=5000)
    progress: int = Field(default=0, ge=0, le=100)

class GoalPatch(BaseModel):
    progress: int = Field(ge=0, le=100)

@app.get('/api/v1/goals')
def goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc())).all()]

@app.post('/api/v1/goals', status_code=201)
def goal_add(payload: GoalIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Goal, user, **payload.model_dump())

@app.patch('/api/v1/goals/{object_id}')
def goal_patch(object_id: str, payload: GoalPatch, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return update(db, owned(db, Goal, user, object_id), payload)

@app.delete('/api/v1/goals/{object_id}')
def goal_delete(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return delete(db, owned(db, Goal, user, object_id))

class MoneyIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    kind: Literal['income', 'expense']
    category: str = Field(default='Другое', min_length=1, max_length=60)

@app.get('/api/v1/transactions')
def transactions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.happened_at.desc())).all()]

@app.post('/api/v1/transactions', status_code=201)
def transaction_add(payload: MoneyIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Transaction, user, **payload.model_dump())

@app.delete('/api/v1/transactions/{object_id}')
def transaction_delete(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return delete(db, owned(db, Transaction, user, object_id))

class RecurringIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    day_of_month: int = Field(ge=1, le=28)

@app.get('/api/v1/recurring')
def recurring(user: User = Depends(current_user), db: Session = Depends(get_db)):
    period = datetime.now(ZoneInfo('Asia/Almaty')).strftime('%Y-%m')
    rows = db.scalars(select(RecurringPayment).where(RecurringPayment.user_id == user.id).order_by(RecurringPayment.day_of_month)).all()
    paid = set(db.scalars(select(Transaction.recurring_id).where(Transaction.user_id == user.id, Transaction.period == period, Transaction.recurring_id.is_not(None))).all())
    return [{**serialize(x), 'paid_this_month': x.id in paid} for x in rows]

@app.post('/api/v1/recurring', status_code=201)
def recurring_add(payload: RecurringIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, RecurringPayment, user, **payload.model_dump())

@app.post('/api/v1/recurring/{object_id}/confirm')
def recurring_confirm(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    payment = owned(db, RecurringPayment, user, object_id)
    if not payment.active: raise HTTPException(409, 'Платёж не активен')
    period = datetime.now(ZoneInfo('Asia/Almaty')).strftime('%Y-%m')
    existing = db.scalar(select(Transaction).where(Transaction.user_id == user.id, Transaction.recurring_id == payment.id, Transaction.period == period))
    if existing: return {'already_paid': True, 'transaction': serialize(existing)}
    transaction = Transaction(user_id=user.id, title=payment.title, amount=payment.amount, kind='expense', category='Регулярные платежи', recurring_id=payment.id, period=period)
    db.add(transaction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Transaction).where(Transaction.user_id == user.id, Transaction.recurring_id == payment.id, Transaction.period == period))
        if existing: return {'already_paid': True, 'transaction': serialize(existing)}
        raise
    return {'already_paid': False, 'transaction': serialize(transaction)}

@app.delete('/api/v1/recurring/{object_id}')
def recurring_delete(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return delete(db, owned(db, RecurringPayment, user, object_id))

class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    client: str = Field(default='', max_length=160)
    hourly_rate: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=14, decimal_places=2)

class WorkIn(BaseModel):
    project_id: str
    minutes: int = Field(ge=1, le=1440)
    note: str = Field(default='', max_length=240)

@app.get('/api/v1/projects')
def projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())).all()
    work = db.scalars(select(WorkEntry).where(WorkEntry.user_id == user.id)).all()
    minutes_by_project = defaultdict(int)
    for entry in work: minutes_by_project[entry.project_id] += entry.minutes
    return [{**serialize(p), 'worked_minutes': minutes_by_project[p.id], 'expected_income': str((Decimal(minutes_by_project[p.id]) * p.hourly_rate / Decimal(60)).quantize(Decimal('0.01')))} for p in items]

@app.post('/api/v1/projects', status_code=201)
def project_add(payload: ProjectIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Project, user, **payload.model_dump())

@app.post('/api/v1/work-entries', status_code=201)
def work_add(payload: WorkIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    owned(db, Project, user, payload.project_id)
    return create(db, WorkEntry, user, **payload.model_dump())

class FocusIn(BaseModel):
    minutes: int = Field(ge=1, le=240)
    task_label: str = Field(default='', max_length=240)

@app.get('/api/v1/focus')
def focus(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(FocusSession).where(FocusSession.user_id == user.id).order_by(FocusSession.created_at.desc()).limit(100)).all()]

@app.post('/api/v1/focus', status_code=201)
def focus_add(payload: FocusIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, FocusSession, user, **payload.model_dump())

class WorkoutIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    minutes: int = Field(ge=1, le=600)
    note: str = Field(default='', max_length=3000)

@app.get('/api/v1/workouts')
def workouts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Workout).where(Workout.user_id == user.id).order_by(Workout.happened_at.desc())).all()]

@app.post('/api/v1/workouts', status_code=201)
def workout_add(payload: WorkoutIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Workout, user, **payload.model_dump())

class HabitIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)

@app.get('/api/v1/habits')
def habits(user: User = Depends(current_user), db: Session = Depends(get_db)):
    day = datetime.now(ZoneInfo('Asia/Almaty')).strftime('%Y-%m-%d')
    rows = db.scalars(select(Habit).where(Habit.user_id == user.id).order_by(Habit.created_at.desc())).all()
    completed = set(db.scalars(select(HabitCheck.habit_id).where(HabitCheck.user_id == user.id, HabitCheck.day == day)).all())
    return [{**serialize(x), 'checked_today': x.id in completed} for x in rows]

@app.post('/api/v1/habits', status_code=201)
def habit_add(payload: HabitIn, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    return create(db, Habit, user, **payload.model_dump())

@app.post('/api/v1/habits/{object_id}/toggle')
def habit_toggle(object_id: str, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    owned(db, Habit, user, object_id)
    day = datetime.now(ZoneInfo('Asia/Almaty')).strftime('%Y-%m-%d')
    check = db.scalar(select(HabitCheck).where(HabitCheck.habit_id == object_id, HabitCheck.user_id == user.id, HabitCheck.day == day))
    if check: db.delete(check)
    else: db.add(HabitCheck(user_id=user.id, habit_id=object_id, day=day))
    db.commit()
    return {'checked_today': not bool(check)}

@app.get('/api/v1/dashboard')
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    task_items = db.scalars(select(Task).where(Task.user_id == user.id)).all()
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id)).all()
    finance = db.scalars(select(Transaction).where(Transaction.user_id == user.id)).all()
    focus = db.scalars(select(FocusSession).where(FocusSession.user_id == user.id)).all()
    workouts = db.scalars(select(Workout).where(Workout.user_id == user.id)).all()
    expenses = defaultdict(Decimal)
    for tx in finance:
        if tx.kind == 'expense': expenses[tx.category] += tx.amount
    return {
        'tasks_total': len(task_items), 'tasks_done': sum(1 for t in task_items if t.completed),
        'goals_count': len(goals), 'goals_average': round(sum(x.progress for x in goals) / len(goals)) if goals else 0,
        'focus_minutes': sum(x.minutes for x in focus),
        'net_flow': str(sum((tx.amount if tx.kind == 'income' else -tx.amount for tx in finance), Decimal('0'))),
        'income_total': str(sum((tx.amount for tx in finance if tx.kind == 'income'), Decimal('0'))),
        'expense_total': str(sum((tx.amount for tx in finance if tx.kind == 'expense'), Decimal('0'))),
        'expense_categories': [{'name': k, 'amount': str(v)} for k, v in sorted(expenses.items(), key=lambda t: t[1], reverse=True)],
        'workouts_count': len(workouts),
    }

# For production the Docker image includes the Vite dist directory, served on
# the SAME ORIGIN as the API. This avoids exposing cookies across app domains.
WEB_DIR = Path(os.getenv('WEB_DIST_DIR', str(Path(__file__).resolve().parents[2] / 'web_dist')))
if WEB_DIR.exists():
    assets = WEB_DIR / 'assets'
    if assets.exists(): app.mount('/assets', StaticFiles(directory=str(assets)), name='assets')
    @app.get('/{full_path:path}', include_in_schema=False)
    def spa_fallback(full_path: str):
        # Serve index.html for valid SPA routes, not for non-existing API endpoints.
        if full_path.startswith(('api/', 'healthz')):
            raise HTTPException(404)
        file = (WEB_DIR / full_path).resolve()
        if WEB_DIR.resolve() in file.parents and file.is_file():
            return FileResponse(file)
        return FileResponse(WEB_DIR / 'index.html')
