import {createContext,useContext,useState,useEffect,useRef,useCallback} from 'react';
import type {ReactNode} from 'react';
import {useApp} from './context';
import {safeRead,safeWrite} from '../lib/dates';
import {newTimer,validTimer,targetSeconds,spentSeconds,displaySeconds,pauseTimer,startTimer,afterSaved,afterBreak} from '../lib/focus';
import type {TimerState,FocusMethod} from '../lib/focus';
type Value={timer:TimerState;seconds:number;spent:number;busy:boolean;error:string;toggle:()=>void;reset:()=>void;finish:()=>Promise<void>;skipBreak:()=>void;configure:(method:FocusMethod,work?:number,rest?:number)=>void;label:(value:string)=>void;};
const Context=createContext<Value|null>(null);
export function useFocus(){const v=useContext(Context);if(!v)throw Error('Focus context missing');return v}
export function FocusProvider({children}:{children:ReactNode}){
 const {user,api,refresh,notify}=useApp();const key=`maqsat:focus:v2:${user.id}`;
 const [timer,setTimer]=useState<TimerState>(()=>{const persisted=safeRead<unknown>(key,null);return validTimer(persisted)?persisted:newTimer('pomodoro',crypto.randomUUID())});
 const [now,setNow]=useState(Date.now());const [busy,setBusy]=useState(false);const [error,setError]=useState('');const attempted=useRef('');const saving=useRef(false);
 useEffect(()=>{const i=setInterval(()=>setNow(Date.now()),250);return()=>clearInterval(i)},[]);
 useEffect(()=>safeWrite(key,timer),[key,timer]);
 const finish=useCallback(async()=>{
  if(saving.current||timer.phase!=='work')return;
  const stopped=pauseTimer(timer,Date.now());const minutes=Math.floor(stopped.elapsed/60);
  if(minutes<1){notify('Для записи нужна хотя бы одна минута фокуса');return}
  saving.current=true;setBusy(true);setError('');setTimer({...stopped,ready:true});attempted.current=timer.clientId;
  try{await api('/focus','POST',{minutes:Math.min(240,minutes),method:timer.method,task_label:timer.label,client_id:timer.clientId});setTimer(afterSaved(stopped,crypto.randomUUID()));refresh();notify('Сеанс фокуса сохранён. Время для перерыва.')}catch(e){setError((e as Error).message);notify('Сеанс пока не сохранён. Его можно отправить повторно.',true)}finally{saving.current=false;setBusy(false)}
 },[timer,api,refresh,notify]);
 useEffect(()=>{
  if(timer.runningAt===null||timer.ready)return;
  const target=targetSeconds(timer);
  if(target&&spentSeconds(timer,now)>=target){
   if(timer.phase==='break'){setTimer(afterBreak(timer,crypto.randomUUID()));notify('Перерыв завершён. Следующий интервал можно начать, когда будете готовы.')}
   else setTimer({...pauseTimer(timer,now),ready:true});
  }
 },[now,timer,notify]);
 useEffect(()=>{if(timer.ready&&!busy&&timer.phase==='work'&&attempted.current!==timer.clientId)void finish()},[timer,busy,finish]);
 const reset=()=>{if(busy)return;setTimer({...newTimer(timer.method,crypto.randomUUID()),work:timer.work,rest:timer.rest,longRest:timer.longRest,label:timer.label});setError('')};
 const configure=(method:FocusMethod,work?:number,rest?:number)=>{if(busy)return;setTimer({...newTimer(method,crypto.randomUUID()),...(work?{work:work*60}:{}),...(rest?{rest:rest*60}:{}),label:timer.label});setError('')};
 return <Context.Provider value={{timer,seconds:displaySeconds(timer,now),spent:spentSeconds(timer,now),busy,error,finish,reset,configure,label:value=>setTimer(s=>({...s,label:value})),skipBreak:()=>setTimer(s=>afterBreak(s,crypto.randomUUID())),toggle:()=>{if(busy||timer.ready)return;setTimer(s=>s.runningAt===null?startTimer(s,Date.now()):pauseTimer(s,Date.now()))}}}>{children}</Context.Provider>
}
