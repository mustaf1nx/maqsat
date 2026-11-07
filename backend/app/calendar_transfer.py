"""Local iCalendar interchange. Never fetches URLs/attachments or sends invitations.

Imports a deliberate RFC5545 subset, explicitly rejecting unsupported recurrence
rules rather than silently changing the schedule. Exports a selected date-range
snapshot: every occurrence is independent, using UTC or DATE (exclusive DTEND).
"""
import re
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from .schemas import EventIn

DAYS = ['MO','TU','WE','TH','FR','SA','SU']


def escape(text):
    return str(text).replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def unescape(text):
    return re.sub(r'\\([nN,;\\])',lambda m:'\n' if m[1].lower()=='n' else m[1],text)


def fold(line):
    """RFC5545 lines <=75 octets, without splitting UTF-8 code points."""
    out=[];part='';size=0
    for char in line:
        length=len(char.encode('utf-8'))
        if size+length>75:
            out.append(part);part=' ';size=1
        part+=char;size+=length
    out.append(part)
    return '\r\n'.join(out)


def export_snapshot(rows):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//MAQSAT//Calendar 0.4//RU','CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:MAQSAT — выбранный период']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for row in rows:
        lines += ['BEGIN:VEVENT',f"UID:{row['occurrence_id']}@maqsat.local",'DTSTAMP:'+stamp]
        if row.get('all_day'):
            lines += ['DTSTART;VALUE=DATE:'+row['start_date'].replace('-',''),'DTEND;VALUE=DATE:'+row['end_date'].replace('-','')]
        else:
            for key,field in [('DTSTART','starts_at'),('DTEND','ends_at')]:
                lines.append(key+':'+datetime.fromisoformat(row[field]).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        lines += ['SUMMARY:'+escape(row['title']),'DESCRIPTION:'+escape(row.get('note','')),'LOCATION:'+escape(row.get('location','')),'TRANSP:'+('TRANSPARENT' if row.get('availability')=='free' else 'OPAQUE')]
        if row.get('meeting_url'):lines.append('URL:'+escape(row['meeting_url']))
        if row.get('category'):lines.append('CATEGORIES:'+escape(row['category']))
        for minutes in row.get('reminders') or ([row['reminder_minutes']] if row.get('reminder_minutes') is not None else []):
            lines += ['BEGIN:VALARM','ACTION:DISPLAY',f'TRIGGER:-PT{minutes}M','DESCRIPTION:'+escape(row['title']),'END:VALARM']
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(x) for x in lines)+'\r\n'


def properties(content):
    if len(content.encode('utf-8'))>2_000_000:raise ValueError('Файл больше 2 МБ')
    content=re.sub(r'\r?\n[ \t]','',content.lstrip('\ufeff')).replace('\r\n','\n')
    if 'BEGIN:VCALENDAR' not in content:raise ValueError('Ожидается файл iCalendar (.ics)')
    rows=[];current=None;alarm=False
    for line in content.splitlines():
        if line=='BEGIN:VEVENT':
            if current is not None:raise ValueError('Повреждённый VEVENT')
            current=[]
        elif line=='END:VEVENT':
            if current is None:raise ValueError('Повреждённый VEVENT')
            rows.append(current);current=None
            if len(rows)>500:raise ValueError('За один импорт допускается не более 500 событий')
        elif current is not None:
            if line=='BEGIN:VALARM':alarm=True;continue
            if line=='END:VALARM':alarm=False;continue
            if ':' not in line:continue
            head,value=line.split(':',1);chunks=head.split(';');name=chunks[0].upper()
            params={}
            for chunk in chunks[1:]:
                if '=' in chunk:
                    k,v=chunk.split('=',1);params[k.upper()]=v.strip('"')
            if not alarm or name=='TRIGGER':current.append((name,params,value))
    if current is not None:raise ValueError('Незавершённое событие')
    return rows


def parse_date(prop, fallback_zone):
    _,params,value=prop
    zone=params.get('TZID',fallback_zone)
    try:tz=ZoneInfo(zone)
    except Exception:raise ValueError('Неподдерживаемый часовой пояс: '+zone[:80]) from None
    try:
        if params.get('VALUE')=='DATE' or re.fullmatch(r'\d{8}',value):
            return datetime.strptime(value,'%Y%m%d').replace(tzinfo=tz),True,zone
        if value.endswith('Z'):
            return datetime.strptime(value,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc),False,'UTC'
        return datetime.strptime(value,'%Y%m%dT%H%M%S').replace(tzinfo=tz),False,zone
    except ValueError:raise ValueError('Некорректная дата в iCalendar') from None


def parse_rule(value,start,zone):
    try:rule=dict(part.split('=',1) for part in value.split(';'))
    except ValueError:raise ValueError('Некорректное правило повторений') from None
    unsupported=set(rule)-{'FREQ','INTERVAL','BYDAY','BYMONTHDAY','BYMONTH','COUNT','UNTIL','WKST'}
    if unsupported:raise ValueError('Правило повторений не поддерживается: '+','.join(sorted(unsupported)))
    freq=rule.get('FREQ','').lower()
    if freq not in {'daily','weekly','monthly','yearly'}:raise ValueError('Поддерживаются дневные, недельные, месячные и годовые циклы')
    if rule.get('WKST','MO')!='MO':raise ValueError('Поддерживается начало недели в понедельник')
    local=start.astimezone(ZoneInfo(zone));r={'frequency':freq,'interval':int(rule.get('INTERVAL','1')),'weekdays':[],'until':None,'count':None,'monthly_mode':'day'}
    if 'BYMONTHDAY' in rule and (freq!='monthly' or rule['BYMONTHDAY']!=str(local.day)):
        raise ValueError('BYMONTHDAY не совпадает с поддерживаемым месячным циклом')
    if 'BYMONTH' in rule and (freq!='yearly' or rule['BYMONTH']!=str(local.month)):
        raise ValueError('BYMONTH не совпадает с поддерживаемым годовым циклом')
    if freq=='weekly':
        values=rule.get('BYDAY',DAYS[local.weekday()]).split(',')
        if any(x not in DAYS for x in values):raise ValueError('Неподдерживаемые дни недели')
        r['weekdays']=sorted(set(DAYS.index(x) for x in values))
    elif 'BYDAY' in rule:
        value=rule['BYDAY'];expected=DAYS[local.weekday()]
        if freq=='monthly' and value in {f'{(local.day-1)//7+1}{expected}',f'-1{expected}'}:
            r['monthly_mode']='last_weekday' if value.startswith('-1') else 'weekday'
        else:raise ValueError('Неподдерживаемое правило BYDAY')
    if 'COUNT' in rule:r['count']=int(rule['COUNT'])
    if 'UNTIL' in rule:
        raw=rule['UNTIL']
        if re.fullmatch(r'\d{8}',raw):r['until']=datetime.strptime(raw,'%Y%m%d').date().isoformat()
        elif raw.endswith('Z'):r['until']=datetime.strptime(raw,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).astimezone(ZoneInfo(zone)).date().isoformat()
        else:raise ValueError('Неподдерживаемая конечная дата цикла')
    return r


def parse_import(content,default_zone):
    parsed=[];warnings=[]
    for index,props in enumerate(properties(content),1):
        def get(name):return next((p for p in props if p[0]==name),None)
        def val(name,default=''):return unescape(get(name)[2]) if get(name) else default
        title=val('SUMMARY','Без названия')
        try:
            if any(get(x) for x in ('RDATE','EXRULE')):raise ValueError('RDATE/EXRULE пока не поддерживаются')
            if not get('DTSTART'):raise ValueError('Нет начала события')
            start,all_day,zone=parse_date(get('DTSTART'),default_zone)
            if get('DTEND'):
                end,end_all,_=parse_date(get('DTEND'),zone)
                if end_all!=all_day:raise ValueError('Разные типы начала и окончания')
            elif get('DURATION'):
                m=re.fullmatch(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?',val('DURATION'))
                if not m:raise ValueError('Неподдерживаемая длительность')
                end=start+timedelta(days=int(m[1] or 0),hours=int(m[2] or 0),minutes=int(m[3] or 0),seconds=int(m[4] or 0))
            else:end=start+timedelta(days=1) if all_day else start+timedelta(hours=1)
            reminders=[]
            for name,_,raw in props:
                if name=='TRIGGER':
                    m=re.fullmatch(r'-P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?',raw)
                    if m:reminders.append(int(m[1] or 0)*1440+int(m[2] or 0)*60+int(m[3] or 0))
            url=val('URL')
            if url and not url.startswith('https://'):
                warnings.append(f'Событие {index}: небезопасная ссылка не импортирована');url=''
            data=EventIn.model_validate(dict(title=title,starts_at=start,ends_at=end,all_day=all_day,timezone=zone,location=val('LOCATION'),note=val('DESCRIPTION'),category=val('CATEGORIES','Личное'),meeting_url=url,availability='free' if val('TRANSP')=='TRANSPARENT' else 'busy',reminders=sorted(set(reminders))[:5],recurrence=parse_rule(val('RRULE'),start,zone) if get('RRULE') else None)).model_dump(mode='json')
            exceptions=[]
            for prop in props:
                if prop[0]=='EXDATE':
                    for item in prop[2].split(','):
                        d,_,_=parse_date((prop[0],prop[1],item),zone)
                        exceptions.append(d.astimezone(ZoneInfo(zone)).date().isoformat())
            recurrence_id=parse_date(get('RECURRENCE-ID'),zone)[0].isoformat() if get('RECURRENCE-ID') else None
            if get('ATTENDEE') or get('ORGANIZER'):
                warnings.append(f'Событие {index}: участники и приглашения не переносятся; импортируется личная запись')
            parsed.append({'data':data,'uid':val('UID')[:512] or None,'exceptions':exceptions,'recurrence_id':recurrence_id,'cancelled':val('STATUS')=='CANCELLED'})
        except (ValueError,TypeError,OverflowError):
            # Do not echo raw file data in diagnostics (may contain private content).
            warnings.append(f'Событие {index} пропущено: неподдерживаемые или некорректные даты/повторения/поля')
    return parsed,warnings
