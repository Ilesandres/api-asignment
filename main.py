import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional

from pydantic import BaseModel

from models import Task, TaskStatus, UserProfile

# Firebase Admin
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
from firebase_admin.exceptions import FirebaseError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


app = FastAPI(
    title="FastAPI Front (Firestore optional)",
    description="CRUD para Task y UserProfile usando Firestore si hay credenciales, con fallback in-memory.",
    version="0.1.0",
)

# Cargar .env si existe
load_dotenv()

# Configuración de colecciones y credenciales (entorno)
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
COLLECTION_TASKS = os.getenv("FIRESTORE_COLLECTION_TASKS", "tasks")
COLLECTION_USERS = os.getenv("FIRESTORE_COLLECTION_USERS", "users")

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
        decoded = auth.verify_id_token(token)
        uid = decoded.get("uid")
        if not uid:
            raise Exception("UID no presente en token")
        return uid
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o expirado: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/", tags=["Root"])
async def root():
    return {"message": "FastAPI front ready (Firestore: %s)" % ("connected" if db else "in-memory")}


"""TASKS CRUD (Firestore cuando esté disponible)"""


@app.get("/tasks/", response_model=List[Task], tags=["Tasks"])
async def list_tasks():
    if db is None:
        return list(tasks.values())
    try:
        docs = db.collection(COLLECTION_TASKS).stream()
        result: List[Task] = []
        for doc in docs:
            data = doc.to_dict()
            result.append(Task(id=doc.id, **data))
        return result
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/tasks/", response_model=Task, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(task: Task):
    if db is None:
        if task.id in tasks:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task ID already exists")
        tasks[task.id] = task
        return task

    # Firestore
    try:
        payload = task.model_dump()
        _, doc_ref = db.collection(COLLECTION_TASKS).add(payload)
        return Task(id=doc_ref.id, **payload)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def get_task(task_id: str):
    if db is None:
        t = tasks.get(task_id)
        if not t:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return t

    try:
        doc = db.collection(COLLECTION_TASKS).document(task_id).get()
        if not doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        data = doc.to_dict()
        return Task(id=doc.id, **data)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.put("/tasks/{task_id}", response_model=Task, tags=["Tasks"])
async def update_task(task_id: str, updated: Task):
    if task_id != updated.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID mismatch")

    if db is None:
        if task_id not in tasks:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        tasks[task_id] = updated
        return updated

    try:
        doc_ref = db.collection(COLLECTION_TASKS).document(task_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        doc_ref.set(updated.model_dump())
        return updated
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
async def delete_task(task_id: str):
    if db is None:
        if task_id in tasks:
            del tasks[task_id]
        return

    try:
        db.collection(COLLECTION_TASKS).document(task_id).delete()
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return


"""USERS CRUD (Firestore opcional)"""


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


if __name__ == "__main__":
    # Permite arrancar la app con `python main.py` (sin hot-reload).
    # Para desarrollo con autoreload usa: `python -m uvicorn main:app --reload`
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


