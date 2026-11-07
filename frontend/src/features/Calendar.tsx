import {useEffect,useMemo,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import type {Task,CalendarEvent} from '../lib/types';
import {useApp,useData} from '../app/context';
import {Head,Button,IconButton,DataState} from '../components/ui';
import {Icon} from '../components/Icon';
import {today,monday,plusDays,atMinute,minutesOf,shortDate,clock,moveTimes,safeRead,safeWrite,WEEKDAYS,weekday} from '../lib/dates';
import {segmentsForDay,snapMinutes} from '../lib/calendar';
import type {Block,Segment} from '../lib/calendar';
const HOUR=64;
type View='day'|'week'|'month'|'list';
type Gesture={block:Block;day:string;startX:number;startY:number;resizing:boolean;moved:boolean;days:number;minutes:number};
export function Calendar(){
 const {user,edit,api,refresh,notify,templates}=useApp();
 const [selected,setSelected]=useState(today(user.timezone));const [view,setView]=useState<View>(()=>{const stored=safeRead<unknown>(`maqsat:calendar:${user.id}`,null);return typeof stored==='string'&&['day','week','month','list'].includes(stored)?stored as View:window.innerWidth<760?'day':'week'});const [filter,setFilter]=useState('all');
 const start=view==='day'?selected:view==='month'?monday(selected.slice(0,7)+'-01'):monday(selected);const count=view==='day'?1:view==='month'?42:7;
 const days=useMemo(()=>Array.from({length:count},(_,i)=>plusDays(start,i)),[start,count]);const end=plusDays(start,count);
 const state=useData<CalendarEvent[]>(`/events?start=${encodeURIComponent(atMinute(start,0,user.timezone))}&end=${encodeURIComponent(atMinute(end,0,user.timezone))}`,[]);
 const tasks=useData<Task[]>('/tasks',[]);const gridRef=useRef<HTMLDivElement>(null);const scrollRef=useRef<HTMLDivElement>(null);const gesture=useRef<Gesture|null>(null);const suppressClick=useRef(false);const [drag,setDrag]=useState<{key:string;start:string;end:string}|null>(null);const [saving,setSaving]=useState(false);
 useEffect(()=>safeWrite(`maqsat:calendar:${user.id}`,view),[view,user.id]);
 useEffect(()=>{if(scrollRef.current&&['week','day'].includes(view))scrollRef.current.scrollTop=7*HOUR},[view]);
 const blocks=useMemo(()=>{
  const events:Block[]=state.data.map(x=>({key:x.occurrence_id,kind:'event',id:x.event_id,title:x.title,start:x.starts_at,end:x.ends_at,category:x.category,location:x.location,recurring:Boolean(x.recurrence),reminder:x.reminder_minutes!==null,completed:x.workout_status==='done',original:x}));
  const taskBlocks:Block[]=tasks.data.filter(x=>x.due_at).map(x=>({key:'task:'+x.id,kind:'task',id:x.id,title:x.title,start:x.due_at!,end:new Date(Date.parse(x.due_at!)+(x.duration_minutes||30)*60000).toISOString(),category:x.area,location:'',recurring:false,reminder:false,completed:x.completed,original:x}));
  return [...events,...taskBlocks].filter(x=>filter==='all'||x.category===filter||filter==='tasks'&&x.kind==='task').map(x=>drag?.key===x.key?{...x,start:drag.start,end:drag.end}:x);
 },[state.data,tasks.data,filter,drag]);
 function open(block:Block){if(suppressClick.current||saving)return;edit(block.kind,block.original)}
 function pointerDown(e:ReactPointerEvent,block:Block,day:string,resizing=false){
  if(e.button!==0||saving)return;e.stopPropagation();suppressClick.current=false;
  gesture.current={block,day,startX:e.clientX,startY:e.clientY,resizing,moved:false,days:0,minutes:0};
 }
 useEffect(()=>{
  function move(e:PointerEvent){const g=gesture.current;const rect=gridRef.current?.getBoundingClientRect();if(!g||!rect)return;
   if(!g.moved&&Math.hypot(e.clientX-g.startX,e.clientY-g.startY)<6)return;g.moved=true;suppressClick.current=true;e.preventDefault();
   const originalColumn=days.indexOf(g.day);const targetColumn=Math.min(days.length-1,Math.max(0,Math.floor((e.clientX-rect.left-56)/((rect.width-56)/days.length))));
   g.days=g.resizing?0:targetColumn-originalColumn;g.minutes=snapMinutes((e.clientY-g.startY)/HOUR*60);
   let values;
   if(g.resizing){const duration=(Date.parse(g.block.end)-Date.parse(g.block.start))/60000;g.minutes=Math.max(15-duration,Math.min(10080-duration,g.minutes));values={starts_at:g.block.start,ends_at:new Date(Date.parse(g.block.end)+g.minutes*60000).toISOString()}}
   else {try{values=moveTimes(g.block.start,g.block.end,g.days,g.minutes,user.timezone)}catch{return}}
   setDrag({key:g.block.key,start:values.starts_at,end:values.ends_at});
  }
  async function up(){setTimeout(()=>{suppressClick.current=false},0);const g=gesture.current;gesture.current=null;if(!g||!g.moved){setDrag(null);return}
   if(g.days===0&&g.minutes===0){setDrag(null);return}
   let values;
   try{values=g.resizing?{starts_at:g.block.start,ends_at:new Date(Date.parse(g.block.end)+g.minutes*60000).toISOString()}:moveTimes(g.block.start,g.block.end,g.days,g.minutes,user.timezone)}catch(e){setDrag(null);notify((e as Error).message,true);return}
   setSaving(true);
   try{
    if(g.block.kind==='task'){
     const t=g.block.original as Task;const updated=await api<Task>(`/tasks/${t.id}`,'PATCH',{due_at:values.starts_at,duration_minutes:Math.max(5,Math.round((Date.parse(values.ends_at)-Date.parse(values.starts_at))/60000)),version:t.version});
     tasks.setData(rows=>rows.map(x=>x.id===t.id?updated:x));
     notify('Время задачи изменено',false,async()=>{await api(`/tasks/${t.id}`,'PATCH',{due_at:t.due_at,duration_minutes:t.duration_minutes,version:updated.version});refresh()});
    }else{
     const ev=g.block.original as CalendarEvent;const path=`/events/${ev.event_id}/occurrences/${ev.occurrence_key}`;
     const result=await api<{version:number}>(path,'PATCH',{...values,version:ev.version});
     state.setData(rows=>rows.map(x=>x.occurrence_id===ev.occurrence_id?{...x,...values,version:result.version}:x));
     notify(ev.recurrence?'Перенесено только это занятие':'Событие перенесено',false,async()=>{await api(path,'PATCH',{starts_at:ev.starts_at,ends_at:ev.ends_at,version:result.version});refresh()});
    }refresh();
   }catch(e){notify((e as Error).message,true)}finally{setSaving(false);setDrag(null)}
  }
  function cancel(){gesture.current=null;setDrag(null);suppressClick.current=false}
  document.addEventListener('pointermove',move,{passive:false});document.addEventListener('pointerup',up);document.addEventListener('pointercancel',cancel);
  return()=>{document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);document.removeEventListener('pointercancel',cancel)};
 },[api,days,notify,refresh,user.timezone,state.setData,tasks.setData]);
 function addAt(day:string,minute=9*60){const start=atMinute(day,minute,user.timezone);edit('event',{starts_at:start,ends_at:new Date(Date.parse(start)+3600000).toISOString()})}
 function navigate(dir:number){if(view==='month'){const d=new Date(selected+'T12:00:00Z');d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()+dir);setSelected(d.toISOString().slice(0,10))}else setSelected(plusDays(selected,dir*(view==='day'?1:7)))}
 function eventBlock(segment:Segment){const {block}=segment;const small=segment.end-segment.start<45;
  return <button key={block.key+segment.day} data-event={block.key} data-testid="calendar-event" className={`event-block cat-${block.category==='Тренировка'?'health':block.kind==='task'?'task':block.category==='Работа'?'work':block.category==='Учёба'?'study':'personal'} ${block.completed?'done':''} ${drag?.key===block.key?'dragging':''}`} style={{top:segment.start/60*HOUR,height:Math.max(24,(segment.end-segment.start)/60*HOUR-3),left:`calc(${segment.lane/segment.lanes*100}% + 3px)`,width:`calc(${100/segment.lanes}% - 6px)`}} onPointerDown={e=>pointerDown(e,block,segment.day)} onClick={e=>{e.stopPropagation();open(block)}} aria-label={`${block.title}, ${clock(block.start,user.timezone)}, ${block.location||''}`}>
   <span className="event-time">{clock(block.start,user.timezone)}–{clock(block.end,user.timezone)}<span>{block.recurring&&<Icon name="habit" size={12}/>} {block.reminder&&<Icon name="bell" size={12}/>}</span></span><strong>{block.title}</strong>{!small&&block.location&&<span className="event-location"><Icon name="pin" size={12}/>{block.location}</span>}{block.completed&&<span className="event-completed"><Icon name="check" size={12}/></span>}{segment.last&&<span className="resize-handle" aria-hidden="true" onPointerDown={e=>pointerDown(e,block,segment.day,true)}/>}
  </button>
 }
 return <><Head title="Расписание" subtitle="Передвигайте события мышью. Потяните за нижний край, чтобы изменить длительность."><Button variant="quiet" icon="template" onClick={()=>templates('event')}>Шаблоны</Button><Button icon="plus" onClick={()=>edit('event')}>Добавить событие</Button></Head>
 <div className="calendar-toolbar"><div className="calendar-date"><IconButton icon="left" label="Предыдущий период" onClick={()=>navigate(-1)}/><IconButton icon="right" label="Следующий период" onClick={()=>navigate(1)}/><Button variant="quiet" onClick={()=>setSelected(today(user.timezone))}>Сегодня</Button><input type="date" aria-label="Дата календаря" value={selected} onChange={e=>{if(e.target.value)setSelected(e.target.value)}}/></div><div className="tabs">{([['day','День'],['week','Неделя'],['month','Месяц'],['list','Список']] as const).map(([key,label])=><button key={key} className={view===key?'active':''} aria-pressed={view===key} onClick={()=>setView(key)}>{label}</button>)}</div></div>
 <div className="calendar-legend"><span><i className="legend-dot study"/>Учёба</span><span><i className="legend-dot work"/>Работа</span><span><i className="legend-dot health"/>Тренировки</span><span className="timezone-note">{user.timezone}</span><select value={filter} aria-label="Фильтр расписания" onChange={e=>setFilter(e.target.value)}><option value="all">Все события и задачи</option><option value="tasks">Только задачи</option>{['Учёба','Работа','Тренировка','Личное','Отдых'].map(x=><option key={x}>{x}</option>)}</select>{saving&&<span role="status">Сохраняем перенос…</span>}</div>
 <DataState {...state}/><DataState {...tasks}/>
 {(view==='week'||view==='day')&&<section className="calendar-shell"><div className="day-headers" style={{gridTemplateColumns:`56px repeat(${days.length},minmax(0,1fr))`}}><span className="time-gutter">Время</span>{days.map(d=><button key={d} className={d===today(user.timezone)?'is-today':''} onClick={()=>{setSelected(d);setView('day')}}><span>{WEEKDAYS[weekday(d)]}</span><strong>{Number(d.slice(-2))}</strong></button>)}</div><div className="calendar-scroll" ref={scrollRef}><div className="calendar-timeline" ref={gridRef} data-testid="calendar-grid" style={{height:24*HOUR,gridTemplateColumns:`56px repeat(${days.length},minmax(0,1fr))`}}><div className="time-labels">{Array.from({length:24},(_,i)=><span key={i} style={{top:i*HOUR}}>{String(i).padStart(2,'0')}:00</span>)}</div>{days.map(d=><div className="day-column" key={d} data-day={d} onClick={e=>{if(e.target!==e.currentTarget||suppressClick.current)return;const rect=e.currentTarget.getBoundingClientRect();addAt(d,Math.min(1425,Math.max(0,snapMinutes((e.clientY-rect.top)/HOUR*60))))}}>{segmentsForDay(blocks,d,user.timezone).map(eventBlock)}{d===today(user.timezone)&&<div className="now-line" style={{top:minutesOf(new Date().toISOString(),user.timezone)/60*HOUR}}/>}</div>)}</div></div></section>}
 {view==='month'&&<div className="month-calendar"><div className="month-weekdays">{WEEKDAYS.map(d=><span key={d}>{d}</span>)}</div><div className="month-grid">{days.map(day=><div key={day} className={`month-day ${day===today(user.timezone)?'is-today':''} ${day.slice(0,7)!==selected.slice(0,7)?'muted-day':''}`}><button className="month-number" onClick={()=>addAt(day)}>{Number(day.slice(-2))}</button>{segmentsForDay(blocks,day,user.timezone).slice(0,4).map(({block})=><button key={block.key} className="month-event" onClick={()=>open(block)}><span>{clock(block.start,user.timezone)}</span>{block.title}</button>)}{segmentsForDay(blocks,day,user.timezone).length>4&&<button className="text-link" onClick={()=>{setSelected(day);setView('day')}}>Показать день</button>}</div>)}</div></div>}
 {view==='list'&&<div className="agenda-list">{days.map(day=>{const rows=segmentsForDay(blocks,day,user.timezone);return <section key={day} className="agenda-day"><h2>{WEEKDAYS[weekday(day)]}, {shortDate(day,user.timezone)}</h2>{rows.length?rows.map(({block})=><button key={block.key} className="agenda-event" onClick={()=>open(block)}><time>{clock(block.start,user.timezone)}<small>{clock(block.end,user.timezone)}</small></time><div><strong>{block.title}</strong><span>{block.location||block.category}</span></div><Icon name="right" size={18}/></button>):<button className="agenda-empty" onClick={()=>addAt(day)}>Свободный день · добавить событие</button>}</section>})}</div>}
 <p className="hint">Перенос повторяющегося события меняет только выбранное занятие. Для изменения цикла откройте событие и выберите «Вся серия».</p></>
}
