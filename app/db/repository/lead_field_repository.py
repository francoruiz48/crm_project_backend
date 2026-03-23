from sqlalchemy import func
from app.db.repository.base_repository import BaseRepository
from app.models.lead_field import LeadField
from app.schemas.lead_field_schema import LeadFieldDetailedResponse, LeadFieldResponse
from sqlalchemy.orm import joinedload

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
        query = session.query(cls.model).options(
            joinedload(cls.model.validation_rules)
        )

        query = cls._apply_tenant_filter(query)

        query = query.filter(cls.model.active == True)

        if campaign_id:
            query = query.filter(cls.model.campaign_id == campaign_id)

        return query.all()
    
    @classmethod
    def get_max_order(cls, session, campaign_id: int) -> int:
        """Obtiene el número de orden más alto en una campaña."""
        query = session.query(func.max(cls.model.order))
        
        query = cls._apply_tenant_filter(query)
        
        result = query.filter(cls.model.campaign_id == campaign_id).scalar()
        return result or 0

    @classmethod
    def order_exists(cls, session, campaign_id: int, order: int) -> bool:
        """Verifica si un número de orden ya está en uso en esa campaña."""
        query = session.query(cls.model.id)
        
        query = cls._apply_tenant_filter(query)
        
        return query.filter(
            cls.model.campaign_id == campaign_id,
            cls.model.order == order,
            cls.model.active == True
        ).first() is not None

