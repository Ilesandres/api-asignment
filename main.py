from fastapi import FastAPI, HTTPException, status
from typing import List, Dict

from models import Task, TaskStatus, UserProfile

app = FastAPI(
    title="FastAPI Front (in-memory)",
    description="CRUD mínimo en memoria para Task y UserProfile (basado en frontend types).",
    version="0.1.0",
)

# Almacenamiento en memoria (temporal)
tasks: Dict[str, Task] = {}
users: Dict[str, UserProfile] = {}


@app.get("/", tags=["Root"])
async def root():
    return {"message": "FastAPI front (in-memory) ready"}


"""TASKS CRUD"""


@app.get("/tasks/", response_model=List[Task], tags=["Tasks"])
async def list_tasks():
    return list(tasks.values())


@app.post("/tasks/", response_model=Task, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(task: Task):
    if task.id in tasks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task ID already exists")
    tasks[task.id] = task
    return task


@app.get("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def get_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return t


@app.put("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def update_task(task_id: str, updated: Task):
    if task_id != updated.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID mismatch")
    if task_id not in tasks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    tasks[task_id] = updated
    return updated


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
async def delete_task(task_id: str):
    if task_id in tasks:
        del tasks[task_id]
    return


"""USERS CRUD"""


@app.get("/users/", response_model=List[UserProfile], tags=["Users"])
async def list_users():
    return list(users.values())


@app.post("/users/", response_model=UserProfile, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(user: UserProfile):
    if user.uid in users:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
    users[user.uid] = user
    return user


@app.get("/users/{uid}", response_model=UserProfile, tags=["Users"])
async def get_user(uid: str):
    u = users.get(uid)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return u


@app.put("/users/{uid}", response_model=UserProfile, tags=["Users"])
async def update_user(uid: str, updated: UserProfile):
    if uid != updated.uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UID mismatch")
    if uid not in users:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    users[uid] = updated
    return updated

