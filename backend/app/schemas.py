from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo
from pydantic import Field, AwareDatetime, field_validator, model_validator, create_model
from .common import Input

class ChecklistItem(Input):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=240)
    completed: bool = False

class TaskIn(Input):
    title: str = Field(min_length=1, max_length=240)
    note: str = Field(default='', max_length=5000)
    area: str = Field(default='Личное', min_length=1, max_length=48)
    priority: Literal['low','normal','high'] = 'normal'
    due_at: AwareDatetime | None = None
    completed: bool = False
    goal_id: str | None = Field(default=None, max_length=36)
    project_id: str | None = Field(default=None, max_length=36)
    duration_minutes: int = Field(default=30, ge=5, le=1440)
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=100)
    @model_validator(mode='after')
    def unique_checklist(self):
        ids=[item.id for item in self.checklist]
        if len(set(ids))!=len(ids): raise ValueError('Подзадачи должны иметь разные ID')
        return self

class IdeaIn(Input):
    title: str = Field(min_length=1, max_length=240)
    note: str = Field(default='', max_length=5000)

class RecurrenceIn(Input):
    frequency: Literal['daily','weekly','monthly','yearly'] = 'weekly'
    interval: int = Field(default=1, ge=1, le=52)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    until: date | None = None
    count: int | None = Field(default=None, ge=1, le=1000)
    monthly_mode: Literal['day','weekday','last_weekday'] = 'day'
    @field_validator('weekdays')
    @classmethod
    def days(cls, value):
        if any(x not in range(7) for x in value): raise ValueError('Дни недели: от 0 до 6')
        return sorted(set(value))
    @model_validator(mode='after')
    def days_required(self):
        if self.frequency=='weekly' and not self.weekdays: raise ValueError('Выберите хотя бы один день недели')
        if self.count and self.until: raise ValueError('Выберите либо число повторений, либо конечную дату')
        return self

class EventIn(Input):
    title: str = Field(min_length=1, max_length=240)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    category: str = Field(default='Личное', min_length=1, max_length=48)
    note: str = Field(default='', max_length=5000)
    location: str = Field(default='', max_length=300)
    timezone: str = 'Asia/Almaty'
    recurrence: RecurrenceIn | None = None
    reminder_minutes: int | None = Field(default=None, ge=0, le=10080)
    workout_template_id: str | None = Field(default=None, max_length=36)
    calendar_id: str | None = Field(default=None, max_length=36)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    all_day: bool = False
    availability: Literal['busy','free'] = 'busy'
    meeting_url: str = Field(default='', max_length=2048)
    reminders: list[int] = Field(default_factory=list, max_length=5)

    @field_validator('meeting_url')
    @classmethod
    def safe_meeting_url(cls, value):
        from urllib.parse import urlsplit
        if not value: return value
        try:
            url = urlsplit(value)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or any(ord(c)<32 for c in value):
                raise ValueError('Укажите HTTPS-ссылку на встречу без логина и пароля')
        except ValueError:
            raise ValueError('Укажите корректную HTTPS-ссылку на встречу') from None
        return value

    @field_validator('reminders')
    @classmethod
    def reminder_values(cls, value):
        if any(x < 0 or x > 10080 for x in value): raise ValueError('Напоминания: от 0 до 10080 минут')
        return sorted(set(value))

    @model_validator(mode='after')
    def check_range(self):
        if self.ends_at <= self.starts_at: raise ValueError('Окончание должно быть после начала')
        if self.all_day:
            zone = ZoneInfo(self.timezone)
            start = self.starts_at.astimezone(zone); end = self.ends_at.astimezone(zone)
            if any((v.hour, v.minute, v.second, v.microsecond) != (0,0,0,0) for v in (start,end)):
                raise ValueError('Событие на весь день должно начинаться и заканчиваться в полночь своего часового пояса')
            if (end.date()-start.date()).days > 366: raise ValueError('Событие не может быть длиннее 366 дней')
        elif self.ends_at-self.starts_at > timedelta(days=7): raise ValueError('Событие не может быть длиннее 7 дней')
        if self.recurrence and self.recurrence.until:
            if self.recurrence.until < self.starts_at.astimezone(ZoneInfo(self.timezone)).date():
                raise ValueError('Конец повторений не может быть раньше начала')
        return self

class OccurrencePatch(Input):
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    title: str | None = Field(default=None, min_length=1, max_length=240)
    note: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, min_length=1, max_length=48)
    calendar_id: str | None = Field(default=None, max_length=36)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    all_day: bool | None = None
    availability: Literal['busy','free'] | None = None
    meeting_url: str | None = Field(default=None, max_length=2048)
    reminder_minutes: int | None = Field(default=None, ge=0, le=10080)
    reminders: list[int] | None = Field(default=None, max_length=5)
    cancelled: bool = False
    version: int | None = None

class CalendarIn(Input):
    title: str = Field(min_length=1, max_length=120)
    color: str = Field(default='#7c83ff', pattern=r'^#[0-9a-fA-F]{6}$')

class CalendarImport(Input):
    content: str = Field(min_length=1, max_length=2_000_000)
    calendar_id: str | None = Field(default=None, max_length=36)


class GoalIn(Input):
    title: str = Field(min_length=1, max_length=240)
    detail: str = Field(default='', max_length=5000)
    progress: int = Field(default=0, ge=0, le=100)
    mode: Literal['manual','tasks'] = 'manual'

class MoneyIn(Input):
    title: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    kind: Literal['income','expense']
    category: str = Field(default='Другое', min_length=1, max_length=60)
    happened_at: AwareDatetime | None = None

class RecurringIn(Input):
    title: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    day_of_month: int = Field(ge=1, le=31)
    active: bool = True

class ProjectIn(Input):
    title: str = Field(min_length=1, max_length=240)
    client: str = Field(default='', max_length=160)
    hourly_rate: Decimal = Field(default=Decimal('0'), ge=0, max_digits=14, decimal_places=2)

class WorkIn(Input):
    project_id: str = Field(min_length=1, max_length=36)
    minutes: int = Field(ge=1, le=1440)
    note: str = Field(default='', max_length=240)

class FocusIn(Input):
    minutes: int = Field(ge=1, le=240)
    task_label: str = Field(default='', max_length=240)
    method: Literal['pomodoro','long','custom','stopwatch'] = 'pomodoro'
    client_id: str | None = Field(default=None, min_length=1, max_length=64)

class ExerciseIn(Input):
    name: str = Field(min_length=1, max_length=160)
    sets: int | None = Field(default=None, ge=1, le=100)
    reps: str = Field(default='', max_length=64)
    note: str = Field(default='', max_length=500)

class WorkoutTemplateIn(Input):
    title: str = Field(min_length=1, max_length=240)
    minutes: int = Field(default=60, ge=1, le=600)
    note: str = Field(default='', max_length=3000)
    exercises: list[ExerciseIn] = Field(default_factory=list, max_length=100)

class WorkoutIn(WorkoutTemplateIn):
    happened_at: AwareDatetime | None = None
    event_id: str | None = Field(default=None, max_length=36)
    event_key: str | None = Field(default=None, max_length=10)
    status: Literal['planned','done'] = 'done'
    @model_validator(mode='after')
    def event_pair(self):
        if bool(self.event_id) != bool(self.event_key): raise ValueError('Укажите событие и дату повторения вместе')
        return self

class HabitIn(Input):
    title: str = Field(min_length=1, max_length=240)
    note: str = Field(default='', max_length=3000)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7)
    target: int = Field(default=1, ge=1, le=10000)
    unit: str = Field(default='раз', min_length=1, max_length=32)
    archived: bool = False
    color: Literal['violet','blue','green','amber','rose'] = 'violet'
    @field_validator('weekdays')
    @classmethod
    def days(cls, value):
        if any(x not in range(7) for x in value): raise ValueError('Недопустимый день недели')
        return sorted(set(value))

class HabitLogIn(Input):
    day: date
    value: int = Field(ge=0, le=10000)

class TemplateIn(Input):
    title: str = Field(min_length=1, max_length=240)
    kind: Literal['task','idea','event','goal','transaction','recurring','project','habit']
    data: dict

# PATCH stays partial on the wire. The endpoint validates the merged object with
# the original creation schema, so null cannot bypass required-field validation.
def partial(schema, *, version=False):
    fields={name:(field.annotation | None, None) for name,field in schema.model_fields.items()}
    if version: fields['version']=(int | None,None)
    return create_model(schema.__name__+'Patch',__base__=Input,**fields)

TaskPatch=partial(TaskIn,version=True)
EventPatch=partial(EventIn,version=True)
IdeaPatch=partial(IdeaIn)
GoalPatch=partial(GoalIn)
MoneyPatch=partial(MoneyIn)
RecurringPatch=partial(RecurringIn)
ProjectPatch=partial(ProjectIn)
WorkPatch=partial(WorkIn)
WorkoutPatch=partial(WorkoutIn)
WorkoutTemplatePatch=partial(WorkoutTemplateIn)
HabitPatch=partial(HabitIn)

CalendarPatch = partial(CalendarIn)
