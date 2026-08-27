from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from app.schemas.base_schema import UserSimpleResponse

class SystemAuditLogResponse(BaseModel):
    # No hereda BaseResponse (standalone), así que el alias a public_uuid se
    # declara acá directo -- ver base_schema.py.
    id: str = Field(validation_alias="public_uuid")
    organization_id: Optional[int]
    entity_type: str
    # Antes exponía el id interno (int) de la entidad auditada. Ahora expone su uuid
    # real (columna entity_uuid, agregada al modelo -- ver backend/AGENTS.md §18-ter),
    # mismo criterio que el resto de la API: el front nunca ve ids internos. El id
    # interno sigue existiendo en la fila (columna entity_id) para uso interno, pero
    # no se serializa.
    entity_id: str = Field(validation_alias="entity_uuid")
    action: str
    changes: Optional[Dict[str, Any]]
    created_at: datetime
    created_by: Optional[int]

    creator: Optional[UserSimpleResponse] = None

    model_config = {"from_attributes": True, "populate_by_name": True}

class SystemAuditLogDetailedResponse(SystemAuditLogResponse):
    pass


