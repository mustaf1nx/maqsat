import {createContext,useContext,useState,useEffect,useCallback} from 'react';
import type {ReactNode} from 'react';
import type {Editor,Person,Page,Kind} from '../lib/types';
export type Api=<T=Record<string,unknown>>(path:string,method?:string,data?:unknown,signal?:AbortSignal)=>Promise<T>;
export type AppState={user:Person;api:Api;version:number;refresh:()=>void;notify:(text:string,error?:boolean,undo?:()=>Promise<void>)=>void;edit:(kind:Kind,value?:object,scope?:'single'|'series')=>void;close:()=>void;go:(page:Page)=>void;templates:(kind?:Kind)=>void;updateUser:(user:Person)=>void;};
export const Context=createContext<AppState|null>(null);
export function useApp(){const ctx=useContext(Context);if(!ctx)throw Error('App context required');return ctx}
export function useData<T>(path:string,initial:T){
 const {api,version}=useApp();const [data,setData]=useState<T>(initial);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [attempt,setAttempt]=useState(0);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');api<T>(path,'GET',undefined,controller.signal).then(setData).catch((e:Error)=>{if(e.name!=='AbortError')setError(e.message)}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});return()=>controller.abort()},[path,api,version,attempt]);
 return {data,setData,loading,error,retry:()=>setAttempt(x=>x+1)};
}
export function useMutation(){
 const {api,refresh,notify}=useApp();const [busy,setBusy]=useState(false);
 const run=useCallback(async(path:string,method:string,data?:unknown,message='Сохранено')=>{setBusy(true);try{const result=await api(path,method,data);refresh();if(message)notify(message);return result}catch(e){notify((e as Error).message,true);throw e}finally{setBusy(false)}},[api,refresh,notify]);
 return {run,busy};
}
export function handled(action:()=>Promise<unknown>){return ()=>{void action().catch(()=>{})}}
export type {ReactNode,Editor};
