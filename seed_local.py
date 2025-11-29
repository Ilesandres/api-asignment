import json
import os
import requests

# Script simple para poblar la API local en memoria usando los datos del JSON cliente
# Lee `seviceAccountKey.json` (o cualquier JSON que indiques) y crea un usuario y una tarea.

ROOT = os.path.dirname(__file__)
CLIENT_JSON = os.path.join(ROOT, "seviceAccountKey.json")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")


def load_client_json(path):
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            # If file contains JS-like config, try to extract JSON object between braces
            raw = f.read()
            start = raw.find('{')
            end = raw.rfind('}')
            if start != -1 and end != -1:
                return json.loads(raw[start:end+1])
            raise


def seed():
    if not os.path.exists(CLIENT_JSON):
        print(f"No se encontró {CLIENT_JSON}. Coloca el archivo con ese nombre o modifica CLIENT_JSON en el script.")
        return

    data = load_client_json(CLIENT_JSON)
    project = data.get("projectId") or data.get("project_id") or "local-project"

    # Crear un usuario de ejemplo
    uid = f"{project}-user-1"
    user = {
        "uid": uid,
        "email": f"{project}@example.com",
        "displayName": project,
        "photoURL": data.get("photoURL", ""),
        "phone": None,
        "location": None,
        "memberSince": None,
        "createdAt": None,
        "updatedAt": None,
    }

    print("Creando usuario:", user)
    r = requests.post(f"{API_BASE}/users/", json=user)
    print("/users/ ->", r.status_code, r.text)

    # Crear una tarea de ejemplo
    task = {
        "title": f"Tarea de {project}",
        "description": "Tarea generada desde seed_local.py",
        "due": None,
        "status": "waiting",
        "owner": uid,
    }

    # Nuestro modelo Task espera un id; si no lo provees el servidor lo generará (pydantic default)
    print("Creando task:", task)
    r2 = requests.post(f"{API_BASE}/tasks/", json=task)
    print("/tasks/ ->", r2.status_code, r2.text)


if __name__ == "__main__":
    seed()
