from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException
from app.core.constans import DEFAULT_PAGE_SIZE

class WorkspaceService(BaseService):
    repository = WorkspaceRepository

    @classmethod
    def create(cls, obj_in, created_by=None):
        
        def do_create(uow):
            errors = []

            existing = cls.repository.get_all(
                session=uow.session, 
                name=obj_in.name,
                only_active=True
            )
            
            if existing:
                errors.append({"field": "name", "message": f"Ya existe un espacio de trabajo llamado '{obj_in.name}'."})
        

            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            data = obj_in.model_dump()
            new_ws = cls.repository.create(uow.session, data, created_by)
            uow.session.flush()

            # LOG DE AUDITORÍA
            cls._log_audit(uow.session, new_ws, action="CREATE", changes=data, user_id=created_by)

            return new_ws

        return cls._execute(action="Crear workspace", func=do_create)
    