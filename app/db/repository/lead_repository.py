from app.db.repository.base_repository import BaseRepository
from app.models.lead import Lead
from app.schemas.lead_schema import LeadResponse
from app.models.lead_field_value import LeadFieldValue
from app.models.lead_field import LeadField
from app.db.session import SessionLocal


class LeadRepository(BaseRepository):
    model = Lead
    schema_out = LeadResponse

    relations = [
        Lead.field_values,
        LeadFieldValue.field,
        LeadField.field_type
    ]

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
        leads = super().get_all()

        result = []
        for lead in leads:
            lead_resp = LeadResponse.model_validate(lead)
            lead_resp._field_values = lead.field_values
            result.append(lead_resp)

        return result

    @classmethod
    def get_by_id(cls, obj_id: int):
        lead = super().get_by_id(obj_id)

        lead_resp = LeadResponse.model_validate(lead)
        lead_resp._field_values = lead.field_values
        return lead_resp
