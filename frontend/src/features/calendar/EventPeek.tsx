import {useState} from 'react';
import type {Block} from '../../lib/calendar';
import type {CalendarEvent} from '../../lib/types';
import {useApp} from '../../app/context';
import {Modal,Button,IconButton} from '../../components/ui';
import {Icon} from '../../components/Icon';
import {shortDate,clock,plusDays,WEEKDAYS} from '../../lib/dates';
import {safeMeetingLink} from '../../lib/calendarSelection';

export function EventPeek({block,onClose,calendarName}:{block:Block;onClose:()=>void;calendarName:string}){
 const {api,edit,refresh,notify,user,go}=useApp();const ev=block.original as CalendarEvent;
 const [scope,setScope]=useState<'single'|'following'|'series'>('single'),[deleting,setDeleting]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const link=safeMeetingLink(ev.meeting_url),reminders=ev.reminders?.length?ev.reminders:ev.reminder_minutes!=null?[ev.reminder_minutes]:[];
 function editEvent(){onClose();edit('event',ev)}
 function duplicate(){const fields=['title','starts_at','ends_at','timezone','all_day','location','category','note','meeting_url','calendar_id','color','availability','reminders','reminder_minutes','workout_template_id'] as const;const data=Object.fromEntries(fields.map(k=>[k,ev[k]]));onClose();edit('event',{...data,title:ev.title+' (копия)',recurrence:null})}
 async function remove(){setBusy(true);setError('');try{
  if(ev.recurrence&&scope==='single'){
   const path=`/events/${ev.event_id}/occurrences/${ev.occurrence_key}`,result=await api<{version:number}>(path,'PATCH',{cancelled:true,version:ev.version});
   notify('Повторение отменено',false,async()=>{await api(path,'PATCH',{cancelled:false,version:result.version});refresh()});
  }else if(ev.recurrence&&scope==='following'){
   await api(`/events/${ev.event_id}/following/${ev.occurrence_key}?version=${ev.version}`,'DELETE');notify('Будущая часть серии удалена');
  }else {await api(`/events/${ev.event_id}`,'DELETE');notify('Событие в корзине',false,async()=>{await api(`/calendar-trash/${ev.event_id}/restore`,'POST');refresh()})}
  refresh();onClose();
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const repeat=ev.recurrence;
 return <Modal title={deleting?'Удаление события':'Событие'} onClose={onClose} busy={busy}><div className="event-peek">
  <div className="event-peek-heading"><span style={{background:block.color}}/><h2>{ev.title}</h2></div>
  {!deleting?<><div className="event-peek-time"><Icon name="clock"/><div><strong>{shortDate(ev.starts_at,ev.all_day?ev.timezone:user.timezone)}</strong><p>{ev.all_day?`Весь день${ev.end_date&&ev.start_date!==plusDays(ev.end_date,-1)?' — '+shortDate(plusDays(ev.end_date,-1),ev.timezone):''}`:`${clock(ev.starts_at,user.timezone)} — ${clock(ev.ends_at,user.timezone)}`}</p><small>{ev.all_day?ev.timezone:user.timezone} · {ev.availability==='free'?'Свободен':'Занят'}</small></div></div>
  {repeat&&<p className="peek-row"><Icon name="habit"/><span>{({daily:'Каждые '+repeat.interval+' дн.',weekly:'Каждые '+repeat.interval+' нед.',monthly:'Каждые '+repeat.interval+' мес.',yearly:'Каждые '+repeat.interval+' г.'})[repeat.frequency]}{repeat.frequency==='weekly'?' · '+repeat.weekdays.map(x=>WEEKDAYS[x]).join(', '):''}{repeat.until?' · до '+shortDate(repeat.until,user.timezone):repeat.count?' · '+repeat.count+' повторений':''}</span></p>}
  {ev.location&&<p className="peek-row"><Icon name="pin"/><span>{ev.location}</span></p>}
  {link&&<a className="btn quiet meeting-link" href={link} target="_blank" rel="noopener noreferrer">Открыть видеовстречу ↗</a>}
  {reminders.length>0&&<p className="peek-row"><Icon name="bell"/><span>{reminders.map(n=>n===0?'В момент начала':`За ${n} мин`).join(' · ')}</span></p>}
  <p className="peek-row"><Icon name="calendar"/><span>{calendarName} · {ev.category}</span></p>
  {ev.note&&<p className="event-note">{ev.note}</p>}
  {ev.is_workout&&<Button variant="quiet" icon="health" onClick={()=>{onClose();go('health')}}>Открыть журнал тренировок</Button>}
  <footer className="form-actions"><div><IconButton label="Создать копию события" icon="copy" onClick={duplicate}/><IconButton label="Удалить событие" icon="trash" onClick={()=>setDeleting(true)}/></div><Button icon="edit" onClick={editEvent}>Редактировать</Button></footer>
  </>:<><p>Уже записанные тренировки останутся в журнале.</p>{ev.recurrence&&<div className="scope-options">{[['single','Только это событие'],['following','Это и последующие'],['series','Вся серия']] .map(([value,label])=><label className="check-label" key={value}><input type="radio" name="delete-scope" value={value} checked={scope===value} onChange={()=>setScope(value as typeof scope)}/>{label}</label>)}</div>}{scope==='following'&&ev.recurrence&&<p className="hint">Предыдущие занятия сохранятся. Будущая часть удаляется без помещения в корзину.</p>}{error&&<p className="error-panel" role="alert">{error}</p>}<footer className="form-actions"><Button variant="quiet" onClick={()=>setDeleting(false)} disabled={busy}>Назад</Button><Button variant="danger" onClick={()=>void remove()} disabled={busy}>Удалить</Button></footer></>}
 </div></Modal>
}
