"""Bounded recurrence expansion using local wall time and stable original-date keys.

Missing month days (31st, Feb 29) are skipped, not shifted to an arbitrary date.
Count counts valid occurrences, including exceptions subsequently cancelled.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .common import aware, serialize


def month_day(first: date, year: int, month: int, mode: str):
    last = monthrange(year, month)[1]
    if mode == 'day':
        return date(year, month, first.day) if first.day <= last else None
    if mode == 'last_weekday':
        end = date(year, month, last)
        return end - timedelta(days=(end.weekday() - first.weekday()) % 7)
    day = 1 + (first.weekday() - date(year, month, 1).weekday()) % 7 + 7 * ((first.day - 1)//7)
    return date(year, month, day) if day <= last else None


def occurrence_number(event, day: date):
    """1-based ordinal or None; does not enforce count/until (used for splitting)."""
    first = aware(event.starts_at).astimezone(ZoneInfo(event.timezone)).date()
    if day < first: return None
    rule = event.recurrence
    if not rule: return 1 if day == first else None
    interval = rule.get('interval', 1)
    frequency = rule['frequency']
    if frequency == 'daily':
        delta = (day - first).days
        return delta // interval + 1 if delta % interval == 0 else None
    if frequency == 'weekly':
        days = sorted(set(rule['weekdays']))
        week = (day - (first - timedelta(days=first.weekday()))).days // 7
        if week % interval or day.weekday() not in days: return None
        if week == 0: return sum(first.weekday() <= x <= day.weekday() for x in days)
        return sum(x >= first.weekday() for x in days) + (week//interval - 1)*len(days) + sum(x <= day.weekday() for x in days)
    if frequency == 'monthly':
        gap = (day.year-first.year)*12 + day.month-first.month
        if gap % interval or month_day(first, day.year, day.month, rule.get('monthly_mode','day')) != day: return None
        n = 0
        for index in range(0, gap+1, interval):
            year, month = divmod(first.year*12 + first.month - 1 + index, 12)
            candidate = month_day(first, year, month+1, rule.get('monthly_mode','day'))
            if candidate and candidate >= first: n += 1
        return n
    if frequency == 'yearly':
        gap = day.year-first.year
        if gap % interval or (day.month,day.day) != (first.month,first.day): return None
        return sum(first.day <= monthrange(y,first.month)[1] for y in range(first.year,day.year+1,interval))
    return None


def matches_day(event, day: date) -> bool:
    rule = event.recurrence or {}
    if rule.get('until') and day > date.fromisoformat(rule['until']): return False
    number = occurrence_number(event, day)
    return number is not None and number > 0 and (not rule.get('count') or number <= rule['count'])


def base_occurrence(event, key: str):
    zone = ZoneInfo(event.timezone)
    start = aware(event.starts_at)
    if not event.recurrence:
        if key != 'single': return None
        occurrence_start = start
    else:
        try: day = date.fromisoformat(key)
        except (ValueError, TypeError): return None
        if not matches_day(event, day): return None
        local = datetime.combine(day, start.astimezone(zone).time().replace(tzinfo=None), zone)
        # A nonexistent DST time is normalized by round-tripping through UTC.
        occurrence_start = local.astimezone(timezone.utc)
    if event.all_day:
        length = (aware(event.ends_at).astimezone(zone).date()-start.astimezone(zone).date()).days
        end_day = occurrence_start.astimezone(zone).date()+timedelta(days=length)
        occurrence_end = datetime.combine(end_day, datetime.min.time(), zone).astimezone(timezone.utc)
    else:
        occurrence_end = occurrence_start + (aware(event.ends_at) - start)
    return {**serialize(event), 'event_id':event.id, 'occurrence_key':key,
            'occurrence_id':f'{event.id}:{key}', 'occurrence_index':occurrence_number(event,date.fromisoformat(key)) if event.recurrence else 1, 'starts_at':occurrence_start.isoformat(),
            'ends_at':occurrence_end.isoformat(), 'is_override':False}


def resolve_occurrence(event, key: str, override=None):
    if event.deleted_at: return None
    obj = base_occurrence(event,key)
    if obj is None or (override and override.cancelled): return None
    if override:
        obj.update(override.data)
        obj['is_override'] = True
    zone = ZoneInfo(event.timezone)
    obj['start_date'] = datetime.fromisoformat(obj['starts_at']).astimezone(zone).date().isoformat()
    obj['end_date'] = datetime.fromisoformat(obj['ends_at']).astimezone(zone).date().isoformat()
    return obj


def expand(event, start: datetime, end: datetime, overrides=()):
    """Occurrences overlapping [start,end), including individual moves into range."""
    start, end = aware(start), aware(end)
    if end <= start or end-start > timedelta(days=367): raise ValueError('Диапазон календаря: до 366 дней')
    if event.deleted_at: return []
    zone = ZoneInfo(event.timezone)
    over = {x.occurrence_key:x for x in overrides}
    keys = set()
    if not event.recurrence:
        keys.add('single')
    else:
        duration = aware(event.ends_at)-aware(event.starts_at)
        day = (start-duration-timedelta(hours=2)).astimezone(zone).date()
        last = end.astimezone(zone).date()
        while day <= last:
            if matches_day(event, day): keys.add(day.isoformat())
            day += timedelta(days=1)
        keys.update(over)
    rows = []
    for key in keys:
        obj = resolve_occurrence(event,key,over.get(key))
        if obj and datetime.fromisoformat(obj['starts_at']) < end and datetime.fromisoformat(obj['ends_at']) > start:
            rows.append(obj)
    return sorted(rows,key=lambda x:x['starts_at'])
