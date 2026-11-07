import {useEffect,useRef,useState,useId,isValidElement,cloneElement} from 'react';
import type {ReactNode,ReactElement,ButtonHTMLAttributes,FormEvent} from 'react';
import {Icon} from './Icon';
export function Button({children,variant='primary',icon,...rest}:ButtonHTMLAttributes<HTMLButtonElement>&{variant?:'primary'|'quiet'|'ghost'|'danger';icon?:string}){
 return <button type="button" {...rest} className={`btn ${variant} ${rest.className||''}`}>{icon&&<Icon name={icon} size={17}/>} {children}</button>
}
export function IconButton({icon,label,...rest}:ButtonHTMLAttributes<HTMLButtonElement>&{icon:string;label:string}){return <button type="button" {...rest} aria-label={label} title={label} className={`icon-btn ${rest.className||''}`}><Icon name={icon} size={18}/></button>}
export function Head({title,subtitle,kicker,children}:{title:string;subtitle?:string;kicker?:string;children?:ReactNode}){return <div className="page-head"><div>{kicker&&<div className="eyebrow">{kicker}</div>}<h1>{title}</h1>{subtitle&&<p>{subtitle}</p>}</div><div className="head-actions">{children}</div></div>}
export function Card({title,action,children,className=''}:{title?:string;action?:ReactNode;children:ReactNode;className?:string}){return <section className={`card ${className}`}>{title&&<header className="card-head"><h2>{title}</h2>{action}</header>}{children}</section>}
export function Empty({title,text,children,icon='plus'}:{title:string;text:string;children?:ReactNode;icon?:string}){return <div className="empty"><span className="empty-symbol"><Icon name={icon} size={26}/></span><h3>{title}</h3><p>{text}</p>{children}</div>}
export function Progress({value,label}:{value:number;label?:string}){return <div className="progress" role="progressbar" aria-label={label||'Прогресс'} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}><span style={{width:`${Math.max(0,Math.min(100,value))}%`}}/></div>}
export function DataState({loading,error,retry}:{loading:boolean;error:string;retry:()=>void}){if(error)return <div className="error-panel" role="alert"><Icon name="error"/><span>{error}</span><Button onClick={retry} variant="quiet">Повторить</Button></div>;return loading?<div className="loading-line" role="status">Обновляем данные…</div>:null}
export function Modal({title,children,onClose,wide=false,busy=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean;busy?:boolean}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const d=ref.current;d?.showModal();return()=>{d?.close()}},[]);
 const close=()=>{if(!busy&&!ref.current?.querySelector('form[aria-busy="true"]'))onClose()};
 return <dialog ref={ref} className={`dialog ${wide?'wide':''}`} onCancel={e=>{e.preventDefault();close()}} onClick={e=>{if(e.target===e.currentTarget&&!busy){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close()}}} aria-label={title}><div className="dialog-title"><h2>{title}</h2><IconButton label="Закрыть" icon="close" onClick={close} disabled={busy}/></div>{children}</dialog>
}
export function Form({children,onSubmit,onClose,extra,submitLabel='Сохранить'}:{children:ReactNode;onSubmit:()=>Promise<void>;onClose:()=>void;extra?:ReactNode;submitLabel?:string}){
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 async function submit(e:FormEvent){e.preventDefault();if(busy)return;setBusy(true);setError('');try{await onSubmit();onClose()}catch(err){setError((err as Error).message)}finally{setBusy(false)}}
 return <form className="editor-form" onSubmit={submit} aria-busy={busy}><fieldset disabled={busy}>{children}</fieldset>{error&&<div className="error-panel" role="alert">{error}</div>}<footer className="form-actions"><div>{extra}</div><div><Button variant="ghost" onClick={onClose} disabled={busy}>Отмена</Button><Button type="submit" disabled={busy}>{busy?'Сохраняем…':submitLabel}</Button></div></footer></form>
}
export function Field({label,hint,children,className=''}:{label:string;hint?:string;children:ReactNode;className?:string}){
 const id=useId();
 const control=isValidElement(children)?cloneElement(children as ReactElement<{'aria-labelledby'?:string;'aria-describedby'?:string}>,{'aria-labelledby':id,'aria-describedby':hint?id+'-hint':undefined}):children;
 return <label className={`field ${className}`}><span id={id}>{label}</span>{control}{hint&&<small id={id+'-hint'}>{hint}</small>}</label>;
}
export function DeleteButton({onDelete,label='Удалить запись?',text='Это действие нельзя отменить.'}:{onDelete:()=>Promise<unknown>;label?:string;text?:string}){
 const [confirm,setConfirm]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 return <><IconButton label="Удалить" icon="trash" onClick={()=>setConfirm(true)}/>{confirm&&<Modal title={label} onClose={()=>setConfirm(false)} busy={busy}><p className="dialog-copy">{text}</p>{error&&<div className="error-panel">{error}</div>}<div className="form-actions"><Button variant="quiet" onClick={()=>setConfirm(false)} disabled={busy}>Оставить</Button><Button variant="danger" disabled={busy} onClick={async()=>{setBusy(true);try{await onDelete();setConfirm(false)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Удалить</Button></div></Modal>}</>
}
export function Pill({children,color='neutral'}:{children:ReactNode;color?:string}){return <span className={`pill ${color}`}>{children}</span>}
export function WeekPicker({days,onChange}:{days:number[];onChange:(v:number[])=>void}){return <div className="week-picker" role="group" aria-label="Дни недели">{['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map((label,i)=><button type="button" key={label} aria-pressed={days.includes(i)} className={days.includes(i)?'selected':''} onClick={()=>onChange(days.includes(i)?days.filter(x=>x!==i):[...days,i].sort())}>{label}</button>)}</div>}
