# services/task_service.py

from typing import List, Dict, Optional
from fastapi import HTTPException, status
from firebase_admin import firestore, exceptions as fb_exceptions

# Importaciones de modelos
from models.task import Task, TaskStatus

# Constante de colección (debe ser el valor por defecto si no se pasa)
COLLECTION_TASKS = "tasks"

# --- Funciones de Asistencia ---

def _handle_firebase_error(e: fb_exceptions.FirebaseError):
    """Lanza una excepción HTTP 500 para errores internos de Firestore."""
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error de Firestore: {e}")

# --- Servicios CRUD e Interrogación ---

async def get_task_service(
    task_id: str,
    db: Optional[firestore.Client],
    in_memory_tasks: Dict[str, Task]
) -> Task:
    """Obtiene una tarea por ID. Lanza 404 si no existe."""
    
    if db is None:
        # Lógica In-Memory
        t = in_memory_tasks.get(task_id)
        if not t:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return t

    # Lógica Firestore
    try:
        doc = db.collection(COLLECTION_TASKS).document(task_id).get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        data = doc.to_dict()
        return Task(id=doc.id, **data)
    except fb_exceptions.FirebaseError as e:
        _handle_firebase_error(e)


async def list_tasks_service(
    db: Optional[firestore.Client],
    in_memory_tasks: Dict[str, Task],
    current_user_uid: Optional[str] = None,
    status_filter: Optional[TaskStatus] = None,
) -> List[Task]:
    """Lista tareas, opcionalmente filtrando por dueño y/o estado."""
    
    if db is None:
        # Lógica In-Memory (aplicando filtros)
        result = list(in_memory_tasks.values())
        if status_filter:
            result = [t for t in result if t.status == status_filter]
        if current_user_uid: # Filtra por dueño si se proporciona UID (Autenticación)
            result = [t for t in result if t.owner == current_user_uid]
        return result

    # Lógica Firestore (aplicando filtros)
    try:
        query = db.collection(COLLECTION_TASKS)
        if status_filter:
            query = query.where("status", "==", status_filter.value)
        if current_user_uid:
            query = query.where("owner", "==", current_user_uid)
            
        docs = query.stream()
        result: List[Task] = []
        for doc in docs:
            data = doc.to_dict()
            result.append(Task(id=doc.id, **data))
        return result
    except fb_exceptions.FirebaseError as e:
        _handle_firebase_error(e)


async def create_task_service(
    task: Task,
    db: Optional[firestore.Client],
    in_memory_tasks: Dict[str, Task],
    current_user_uid: str
) -> Task:
    """Crea una nueva tarea, asigna el propietario si no está definido."""

    # Pre-procesamiento: Asignar owner del usuario autenticado si no está seteado
    if not task.owner:
        task.owner = current_user_uid

    if db is None:
        # Lógica In-Memory
        if task.id in in_memory_tasks:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task ID already exists")
        in_memory_tasks[task.id] = task
        return task

    # Lógica Firestore
    try:
        payload = task.model_dump(exclude_none=True)
        # Quitar el ID para que Firestore lo genere
        if 'id' in payload:
             del payload['id'] 
        
        _, doc_ref = db.collection(COLLECTION_TASKS).add(payload)
        return Task(id=doc_ref.id, **payload)
    except fb_exceptions.FirebaseError as e:
        _handle_firebase_error(e)


async def update_task_service(
    task_id: str,
    updated_task: Task,
    db: Optional[firestore.Client],
    in_memory_tasks: Dict[str, Task],
    current_user_uid: str
) -> Task:
    """Actualiza una tarea (PUT). Lanza 403 si el usuario no es el dueño."""

    if task_id != updated_task.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID mismatch")
    
    # 1. Autorización: Obtenemos la tarea existente para chequear el dueño
    existing_task = await get_task_service(task_id, db, in_memory_tasks)
    
    # 2. Chequeo de Dueño
    if existing_task.owner and existing_task.owner != current_user_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar esta tarea."
        )

    # 3. Lógica de actualización (PUT)
    if db is None:
        in_memory_tasks[task_id] = updated_task
        return updated_task

    # Lógica Firestore
    try:
        doc_ref = db.collection(COLLECTION_TASKS).document(task_id)
        doc_ref.set(updated_task.model_dump(exclude_none=True))
        return updated_task
    except fb_exceptions.FirebaseError as e:
        _handle_firebase_error(e)


async def delete_task_service(
    task_id: str,
    db: Optional[firestore.Client],
    in_memory_tasks: Dict[str, Task],
    current_user_uid: str
):
    """Elimina una tarea. Lanza 403 si el usuario no es el dueño."""

    # 1. Autorización: Obtenemos la tarea existente para chequear el dueño
    existing_task = await get_task_service(task_id, db, in_memory_tasks)
    
    # 2. Chequeo de Dueño
    if existing_task.owner and existing_task.owner != current_user_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para eliminar esta tarea."
        )
    
    # 3. Lógica de eliminación
    if db is None:
        if task_id in in_memory_tasks:
            del in_memory_tasks[task_id]
        return

    # Lógica Firestore
    try:
        db.collection(COLLECTION_TASKS).document(task_id).delete()
    except fb_exceptions.FirebaseError as e:
        _handle_firebase_error(e)
    return