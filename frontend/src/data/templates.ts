import type {Kind,Template} from '../lib/types';
import {today,atMinute} from '../lib/dates';
export const KIND_LABEL:Record<Kind,string>={task:'Задача',event:'Событие',idea:'Идея',goal:'Цель',transaction:'Операция',recurring:'Регулярный платёж',project:'Проект',work:'Рабочее время',workout:'Тренировка',workoutTemplate:'Шаблон тренировки',habit:'Привычка'};
export const ENDPOINT:Record<Kind,string>={task:'/tasks',event:'/events',idea:'/ideas',goal:'/goals',transaction:'/transactions',recurring:'/recurring',project:'/projects',work:'/work-entries',workout:'/workouts',workoutTemplate:'/workout-templates',habit:'/habits'};
export function builtins(zone:string):Template[]{
 const day=today(zone);
 return [
  {id:'weekly-review',kind:'task',title:'Недельный обзор',description:'Итоги, незавершённые дела и три приоритета.',data:{title:'Подвести итоги недели',area:'Личное',duration_minutes:30,checklist:['Посмотреть выполненные дела','Разобрать незавершённые задачи','Выбрать три приоритета'].map((title,i)=>({id:`review-${i}`,title,completed:false}))}},
  {id:'lesson',kind:'task',title:'Подготовка к занятию',description:'Материал, практика и проверка понимания.',data:{title:'Подготовить занятие',area:'Работа',duration_minutes:45,checklist:['Определить цель занятия','Подготовить примеры и задания','Добавить вопросы для проверки'].map((title,i)=>({id:`lesson-${i}`,title,completed:false}))}},
  {id:'idea-project',kind:'idea',title:'Новая идея проекта',description:'Проблема, решение и первый небольшой шаг.',data:{title:'Идея проекта',note:'Проблема:\n\nКому поможет:\n\nКак проверить идею:\n\nПервый шаг:'}},
  {id:'meeting',kind:'event',title:'Встреча',description:'Один час, место встречи и напоминание.',data:{title:'Встреча',starts_at:atMinute(day,18*60,zone),ends_at:atMinute(day,19*60,zone),category:'Работа',location:'',note:'Повестка:\n\nОжидаемый результат:',reminder_minutes:15}},
  {id:'classes',kind:'event',title:'Занятия по дням недели',description:'Понедельник, среда, пятница. Время можно изменить.',data:{title:'Занятие',starts_at:atMinute(day,16*60,zone),ends_at:atMinute(day,17*60,zone),category:'Учёба',recurrence:{frequency:'weekly',interval:1,weekdays:[0,2,4],until:null},reminder_minutes:15}},
  {id:'gym',kind:'event',title:'Зал в расписании',description:'Сразу появится в разделе тренировок.',data:{title:'Зал',starts_at:atMinute(day,18*60,zone),ends_at:atMinute(day,19*60,zone),category:'Тренировка',reminder_minutes:30}},
  {id:'goal-project',kind:'goal',title:'Завершить проект',description:'Прогресс рассчитывается по связанным задачам.',data:{title:'Завершить свой проект',detail:'Результат:\n\nКритерии готовности:',mode:'tasks',progress:0}},
  {id:'expense',kind:'transaction',title:'Повседневный расход',description:'Название, категория, сумма и дата.',data:{title:'Покупка',kind:'expense',category:'Покупки',amount:''}},
  {id:'income',kind:'transaction',title:'Доход от работы',description:'Только фактически полученные деньги.',data:{title:'Оплата работы',kind:'income',category:'Работа',amount:''}},
  {id:'subscription',kind:'recurring',title:'Ежемесячный счёт',description:'Например, интернет или абонемент. Сумма — твоя.',data:{title:'Интернет',day_of_month:10,amount:'',active:true}},
  {id:'work-project',kind:'project',title:'Проект для клиента',description:'Ставка и учёт фактически отработанного времени.',data:{title:'Новый проект',client:'',hourly_rate:'0'}},
  {id:'read',kind:'habit',title:'Чтение',description:'Одна отметка в выбранные дни, без штрафов за пропуски.',data:{title:'Почитать',target:1,unit:'занятие',weekdays:[0,1,2,3,4,5,6],color:'blue'}},
  {id:'review',kind:'habit',title:'Итоги дня',description:'Короткая заметка о том, что получилось.',data:{title:'Записать итоги дня',target:1,unit:'запись',weekdays:[0,1,2,3,4],color:'violet'}},
  {id:'blank-workout',kind:'workout',title:'Свободная тренировка',description:'Пустая таблица упражнений. Подходы и повторы задаёшь сам.',data:{title:'Тренировка',minutes:60,note:'',exercises:[],status:'planned'}}
 ];
}
