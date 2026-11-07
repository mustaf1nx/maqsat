// Pure domain tests use the installed project TypeScript compiler, no browser or API.
const fs=require('node:fs');
const ts=require('typescript');
require.extensions['.ts']=(module,filename)=>module._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {test}=require('node:test');
const assert=require('node:assert/strict');
const d=require('../src/lib/dates.ts');
const f=require('../src/lib/focus.ts');
const c=require('../src/lib/calendar.ts');
const t=require('../src/data/templates.ts');
const Z='Asia/Almaty';
for(const [zone,local,iso] of [
 [Z,'2026-11-07T09:30','2026-11-07T04:30:00.000Z'],
 ['UTC','2026-11-07T00:00','2026-11-07T00:00:00.000Z'],
 ['America/New_York','2026-07-01T10:00','2026-07-01T14:00:00.000Z'],
 ['America/New_York','2026-12-01T10:00','2026-12-01T15:00:00.000Z'],
 ['Asia/Kathmandu','2026-11-07T10:00','2026-11-07T04:15:00.000Z'],
])test('wall-clock ↔ UTC '+zone+' '+local,()=>{assert.equal(d.toISO(local,zone),iso);assert.equal(d.localInput(iso,zone),local)});
for(const value of ['', 'tomorrow','2026-02-31T10:00','2026-11-07T25:00'])test('invalid date rejected: '+value,()=>assert.throws(()=>d.toISO(value,Z)));
test('nonexistent DST wall time rejected',()=>assert.throws(()=>d.toISO('2026-03-08T02:30','America/New_York')));
test('ambiguous DST time deterministic and round-trips',()=>{const v=d.toISO('2026-11-01T01:30','America/New_York');assert.equal(d.localInput(v,'America/New_York'),'2026-11-01T01:30');assert.equal(d.toISO('2026-11-01T01:30','America/New_York'),v)});
test('Monday/weekend/leap/year rollover',()=>{assert.equal(d.monday('2026-11-08'),'2026-11-02');assert.equal(d.plusDays('2024-02-28',1),'2024-02-29');assert.equal(d.plusDays('2026-12-31',1),'2027-01-01');assert.equal(d.weekday('2026-11-09'),0)});
test('negative and next-day calendar minute',()=>{assert.equal(d.localInput(d.atMinute('2026-11-07',-15,Z),Z),'2026-11-06T23:45');assert.equal(d.localInput(d.atMinute('2026-11-07',1470,Z),Z),'2026-11-08T00:30')});
test('move preserves duration over day and minute rollover',()=>{const v=d.moveTimes('2026-11-07T18:30:00Z','2026-11-07T20:00:00Z',1,60,Z);assert.equal(d.localInput(v.starts_at,Z),'2026-11-09T00:30');assert.equal(Date.parse(v.ends_at)-Date.parse(v.starts_at),5400000)});
test('move by day preserves local hour over DST',()=>{const v=d.moveTimes('2026-03-07T15:00:00Z','2026-03-07T16:00:00Z',1,0,'America/New_York');assert.equal(v.starts_at,'2026-03-08T14:00:00.000Z')});
test('completed tasks are not overdue',()=>assert.equal(d.isOverdue({completed:true,due_at:'2001-01-01T00:00:00Z'},Z),false));
test('Russian finance enum labels',()=>assert.deepEqual(d.MONEY_KIND,{expense:'Расход',income:'Доход'}));
test('currency formats decimal amount',()=>assert.ok(d.money('1234.50').includes('1\u00a0234,5')));
test('disabled or corrupt local storage is safe',()=>{global.localStorage={getItem(){throw Error('disabled')},setItem(){throw Error('disabled')}};assert.equal(d.safeRead('x',5),5);assert.doesNotThrow(()=>d.safeWrite('x',1));global.localStorage={getItem:()=>'{broken'};assert.equal(d.safeRead('x',5),5);delete global.localStorage});
const block=(id,start,end)=>({key:id,id,kind:'event',title:id,start,end,category:'Личное',location:'',recurring:false,reminder:false,completed:false,original:{}});
test('overlapping blocks get nonoverlapping lanes',()=>{const r=c.segmentsForDay([block('a','2026-11-07T05:00Z','2026-11-07T06:00Z'),block('b','2026-11-07T05:30Z','2026-11-07T07:00Z')],'2026-11-07',Z);assert.deepEqual(r.map(x=>[x.lane,x.lanes]),[[0,2],[1,2]])});
test('adjacent blocks share a full-width lane',()=>{const r=c.segmentsForDay([block('a','2026-11-07T05:00Z','2026-11-07T06:00Z'),block('b','2026-11-07T06:00Z','2026-11-07T07:00Z')],'2026-11-07',Z);assert.deepEqual(r.map(x=>[x.lane,x.lanes]),[[0,1],[0,1]])});
test('night event clips across two local days',()=>{const b=block('a','2026-11-07T18:30Z','2026-11-07T20:00Z');const a=c.segmentsForDay([b],'2026-11-07',Z)[0],n=c.segmentsForDay([b],'2026-11-08',Z)[0];assert.equal(a.start,1410);assert.equal(a.end,1440);assert.equal(a.last,false);assert.equal(n.start,0);assert.equal(n.end,60);assert.equal(n.first,false)});
test('event ending at midnight does not appear next day',()=>{const b=block('a','2026-11-07T18:00Z','2026-11-07T19:00Z');assert.equal(c.segmentsForDay([b],'2026-11-08',Z).length,0);assert.equal(c.segmentsForDay([b],'2026-11-07',Z)[0].last,true)});
for(const [n,expected] of [[7,0],[8,15],[22,15],[23,30],[-8,-15]])test('snap 15 min: '+n,()=>assert.equal(c.snapMinutes(n),expected));
for(const method of ['pomodoro','long','custom','stopwatch'])test('valid initial focus '+method,()=>{const s=f.newTimer(method,'abc');assert.equal(f.validTimer(s),true);assert.equal(s.runningAt,null);assert.equal(f.spentSeconds(s,10000),0)});
test('focus pause/resume uses timestamps',()=>{let s=f.startTimer(f.newTimer('pomodoro','id'),1000);assert.equal(f.displaySeconds(s,66000),1435);s=f.pauseTimer(s,66000);assert.equal(f.spentSeconds(s,999999),65);s=f.startTimer(s,100000);assert.equal(f.spentSeconds(s,110000),75)});
test('sleeping tab cannot overcount a work interval',()=>{const s=f.startTimer(f.newTimer('pomodoro','id'),0);assert.equal(f.spentSeconds(s,86400000),1500);assert.equal(f.displaySeconds(s,86400000),0)});
test('clock backwards never creates negative time',()=>{const s=f.startTimer(f.newTimer('stopwatch','id'),1000);assert.equal(f.spentSeconds(s,0),0)});
test('stopwatch is bounded to 4h',()=>{const s=f.startTimer(f.newTimer('stopwatch','id'),0);assert.equal(f.spentSeconds(s,99999999),14400)});
test('fourth completed round selects long break; never autostarts',()=>{let s={...f.newTimer('pomodoro','id'),round:3};s=f.afterSaved(s,'next');assert.equal(s.phase,'break');assert.equal(f.targetSeconds(s),900);assert.equal(s.runningAt,null);assert.equal(f.afterBreak(s,'new').phase,'work')});
for(const v of [null,{}, {method:'toString'}, {...f.newTimer(),elapsed:-1},{...f.newTimer(),runningAt:'wrong'},{...f.newTimer(),work:Infinity},{...f.newTimer(),label:'x'.repeat(241)}])test('corrupted timer rejected '+JSON.stringify(v),()=>assert.equal(f.validTimer(v),false));
test('timer JSON survives serialization',()=>{const s=f.startTimer(f.newTimer('long','unique'),1000);assert.equal(f.validTimer(JSON.parse(JSON.stringify(s))),true);assert.equal(f.timerClock(65),'01:05')});
test('all built-in templates are usable editor payloads',()=>{const items=t.builtins(Z);assert.equal(items.length,14);assert.equal(new Set(items.map(x=>x.id)).size,14);for(const item of items){assert.ok(t.ENDPOINT[item.kind]);assert.ok(item.data.title);assert.ok(!('id' in item.data));assert.ok(!item.description.includes('будут'))}});
test('templates do not share mutable exercise or checklist objects',()=>{const a=t.builtins(Z),b=t.builtins(Z);a[0].data.checklist[0].completed=true;assert.equal(b[0].data.checklist[0].completed,false)});
