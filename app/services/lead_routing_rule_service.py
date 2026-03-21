from app.services.base_service import BaseService
from app.db.repository.lead_routing_rule_repository import LeadRoutingRuleRepository
from sqlalchemy import func

class LeadRoutingRuleService(BaseService):
    repository = LeadRoutingRuleRepository


    @classmethod
    def create(cls, obj_in, created_by=None, **kwargs):
        def do_create(uow):
            data = obj_in.model_dump(exclude_unset=True)
            data.update(kwargs) # Por si inyectas organization_id desde el controller

            # 1. Autocalcular el Order si no viene
            if not data.get("order"):
                max_order = uow.session.query(func.max(cls.repository.model.order)).filter_by(
                    organization_id=data.get("organization_id"),
                    campaign_id=data.get("campaign_id")
                ).scalar()
                
                data["order"] = (max_order or 0) + 1

            # 2. Guardar y Auditar
            new_rule = cls.repository.create(uow.session, data, created_by)
            uow.session.flush()
            
            cls._log_audit(uow.session, new_rule, action="CREATE", changes=data, user_id=created_by)
            return new_rule

        return cls._execute(action="Crear Regla de Enrutamiento", func=do_create)
