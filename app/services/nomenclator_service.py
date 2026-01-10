from typing import Optional
from app.core.constans import DEFAULT_PAGE_SIZE
from app.services.base_service import BaseService
from app.db.repository.nomenclator_repository import NomenclatorRepository


class NomenclatorService(BaseService):
    repository = NomenclatorRepository
