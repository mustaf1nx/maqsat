import {atMinute,plusDays,weekday,localInput,minutesOf} from './dates';
import type {Block} from './calendar';
export type View='day'|'week'|'workweek'|'month'|'year'|'list';
export type CalendarPreferences={step:number;hourHeight:number;duration:number;weekStart:0|6;workingStart:number;workingEnd:number;showTasks:boolean;showCompleted:boolean;secondZone:string};
export const DEFAULT_PREFS:CalendarPreferences={step:15,hourHeight:64,duration:60,weekStart:0,workingStart:9,workingEnd:18,showTasks:true,showCompleted:false,secondZone:''};
export function validPreferences(value:unknown):CalendarPreferences{
 const v=value&&typeof value==='object'?value as Partial<CalendarPreferences>:{};
 let zone='';try{if(typeof v.secondZone==='string'&&v.secondZone){new Intl.DateTimeFormat('en',{timeZone:v.secondZone});zone=v.secondZone}}catch{/* Ignore corrupt storage. */}
 const start=Number.isInteger(v.workingStart)&&v.workingStart!>=0&&v.workingStart!<=23?v.workingStart!:9;
 const end=Number.isInteger(v.workingEnd)&&v.workingEnd!>start&&v.workingEnd!<=24?v.workingEnd!:Math.max(18,start+1);
 return {step:[5,15,30,60].includes(v.step!)?v.step!:15,hourHeight:[48,64,88].includes(v.hourHeight!)?v.hourHeight!:64,duration:[15,30,60,90,120].includes(v.duration!)?v.duration!:60,weekStart:v.weekStart===6?6:0,workingStart:start,workingEnd:end,showTasks:typeof v.showTasks==='boolean'?v.showTasks:true,showCompleted:v.showCompleted===true,secondZone:zone};
}
export const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
export const snap=(value:number,step=15)=>Math.round(value/step)*step;
export const weekStart=(day:string,first=0)=>plusDays(day,-((weekday(day)-first+7)%7));
export function dayDistance(a:string,b:string){return Math.round((Date.parse(b+'T12:00Z')-Date.parse(a+'T12:00Z'))/86400000)}
export function monthShift(day:string,delta:number){const d=new Date(day.slice(0,7)+'-01T12:00Z');d.setUTCMonth(d.getUTCMonth()+delta);return d.toISOString().slice(0,10)}
export type Selection={starts_at:string;ends_at:string;all_day:boolean;timezone:string};
export function selectionBetween(anchorDay:string,anchorMinute:number,day:string,minute:number,zone:string,step=15):Selection{
 const anchor=clamp(Math.floor(anchorMinute/step)*step,0,1440-step);
 const relative=dayDistance(anchorDay,day)*1440+clamp(snap(minute,step),0,1440);
 let start=Math.min(anchor,relative),end=Math.max(anchor,relative);
 if(start===end)end=start+step;
 // No silent zero-duration events; align DST using the same timezone conversion as the editor.
 const a=atMinute(anchorDay,start,zone),b=atMinute(anchorDay,end,zone);
 if(Date.parse(b)<=Date.parse(a))throw Error('Выберите корректный интервал времени');
 if(Date.parse(b)-Date.parse(a)>7*86400000)throw Error('Выберите интервал не длиннее семи дней');
 return {starts_at:a,ends_at:b,all_day:false,timezone:zone};
}
export function allDaySelection(a:string,b:string,zone:string):Selection{
 const first=a<b?a:b,last=a>b?a:b;
 return {starts_at:atMinute(first,0,zone),ends_at:atMinute(plusDays(last,1),0,zone),all_day:true,timezone:zone};
}
export function clickSelection(day:string,minute:number,zone:string,duration=60,step=15):Selection{
 const start=clamp(Math.floor(minute/step)*step,0,1440-step);
 return {starts_at:atMinute(day,start,zone),ends_at:atMinute(day,Math.min(1440,start+duration),zone),all_day:false,timezone:zone};
}
export function allDayOn(block:Block,day:string){return Boolean(block.allDay&&block.startDate&&block.endDate&&block.startDate<=day&&block.endDate>day)}
export function selectionSegments(selection:Selection,days:string[],zone:string){
 const a=localInput(selection.starts_at,zone),b=localInput(selection.ends_at,zone);
 return days.flatMap(day=>{
  if(day<a.slice(0,10)||day>b.slice(0,10)||day===b.slice(0,10)&&b.slice(11)==='00:00')return [];
  return [{day,start:day===a.slice(0,10)?minutesOf(selection.starts_at,zone):0,end:day===b.slice(0,10)?minutesOf(selection.ends_at,zone):1440}];
 });
}
export function isTyping(target:EventTarget|null){return target instanceof HTMLElement&&Boolean(target.closest('input,textarea,select,[contenteditable="true"]'))}
export const COLORS=['#7c83ff','#3b82f6','#25966d','#cf6348','#b98b24','#a869c9','#d05287','#508c9c'];
export const CATEGORY_COLORS:Record<string,string>={'Учёба':'#7c83ff','Работа':'#3b82f6','Тренировка':'#25966d','Здоровье':'#25966d','Личное':'#a869c9','Отдых':'#b98b24'};
export function safeColor(color:unknown,fallback='#7c83ff'){return typeof color==='string'&&/^#[a-f\d]{6}$/i.test(color)?color:fallback}
export function safeMeetingLink(value:unknown){try{if(typeof value!=='string')return '';const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password?u.href:''}catch{return ''}}
export function textColor(hex:string){const v=safeColor(hex).slice(1);const c=[0,2,4].map(i=>parseInt(v.slice(i,i+2),16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]>.179?'#000000':'#ffffff'}
