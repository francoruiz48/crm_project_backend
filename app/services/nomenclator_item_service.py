from app.services.base_service import BaseService
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository


class NomenclatorItemService(BaseService):
    repository = NomenclatorItemRepository

    @classmethod
    def get_all(cls, only_active: bool = True, detailed: bool = False, nomenclator_id: int = None, parent_item_id: int = None):
        return cls._execute(
            action="Obteniendo Items de Nomencladores",
            func=lambda uow: cls.repository.get_all(
                session=uow.session, 
                only_active=only_active, 
                detailed=detailed, 
                nomenclator_id=nomenclator_id,
                parent_item_id = parent_item_id
            )
        )