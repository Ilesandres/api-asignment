import os
import json
from datetime import datetime
from typing import List

# Este script usa firebase-admin para poblar Firestore con ejemplos de tasks y users.
# Requiere que `FIREBASE_CREDENTIALS_PATH` (ruta al JSON) o `FIREBASE_CREDENTIALS_JSON` (JSON string) esté en el entorno o en .env.

from dotenv import load_dotenv
load_dotenv()

FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")
COLLECTION_TASKS = os.getenv("FIRESTORE_COLLECTION_TASKS", "tasks")
COLLECTION_USERS = os.getenv("FIRESTORE_COLLECTION_USERS", "users")

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception as e:
    raise RuntimeError("firebase-admin no está instalado. Ejecuta `pip install -r requirements.txt`.") from e


def init_firebase():
    cred = None
    if FIREBASE_CREDENTIALS_JSON:
        try:
            cred_dict = json.loads(FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(cred_dict)
        except Exception as e:
            print(f"Error parseando FIREBASE_CREDENTIALS_JSON: {e}")
    if not cred and FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)

    if not cred:
        raise RuntimeError("No se encontraron credenciales de servicio válidas. Define FIREBASE_CREDENTIALS_PATH o FIREBASE_CREDENTIALS_JSON.")

    firebase_admin.initialize_app(cred)
    return firestore.client()


def make_sample_user(project_id: str, idx: int = 1) -> dict:
    uid = f"{project_id}-user-{idx}"
    now = datetime.utcnow().isoformat()
    return {
        "uid": uid,
        "email": f"{project_id}+{idx}@example.com",
        "displayName": f"{project_id} User {idx}",
        "photoURL": "",
        "phone": None,
        "location": None,
        "memberSince": now,
        "createdAt": now,
        "updatedAt": now,
    }


def make_sample_task(owner_uid: str, idx: int = 1) -> dict:
    now = datetime.utcnow().isoformat()
    return {
        "title": f"Sample task {idx}",
        "description": "Tarea creada por seed_firestore.py",
        "due": None,
        "status": "waiting",
        "owner": owner_uid,
        "createdAt": now,
        "updatedAt": now,
    }


def seed_firestore():
    db = init_firebase()
    # Intenta determinar project id desde las credenciales si está disponible
    project_id = None
    try:
        cred_info = None
        if FIREBASE_CREDENTIALS_JSON:
            cred_info = json.loads(FIREBASE_CREDENTIALS_JSON)
        elif FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
            with open(FIREBASE_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                cred_info = json.load(f)
        if cred_info:
            project_id = cred_info.get("project_id") or cred_info.get("projectId") or "project"
    except Exception:
        project_id = "project"

    users_coll = db.collection(COLLECTION_USERS)
    tasks_coll = db.collection(COLLECTION_TASKS)

    created_users: List[str] = []

    # Crear 3 usuarios de ejemplo
    for i in range(1, 4):
        user = make_sample_user(project_id, i)
        uid = user["uid"]
        users_coll.document(uid).set(user)
        created_users.append(uid)
        print(f"Usuario creado: {uid}")

    # Crear 5 tareas de ejemplo, asignando a usuarios en round-robin
    for i in range(1, 6):
        owner = created_users[(i - 1) % len(created_users)]
        task = make_sample_task(owner, i)
        tasks_coll.add(task)
        print(f"Tarea creada para {owner}: Sample task {i}")

    print("Seed completo.")


if __name__ == "__main__":
    seed_firestore()
