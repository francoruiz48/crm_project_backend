from app.services.base_service import BaseService
from app.db.repository.workspace_repository import WorkspaceRepository
from fastapi import status, HTTPException

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
            
            return cls.repository.create(uow.session, obj_in.model_dump(), created_by)

        return cls._execute(action="Crear workspace", func=do_create)