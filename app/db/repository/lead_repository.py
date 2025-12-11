
from app.db.repository.base_repository import BaseRepository
from app.models.lead import Lead
from app.schemas.lead_schema import LeadResponse
from app.db.session import SessionLocal
from app.models.lead_field_value import LeadFieldValue
from app.models.lead_field import LeadField
from sqlalchemy.orm import selectinload

class LeadRepository(BaseRepository):
    model = Lead
    schema_out = LeadResponse

    @classmethod
    def create_empty(cls, _data=None):
        with SessionLocal() as db:
            obj = Lead()
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj

    
    @classmethod
    def get_all(cls):
        with SessionLocal() as db:
            leads = (
                db.query(cls.model)
                .options(
                    selectinload(cls.model.field_values)
                    .selectinload(LeadFieldValue.field)
                    .selectinload(LeadField.field_type)
                )
                .all()
            )

            result = []
            for lead in leads:
                lead_resp = LeadResponse.model_validate(lead)
                lead_resp._field_values = lead.field_values
                result.append(lead_resp)
            return result

    @classmethod
    def get_by_id(cls, obj_id: int):
        with SessionLocal() as db:
            lead = (
                db.query(cls.model)
                .options(
                    selectinload(cls.model.field_values)
                    .selectinload(LeadFieldValue.field)
                    .selectinload(LeadField.field_type) 
                )
                .filter(cls.model.id == obj_id)
                .first()
            )

            lead_resp = LeadResponse.model_validate(lead)
            lead_resp._field_values = lead.field_values 
            return lead_resp