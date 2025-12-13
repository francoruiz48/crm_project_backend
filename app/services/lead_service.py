from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.db.unit_of_work import UnitOfWork

class LeadService(BaseService):
    repository = LeadRepository

    @classmethod
    def create(cls, obj_in):
        with UnitOfWork() as uow:
            lead = cls.repository.create(uow.session)
            cls.repository.upsert_values(uow.session, lead.id, obj_in.values)
            return cls.repository.get_by_id(uow.session, lead.id)

    @classmethod
    def update(cls, obj_id: int, obj_in):
        with UnitOfWork() as uow:
            cls.repository.upsert_values(uow.session, obj_id, obj_in.values)
            return cls.repository.get_by_id(uow.session, obj_id)