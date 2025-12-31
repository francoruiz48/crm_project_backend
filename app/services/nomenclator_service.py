from typing import Optional
from app.services.base_service import BaseService
from app.db.repository.nomenclator_repository import NomenclatorRepository


class NomenclatorService(BaseService):
    repository = NomenclatorRepository

    @classmethod
    def get_all(cls, page: int = 1, page_size: int = 20, only_active: bool = True, detailed: bool = False, campaign_id: int = None, global_nomenclator: Optional[bool] = None):
        return cls._execute(
            action="Obteniendo Nomencladores",
            func=lambda uow: cls.repository.get_all(
                session=uow.session, 
                page=page,
                page_size=page_size,
                only_active=only_active, 
                detailed=detailed, 
                campaign_id=campaign_id,
                global_nomenclator = global_nomenclator
            )
        )