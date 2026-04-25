from typing import Optional
from fastapi import HTTPException, status
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from app.db.unit_of_work import UnitOfWork
from app.models.tag import Tag
from app.db.repository.tag_repository import TagRepository
from app.schemas.tag_schema import TagCreate, TagUpdate
from app.services.base_service import BaseService

class TagService(BaseService):
    repository = TagRepository

    @classmethod
    def create(cls, obj_in: TagCreate, user_context: Optional[UserContext] = None):
        def do_create(uow):
            org_id = user_context.organization_id if user_context and user_context.organization_id else TENANT_ORG_ID.get()
            
            # Validación: Nombre único por organización
            existing = uow.session.query(Tag).filter(
                Tag.name.ilike(obj_in.name),
                Tag.organization_id == org_id
            ).first()
            if existing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "name", "message": f"Ya existe una etiqueta llamada '{obj_in.name}'."}]
                )

            new_tag = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_tag, action="CREATE", changes=obj_in.model_dump(), user_id=user_id)
            return new_tag

        return cls._execute(action="Crear Etiqueta", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            current_obj = uow.session.query(Tag).filter_by(id=obj_id).first()
            if not current_obj:
                cls._not_found(obj_id)

            org_id = user_context.organization_id if user_context and user_context.organization_id else TENANT_ORG_ID.get()
            
            # Validación: Nombre único por organización
            existing = uow.session.query(Tag).filter(
                Tag.name.ilike(obj_in.name),
                Tag.organization_id == org_id
            ).first()
            if existing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "name", "message": f"Ya existe una etiqueta llamada '{obj_in.name}'."}]
                )

            updated_obj = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and getattr(user_context, 'user', None) else None
            cls._log_audit(uow.session, updated_obj, action="UPDATE", changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)
            return updated_obj

        return cls._execute(action="Actualizar Etiqueta", obj_id=obj_id, func=do_update)