import {useCallback,useEffect,useMemo,useState} from 'react';
import type {FormEvent} from 'react';
import type {Person,Page,Editor,Kind,Reminder} from './lib/types';
import {Context} from './app/context';
import type {Api} from './app/context';
import {FocusProvider} from './app/FocusContext';
import {Icon} from './components/Icon';
import {Button,IconButton,Field} from './components/ui';
import {TemplatePanel,QuickPanel,ReminderPanel} from './components/Panels';
import {EditorRouter} from './features/editors';
import {Tasks,Ideas,Goals} from './features/Planning';
import {Calendar} from './features/Calendar';
import {Finance,Work} from './features/FinanceWork';
import {Health,Habits} from './features/HealthHabits';
import {Focus,FocusMini} from './features/Focus';
import {Dashboard,Analytics} from './features/Dashboard';
import {Settings} from './features/Settings';
import {safeRead,safeWrite} from './lib/dates';
const NAV:{page:Page;label:string;icon:string;group:string}[]=[
 {page:'home',label:'Сегодня',icon:'home',group:'ОБЗОР'},
 {page:'calendar',label:'Расписание',icon:'calendar',group:'ПЛАНИРОВАНИЕ'},
 {page:'tasks',label:'Задачи',icon:'tasks',group:'ПЛАНИРОВАНИЕ'},
 {page:'ideas',label:'Корзина идей',icon:'idea',group:'ПЛАНИРОВАНИЕ'},
 {page:'focus',label:'Фокус',icon:'focus',group:'ПЛАНИРОВАНИЕ'},
 {page:'goals',label:'Цели',icon:'goal',group:'СФЕРЫ ЖИЗНИ'},
 {page:'work',label:'Работа',icon:'work',group:'СФЕРЫ ЖИЗНИ'},
 {page:'money',label:'Финансы',icon:'money',group:'СФЕРЫ ЖИЗНИ'},
 {page:'health',label:'Тренировки',icon:'health',group:'СФЕРЫ ЖИЗНИ'},
 {page:'habits',label:'Привычки',icon:'habit',group:'СФЕРЫ ЖИЗНИ'},
 {page:'analytics',label:'Аналитика',icon:'chart',group:'ОБЗОР РЕЗУЛЬТАТОВ'},
];
function readPage():Page{const p=window.location.hash.replace('#/','');return p==='settings'||NAV.some(x=>x.page===p)?p as Page:'home'}
type Toast={text:string;error:boolean;undo?:()=>Promise<void>};
function Login({onLogin}:{onLogin:(v:{user:Person;csrf:string})=>void}){
 const [login,setLogin]=useState('');const [password,setPassword]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 async function submit(e:FormEvent){e.preventDefault();if(busy)return;setBusy(true);setError('');try{const r=await fetch('/api/v1/auth/login',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:login,password})});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Не удалось войти');onLogin(data)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="login-page"><div className="login-story"><div className="brand"><span className="logo">M.</span><strong>MAQSAT<span className="brand-dot">.</span></strong></div><span className="eyebrow">ОТ МЫСЛИ К ДЕЙСТВИЮ</span><h1>Ваш день.<br/>Ваш ритм.<br/><span>Ваши цели.</span></h1><p>Планы, работа, деньги и маленькие победы.<br/>В одном месте, без лишнего шума.</p><div className="login-orbit"/></div><div className="login-form-wrap"><form className="login-card" onSubmit={submit}><div className="eyebrow">С ВОЗВРАЩЕНИЕМ</div><h2>Войти в MAQSAT</h2><p>Продолжим с того, на чём остановились.</p><Field label="Логин"><input autoFocus autoComplete="username" required minLength={3} maxLength={64} value={login} onChange={e=>setLogin(e.target.value)}/></Field><Field label="Пароль"><input autoComplete="current-password" type="password" required maxLength={256} value={password} onChange={e=>setPassword(e.target.value)}/></Field>{error&&<div className="error-panel" role="alert">{error}</div>}<Button type="submit" disabled={busy}>{busy?'Входим…':'Войти'}<Icon name="arrow" size={17}/></Button><p className="hint">Аккаунт создаёт администратор. Личные записи доступны только владельцу.</p></form></div></div>
}
export default function App(){
 const [user,setUser]=useState<Person|null>(null);const [csrf,setCsrf]=useState('');const [boot,setBoot]=useState(true);const [bootError,setBootError]=useState('');const [page,setPage]=useState<Page>(readPage);const [editor,setEditor]=useState<Editor|null>(null);const [version,setVersion]=useState(0);const [toast,setToast]=useState<Toast|null>(null);const [mobile,setMobile]=useState(false);const [quick,setQuick]=useState(false);const [library,setLibrary]=useState<{kind?:Kind}|null>(null);const [showReminders,setShowReminders]=useState(false);const [reminders,setReminders]=useState<Reminder[]>([]);const [theme,setTheme]=useState<'dark'|'light'>(()=>safeRead<unknown>('maqsat:theme','dark')==='light'?'light':'dark');
 const notify=useCallback((text:string,error=false,undo?:()=>Promise<void>)=>setToast({text,error,undo}),[]);
 const refresh=useCallback(()=>setVersion(x=>x+1),[]);
 const close=useCallback(()=>setEditor(null),[]);
 const edit=useCallback((kind:Kind,value?:object,scope?:'single'|'following'|'series')=>{setQuick(false);setLibrary(null);setEditor({kind,value:value as Record<string,unknown>|undefined,scope})},[]);
 const go=useCallback((p:Page)=>{window.location.hash='/'+p;setPage(p);setMobile(false);window.scrollTo(0,0)},[]);
 const templates=useCallback((kind?:Kind)=>setLibrary({kind}),[]);
 useEffect(()=>{const fn=()=>setPage(readPage());window.addEventListener('hashchange',fn);return()=>window.removeEventListener('hashchange',fn)},[]);
 useEffect(()=>{document.documentElement.dataset.theme=theme;safeWrite('maqsat:theme',theme)},[theme]);
 useEffect(()=>{if(!toast)return;const timeout=setTimeout(()=>setToast(null),toast.undo?9000:5000);return()=>clearTimeout(timeout)},[toast]);
 useEffect(()=>{const onKey=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(user&&!editor)setQuick(true)}};window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey)},[user,editor]);
 useEffect(()=>{fetch('/api/v1/auth/me',{credentials:'include'}).then(async r=>{if(r.status===401)return null;if(!r.ok)throw Error('Не удалось проверить сессию. Обновите страницу.');return r.json()}).then(data=>{if(data){setUser(data.user);setCsrf(data.csrf)}}).catch((e:Error)=>setBootError(e.message)).finally(()=>setBoot(false))},[]);
 const api=useCallback<Api>(async<T,>(path:string,method='GET',data?:unknown,signal?:AbortSignal):Promise<T>=>{
  let res:Response;try{res=await fetch('/api/v1'+path,{method,credentials:'include',signal,headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-CSRF-Token':csrf}:{})},...(data!==undefined?{body:JSON.stringify(data)}:{})})}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('Нет связи с сервером. Данные не сохранены, повторите действие.')}
  const value=await res.json().catch(()=>({detail:'Сервер вернул неожиданный ответ'}));
  if(res.status===401){setUser(null);setCsrf('');setEditor(null);setQuick(false);setLibrary(null);throw Error('Сессия завершена. Войдите снова.')}
  if(!res.ok)throw Error(typeof value.detail==='string'?value.detail:'Проверьте заполнение полей');return value as T;
 },[csrf]);
 useEffect(()=>{
  if(!user)return;let active=true;const key=`maqsat:reminders:${user.id}`;const stored=safeRead<unknown>(key,[]);const seen=new Set<string>(Array.isArray(stored)?stored.filter((x):x is string=>typeof x==='string'):[]);
  async function poll(){try{const rows=await api<Reminder[]>('/reminders');if(!active)return;setReminders(rows);for(const r of rows){if(r.is_due&&!seen.has(r.id)){seen.add(r.id);notify(`Напоминание: ${r.title}`);if('Notification'in window&&Notification.permission==='granted'){try{new Notification('MAQSAT · Напоминание',{body:r.title,tag:r.id})}catch{/* In-app reminder remains visible on unsupported mobile browsers. */}}}}safeWrite(key,[...seen].slice(-200))}catch{/* API failure is surfaced by the active page. Never show false reminders. */}}
  void poll();const id=setInterval(()=>void poll(),30000);return()=>{active=false;clearInterval(id)};
 },[user?.id,api,version,notify]);
 async function logout(){await api('/auth/logout','POST');setUser(null);setCsrf('');setEditor(null);setReminders([]);setToast(null)}
 const context=useMemo(()=>user?{user,api,version,refresh,notify,edit,close,go,templates,updateUser:setUser}:null,[user,api,version,refresh,notify,edit,close,go,templates]);
 if(boot)return <div className="boot-screen"><span className="logo">M.</span><p>Открываем MAQSAT…</p></div>;
 if(bootError)return <div className="boot-screen"><p>{bootError}</p><Button onClick={()=>location.reload()}>Повторить</Button></div>;
 if(!user||!context)return <Login onLogin={data=>{setUser(data.user);setCsrf(data.csrf);refresh()}}/>;
 const label=page==='settings'?'Настройки':NAV.find(x=>x.page===page)?.label||'Сегодня';
 return <Context.Provider value={context}><FocusProvider key={user.id}><div className="app-shell"><aside className={`sidebar ${mobile?'open':''}`}><button className="brand brand-button" onClick={()=>go('home')}><span className="logo">M.</span><strong>MAQSAT<span className="brand-dot">.</span></strong></button><button className="sidebar-quick" onClick={()=>setQuick(true)}><Icon name="plus" size={17}/><span>Быстро добавить</span><kbd>⌘ K</kbd></button><nav aria-label="Основное меню">{NAV.map((item,i)=><div key={item.page}>{(i===0||NAV[i-1].group!==item.group)&&<div className="nav-group-label">{item.group}</div>}<button className={`nav-item ${page===item.page?'active':''}`} aria-current={page===item.page?'page':undefined} onClick={()=>go(item.page)}><Icon name={item.icon} size={19}/><span>{item.label}</span>{page===item.page&&<span className="active-mark"/>}</button></div>)}</nav><div className="sidebar-bottom"><FocusMini/><button className={`nav-item ${page==='settings'?'active':''}`} onClick={()=>go('settings')}><Icon name="settings" size={19}/><span>Настройки</span></button><button className="profile-button" onClick={()=>go('settings')}><span className="avatar">{user.display_name.slice(0,2).toUpperCase()}</span><span><strong>{user.display_name}</strong><small>@{user.username}</small></span><Icon name="right" size={16}/></button></div></aside>{mobile&&<button className="sidebar-overlay" aria-label="Закрыть меню" onClick={()=>setMobile(false)}/>}<main className="main"><header className="topbar"><div className="topbar-title"><IconButton className="mobile-only" icon="menu" label="Открыть меню" onClick={()=>setMobile(true)}/><span>{label}</span></div><div className="topbar-actions"><button className="global-search" onClick={()=>setQuick(true)}><Icon name="search" size={17}/><span>Найти или добавить…</span><kbd>Ctrl K</kbd></button><IconButton icon={theme==='dark'?'sun':'moon'} label="Сменить тему" onClick={()=>setTheme(theme==='dark'?'light':'dark')}/><button className="icon-btn notification-button" aria-label="Напоминания" title="Напоминания" onClick={()=>setShowReminders(true)}><Icon name="bell" size={19}/>{reminders.some(r=>r.is_due)&&<span/>}</button><span className="topbar-divider"/><span className="avatar small">{user.display_name.slice(0,1).toUpperCase()}</span></div></header><div className="page-content">{page==='home'?<Dashboard/>:page==='tasks'?<Tasks/>:page==='calendar'?<Calendar/>:page==='ideas'?<Ideas/>:page==='focus'?<Focus/>:page==='goals'?<Goals/>:page==='work'?<Work/>:page==='money'?<Finance/>:page==='health'?<Health/>:page==='habits'?<Habits/>:page==='analytics'?<Analytics/>:<Settings logout={logout}/>}<footer className="page-footer"><span>MAQSAT · В своём ритме</span><span>Записи сохраняются в вашем аккаунте</span></footer></div></main><nav className="mobile-bottom" aria-label="Мобильная навигация">{NAV.filter(x=>['home','calendar','tasks','focus'].includes(x.page)).map(x=><button key={x.page} className={page===x.page?'active':''} onClick={()=>go(x.page)}><Icon name={x.icon} size={20}/><span>{x.label}</span></button>)}<button onClick={()=>setMobile(true)}><Icon name="menu" size={20}/><span>Ещё</span></button></nav></div>{editor&&<EditorRouter key={editor.kind+String(editor.value?.id||'new')+(editor.scope||'single')} editor={editor}/>} {library&&<TemplatePanel initial={library.kind} onClose={()=>setLibrary(null)}/>} {quick&&<QuickPanel onClose={()=>setQuick(false)}/>} {showReminders&&<ReminderPanel items={reminders} onClose={()=>setShowReminders(false)}/>} {toast&&<div role="status" className={`toast ${toast.error?'error':''}`}><Icon name={toast.error?'error':'check'} size={18}/><span>{toast.text}</span>{toast.undo&&<button onClick={async()=>{const action=toast.undo;setToast(null);try{await action?.();notify('Изменение отменено')}catch(e){notify((e as Error).message,true)}}}>Отменить</button>}<IconButton icon="close" label="Скрыть уведомление" onClick={()=>setToast(null)}/></div>}</FocusProvider></Context.Provider>
}
