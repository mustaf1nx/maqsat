"""All personal objects carry user_id. API must always scope queries to owner."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, JSON, false
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    timezone: Mapped[str] = mapped_column(String(64), default='Asia/Almaty', server_default='Asia/Almaty')

class LoginSession(Base):
    __tablename__ = 'login_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    note: Mapped[str] = mapped_column(Text, default='')
    area: Mapped[str] = mapped_column(String(48), default='Личное')
    priority: Mapped[str] = mapped_column(String(12), default='normal')
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey('goals.id', ondelete='SET NULL', name='fk_tasks_goal'), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id', ondelete='SET NULL', name='fk_tasks_project'), nullable=True)
    checklist: Mapped[list] = mapped_column(JSON, default=list, server_default='[]')
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default='30')
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')

class Idea(Base):
    __tablename__ = 'ideas'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    note: Mapped[str] = mapped_column(Text, default='')
    converted_task_id: Mapped[str | None] = mapped_column(ForeignKey('tasks.id', ondelete='SET NULL', name='fk_ideas_task'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[str] = mapped_column(String(48), default='Личное')
    note: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    location: Mapped[str] = mapped_column(String(300), default='', server_default='')
    timezone: Mapped[str] = mapped_column(String(64), default='Asia/Almaty', server_default='Asia/Almaty')
    recurrence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reminder_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workout_template_id: Mapped[str | None] = mapped_column(ForeignKey('workout_templates.id', ondelete='SET NULL', name='fk_events_workout_template'), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')

class Goal(Base):
    __tablename__ = 'goals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    detail: Mapped[str] = mapped_column(Text, default='')
    progress: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    mode: Mapped[str] = mapped_column(String(16), default='manual', server_default='manual')

class Transaction(Base):
    __tablename__ = 'finance_transactions'
    __table_args__ = (UniqueConstraint('user_id', 'recurring_id', 'period', name='uq_recurring_payment_period'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))  # Decimal at runtime
    kind: Mapped[str] = mapped_column(String(12))
    category: Mapped[str] = mapped_column(String(60), default='Другое')
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    recurring_id: Mapped[str | None] = mapped_column(ForeignKey('recurring_payments.id', ondelete='SET NULL', name='fk_transactions_recurring'), nullable=True)
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class RecurringPayment(Base):
    __tablename__ = 'recurring_payments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    day_of_month: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    client: Mapped[str] = mapped_column(String(160), default='')
    hourly_rate: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class WorkEntry(Base):
    __tablename__ = 'work_entries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    minutes: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(240), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class FocusSession(Base):
    __tablename__ = 'focus_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    minutes: Mapped[int] = mapped_column(Integer)
    task_label: Mapped[str] = mapped_column(String(240), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    method: Mapped[str] = mapped_column(String(24), default='pomodoro', server_default='pomodoro')
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (UniqueConstraint('user_id', 'client_id', name='uq_focus_client'),)

class Workout(Base):
    __tablename__ = 'workouts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    minutes: Mapped[int] = mapped_column(Integer, default=30)
    note: Mapped[str] = mapped_column(Text, default='')
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    exercises: Mapped[list] = mapped_column(JSON, default=list, server_default='[]')
    event_id: Mapped[str | None] = mapped_column(ForeignKey('events.id', ondelete='SET NULL', name='fk_workouts_event'), nullable=True)
    event_key: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default='done', server_default='done')
    __table_args__ = (UniqueConstraint('user_id', 'event_id', 'event_key', name='uq_workout_occurrence'),)

class Habit(Base):
    __tablename__ = 'habits'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    note: Mapped[str] = mapped_column(Text, default='', server_default='')
    weekdays: Mapped[list] = mapped_column(JSON, default=lambda: list(range(7)), server_default='[0,1,2,3,4,5,6]')
    target: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    unit: Mapped[str] = mapped_column(String(32), default='раз', server_default='раз')
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    color: Mapped[str] = mapped_column(String(16), default='violet', server_default='violet')

class HabitCheck(Base):
    __tablename__ = 'habit_checks'
    __table_args__ = (UniqueConstraint('user_id', 'habit_id', 'day', name='uq_habit_day'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    habit_id: Mapped[str] = mapped_column(ForeignKey('habits.id', ondelete='CASCADE'), index=True)
    day: Mapped[str] = mapped_column(String(10))
    value: Mapped[int] = mapped_column(Integer, default=1, server_default='1')


class EventOverride(Base):
    __tablename__ = 'event_overrides'
    __table_args__ = (UniqueConstraint('event_id', 'occurrence_key', name='uq_event_override'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('events.id', ondelete='CASCADE'), index=True)
    occurrence_key: Mapped[str] = mapped_column(String(10))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

class WorkoutTemplate(Base):
    __tablename__ = 'workout_templates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(240))
    minutes: Mapped[int] = mapped_column(Integer, default=60)
    note: Mapped[str] = mapped_column(Text, default='')
    exercises: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class SavedTemplate(Base):
    __tablename__ = 'saved_templates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(240))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
