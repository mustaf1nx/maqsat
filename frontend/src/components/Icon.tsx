import type {CSSProperties} from 'react';
const paths:Record<string,string[]>={
 home:['M3 10 12 3l9 7v11h-6v-7H9v7H3Z'],tasks:['m3 6 2 2 3-4','M11 6h10','m3 13 2 2 3-4','M11 13h10','M11 20h10'],
 calendar:['M5 5h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z','M7 2v6M17 2v6M3 11h18'],
 idea:['M9 18h6M9 22h6','M8 14a7 7 0 1 1 8 0l-1 4H9Z'],focus:['M12 8v5l3 2','M9 2h6M12 2v3','M20 14a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z'],
 work:['M4 7h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z','M8 7V3h8v4M2 12c6 4 14 4 20 0M12 12v4'],
 money:['M3 6h17v15H3Z','M3 6V3h14v3M15 12h6v5h-6Z'],goal:['M22 12a10 10 0 1 1-10-10','M17 12a5 5 0 1 1-5-5','m12 12 9-9M16 3h5v5'],
 health:['M2 9v6M5 6v12M19 6v12M22 9v6M5 12h14'],habit:['M4 7h13l-4-4M20 17H7l4 4','M4 7a9 9 0 0 0-1 9M20 17a9 9 0 0 0 1-9'],
 chart:['M3 3v18h18M7 16v-5M12 16V7M17 16V4'],settings:['M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z','m12 2 3 2 4 1 1 4 2 3-2 3-1 4-4 1-3 2-3-2-4-1-1-4-2-3 2-3 1-4 4-1Z'],
 plus:['M12 5v14M5 12h14'],search:['M20 20l-5-5','M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z'],close:['m6 6 12 12M18 6 6 18'],check:['m5 12 4 4L19 6'],
 arrow:['M4 12h16m-6-6 6 6-6 6'],left:['m15 6-6 6 6 6'],right:['m9 6 6 6-6 6'],down:['m6 9 6 6 6-6'],trash:['M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7'],
 edit:['m4 16 12-12 4 4L8 20H4ZM14 6l4 4'],copy:['M8 8h13v13H8ZM3 16V3h13'],clock:['M12 7v5l4 2','M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z'],
 pin:['M12 22s8-8 8-14A8 8 0 0 0 4 8c0 6 8 14 8 14Z','M15 8a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'],bell:['M5 16V9a7 7 0 0 1 14 0v7l2 2H3ZM9 21h6'],
 moon:['M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10Z'],sun:['M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM12 1v3M12 20v3M1 12h3M20 12h3M4 4l2 2M18 18l2 2M4 20l2-2M18 6l2-2'],
 menu:['M3 6h18M3 12h18M3 18h18'],play:['m8 4 12 8-12 8Z'],pause:['M8 4v16M16 4v16'],reset:['M3 11a9 9 0 1 1 2 7M3 4v7h7'],
 template:['M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z'],logout:['M9 3H3v18h6M9 12h12m-5-5 5 5-5 5'],
 shield:['m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Z','m8 11 3 3 5-6'],error:['M12 3 2 21h20ZM12 9v5M12 17v1'],archive:['M3 3h18v5H3ZM5 8v13h14V8M10 12h4'],bolt:['m13 2-9 12h7l-1 8 10-13h-7Z'],
};
export function Icon({name,size=20,className='',style}:{name:string;size?:number;className?:string;style?:CSSProperties}){
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className} style={style}>{(paths[name]||paths.tasks).map((d,i)=><path key={i} d={d}/>)}</svg>
}
