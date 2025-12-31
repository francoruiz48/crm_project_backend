from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.schemas.lead_field_schema import LeadFieldResponse
from sqlalchemy.orm import joinedload

class LeadFieldRepository(BaseRepository):
    model = LeadField
    schema_out = LeadFieldResponse

    relationships = [
        (LeadField.field_type,),
        (LeadField.validation_rules,),
    ]

    @classmethod
    def get_all_active_with_rules(cls, session, page: int = 0, page_size: int = 0):

        query = session.query(cls.model).options(
            joinedload(cls.model.validation_rules)
        ).filter(cls.model.active == True)
        

        total, query = cls._paginate(query, page, page_size)
        

        return total, query.all()
