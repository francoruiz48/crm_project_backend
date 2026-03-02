from sqlalchemy import func
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldResponse
from sqlalchemy.orm import joinedload
from app.core.constans import DEFAULT_PAGE_SIZE

class LeadFieldRepository(BaseRepository):
    model = LeadField
    schema_out = LeadFieldResponse
    schema_out_detail = LeadFieldDetailedResponse

    relationships = [
        (LeadField.field_type,),
        (LeadField.validation_rules,),
    ]


    @classmethod
    def get_all_active_with_rules(cls, session, campaign_id: int=None):
        if campaign_id:
            return session.query(cls.model).options(
                joinedload(cls.model.validation_rules)
            ).filter(
                cls.model.active == True,
                cls.model.campaign_id == campaign_id
            ).all()
        
        return session.query(cls.model).options(
            joinedload(cls.model.validation_rules)
        ).filter(cls.model.active == True).all()
    
    @classmethod
    def get_max_order(cls, session, campaign_id: int) -> int:
        """Obtiene el número de orden más alto en una campaña."""
        result = session.query(func.max(cls.model.order)).filter(
            cls.model.campaign_id == campaign_id
        ).scalar()
        return result or 0

    @classmethod
    def order_exists(cls, session, campaign_id: int, order: int) -> bool:
        """Verifica si un número de orden ya está en uso en esa campaña."""
        return session.query(cls.model.id).filter(
            cls.model.campaign_id == campaign_id,
            cls.model.order == order,
            cls.model.active == True
        ).first() is not None

