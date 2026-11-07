"""Bounded calendar expansion in the series' IANA timezone.

Keys are the original local dates (or 'single'), not moved dates. One-off moves
therefore cannot produce a duplicate on the original day. DST keeps wall time.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .common import aware, serialize


def matches_day(event, day: date) -> bool:
    zone = ZoneInfo(event.timezone)
    first = aware(event.starts_at).astimezone(zone).date()
    if day < first:
        return False
    rule = event.recurrence
    if not rule:
        return day == first
    if rule.get('until') and day > date.fromisoformat(rule['until']):
        return False
    interval = rule.get('interval', 1)
    if rule['frequency'] == 'daily':
        return (day - first).days % interval == 0
    week_start = first - timedelta(days=first.weekday())
    return ((day - week_start).days // 7) % interval == 0 and day.weekday() in rule['weekdays']


def base_occurrence(event, key: str):
    zone = ZoneInfo(event.timezone)
    start = aware(event.starts_at)
    if not event.recurrence:
        if key != 'single':
            return None
        occurrence_start = start
    else:
        try:
            day = date.fromisoformat(key)
        except ValueError:
            return None
        if not matches_day(event, day):
            return None
        wall_time = start.astimezone(zone).time().replace(tzinfo=None)
        local = datetime.combine(day, wall_time, zone)
        # In a spring-forward gap, normalize to the first valid wall-clock time.
        occurrence_start = local.astimezone(timezone.utc)
    duration = aware(event.ends_at) - start
    return {**serialize(event), 'event_id': event.id, 'occurrence_key': key,
            'occurrence_id': f'{event.id}:{key}', 'starts_at': occurrence_start.isoformat(),
            'ends_at': (occurrence_start + duration).isoformat(), 'is_override': False}


def resolve_occurrence(event, key: str, override=None):
    obj = base_occurrence(event, key)
    if obj is None or (override and override.cancelled):
        return None
    if override:
        obj.update(override.data)
        obj['is_override'] = True
    return obj


def expand(event, start: datetime, end: datetime, overrides=()):
    """Return occurrences overlapping [start, end), including moves into the range."""
    start, end = aware(start), aware(end)
    if end <= start or end - start > timedelta(days=367):
        raise ValueError('Диапазон календаря: от 1 минуты до 366 дней')
    zone = ZoneInfo(event.timezone)
    over = {x.occurrence_key: x for x in overrides}
    keys = set()
    if not event.recurrence:
        keys.add('single')
    else:
        # Include long events starting just before the requested window.
        duration = aware(event.ends_at) - aware(event.starts_at)
        day = (start - duration).astimezone(zone).date()
        last = end.astimezone(zone).date()
        while day <= last:
            if matches_day(event, day):
                keys.add(day.isoformat())
            day += timedelta(days=1)
        keys.update(over)
    rows = []
    for key in keys:
        obj = resolve_occurrence(event, key, over.get(key))
        if obj:
            a = datetime.fromisoformat(obj['starts_at'])
            b = datetime.fromisoformat(obj['ends_at'])
            if a < end and b > start:
                rows.append(obj)
    return sorted(rows, key=lambda x: x['starts_at'])
