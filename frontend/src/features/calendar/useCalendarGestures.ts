import {useEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent,RefObject} from 'react';
import type {Block} from '../../lib/calendar';
import type {CalendarEvent} from '../../lib/types';
import {atMinute,dayKey,moveTimes,plusDays} from '../../lib/dates';
import {allDaySelection,clamp,clickSelection,dayDistance,selectionBetween,snap} from '../../lib/calendarSelection';
import type {CalendarPreferences,Selection} from '../../lib/calendarSelection';

type Surface='time'|'date';
type Gesture={kind:'create'|'move'|'resize-start'|'resize-end';pointerId:number;target:HTMLElement;surface:Surface;day:string;minute:number;x:number;y:number;lastX:number;lastY:number;scrollTop:number;moved:boolean;block?:Block;selection?:Selection;times?:{starts_at:string;ends_at:string}};
type Config={root:RefObject<HTMLDivElement|null>;scroll:RefObject<HTMLDivElement|null>;zone:string;prefs:CalendarPreferences;disabled:boolean;onDraft:(s:Selection)=>void;onCommit:(b:Block,t:{starts_at:string;ends_at:string})=>Promise<void>;onError:(s:string)=>void};
export function useCalendarGestures(config:Config){
 const cfg=useRef(config);cfg.current=config;
 const active=useRef<Gesture|null>(null),frame=useRef<number|null>(null),suppressUntil=useRef(0);
 const [preview,setPreview]=useState<Selection|null>(null),[drag,setDrag]=useState<{key:string;start:string;end:string}|null>(null),[isDragging,setIsDragging]=useState(false);
 function capture(e:ReactPointerEvent,g:Gesture){active.current=g;try{e.currentTarget.setPointerCapture(e.pointerId)}catch{/* Document listeners still complete the gesture. */}e.preventDefault();e.stopPropagation()}
 function beginCreate(e:ReactPointerEvent,day:string,surface:Surface='time'){
  if(e.button!==0||!e.isPrimary||e.pointerType==='touch'||cfg.current.disabled)return;
  if((e.target as Element).closest('[data-calendar-event],button,input,select,a'))return;
  const rect=e.currentTarget.getBoundingClientRect();const minute=clamp((e.clientY-rect.top)/cfg.current.prefs.hourHeight*60,0,1439);
  const g:Gesture={kind:'create',pointerId:e.pointerId,target:e.currentTarget as HTMLElement,surface,day,minute,x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,scrollTop:cfg.current.scroll.current?.scrollTop||0,moved:false};
  try{const selection=surface==='date'?allDaySelection(day,day,cfg.current.zone):clickSelection(day,minute,cfg.current.zone,cfg.current.prefs.step,cfg.current.prefs.step);capture(e,g);setPreview(selection)}catch(error){cfg.current.onError((error as Error).message)}
 }
 function beginBlock(e:ReactPointerEvent,block:Block,day:string,kind:Gesture['kind']='move',surface:Surface='time'){
  if(e.button!==0||!e.isPrimary||e.pointerType==='touch'||cfg.current.disabled)return;
  const g:Gesture={kind,pointerId:e.pointerId,target:e.currentTarget as HTMLElement,surface,day,minute:0,x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,scrollTop:cfg.current.scroll.current?.scrollTop||0,moved:false,block};
  capture(e,g);
 }
 useEffect(()=>{
  function stopFrame(){if(frame.current!==null){cancelAnimationFrame(frame.current);frame.current=null}}
  function release(g:Gesture){try{if(g.target.hasPointerCapture(g.pointerId))g.target.releasePointerCapture(g.pointerId)}catch{/* Detached DOM node. */}}
  function reset(){const g=active.current;active.current=null;stopFrame();if(g)release(g);setPreview(null);setDrag(null);setIsDragging(false);document.body.classList.remove('calendar-gesturing')}
  function cancel(){if(active.current){suppressUntil.current=Date.now()+250;reset()}}
  function timeCell(x:number){const cells=cfg.current.root.current?.querySelectorAll<HTMLElement>('[data-time-day]');if(!cells?.length)return null;let result=cells[0],distance=Infinity;for(const cell of cells){const r=cell.getBoundingClientRect();const d=x<r.left?r.left-x:x>r.right?x-r.right:0;if(d<distance){distance=d;result=cell}}return result}
  function dateCell(x:number,y:number){return document.elementsFromPoint(x,y).map(el=>el.closest<HTMLElement>('[data-select-day]')).find(el=>el&&cfg.current.root.current?.contains(el))||null}
  function update(g:Gesture){
   const c=cfg.current;let day=g.day,minute=g.minute;
   if(g.surface==='time'){
    const cell=timeCell(g.lastX);if(!cell)return;day=cell.dataset.timeDay!;
    minute=clamp((g.lastY-cell.getBoundingClientRect().top)/c.prefs.hourHeight*60,0,1440);
   }else{
    const cell=dateCell(g.lastX,g.lastY);if(cell)day=cell.dataset.selectDay!;
   }
   try{
    if(g.kind==='create'){
     g.selection=g.surface==='date'?allDaySelection(g.day,day,c.zone):selectionBetween(g.day,g.minute,day,minute,c.zone,c.prefs.step);
     setPreview(g.selection);return;
    }
    const block=g.block!;const dayDelta=dayDistance(g.day,day);
    const minutes=g.surface==='time'?snap((g.lastY-g.y+(c.scroll.current?.scrollTop||0)-g.scrollTop)/c.prefs.hourHeight*60,c.prefs.step):0;
    if(g.kind==='move'){
     if(block.allDay){const ev=block.original as CalendarEvent,z=ev.timezone||c.zone;g.times={starts_at:atMinute(plusDays(block.startDate||dayKey(block.start,z),dayDelta),0,z),ends_at:atMinute(plusDays(block.endDate||dayKey(block.end,z),dayDelta),0,z)}}
     else g.times=moveTimes(block.start,block.end,dayDelta,minutes,c.zone);
    }else{
     const start=Date.parse(block.start),end=Date.parse(block.end),delta=minutes*60000;
     if(g.kind==='resize-start')g.times={starts_at:new Date(clamp(start+delta,end-7*86400000,end-c.prefs.step*60000)).toISOString(),ends_at:block.end};
     else g.times={starts_at:block.start,ends_at:new Date(clamp(end+delta,start+c.prefs.step*60000,start+7*86400000)).toISOString()};
    }
    setDrag({key:block.key,start:g.times.starts_at,end:g.times.ends_at});
   }catch{/* Pointer may pass through a nonexistent DST hour; retain last valid draft. */}
  }
  function tick(){
   frame.current=null;const g=active.current;if(!g||!g.moved||g.surface!=='time')return;
   const sc=cfg.current.scroll.current;
   if(sc){const r=sc.getBoundingClientRect();let speed=0;if(g.lastY<r.top+42)speed=-clamp((r.top+42-g.lastY)/2,0,20);else if(g.lastY>r.bottom-42)speed=clamp((g.lastY-r.bottom+42)/2,0,20);if(speed){const old=sc.scrollTop;sc.scrollTop+=speed;if(sc.scrollTop!==old)update(g)}}
   frame.current=requestAnimationFrame(tick);
  }
  function move(e:PointerEvent){const g=active.current;if(!g||e.pointerId!==g.pointerId)return;g.lastX=e.clientX;g.lastY=e.clientY;
   if(!g.moved&&Math.hypot(e.clientX-g.x,e.clientY-g.y)<5)return;
   if(!g.moved){g.moved=true;setIsDragging(true);document.body.classList.add('calendar-gesturing');frame.current=requestAnimationFrame(tick)}
   e.preventDefault();update(g);
  }
  function up(e:PointerEvent){const g=active.current;if(!g||e.pointerId!==g.pointerId)return;
   if(g.moved){g.lastX=e.clientX;g.lastY=e.clientY;update(g)}
   const selection=g.selection,times=g.times;const c=cfg.current;
   // A browser-generated click after pointerup must not create a second event.
   if(g.kind==='create'||g.moved)suppressUntil.current=Date.now()+250;
   reset();
   if(g.kind==='create'){
    try{c.onDraft(g.moved&&selection?selection:g.surface==='date'?allDaySelection(g.day,g.day,c.zone):clickSelection(g.day,g.minute,c.zone,c.prefs.duration,c.prefs.step))}catch(error){c.onError((error as Error).message)}
   }else if(g.moved&&times&&g.block&&(Date.parse(times.starts_at)!==Date.parse(g.block.start)||Date.parse(times.ends_at)!==Date.parse(g.block.end))){
    void c.onCommit(g.block,times).catch(error=>c.onError((error as Error).message));
   }
  }
  function key(e:KeyboardEvent){if(e.key==='Escape'&&active.current){e.preventDefault();e.stopPropagation();cancel()}}
  function lost(e:PointerEvent){if(active.current?.pointerId===e.pointerId)cancel()}
  document.addEventListener('pointermove',move,{passive:false});document.addEventListener('pointerup',up);document.addEventListener('pointercancel',cancel);document.addEventListener('lostpointercapture',lost);window.addEventListener('blur',cancel);window.addEventListener('keydown',key,true);
  return()=>{stopFrame();const g=active.current;active.current=null;if(g)release(g);document.body.classList.remove('calendar-gesturing');document.removeEventListener('pointermove',move);document.removeEventListener('pointerup',up);document.removeEventListener('pointercancel',cancel);document.removeEventListener('lostpointercapture',lost);window.removeEventListener('blur',cancel);window.removeEventListener('keydown',key,true)};
 },[]);
 return {beginCreate,beginBlock,preview,drag,isDragging,suppressClick:()=>Date.now()<suppressUntil.current};
}
