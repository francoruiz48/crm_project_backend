from app.services.base_service import BaseService
from app.db.unit_of_work import UnitOfWork
from app.db.repository.lead_state_history_repository import LeadStateHistoryRepository
from app.schemas.lead_state_history_schema import LeadStateHistoryCreate

class LeadStateHistoryService(BaseService):
    repository = LeadStateHistoryRepository()


    @classmethod
    def create(cls, obj_in: LeadStateHistoryCreate, **kwargs):
        """
        Crea un registro de auditoría en el historial de estados.
        NOTA: Este método está diseñado para ser llamado internamente por la lógica 
        de negocio (ej: LeadService), no directamente desde un endpoint POST público.
        """
        with UnitOfWork() as uow:
            # Preparamos los datos
            history_data = obj_in.model_dump(exclude_unset=True)
            
            # kwargs nos permite inyectar cosas como 'created_by' (el usuario que hizo la acción)
            history_data.update(kwargs) 
            
            created_obj = cls.repository.create(uow.session, history_data)
            return created_obj
            
    # No sobrescribimos update() ni delete() porque BaseController 
    # ya tiene bloqueados esos endpoints para este recurso. 
    # Si alguien los llamara por código interno, usaría los genéricos de BaseService, 
    # lo cual está bien para un super-admin si alguna vez fuera estrictamente necesario.