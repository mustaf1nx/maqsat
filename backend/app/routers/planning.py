from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Task, Idea, Goal, Project
from ..schemas import TaskIn, TaskPatch, IdeaIn, IdeaPatch, GoalIn, GoalPatch
from ..common import owned, records, serialize, add, change, remove, merge_validated, utcnow
from ..security import current_user, csrf_protected

router=APIRouter(prefix='/api/v1')


def task_links(db,user,data):
    for key,cls in [('goal_id',Goal),('project_id',Project)]:
        if data.get(key): owned(db,cls,user,data[key])

@router.get('/tasks')
def tasks(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [serialize(x) for x in db.scalars(select(Task).where(Task.user_id==user.id).order_by(Task.completed,Task.created_at.desc())).all()]

@router.post('/tasks',status_code=201)
def task_add(payload: TaskIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    data=payload.model_dump();task_links(db,user,data)
    data['completed_at']=utcnow() if data['completed'] else None
    return add(db,Task,user,**data)

@router.patch('/tasks/{object_id}')
def task_patch(object_id: str,payload: TaskPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Task,user,object_id,lock=True)
    data=merge_validated(obj,payload,TaskIn);task_links(db,user,data)
    if data['completed']!=obj.completed: data['completed_at']=utcnow() if data['completed'] else None
    return change(db,obj,data)

@router.delete('/tasks/{object_id}')
def task_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Task,user,object_id)
    # Explicit cleanup as well as FK SET NULL: also works on older SQLite copies.
    db.execute(update(Idea).where(Idea.user_id==user.id,Idea.converted_task_id==object_id).values(converted_task_id=None))
    return remove(db,obj)

@router.get('/ideas')
def ideas(user: User=Depends(current_user),db: Session=Depends(get_db)):
    linked={x.id:x for x in records(db,Task,user)}
    rows=sorted(records(db,Idea,user),key=lambda x:x.created_at,reverse=True)
    return [{**serialize(x),'converted_task_id':x.converted_task_id if x.converted_task_id in linked else None,
             'task_completed':linked[x.converted_task_id].completed if x.converted_task_id in linked else False} for x in rows]

@router.post('/ideas',status_code=201)
def idea_add(payload: IdeaIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return add(db,Idea,user,**payload.model_dump())

@router.patch('/ideas/{object_id}')
def idea_patch(object_id: str,payload: IdeaPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Idea,user,object_id)
    return change(db,obj,merge_validated(obj,payload,IdeaIn))

@router.post('/ideas/{object_id}/to-task')
def idea_to_task(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    idea=owned(db,Idea,user,object_id,lock=True)
    if idea.converted_task_id:
        task=db.scalar(select(Task).where(Task.id==idea.converted_task_id,Task.user_id==user.id))
        if task:return serialize(task)
    task=Task(user_id=user.id,title=idea.title,note=idea.note)
    db.add(task);db.flush();idea.converted_task_id=task.id;db.commit()
    return serialize(task)

@router.delete('/ideas/{object_id}')
def idea_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return remove(db,owned(db,Idea,user,object_id))


def goal_data(db,user):
    tasks=records(db,Task,user)
    result=[]
    for goal in records(db,Goal,user):
        linked=[x for x in tasks if x.goal_id==goal.id]
        done=sum(x.completed for x in linked)
        progress=round(done/len(linked)*100) if linked else 0
        result.append({**serialize(goal),'progress':progress if goal.mode=='tasks' else goal.progress,
                       'linked_tasks':len(linked),'completed_tasks':done})
    return result

@router.get('/goals')
def goals(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return goal_data(db,user)

@router.post('/goals',status_code=201)
def goal_add(payload: GoalIn,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    return add(db,Goal,user,**payload.model_dump())

@router.patch('/goals/{object_id}')
def goal_patch(object_id: str,payload: GoalPatch,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Goal,user,object_id)
    return change(db,obj,merge_validated(obj,payload,GoalIn))

@router.delete('/goals/{object_id}')
def goal_delete(object_id: str,user: User=Depends(csrf_protected),db: Session=Depends(get_db)):
    obj=owned(db,Goal,user,object_id)
    db.execute(update(Task).where(Task.user_id==user.id,Task.goal_id==object_id).values(goal_id=None))
    return remove(db,obj)
