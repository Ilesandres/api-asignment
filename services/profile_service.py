import os
from datetime import datetime
from typing import Optional, Dict, Any

from firebase_admin import firestore

from models.user import UserProfile

COLLECTION = os.getenv("FIRESTORE_COLLECTION_PROFILE", "userProfiles")


def _to_datetime(value):
    try:
        if hasattr(value, "to_datetime"):
            return value.to_datetime()
    except Exception:
        pass
    return value


async def get_profile_service(uid: str, db: Optional[firestore.Client] = None, in_memory_users: Optional[Dict[str, dict]] = None) -> Optional[UserProfile]:
    if db:
        doc_ref = db.collection(COLLECTION).document(uid)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        for k in ("memberSince", "createdAt", "updatedAt"):
            if k in data:
                data[k] = _to_datetime(data[k])
        data.pop("uid", None)
        return UserProfile(uid=doc.id, **data)

    if in_memory_users is None:
        return None
    data = in_memory_users.get(uid)
    if not data:
        return None
    return UserProfile(uid=uid, **data)


async def create_profile_service(uid: str, payload: Dict[str, Any], db: Optional[firestore.Client] = None, in_memory_users: Optional[Dict[str, dict]] = None) -> UserProfile:
    now = datetime.utcnow()
    profile = {
        "email": payload.get("email"),
        "displayName": payload.get("displayName"),
        "photoURL": payload.get("photoURL"),
        "phone": payload.get("phone"),
        "location": payload.get("location"),
        "memberSince": payload.get("memberSince", now),
        "createdAt": payload.get("createdAt", now),
        "updatedAt": payload.get("updatedAt", now),
    }

    if db:
        doc_ref = db.collection(COLLECTION).document(uid)
        doc_ref.set(profile, merge=True)
        doc = doc_ref.get()
        data = doc.to_dict() or {}
        for k in ("memberSince", "createdAt", "updatedAt"):
            if k in data:
                data[k] = _to_datetime(data[k])
        data.pop("uid", None)
        return UserProfile(uid=doc.id, **data)

    if in_memory_users is not None:
        in_memory_users[uid] = profile
        return UserProfile(uid=uid, **profile)

    return UserProfile(uid=uid, **profile)


async def update_profile_service(uid: str, updates: Dict[str, Any], current_user_uid: str, db: Optional[firestore.Client] = None, in_memory_users: Optional[Dict[str, dict]] = None) -> Optional[UserProfile]:
    if uid != current_user_uid:
        return None

    updates = {k: v for k, v in updates.items() if k not in ("uid", "createdAt", "memberSince")}
    updates["updatedAt"] = datetime.utcnow()

    if db:
        doc_ref = db.collection(COLLECTION).document(uid)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        doc_ref.update(updates)
        doc = doc_ref.get()
        data = doc.to_dict() or {}
        for k in ("memberSince", "createdAt", "updatedAt"):
            if k in data:
                data[k] = _to_datetime(data[k])
        data.pop("uid", None)
        return UserProfile(uid=doc.id, **data)

    if in_memory_users is not None:
        if uid not in in_memory_users:
            return None
        in_memory_users[uid].update(updates)
        return UserProfile(uid=uid, **in_memory_users[uid])

    return None
