from typing import Optional
from app.services.base_service import BaseService
from app.db.repository.nomenclator_repository import NomenclatorRepository


class NomenclatorService(BaseService):
    repository = NomenclatorRepository

    @classmethod
    def get_all(cls, only_active: bool = True, detailed: bool = False, campaign_id: int = None, global_nomenclator: Optional[bool] = None):
        return cls._execute(
            action="Obteniendo Nomencladores",
            func=lambda uow: cls.repository.get_all(
                session=uow.session, 
                only_active=only_active, 
                detailed=detailed, 
                campaign_id=campaign_id,
                global_nomenclator = global_nomenclator
            )
        )