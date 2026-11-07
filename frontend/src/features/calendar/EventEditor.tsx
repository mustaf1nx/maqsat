import {useState} from 'react';
import type {CalendarEvent,CalendarCollection,WorkoutTemplate,Rule} from '../../lib/types';
import {useApp,useData} from '../../app/context';
import {Form,Field,Button,WeekPicker,DeleteButton} from '../../components/ui';
import {localInput,toISO,today,atMinute,plusDays,weekday,WEEKDAYS} from '../../lib/dates';
import {COLORS} from '../../lib/calendarSelection';

type Scope='single'|'following'|'series';
const CATEGORIES=['Личное','Учёба','Работа','Тренировка','Отдых','Фокус','Нет на месте'];
export function EventEditor({value={},scope='single'}:{value?:Record<string,unknown>;scope?:Scope}){
 const {close,user,api,refresh,notify,edit}=useApp();const original=value as Partial<CalendarEvent>;
 const existing=Boolean(original.id),rule=original.recurrence;
 const instance=existing&&Boolean(original.occurrence_key)&&Boolean(rule)&&scope==='single';
 const [zone,setZone]=useState(original.timezone||user.timezone);
 const [v,setV]=useState(()=>{
  const z=original.timezone||user.timezone;
  const start=localInput(original.starts_at||atMinute(today(z),9*60,z),z),end=localInput(original.ends_at||atMinute(today(z),10*60,z),z);
  return {title:original.title||'',start,end,allDay:original.all_day||false,endDay:original.all_day?plusDays(end.slice(0,10),-1):start.slice(0,10),category:original.category||'Личное',note:original.note||'',location:original.location||'',repeat:rule?.frequency||'none',interval:rule?.interval||1,days:rule?.weekdays?.length?rule.weekdays:[weekday(start.slice(0,10))],until:rule?.until||'',count:scope==='following'&&rule?.count?Math.max(1,rule.count-(original.occurrence_index||1)+1):rule?.count||10,ending:rule?.until?'until':rule?.count?'count':'never',monthlyMode:rule?.monthly_mode||'day',reminders:original.reminders?.length?original.reminders:original.reminder_minutes!=null?[original.reminder_minutes]:[],calendar:original.calendar_id||'',color:original.color||'',availability:original.availability||'busy',meeting:original.meeting_url||'',template:original.workout_template_id||''};
 });
 const calendars=useData<CalendarCollection[]>('/calendars',[]),templates=useData<WorkoutTemplate[]>('/workout-templates',[]);
 function payload(){
  const recurrence:Rule|null=v.repeat==='none'?null:{frequency:v.repeat as Rule['frequency'],interval:Number(v.interval),weekdays:v.repeat==='weekly'?v.days:[],until:v.ending==='until'?v.until||null:null,count:v.ending==='count'?Number(v.count):null,monthly_mode:v.monthlyMode};
  return {title:v.title,starts_at:v.allDay?atMinute(v.start.slice(0,10),0,zone):toISO(v.start,zone),ends_at:v.allDay?atMinute(plusDays(v.endDay,1),0,zone):toISO(v.end,zone),category:v.category,note:v.note,location:v.location,timezone:zone,recurrence,reminder_minutes:null,reminders:v.reminders.map(Number),workout_template_id:v.template||null,calendar_id:v.calendar||null,color:v.color||null,all_day:v.allDay,availability:v.availability,meeting_url:v.meeting};
 }
 async function save(){
  const data=payload();if(Date.parse(data.ends_at)<=Date.parse(data.starts_at))throw Error('Окончание должно быть позже начала');
  if(v.repeat==='weekly'&&!v.days.length)throw Error('Выберите дни недели');
  if(v.repeat!=='none'&&v.ending==='until'&&!v.until)throw Error('Укажите конечную дату повторений');
  const id=original.event_id||original.id;
  if(instance){const {recurrence:_,timezone:__,workout_template_id:___,...fields}=data;await api(`/events/${id}/occurrences/${original.occurrence_key}`,'PATCH',{...fields,version:original.version})}
  else if(existing&&scope==='following')await api(`/events/${id}/following/${original.occurrence_key}`,'PATCH',{...data,version:original.version});
  else await api('/events'+(existing?`/${id}`:''),existing?'PATCH':'POST',{...data,...(existing?{version:original.version}:{})});
  refresh();notify(instance?'Изменено только это событие':scope==='following'?'Изменена будущая часть серии':'Событие сохранено');
 }
 async function changeScope(next:Scope){
  if(next==='series'){
   try{const masters=await api<CalendarEvent[]>('/events');const master=masters.find(x=>x.id===(original.event_id||original.id));if(master)edit('event',master,'series');else notify('Серия уже удалена',true)}catch(e){notify((e as Error).message,true)}
  }else edit('event',value,next);
 }
 async function remove(){
  const id=original.event_id||original.id;
  if(instance)await api(`/events/${id}/occurrences/${original.occurrence_key}`,'PATCH',{cancelled:true,version:original.version});
  else if(scope==='following')await api(`/events/${id}/following/${original.occurrence_key}?version=${original.version}`,'DELETE');
  else {await api(`/events/${id}`,'DELETE');notify('Событие в корзине',false,async()=>{await api(`/calendar-trash/${id}/restore`,'POST');refresh()})}
  refresh();close();
 }
 function startChange(start:string){
  const delta=Date.parse(start+':00Z')-Date.parse(v.start+':00Z'),newEnd=Date.parse(v.end+':00Z')+delta;
  setV({...v,start,end:Number.isFinite(newEnd)?new Date(newEnd).toISOString().slice(0,16):v.end,endDay:!v.endDay||v.endDay<start.slice(0,10)?start.slice(0,10):v.endDay});
 }
 return <Form onClose={close} onSubmit={save} extra={<>
  {!instance&&<Button variant="ghost" icon="template" onClick={async()=>{try{const data=payload();await api('/templates','POST',{kind:'event',title:v.title||'Моё событие',data});refresh();notify('Шаблон сохранён')}catch(e){notify((e as Error).message,true)}}}>В шаблоны</Button>}
  {existing&&<DeleteButton label={instance?'Удалить это повторение?':scope==='following'?'Удалить это и последующие?':rule?'Переместить серию в корзину?':'Переместить событие в корзину?'} text="Журнал уже записанных тренировок сохранится. Удаление отдельного повторения или будущей части серии не добавляет её в корзину целых событий." onDelete={remove}/>}
 </>}>
  {existing&&rule&&<div className="info-panel"><strong>{instance?'Только это событие':scope==='following'?'Это и последующие события':'Вся серия'}</strong><div className="inline-actions">{original.occurrence_key&&scope!=='following'&&<Button variant="quiet" onClick={()=>void changeScope('following')}>Это и последующие</Button>}{scope!=='series'&&<Button variant="quiet" onClick={()=>void changeScope('series')}>Вся серия</Button>}</div><small>Переход между областями редактирования откроет сохранённую версию. Сначала сохраните текущие правки.</small></div>}
  <Field label="Название события"><input autoFocus required maxLength={240} value={v.title} onChange={e=>setV({...v,title:e.target.value,category:['зал','gym','спортзал'].includes(e.target.value.trim().toLowerCase())?'Тренировка':v.category})} placeholder="Добавьте название"/></Field>
  <label className="check-label"><input type="checkbox" checked={v.allDay} onChange={e=>setV({...v,allDay:e.target.checked,endDay:v.start.slice(0,10)})}/>Весь день</label>
  <div className="form-grid"><Field label="Начало"><input required type={v.allDay?'date':'datetime-local'} value={v.allDay?v.start.slice(0,10):v.start} onChange={e=>startChange(v.allDay?e.target.value+'T09:00':e.target.value)}/></Field><Field label={v.allDay?'Последний день включительно':'Окончание'}><input required type={v.allDay?'date':'datetime-local'} min={v.allDay?v.start.slice(0,10):undefined} value={v.allDay?v.endDay:v.end} onChange={e=>setV({...v,...(v.allDay?{endDay:e.target.value}:{end:e.target.value})})}/></Field></div>
  {!instance&&<Field label="Часовой пояс" hint="При смене пояса введённые часы сохраняются, меняется соответствующее мировое время."><input list="event-timezones" required value={zone} onChange={e=>setZone(e.target.value)}/></Field>}
  <datalist id="event-timezones">{['Asia/Almaty','UTC','Europe/Moscow','Europe/London','Europe/Berlin','Asia/Dubai','Asia/Tashkent','America/New_York','America/Los_Angeles','Asia/Tokyo'].map(x=><option key={x} value={x}/>)}</datalist>
  <div className="form-grid"><Field label="Место"><input maxLength={300} value={v.location} onChange={e=>setV({...v,location:e.target.value})} placeholder="Адрес, аудитория, зал"/></Field><Field label="Категория"><select value={v.category} onChange={e=>setV({...v,category:e.target.value})}>{[...new Set([...CATEGORIES,v.category])].map(x=><option key={x}>{x}</option>)}</select></Field>
  <Field label="Календарь"><select value={v.calendar} onChange={e=>setV({...v,calendar:e.target.value})}><option value="">Основной</option>{calendars.data.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></Field><Field label="Доступность"><select value={v.availability} onChange={e=>setV({...v,availability:e.target.value as 'busy'|'free'})}><option value="busy">Занят</option><option value="free">Свободен</option></select></Field></div>
  <Field label="Ссылка на видеовстречу" hint="Вставьте существующую HTTPS-ссылку. MAQSAT не создаёт Google Meet автоматически."><input type="url" maxLength={2048} value={v.meeting} onChange={e=>setV({...v,meeting:e.target.value})} placeholder="https://…"/></Field>
  <div className="field"><span>Цвет события</span><div className="color-palette"><button type="button" className={!v.color?'selected':''} aria-pressed={!v.color} onClick={()=>setV({...v,color:''})}>Как у календаря</button>{COLORS.map(color=><button key={color} type="button" className={v.color===color?'selected':''} aria-label={`Цвет ${color}`} aria-pressed={v.color===color} style={{background:color}} onClick={()=>setV({...v,color})}/>)}</div></div>
  {!instance&&<><Field label="Повторять"><select value={v.repeat} onChange={e=>setV({...v,repeat:e.target.value})}><option value="none">Не повторять</option><option value="daily">Ежедневно / каждые N дней</option><option value="weekly">По неделям и дням недели</option><option value="monthly">Ежемесячно</option><option value="yearly">Ежегодно</option></select></Field>
   {v.repeat!=='none'&&<div className="repeat-box"><div className="form-grid"><Field label="Интервал повторения" hint={v.repeat==='weekly'?'В неделях':v.repeat==='monthly'?'В месяцах':v.repeat==='yearly'?'В годах':'В днях'}><input required type="number" min={1} max={52} value={v.interval} onChange={e=>setV({...v,interval:Number(e.target.value)})}/></Field><Field label="Завершение серии"><select value={v.ending} onChange={e=>setV({...v,ending:e.target.value})}><option value="never">Без окончания</option><option value="until">В указанную дату</option><option value="count">После N повторений</option></select></Field>{v.ending==='until'&&<Field label="Повторять до"><input type="date" required min={v.start.slice(0,10)} value={v.until} onChange={e=>setV({...v,until:e.target.value})}/></Field>}{v.ending==='count'&&<Field label="Число повторений"><input type="number" required min={1} max={1000} value={v.count} onChange={e=>setV({...v,count:Number(e.target.value)})}/></Field>}</div>
   {v.repeat==='weekly'&&<WeekPicker days={v.days} onChange={days=>setV({...v,days})}/>}
   {v.repeat==='monthly'&&<Field label="Правило месяца"><select value={v.monthlyMode} onChange={e=>setV({...v,monthlyMode:e.target.value as Rule['monthly_mode']||'day'})}><option value="day">{Number(v.start.slice(8,10))}-го числа</option><option value="weekday">{Math.floor((Number(v.start.slice(8,10))-1)/7)+1}-й день {WEEKDAYS[weekday(v.start.slice(0,10))]} месяца</option><option value="last_weekday">Последний {WEEKDAYS[weekday(v.start.slice(0,10))]} месяца</option></select></Field>}
   {['monthly','yearly'].includes(v.repeat)&&<small>Отсутствующая дата, например 31-е число или 29 февраля, пропускается, а не переносится.</small>}</div>}
  </>}
  <div className="field"><span>Напоминания</span><small>При открытом сайте. Для системных уведомлений требуется разрешение браузера.</small><div className="reminder-editor">{v.reminders.map((minute,index)=><div className="reminder-edit-row" key={index}><input aria-label={`Напомнить за минут ${index+1}`} type="number" min={0} max={10080} required value={minute} onChange={e=>setV({...v,reminders:v.reminders.map((x,i)=>i===index?Number(e.target.value):x)})}/><span>минут до начала</span><Button variant="ghost" onClick={()=>setV({...v,reminders:v.reminders.filter((_,i)=>i!==index)})}>Убрать</Button></div>)}{v.reminders.length<5&&<Button variant="quiet" icon="bell" onClick={()=>setV({...v,reminders:[...v.reminders,15]})}>Добавить напоминание</Button>}</div></div>
  {!instance&&v.category==='Тренировка'&&<Field label="Шаблон тренировки"><select value={v.template} onChange={e=>setV({...v,template:e.target.value})}><option value="">Свободная тренировка</option>{templates.data.map(x=><option key={x.id} value={x.id}>{x.title}</option>)}</select></Field>}
  <Field label="Заметка"><textarea rows={3} maxLength={5000} value={v.note} onChange={e=>setV({...v,note:e.target.value})}/></Field>
 </Form>
}
