export const WEEKDAYS=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
export const MONEY_KIND={expense:'Расход',income:'Доход'} as const;
export const PRIORITIES={low:'Низкий',normal:'Обычный',high:'Высокий'} as const;
export const pad=(n:number)=>String(n).padStart(2,'0');
export const money=(value:string|number=0)=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(value))+' ₸';
export function parts(value:Date|string,zone:string){
 const date=typeof value==='string'?new Date(value):value;
 const data=Object.fromEntries(new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date).map(p=>[p.type,p.value]));
 return {day:`${data.year}-${data.month}-${data.day}`,time:`${data.hour}:${data.minute}`};
}
export const dayKey=(value:Date|string,zone:string)=>parts(value,zone).day;
export const localInput=(value:Date|string,zone:string)=>{const p=parts(value,zone);return `${p.day}T${p.time}`};
export function toISO(local:string,zone:string):string{
 if(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local))throw Error('Укажите дату и время');
 // Solve a local wall-clock time using Intl, without silently using the device zone.
 const desired=Date.parse(local+':00Z');let guess=desired;
 for(let i=0;i<4;i++){
  const observed=Date.parse(localInput(new Date(guess),zone)+':00Z');
  const delta=desired-observed;if(!delta)break;guess+=delta;
 }
 if(localInput(new Date(guess),zone)!==local)throw Error('Это время не существует из-за перевода часов. Выберите другое.');
 return new Date(guess).toISOString();
}
export const shortDate=(value:string,zone:string)=>/^\d{4}-\d{2}-\d{2}$/.test(value)?new Date(value+'T12:00:00Z').toLocaleDateString('ru-RU',{day:'numeric',month:'short',timeZone:'UTC'}):new Date(value).toLocaleDateString('ru-RU',{day:'numeric',month:'short',timeZone:zone});
export const clock=(value:string,zone:string)=>parts(value,zone).time;
export const today=(zone:string)=>dayKey(new Date(),zone);
export function plusDays(day:string,n:number){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)}
export function weekday(day:string){return (new Date(day+'T12:00:00Z').getUTCDay()+6)%7}
export const monday=(day:string)=>plusDays(day,-weekday(day));
export const minutesOf=(iso:string,zone:string)=>{const [h,m]=parts(iso,zone).time.split(':').map(Number);return h*60+m};
export const atMinute=(day:string,minute:number,zone:string)=>toISO(`${plusDays(day,Math.floor(minute/1440))}T${pad(Math.floor(((minute%1440)+1440)%1440/60))}:${pad(((minute%60)+60)%60)}`,zone);
export const fromNow=(minute:number)=>new Date(Date.now()+minute*60000).toISOString();
export const formatDuration=(minutes:number)=>minutes>=60?`${Math.floor(minutes/60)} ч ${minutes%60?`${minutes%60} мин`:''}`.trim():`${minutes} мин`;
export function safeRead<T>(key:string,fallback:T):T{try{const value=localStorage.getItem(key);return value?JSON.parse(value) as T:fallback}catch{return fallback}}
export function safeWrite(key:string,value:unknown){try{localStorage.setItem(key,JSON.stringify(value))}catch{/* Storage may be disabled. Server records remain unaffected. */}}
export function isToday(task:{due_at:string|null},zone:string){return Boolean(task.due_at&&dayKey(task.due_at,zone)===today(zone))}
export function isOverdue(task:{due_at:string|null;completed:boolean},zone:string){return Boolean(!task.completed&&task.due_at&&dayKey(task.due_at,zone)<today(zone))}
export function moveTimes(start:string,end:string,dayDelta:number,minuteDelta:number,zone:string){
 const p=parts(start,zone);const newStart=atMinute(plusDays(p.day,dayDelta),minutesOf(start,zone)+minuteDelta,zone);
 return {starts_at:newStart,ends_at:new Date(Date.parse(newStart)+Date.parse(end)-Date.parse(start)).toISOString()};
}
