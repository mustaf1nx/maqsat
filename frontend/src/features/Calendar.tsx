import {useEffect,useMemo,useRef,useState} from 'react';
import type {CSSProperties,DragEvent as ReactDragEvent,MouseEvent as ReactMouseEvent} from 'react';
import type {Task,CalendarEvent,CalendarCollection} from '../lib/types';
import {useApp,useData} from '../app/context';
import {Head,Button,IconButton,DataState} from '../components/ui';
import {Icon} from '../components/Icon';
import {today,plusDays,atMinute,minutesOf,shortDate,clock,safeRead,safeWrite,WEEKDAYS,weekday,dayKey,monday} from '../lib/dates';
import {segmentsForDay} from '../lib/calendar';
import type {Block,Segment} from '../lib/calendar';
import {allDayOn,allDaySelection,clickSelection,selectionSegments,validPreferences,weekStart,monthShift,isTyping,safeColor,textColor,CATEGORY_COLORS} from '../lib/calendarSelection';
import type {View,Selection,CalendarPreferences} from '../lib/calendarSelection';
import {useCalendarGestures} from './calendar/useCalendarGestures';
import {MiniCalendar,QuickEvent,CalendarManager,CalendarSettings,CalendarTransfer,CalendarTrash,CalendarHelp} from './calendar/CalendarPanels';
import {EventPeek} from './calendar/EventPeek';

const VIEWS:{key:View;label:string}[]=[{key:'day',label:'День'},{key:'week',label:'Неделя'},{key:'workweek',label:'5 дней'},{key:'month',label:'Месяц'},{key:'year',label:'Год'},{key:'list',label:'Список'}];
type Panel='calendars'|'settings'|'transfer'|'trash'|'help'|null;
export function Calendar(){
 const {user,edit,api,refresh,notify,templates}=useApp();
 const [selected,setSelected]=useState(today(user.timezone));
 const [view,setView]=useState<View>(()=>{const stored=safeRead<unknown>(`maqsat:calendar:${user.id}`,null);return VIEWS.some(v=>v.key===stored)?stored as View:window.innerWidth<760?'day':'week'});
 const [prefs,setPrefs]=useState<CalendarPreferences>(()=>validPreferences(safeRead(`maqsat:calendar-prefs:${user.id}`,null)));
 const [hidden,setHidden]=useState<string[]>(()=>{const v=safeRead<unknown>(`maqsat:calendar-hidden:${user.id}`,[]);return Array.isArray(v)?v.filter(x=>typeof x==='string'):[]});
 const [filter,setFilter]=useState('all'),[query,setQuery]=useState(''),[aside,setAside]=useState(window.innerWidth>=1180),[panel,setPanel]=useState<Panel>(null),[draft,setDraft]=useState<Selection|null>(null),[peek,setPeek]=useState<Block|null>(null),[saving,setSaving]=useState(false),[now,setNow]=useState(Date.now()),[keyMinute,setKeyMinute]=useState(9*60);
 const root=useRef<HTMLDivElement>(null),scroll=useRef<HTMLDivElement>(null),search=useRef<HTMLInputElement>(null),dateInput=useRef<HTMLInputElement>(null);
 const timed=['day','week','workweek'].includes(view),year=selected.slice(0,4);
 const start=view==='day'?selected:view==='year'?year+'-01-01':view==='month'?weekStart(selected.slice(0,7)+'-01',prefs.weekStart):view==='workweek'?monday(selected):weekStart(selected,prefs.weekStart);
 const count=view==='day'?1:view==='workweek'?5:view==='month'?42:7;
 const days=useMemo(()=>Array.from({length:count},(_,i)=>plusDays(start,i)),[start,count]);
 const end=view==='year'?String(Number(year)+1)+'-01-01':plusDays(start,count);
 const rangeStart=atMinute(start,0,user.timezone),rangeEnd=atMinute(end,0,user.timezone);
 const state=useData<CalendarEvent[]>(`/events?start=${encodeURIComponent(rangeStart)}&end=${encodeURIComponent(rangeEnd)}`,[]),tasks=useData<Task[]>('/tasks',[]),calendars=useData<CalendarCollection[]>('/calendars',[]);
 useEffect(()=>safeWrite(`maqsat:calendar:${user.id}`,view),[view,user.id]);
 useEffect(()=>safeWrite(`maqsat:calendar-prefs:${user.id}`,prefs),[prefs,user.id]);
 useEffect(()=>safeWrite(`maqsat:calendar-hidden:${user.id}`,hidden),[hidden,user.id]);
 useEffect(()=>{const t=setInterval(()=>setNow(Date.now()),30000);return()=>clearInterval(t)},[]);
 useEffect(()=>{if(scroll.current&&timed)scroll.current.scrollTop=Math.max(0,prefs.workingStart-1)*prefs.hourHeight},[view,prefs.hourHeight]);
 const colors=useMemo(()=>new Map(calendars.data.map(c=>[c.id,c.color])),[calendars.data]);
 const allBlocks=useMemo(()=>{
  const events:Block[]=state.data.map(x=>({key:x.occurrence_id,kind:'event',id:x.event_id,title:x.title,start:x.starts_at,end:x.ends_at,category:x.category,location:x.location,recurring:Boolean(x.recurrence),reminder:x.reminder_minutes!=null||Boolean(x.reminders?.length),completed:x.workout_status==='done',original:x,allDay:x.all_day,color:safeColor(x.color||colors.get(x.calendar_id||'')||CATEGORY_COLORS[x.category]),calendarId:x.calendar_id||'default',availability:x.availability,startDate:x.start_date,endDate:x.end_date}));
  const taskBlocks:Block[]=prefs.showTasks?tasks.data.filter(x=>x.due_at&&(prefs.showCompleted||!x.completed)).map(x=>({key:'task:'+x.id,kind:'task',id:x.id,title:x.title,start:x.due_at!,end:new Date(Date.parse(x.due_at!)+(x.duration_minutes||30)*60000).toISOString(),category:x.area,location:'',recurring:false,reminder:false,completed:x.completed,original:x,allDay:false,color:'#508c9c',calendarId:'tasks'})):[];
  const q=query.toLocaleLowerCase('ru');
  return [...events,...taskBlocks].filter(x=>!hidden.includes(x.calendarId||'default')&&(filter==='all'||filter==='tasks'&&x.kind==='task'||x.category===filter)&&(!q||[x.title,x.location,(x.original as CalendarEvent).note].some(s=>s?.toLocaleLowerCase('ru').includes(q))));
 },[state.data,tasks.data,prefs.showTasks,prefs.showCompleted,hidden,filter,query,colors]);
 async function commit(block:Block,values:{starts_at:string;ends_at:string}){
  setSaving(true);
  try{
   if(block.kind==='task'){
    const t=block.original as Task;const duration=Math.round((Date.parse(values.ends_at)-Date.parse(values.starts_at))/60000);if(duration>1440)throw Error('Задача не может быть длиннее 24 часов');
    const result=await api<Task>(`/tasks/${t.id}`,'PATCH',{due_at:values.starts_at,duration_minutes:Math.max(5,duration),version:t.version});
    tasks.setData(rows=>rows.map(x=>x.id===t.id?result:x));
    notify('Время задачи изменено',false,async()=>{await api(`/tasks/${t.id}`,'PATCH',{due_at:t.due_at,duration_minutes:t.duration_minutes,version:result.version});refresh()});
   }else{
    const ev=block.original as CalendarEvent,path=`/events/${ev.event_id}/occurrences/${ev.occurrence_key}`;
    const result=await api<{version:number}>(path,'PATCH',{...values,version:ev.version});
    state.setData(rows=>rows.map(x=>x.event_id===ev.event_id?{...x,...(x.occurrence_id===ev.occurrence_id?{...values,start_date:dayKey(values.starts_at,ev.timezone),end_date:dayKey(values.ends_at,ev.timezone)}:{}),version:result.version}:x));
    notify(ev.recurrence?'Перенесено только это повторение':'Событие перенесено',false,async()=>{await api(path,'PATCH',{starts_at:ev.starts_at,ends_at:ev.ends_at,version:result.version});refresh()});
   }
   refresh();
  }catch(e){notify((e as Error).message,true)}finally{setSaving(false)}
 }
 const gestures=useCalendarGestures({root,scroll,zone:user.timezone,prefs,disabled:saving||Boolean(draft||peek||panel),onDraft:setDraft,onCommit:commit,onError:message=>notify(message,true)});
 const blocks=useMemo(()=>allBlocks.map(b=>gestures.drag?.key===b.key?{...b,start:gestures.drag.start,end:gestures.drag.end,startDate:dayKey(gestures.drag.start,(b.original as CalendarEvent).timezone||user.timezone),endDate:dayKey(gestures.drag.end,(b.original as CalendarEvent).timezone||user.timezone)}:b),[allBlocks,gestures.drag,user.timezone]);
 const selectionParts=gestures.preview?selectionSegments(gestures.preview,days,user.timezone):[];
 function open(block:Block){if(gestures.suppressClick()||saving)return;if(block.kind==='task')edit('task',block.original);else setPeek(block)}
 function navigate(dir:number){if(view==='year')setSelected(String(Number(year)+dir)+'-01-01');else if(view==='month')setSelected(monthShift(selected,dir));else setSelected(plusDays(selected,dir*(view==='day'?1:7)))}
 function addAt(day=selected,minute=9*60){try{setDraft(clickSelection(day,minute,user.timezone,prefs.duration,prefs.step))}catch(e){notify((e as Error).message,true)}}
 function toggle(id:string){setHidden(value=>value.includes(id)?value.filter(x=>x!==id):[...value,id])}
 function todayView(){setSelected(today(user.timezone));if(scroll.current)scroll.current.scrollTop=Math.max(0,minutesOf(new Date().toISOString(),user.timezone)/60-1)*prefs.hourHeight}
 useEffect(()=>{
  function key(e:KeyboardEvent){if(isTyping(e.target)||document.querySelector('dialog[open]')||gestures.isDragging||e.ctrlKey||e.metaKey||e.altKey)return;
   const value=e.key.toLowerCase(),map:Record<string,View>={d:'day','1':'day',w:'week','2':'week',x:'workweek',m:'month','3':'month',y:'year',a:'list','5':'list'};
   if(map[value]){e.preventDefault();setView(map[value])}
   else if(value==='t'){e.preventDefault();todayView()}
   else if(value==='c'){e.preventDefault();addAt()}
   else if(['j','n','arrowright'].includes(value)){e.preventDefault();navigate(1)}
   else if(['k','p','arrowleft'].includes(value)){e.preventDefault();navigate(-1)}
   else if(value==='/'){e.preventDefault();search.current?.focus()}
   else if(value==='g'){e.preventDefault();dateInput.current?.focus();try{dateInput.current?.showPicker()}catch{/* Browser may not support the native picker. */}}
   else if(value==='?'){e.preventDefault();setPanel('help')}
  }
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
 },[view,selected,prefs,user.timezone,gestures.isDragging]);
 function styleFor(block:Block):CSSProperties{return {'--event-color':block.color||'#7c83ff','--event-text':textColor(block.color||'#7c83ff')} as CSSProperties}
 function eventBlock(segment:Segment){
  const {block}=segment,small=segment.end-segment.start<45;
  return <button key={block.key+segment.day} data-event={block.key} data-calendar-event={block.key} data-testid="calendar-event" className={`event-block calendar-event-new ${block.completed?'done':''} ${small?'short-event':''} ${block.availability==='free'?'is-free':''} ${gestures.drag?.key===block.key?'dragging':''}`} style={{...styleFor(block),top:segment.start/60*prefs.hourHeight,height:Math.max(10,(segment.end-segment.start)/60*prefs.hourHeight-2),left:`calc(${segment.lane/segment.lanes*100}% + 2px)`,width:`calc(${100/segment.lanes}% - 4px)`}} onPointerDown={e=>gestures.beginBlock(e,block,segment.day)} onClick={e=>{e.stopPropagation();open(block)}} onContextMenu={e=>{e.preventDefault();open(block)}} aria-label={`${block.title}, ${clock(block.start,user.timezone)}–${clock(block.end,user.timezone)}, ${block.location||''}`} title={`${block.title} · ${clock(block.start,user.timezone)}–${clock(block.end,user.timezone)}${block.location?' · '+block.location:''}`}>
   {segment.first&&<span className="resize-handle top" aria-hidden="true" onPointerDown={e=>gestures.beginBlock(e,block,segment.day,'resize-start')}/>}
   <strong>{block.kind==='task'&&<Icon name="tasks" size={12}/>} {block.title}</strong>{!small&&<span className="event-time">{clock(block.start,user.timezone)}–{clock(block.end,user.timezone)}<span>{block.recurring&&<Icon name="habit" size={12}/>} {block.reminder&&<Icon name="bell" size={12}/>}</span></span>}{!small&&block.location&&<span className="event-location">{block.location}</span>}
   {segment.last&&<span className="resize-handle bottom" aria-hidden="true" onPointerDown={e=>gestures.beginBlock(e,block,segment.day,'resize-end')}/>}
  </button>
 }
 function dateEvent(block:Block,day:string){return <button key={block.key} data-calendar-event={block.key} className={`calendar-date-event ${block.allDay?'all-day-event':''} ${block.completed?'done':''}`} style={styleFor(block)} onPointerDown={e=>gestures.beginBlock(e,block,day,'move','date')} onClick={e=>{e.stopPropagation();open(block)}} title={block.title}>{!block.allDay&&<time>{clock(block.start,user.timezone)}</time>}<strong>{block.title}</strong></button>}
 function dayBlocks(day:string){return [...blocks.filter(b=>allDayOn(b,day)),...segmentsForDay(blocks,day,user.timezone).map(s=>s.block)]}
 async function dropTask(e:ReactDragEvent<HTMLDivElement>,day:string){e.preventDefault();if(saving)return;const task=tasks.data.find(t=>t.id===e.dataTransfer.getData('application/x-maqsat-task'));if(!task)return;const minute=Math.max(0,Math.min(1425,Math.floor((e.clientY-e.currentTarget.getBoundingClientRect().top)/prefs.hourHeight*60/prefs.step)*prefs.step));setSaving(true);try{const updated=await api<Task>(`/tasks/${task.id}`,'PATCH',{due_at:atMinute(day,minute,user.timezone),version:task.version});tasks.setData(rows=>rows.map(x=>x.id===task.id?updated:x));refresh();notify('Задача запланирована',false,async()=>{await api(`/tasks/${task.id}`,'PATCH',{due_at:task.due_at,version:updated.version});refresh()})}catch(error){notify((error as Error).message,true)}finally{setSaving(false)}}
 function touchClick(e:ReactMouseEvent<HTMLDivElement>,day:string,allDay=false){if((e.nativeEvent as PointerEvent).pointerType!=='touch'||(e.target as Element).closest('[data-calendar-event],button')||gestures.suppressClick())return;if(allDay)setDraft(allDaySelection(day,day,user.timezone));else addAt(day,(e.clientY-e.currentTarget.getBoundingClientRect().top)/prefs.hourHeight*60)}
 function secondaryTime(day:string,hour:number){try{return clock(atMinute(day,hour*60,user.timezone),prefs.secondZone)}catch{return '—'}}
 const timeWidth=prefs.secondZone?92:60,columns=`${timeWidth}px repeat(${days.length},minmax(0,1fr))`;
 const heading=new Date(selected+'T12:00Z').toLocaleDateString('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'});
 const monthOrder=Array.from({length:7},(_,i)=>WEEKDAYS[(prefs.weekStart+i)%7]);
 const currentDay=today(user.timezone),markers=state.data.map(x=>x.start_date||dayKey(x.starts_at,user.timezone));
 const emptyTasks=tasks.data.filter(x=>!x.completed&&!x.due_at).slice(0,8);
 return <div className="calendar-page">
  <Head title="Расписание" subtitle="Выделите время мышью — событие почти готово."><Button variant="quiet" icon="template" onClick={()=>templates('event')}>Шаблоны</Button><Button icon="plus" onClick={()=>addAt()}>Создать</Button></Head>
  <div className="calendar-toolbar"><div className="calendar-date"><IconButton icon="menu" label="Показать панель календарей" onClick={()=>setAside(!aside)}/><Button variant="quiet" onClick={todayView}>Сегодня</Button><IconButton icon="left" label="Предыдущий период" onClick={()=>navigate(-1)}/><IconButton icon="right" label="Следующий период" onClick={()=>navigate(1)}/><strong className="calendar-period">{view==='year'?year:heading}</strong><input ref={dateInput} type="date" aria-label="Дата календаря" value={selected} onChange={e=>{if(e.target.value)setSelected(e.target.value)}}/></div><div className="calendar-tools"><select aria-label="Вид календаря" value={view} onChange={e=>setView(e.target.value as View)}>{VIEWS.map(x=><option key={x.key} value={x.key}>{x.label}</option>)}</select><IconButton icon="settings" label="Настройки календаря" onClick={()=>setPanel('settings')}/><IconButton icon="copy" label="Импорт и экспорт" onClick={()=>setPanel('transfer')}/><IconButton icon="trash" label="Корзина событий" onClick={()=>setPanel('trash')}/><button className="icon-btn" aria-label="Горячие клавиши" title="Горячие клавиши" onClick={()=>setPanel('help')}>?</button></div></div>
  <div className="calendar-filterbar"><div className="calendar-search"><Icon name="search" size={17}/><input ref={search} value={query} onChange={e=>setQuery(e.target.value)} aria-label="Поиск по текущему периоду" placeholder="Найти в этом периоде…"/>{query&&<IconButton label="Очистить поиск" icon="close" onClick={()=>setQuery('')}/>}</div><select value={filter} aria-label="Фильтр расписания" onChange={e=>setFilter(e.target.value)}><option value="all">Все категории</option><option value="tasks">Только задачи</option>{['Учёба','Работа','Тренировка','Личное','Отдых','Фокус','Нет на месте'].map(x=><option key={x}>{x}</option>)}</select><span className="timezone-note">{user.timezone}</span>{saving&&<span role="status">Сохраняем…</span>}</div>
  <DataState {...state}/><DataState {...tasks}/><DataState {...calendars}/>
  <div className={`calendar-workspace ${aside?'has-aside':''}`}>
   {aside&&<aside className="calendar-aside"><MiniCalendar selected={selected} onSelect={setSelected} firstDay={prefs.weekStart} markers={markers}/><div className="calendar-aside-head"><h3>Мои календари</h3><IconButton label="Управление календарями" icon="plus" onClick={()=>setPanel('calendars')}/></div>{[{id:'default',title:'Основной',color:'#7c83ff'},...calendars.data,{id:'tasks',title:'Задачи',color:'#508c9c'}].map(c=><label className="calendar-check" key={c.id}><input type="checkbox" checked={!hidden.includes(c.id)} style={{accentColor:safeColor(c.color)}} onChange={()=>toggle(c.id)}/><span>{c.title}</span></label>)}{hidden.length>0&&<Button variant="ghost" onClick={()=>setHidden([])}>Показать все</Button>}<div className="calendar-aside-head"><h3>Без времени</h3><small>{emptyTasks.length}</small></div><p className="hint">Перетащите задачу на сетку или откройте её для выбора времени.</p><div className="unscheduled-tasks">{emptyTasks.map(t=><button key={t.id} draggable onDragStart={e=>{e.dataTransfer.setData('application/x-maqsat-task',t.id);e.dataTransfer.effectAllowed='move'}} onClick={()=>edit('task',t)}><Icon name="tasks" size={14}/>{t.title}</button>)}{!emptyTasks.length&&<p className="hint">Нет незапланированных задач</p>}</div></aside>}
   <div className={`calendar-board ${gestures.isDragging?'is-selecting':''}`} ref={root}>
    {timed&&<section className="calendar-shell">
     <div className="day-headers" style={{gridTemplateColumns:columns}}><span className="time-gutter">{prefs.secondZone?'2 пояса':'Время'}</span>{days.map(d=><button key={d} className={d===currentDay?'is-today':''} onClick={()=>{setSelected(d);setView('day')}}><span>{WEEKDAYS[weekday(d)]}</span><strong>{Number(d.slice(-2))}</strong></button>)}</div>
     <div className="all-day-strip" style={{gridTemplateColumns:columns}}><span className="time-gutter">Весь день</span>{days.map(day=><div key={day} data-select-day={day} className={`all-day-cell ${gestures.preview?.all_day&&selectionParts.some(x=>x.day===day)?'range-selected':''}`} onPointerDown={e=>gestures.beginCreate(e,day,'date')} onClick={e=>touchClick(e,day,true)} tabIndex={0} role="button" aria-label={`Весь день ${day}`} onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();setDraft(allDaySelection(day,day,user.timezone))}}}>{blocks.filter(b=>allDayOn(b,day)).map(b=>dateEvent(b,day))}</div>)}</div>
     <div className="calendar-scroll" ref={scroll}><div className="calendar-timeline" data-testid="calendar-grid" style={{height:24*prefs.hourHeight,gridTemplateColumns:columns,'--hour-height':`${prefs.hourHeight}px`} as CSSProperties}><div className="time-labels">{Array.from({length:24},(_,i)=><span key={i} style={{top:i*prefs.hourHeight}}>{prefs.secondZone&&<small>{secondaryTime(selected,i)}</small>}{String(i).padStart(2,'0')}:00</span>)}</div>{days.map(day=><div key={day} className={`day-column ${day===currentDay?'current-day':''}`} data-day={day} data-time-day={day} onPointerDown={e=>gestures.beginCreate(e,day)} onClick={e=>touchClick(e,day)} role="button" tabIndex={0} aria-label={`Добавить событие ${day}`} onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();e.stopPropagation();setKeyMinute(m=>Math.max(0,Math.min(1440-prefs.step,m+(e.key==='ArrowUp'?-prefs.step:prefs.step))))}else if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();addAt(day,keyMinute)}}} onDragOver={e=>{if(e.dataTransfer.types.includes('application/x-maqsat-task')){e.preventDefault();e.dataTransfer.dropEffect='move'}}} onDrop={e=>void dropTask(e,day)}>
       <div className="off-hours" style={{height:prefs.workingStart*prefs.hourHeight}}/><div className="off-hours" style={{top:prefs.workingEnd*prefs.hourHeight,bottom:0}}/>
       <div className="keyboard-slot" style={{top:keyMinute/60*prefs.hourHeight,height:prefs.step/60*prefs.hourHeight}}><span>{String(Math.floor(keyMinute/60)).padStart(2,'0')}:{String(keyMinute%60).padStart(2,'0')} · Enter</span></div>
       {segmentsForDay(blocks,day,user.timezone).map(eventBlock)}
       {!gestures.preview?.all_day&&selectionParts.filter(s=>s.day===day).map(s=><div key={s.day} className="calendar-selection" data-testid="selection-preview" style={{top:s.start/60*prefs.hourHeight,height:Math.max(12,(s.end-s.start)/60*prefs.hourHeight)}}><strong>Новое событие</strong><span>{gestures.preview&&clock(gestures.preview.starts_at,user.timezone)} — {gestures.preview&&clock(gestures.preview.ends_at,user.timezone)}</span></div>)}
       {day===currentDay&&<div className="now-line" style={{top:minutesOf(new Date(now).toISOString(),user.timezone)/60*prefs.hourHeight}}/>}
      </div>)}</div></div>
    </section>}
    {view==='month'&&<div className="month-calendar"><div className="month-weekdays">{monthOrder.map(d=><span key={d}>{d}</span>)}</div><div className="month-grid">{days.map(day=>{const items=dayBlocks(day);return <div key={day} data-select-day={day} className={`month-day ${day===currentDay?'is-today':''} ${day.slice(0,7)!==selected.slice(0,7)?'muted-day':''} ${gestures.preview?.all_day&&selectionParts.some(x=>x.day===day)?'range-selected':''}`} onPointerDown={e=>gestures.beginCreate(e,day,'date')} onClick={e=>touchClick(e,day,true)}><button className="month-number" onClick={()=>{setSelected(day);setView('day')}} aria-label={`Открыть день ${day}`}>{Number(day.slice(-2))}</button>{items.slice(0,4).map(b=>dateEvent(b,day))}{items.length>4&&<button className="text-link" onClick={()=>{setSelected(day);setView('day')}}>Ещё {items.length-4}</button>}<button className="month-add-keyboard" aria-label={`Создать на весь день ${day}`} onClick={()=>setDraft(allDaySelection(day,day,user.timezone))}>+</button></div>})}</div></div>}
    {view==='year'&&<div className="year-calendar">{Array.from({length:12},(_,i)=><MiniCalendar key={i} fixedMonth={`${year}-${String(i+1).padStart(2,'0')}-01`} selected={selected} firstDay={prefs.weekStart} markers={markers} onSelect={day=>{setSelected(day);setView('day')}}/>)}</div>}
    {view==='list'&&<div className="agenda-list">{days.map(day=>{const items=dayBlocks(day);return <section key={day} className="agenda-day"><h2>{WEEKDAYS[weekday(day)]}, {shortDate(day,user.timezone)}</h2>{items.length?items.map(block=><button key={block.key} className="agenda-event" onClick={()=>open(block)}><time>{block.allDay?'Весь день':clock(block.start,user.timezone)}{!block.allDay&&<small>{clock(block.end,user.timezone)}</small>}</time><i className="agenda-color" style={{background:block.color}}/><div><strong>{block.title}</strong><span>{block.location||block.category}</span></div><Icon name="right" size={18}/></button>):<button className="agenda-empty" onClick={()=>addAt(day)}>Свободный день · добавить событие</button>}</section>})}</div>}
   </div>
  </div>
  <p className="hint calendar-bottom-hint">Выделение мышью — создать · края события — изменить время · Esc — отменить · ? — все горячие клавиши.</p>
  {draft&&<QuickEvent selection={draft} onClose={()=>setDraft(null)}/>}
  {peek&&<EventPeek block={peek} calendarName={calendars.data.find(c=>c.id===peek.calendarId)?.title||'Основной'} onClose={()=>setPeek(null)}/>}
  {panel==='calendars'&&<CalendarManager onClose={()=>setPanel(null)}/>}{panel==='settings'&&<CalendarSettings prefs={prefs} onChange={setPrefs} onClose={()=>setPanel(null)}/>}{panel==='transfer'&&<CalendarTransfer start={rangeStart} end={rangeEnd} onClose={()=>setPanel(null)}/>}{panel==='trash'&&<CalendarTrash onClose={()=>setPanel(null)}/>}{panel==='help'&&<CalendarHelp onClose={()=>setPanel(null)}/>}
 </div>
}
