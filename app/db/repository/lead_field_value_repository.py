
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field_value import LeadFieldValue
from app.schemas.lead_field_value_schema import LeadFieldValueResponse

class LeadFieldValueRepository(BaseRepository):
    model = LeadFieldValue
    schema_out = LeadFieldValueResponse

    @classmethod
    def create_simple(cls, data: dict):
        """Crea un LeadFieldValue directamente desde un dict."""
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            obj = cls.model(**data)
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj