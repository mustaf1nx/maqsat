export type FocusMethod='pomodoro'|'long'|'custom'|'stopwatch';
export type TimerState={method:FocusMethod;phase:'work'|'break';work:number;rest:number;longRest:number;round:number;elapsed:number;runningAt:number|null;label:string;clientId:string;ready:boolean;};
export const FOCUS_PRESETS={pomodoro:{label:'Помодоро',work:25,rest:5,longRest:15},long:{label:'Длинный интервал',work:50,rest:10,longRest:20},custom:{label:'Свой ритм',work:30,rest:5,longRest:15},stopwatch:{label:'Секундомер',work:0,rest:5,longRest:15}};
export function newTimer(method:FocusMethod='pomodoro',id='new'):TimerState{const p=FOCUS_PRESETS[method];return {method,phase:'work',work:p.work*60,rest:p.rest*60,longRest:p.longRest*60,round:0,elapsed:0,runningAt:null,label:'',clientId:id,ready:false}}
export function targetSeconds(s:TimerState){return s.phase==='work'?s.work:(s.round>0&&s.round%4===0?s.longRest:s.rest)}
export function spentSeconds(s:TimerState,now:number){const spent=s.elapsed+(s.runningAt!==null?Math.max(0,(now-s.runningAt)/1000):0);const target=targetSeconds(s);return Math.floor(Math.min(target||14400,Math.max(0,spent)))}
export function displaySeconds(s:TimerState,now:number){const target=targetSeconds(s);return target?Math.max(0,target-spentSeconds(s,now)):spentSeconds(s,now)}
export function pauseTimer(s:TimerState,now:number):TimerState{return {...s,elapsed:spentSeconds(s,now),runningAt:null}}
export function startTimer(s:TimerState,now:number):TimerState{return s.runningAt===null&&!s.ready?{...s,runningAt:now}:s}
export function afterSaved(s:TimerState,id:string):TimerState{return {...s,phase:s.method==='stopwatch'?'work':'break',round:s.round+1,elapsed:0,runningAt:null,ready:false,clientId:id}}
export function afterBreak(s:TimerState,id:string):TimerState{return {...s,phase:'work',elapsed:0,runningAt:null,ready:false,clientId:id}}
export function validTimer(value:unknown):value is TimerState{if(!value||typeof value!=='object')return false;const s=value as TimerState;return Object.hasOwn(FOCUS_PRESETS,s.method)&&['work','break'].includes(s.phase)&&typeof s.clientId==='string'&&typeof s.label==='string'&&s.label.length<=240&&[s.work,s.rest,s.longRest,s.round,s.elapsed].every(x=>Number.isFinite(x)&&x>=0)&&s.work<=14400&&s.rest<=3600&&s.longRest<=3600&&s.elapsed<=14400&&(s.runningAt===null||Number.isFinite(s.runningAt))&&typeof s.ready==='boolean'}
export const timerClock=(n:number)=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;
