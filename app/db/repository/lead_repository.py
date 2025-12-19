from app.core.error_messages import ERROR_NOT_FOUND
from app.core.exceptions import NotFoundException
from app.db.repository.base_repository import BaseRepository
from app.models.lead import Lead
from app.schemas.lead_schema import LeadResponse
from app.models.lead_field_value import LeadFieldValue
from app.models.lead_field import LeadField
from app.db.session import SessionLocal


class LeadRepository(BaseRepository):
    model = Lead
    schema_out = LeadResponse

    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
    ]

    @classmethod
    def upsert_values(cls, session, lead_id: int, values: list):
        cls.upsert_children(
            session=session,
            parent_model=Lead,
            parent_id=lead_id,
            relation_name="field_values",
            items=values,
            key_attr="field_id",
            # CORRECCIÓN AQUÍ:
            create_fn=lambda item: LeadFieldValue(
                lead_id=lead_id, 
                **item.dict()     
            )
        )
