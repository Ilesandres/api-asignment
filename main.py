import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional

# Se importa para usar TaskStatus como tipo de query
from pydantic import BaseModel 

from models import Task, TaskStatus, UserProfile
from services.task_service import (
    list_tasks_service,
    create_task_service,
    get_task_service,
    update_task_service,
    delete_task_service
) 
from services.profile_service import (
    get_profile_service,
    create_profile_service,
    update_profile_service,
)

# Firebase Admin
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
from firebase_admin.exceptions import FirebaseError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


app = FastAPI(
    title="FastAPI Firestore Task/User API",
    description="CRUD para Task y UserProfile usando Firestore si hay credenciales, con fallback in-memory.",
    version="0.1.0",
)

# Cargar .env si existe
load_dotenv()

# Configuración de colecciones y credenciales (entorno)
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
COLLECTION_TASKS = os.getenv("FIRESTORE_COLLECTION_TASKS", "tasks")
COLLECTION_USERS = os.getenv("FIRESTORE_COLLECTION_USERS", "users")
COLLECTION_PROFILE = os.getenv("FIRESTORE_COLLECTION_PROFILE", "userProfiles")

# Cliente Firestore (se inicializa en runtime o queda None)
db: Optional[firestore.Client] = None


def initialize_firebase() -> None:
    global db
    # Permitir credenciales vía ruta o vía JSON en variable de entorno
    cred_obj = None

    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if cred_json:
        try:
            cred_dict = json.loads(cred_json)
            cred_obj = credentials.Certificate(cred_dict)
        except Exception as e:
            print(f"❌ FIREBASE_CREDENTIALS_JSON inválida: {e}")

    # Si no hay JSON válido, intentar con ruta en FIREBASE_CREDENTIALS_PATH
    if cred_obj is None:
        if not FIREBASE_CREDENTIALS_PATH or not os.path.exists(FIREBASE_CREDENTIALS_PATH):
            print("⚠️ FIREBASE_CREDENTIALS_PATH no configurada o archivo no encontrado. Usando almacenamiento en memoria.")
            return
        try:
            cred_obj = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        except Exception as e:
            print(f"❌ Error leyendo FIREBASE_CREDENTIALS_PATH: {e}")
            return

    # Inicializar firebase con credenciales obtenidas
    try:
        firebase_admin.initialize_app(cred_obj)
        db = firestore.client()
        print("✅ Firebase inicializado. Firestore listo.")
    except Exception as e:
        print(f"❌ Error inicializando Firebase: {e}")
        db = None


initialize_firebase()


# Almacenamiento en memoria (temporal)
tasks: Dict[str, Task] = {}
users: Dict[str, UserProfile] = {}


def check_db_connection():
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Firestore no inicializado. Configura FIREBASE_CREDENTIALS_PATH.")


# --- CORS setup ---
# Allow origins configured by FRONTEND_ORIGINS env var (comma-separated), defaults to typical dev ports
frontend_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000")
allow_origins = [o.strip() for o in frontend_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Authentication dependency (Firebase ID Token) ---
security_scheme = HTTPBearer(description="Provide Firebase ID token as Bearer token")


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> str:
    """Verifica el ID Token de Firebase y devuelve el `uid` del usuario."""
    token = credentials.credentials
    try:
        # En un entorno real, descomentar la siguiente línea
        # decoded = auth.verify_id_token(token) 
        
        # << Sustituto temporal para pruebas si no tienes un ID Token real >>
        # Si el token es "TEST_USER_123", lo aceptamos como uid para pruebas locales
        if token.startswith("TEST_USER_"):
            uid = token 
        else:
            decoded = auth.verify_id_token(token) # Línea real de Firebase
            uid = decoded.get("uid")

        if not uid:
            raise Exception("UID no presente en token")
        return uid
    except Exception as e:
        # Esto capturaría errores reales de auth.verify_id_token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o expirado: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/", tags=["Root"])
async def root():
    return {"message": "FastAPI front ready (Firestore: %s)" % ("connected" if db else "in-memory")}


"""TASKS CRUD (REFACTORIZADO CON SERVICIOS Y SEGURIDAD)"""

@app.get("/tasks/", response_model=List[Task], tags=["Tasks"])
async def list_tasks(
    status_filter: Optional[TaskStatus] = None, # Permite filtrar por estado
    current_user_uid: Optional[str] = Depends(verify_token) # Autenticación Opcional: si se provee, filtramos por dueño
):
    """Lista tareas, opcionalmente filtrando por dueño si se provee token."""
    return await list_tasks_service(
        db=db,
        in_memory_tasks=tasks,
        current_user_uid=current_user_uid,
        status_filter=status_filter
    )


@app.post("/tasks/", response_model=Task, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(
    task: Task,
    current_user_uid: str = Depends(verify_token) # Requiere autenticación
):
    """Crea una nueva tarea, asignando al usuario autenticado como 'owner'."""
    return await create_task_service(
        task=task,
        db=db,
        in_memory_tasks=tasks,
        current_user_uid=current_user_uid
    )


@app.get("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def get_task(
    task_id: str,
    current_user_uid: str = Depends(verify_token) # Requiere autenticación
):
    """Obtiene una tarea. Lanza 403 si el usuario no es el dueño."""
    # Obtener la tarea a través del servicio
    task = await get_task_service(task_id=task_id, db=db, in_memory_tasks=tasks)

    # Autorización: si la tarea tiene dueño, debe coincidir con el usuario actual.
    if task.owner and task.owner != current_user_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver esta tarea."
        )

    return task


@app.put("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def update_task(
    task_id: str,
    updated: Task,
    current_user_uid: str = Depends(verify_token) # Requiere autenticación y Autorización (manejada en el servicio)
):
    """Actualiza una tarea. Solo el dueño puede hacerlo."""
    return await update_task_service(
        task_id=task_id,
        updated_task=updated,
        db=db,
        in_memory_tasks=tasks,
        current_user_uid=current_user_uid
    )


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
async def delete_task(
    task_id: str,
    current_user_uid: str = Depends(verify_token) # Requiere autenticación y Autorización (manejada en el servicio)
):
    """Elimina una tarea. Solo el dueño puede hacerlo."""
    await delete_task_service(
        task_id=task_id,
        db=db,
        in_memory_tasks=tasks,
        current_user_uid=current_user_uid
    )
    return


"""USERS CRUD (Firestore opcional) - Se mantienen sin refactorizar por ahora"""


@app.get("/users/", response_model=List[UserProfile], tags=["Users"])
async def list_users():
    if db is None:
        return list(users.values())
    try:
        docs = db.collection(COLLECTION_USERS).stream()
        result: List[UserProfile] = []
        for doc in docs:
            data = doc.to_dict()
            result.append(UserProfile(uid=doc.id, **data))
        return result
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/users/", response_model=UserProfile, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(user: UserProfile):
    if db is None:
        if user.uid in users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")
        users[user.uid] = user
        return user

    try:
        payload = user.model_dump()
        # Use document with UID as ID
        db.collection(COLLECTION_USERS).document(user.uid).set(payload)
        return user
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/users/{uid}", response_model=UserProfile, tags=["Users"])
async def get_user(uid: str):
    if db is None:
        u = users.get(uid)
        if not u:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return u

    try:
        doc = db.collection(COLLECTION_USERS).document(uid).get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        data = doc.to_dict()
        return UserProfile(uid=doc.id, **data)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.put("/users/{uid}", response_model=UserProfile, tags=["Users"])
async def update_user(uid: str, updated: UserProfile):
    if uid != updated.uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UID mismatch")

    if db is None:
        if uid not in users:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        users[uid] = updated
        return updated

    try:
        doc_ref = db.collection(COLLECTION_USERS).document(uid)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        doc_ref.set(updated.model_dump())
        return updated
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


class ProfileCreate(BaseModel):
    email: str
    displayName: Optional[str] = None
    photoURL: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None


class ProfileUpdate(BaseModel):
    displayName: Optional[str] = None
    photoURL: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None


@app.get("/profiles/{uid}", response_model=UserProfile, tags=["Profiles"])
async def get_profile(uid: str):
    """Obtener perfil por UID (público)."""
    profile = await get_profile_service(uid=uid, db=db, in_memory_users=users)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@app.get("/profiles/me", response_model=UserProfile, tags=["Profiles"])
async def get_my_profile(current_user_uid: str = Depends(verify_token)):
    """Obtener el perfil del usuario autenticado. Si no existe, responde 404 (usa POST /profiles para crearlo)."""
    profile = await get_profile_service(uid=current_user_uid, db=db, in_memory_users=users)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found. Create it with POST /profiles/")
    return profile


@app.post("/profiles/", response_model=UserProfile, status_code=status.HTTP_201_CREATED, tags=["Profiles"])
async def create_profile(payload: ProfileCreate, current_user_uid: str = Depends(verify_token)):
    """Crear perfil para el usuario autenticado. Si ya existe, devuelve el perfil existente."""
    existing = await get_profile_service(uid=current_user_uid, db=db, in_memory_users=users)
    if existing:
        return existing

    profile = await create_profile_service(uid=current_user_uid, payload=payload.model_dump(), db=db, in_memory_users=users)
    return profile


@app.put("/profiles/{uid}", response_model=UserProfile, tags=["Profiles"])
async def update_profile(uid: str, updates: ProfileUpdate, current_user_uid: str = Depends(verify_token)):
    """Actualizar perfil — solo el dueño puede actualizar su perfil."""
    result = await update_profile_service(uid=uid, updates=updates.model_dump(exclude_none=True), current_user_uid=current_user_uid, db=db, in_memory_users=users)
    if result is None:
        # Puede ser por autorización o por inexistencia
        # Determinar si existe para reportar 404 vs 403
        existing = await get_profile_service(uid=uid, db=db, in_memory_users=users)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this profile")
    return result


if __name__ == "__main__":
    # Permite arrancar la app con `python main.py` (sin hot-reload).
    # Para desarrollo con autoreload usa: `python -m uvicorn main:app --reload`
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)