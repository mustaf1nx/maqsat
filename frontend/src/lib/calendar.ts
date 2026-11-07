import {minutesOf,dayKey,plusDays} from './dates';
export type Block={key:string;kind:'event'|'task';id:string;title:string;start:string;end:string;category:string;location:string;recurring:boolean;reminder:boolean;completed:boolean;original:object;allDay?:boolean;color?:string;calendarId?:string;availability?:'busy'|'free';startDate?:string;endDate?:string};
export type Segment={block:Block;day:string;start:number;end:number;lane:number;lanes:number;first:boolean;last:boolean};
export function segmentsForDay(blocks:Block[],day:string,zone:string):Segment[]{
 const next=plusDays(day,1);const result:Segment[]=[];
 for(const block of blocks){if(block.allDay)continue;const a=dayKey(block.start,zone),b=dayKey(block.end,zone);const endMinute=minutesOf(block.end,zone);
  if(a>day||b<day||(b===day&&endMinute===0))continue;
  result.push({block,day,start:a<day?0:minutesOf(block.start,zone),end:b>=next?1440:endMinute,lane:0,lanes:1,first:a===day,last:b===day||b===next&&endMinute===0});
 }
 result.sort((a,b)=>a.start-b.start||b.end-a.end);
 let group:Segment[]=[];let active:Segment[]=[];let maxLanes=0;
 function finish(){for(const item of group)item.lanes=maxLanes;group=[];maxLanes=0}
 for(const item of result){active=active.filter(x=>x.end>item.start);if(!active.length)finish();const used=new Set(active.map(x=>x.lane));let lane=0;while(used.has(lane))lane++;item.lane=lane;active.push(item);group.push(item);maxLanes=Math.max(maxLanes,lane+1)}finish();
 return result;
}
export const snapMinutes=(minutes:number)=>Math.round(minutes/15)*15;
