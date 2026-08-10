from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from app.schemas.base_schema import UserSimpleResponse

class LeadActivityHistoryResponse(BaseModel):
    # No hereda BaseResponse (standalone). A diferencia del resto de entidades
    # migradas en Fase 2/3, LeadActivityHistory NO tiene public_uuid (es un log
    # de auditoría solo-inserción que nunca heredó BaseModelDB) -- por eso `id`
    # se expone acá como el id interno (int), no como uuid. Bug real encontrado
    # 2026-07-30: antes declaraba `id: str = Field(validation_alias="public_uuid")`,
    # que rompía CUALQUIER GET_ALL con al menos un resultado con un 400 ("Input
    # should be a valid string, input_value=<int>"), porque Pydantic no encontraba
    # `public_uuid` en el ORM y terminaba validando el `id` entero crudo contra un
    # campo tipado `str`. lead_id queda como FK sin traducir (alcance de Fase 4).
    id: int
    lead_id: Optional[int]
    activity_type: str
    details: Optional[Dict[str, Any]]
    created_at: datetime
    created_by: Optional[int]
    creator: Optional[UserSimpleResponse] = None

    model_config = {"from_attributes": True, "populate_by_name": True}

class LeadActivityHistoryDetailedResponse(LeadActivityHistoryResponse):
    pass