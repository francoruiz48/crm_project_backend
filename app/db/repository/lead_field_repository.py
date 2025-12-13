from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.schemas.lead_field_schema import LeadFieldResponse
from app.db.session import SessionLocal
from sqlalchemy.orm import selectinload

class LeadFieldRepository(BaseRepository):
    model = LeadField
    schema_out = LeadFieldResponse

    relationships = [
        (LeadField.field_type,),
        (LeadField.validation_rules,),
        (LeadField.validation_rules_related,),
    ]
