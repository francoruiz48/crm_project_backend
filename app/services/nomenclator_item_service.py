from app.core.constans import DEFAULT_PAGE_SIZE
from app.services.base_service import BaseService
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository


class NomenclatorItemService(BaseService):
    repository = NomenclatorItemRepository
