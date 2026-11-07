"""Shared validation and owner-scoped access; no unscoped personal queries."""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import inspect, select

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, validate_default=True)

    @field_validator('title', 'display_name', check_fields=False)
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Название не должно быть пустым')
        return value

    @field_validator('timezone', check_fields=False)
    @classmethod
    def valid_timezone(cls, value):
        if value is None:
            return value  # PATCH default; merged creation schema still rejects null.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError('Неизвестный часовой пояс')
        return value

    @field_validator('starts_at', 'ends_at', 'due_at', 'happened_at', check_fields=False)
    @classmethod
    def store_utc(cls, value):
        return value.astimezone(timezone.utc) if isinstance(value, datetime) else value


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def utcnow():
    return datetime.now(timezone.utc)


def user_today(user):
    return utcnow().astimezone(ZoneInfo(user.timezone)).date()


def serialize(obj):
    result = {}
    for col in inspect(obj).mapper.column_attrs:
        value = getattr(obj, col.key)
        if isinstance(value, Decimal):
            value = format(value, '.2f')
        elif isinstance(value, datetime):
            value = aware(value).isoformat()
        result[col.key] = value
    return result


def owned(db, cls, user, object_id, lock=False):
    stmt = select(cls).where(cls.id == object_id, cls.user_id == user.id)
    if lock:
        stmt = stmt.with_for_update()
    obj = db.scalar(stmt)
    if obj is None:
        raise HTTPException(404, 'Запись не найдена')
    return obj


def records(db, cls, user):
    return db.scalars(select(cls).where(cls.user_id == user.id)).all()


def add(db, cls, user, **data):
    obj = cls(user_id=user.id, **data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return serialize(obj)


def change(db, obj, data):
    for key, value in data.items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return serialize(obj)


def remove(db, obj):
    db.delete(obj)
    db.commit()
    return {'ok': True}


def merge_validated(obj, payload, schema):
    from pydantic import ValidationError
    incoming=payload.model_dump(exclude_unset=True)
    version=incoming.pop('version',None)
    if version is not None and version != obj.version:
        raise HTTPException(409, 'Запись уже изменена. Обновите страницу и повторите.')
    current={name:getattr(obj,name) for name in schema.model_fields}
    for key,value in current.items():
        if isinstance(value,datetime): current[key]=aware(value)
    current.update(incoming)
    try:
        valid=schema.model_validate(current)
    except ValidationError:
        # Never echo an input value, secret, SQL, or traceback into an API response.
        raise HTTPException(422, 'Проверьте поля: название, даты и допустимые значения') from None
    data=valid.model_dump()
    if hasattr(obj,'version'): data['version']=obj.version+1
    return data
