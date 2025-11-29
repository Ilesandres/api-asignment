from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum
import uuid


class TaskStatus(str, Enum):
    waiting = 'waiting'
    in_progress = 'in-progress'
    completed = 'completed'
    abandoned = 'abandoned'


class Task(BaseModel):
    """Modelo Pydantic para una tarea (Task) extraída del frontend."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="ID único")
    title: str = Field(..., description="Título de la tarea")
    description: Optional[str] = Field(None, description="Descripción opcional")
    due: Optional[datetime] = Field(None, description="Fecha límite (ISO) opcional")
    status: TaskStatus = Field(TaskStatus.waiting, description="Estado de la tarea")
    owner: Optional[str] = Field(None, description="UID del propietario")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": str(uuid.uuid4()),
                "title": "Comprar ingredientes",
                "description": "Comprar harina y levadura",
                "due": None,
                "status": "waiting",
                "owner": None,
            }
        }
    }
