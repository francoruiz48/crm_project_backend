from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# A partir de la Fase 3 de "ID público por UUID" (ver backend/AGENTS.md §16-18):
# el campo `id` de CUALQUIER respuesta de la API sale del `public_uuid` de la fila
# (agregado a BaseModelDB en la Fase 1), NO del id interno autoincremental. Se logra
# con validation_alias="public_uuid": el campo sigue llamándose `id` (así que el JSON
# de salida sigue teniendo la clave "id", sin tocar cada schema de cada módulo), pero
# al validar `from_attributes` desde el objeto ORM lee `obj.public_uuid` en vez de
# `obj.id`. El id interno (int) nunca se serializa a través de estos mixins.
class UserSimpleResponse(BaseModel):
    id: str = Field(validation_alias="public_uuid")
    name: str
    last_name: Optional[str] = None
    email: str

    model_config = {"from_attributes": True, "populate_by_name": True}

class BaseResponse():
    id: str = Field(validation_alias="public_uuid")
    active: bool

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }

class BaseDetailedResponse(BaseResponse):
    created_at: datetime
    updated_at: datetime

    # created_by/updated_by (antes exponían el id interno del usuario creador/editor)
    # se eliminaron: son redundantes con creator/updater, que ya traen toda la data
    # del usuario y ahora exponen su public_uuid en vez del id interno. Si el frontend
    # lee estos dos campos directamente en vez de creator.id/updater.id, hay que
    # corregirlo (ver backend/AGENTS.md §18 para el caso encontrado en LeadComments).
    creator: Optional[UserSimpleResponse] = None
    updater: Optional[UserSimpleResponse] = None

class BaseCreate():
    pass