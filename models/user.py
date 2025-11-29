from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
import uuid


class UserProfile(BaseModel):
    """Modelo Pydantic para UserProfile extraído del frontend."""
    uid: str = Field(..., description="UID de Firebase")
    email: EmailStr = Field(..., description="Correo electrónico")
    displayName: Optional[str] = Field(None, description="Nombre para mostrar")
    photoURL: Optional[str] = Field(None, description="URL de la foto de perfil")
    phone: Optional[str] = Field(None, description="Teléfono")
    location: Optional[str] = Field(None, description="Ubicación")
    memberSince: Optional[datetime] = Field(None, description="Fecha de membresía (ISO)")
    createdAt: Optional[datetime] = Field(None, description="Timestamp de creación")
    updatedAt: Optional[datetime] = Field(None, description="Timestamp de actualización")

    model_config = {
        "json_schema_extra": {
            "example": {
                "uid": str(uuid.uuid4()),
                "email": "user@example.com",
                "displayName": "Usuario Demo",
                "photoURL": "https://example.com/photo.jpg",
                "phone": None,
                "location": None,
                "memberSince": None,
                "createdAt": None,
                "updatedAt": None,
            }
        }
    }
