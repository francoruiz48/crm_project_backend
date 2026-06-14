from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from app.db.repository.nomenclator_repository import NomenclatorRepository
from app.db.unit_of_work import UnitOfWork
from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction

class NomenclatorService(BaseService):
    repository = NomenclatorRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # 1. Obtener ORG ID del contexto seguro (o de la variable global)
            org_id = user_context.organization_id if user_context and user_context.organization_id is not None else TENANT_ORG_ID.get()

            # REGLA 1: Solo SuperAdmin puede crear Nomencladores Globales
            if org_id is None:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "Solo un SuperAdmin puede crear nomencladores globales en el sistema."}]
                    )

            # REGLA 2: Unicidad del Nombre (No chocar con la org ni con globales)
            if obj_in.name:
                existing = uow.session.query(Nomenclator).filter(
                    Nomenclator.name.ilike(obj_in.name),
                    or_(Nomenclator.organization_id == org_id, Nomenclator.organization_id.is_(None))
                ).first()
                
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "name", "message": "Ya existe un nomenclador con este nombre en su empresa o a nivel global."}]
                    )

            # Persistencia
            new_obj = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()
            
            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_id)
            
            return new_obj

        return cls._execute(action="Crear Nomenclador", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            current_obj = uow.session.query(Nomenclator).filter_by(id=obj_id).first()
            if not current_obj:
                cls._not_found(obj_id)

            # REGLA 1: Protección Anti-Escritura de Globales
            if current_obj.organization_id is None:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No tienes permisos para modificar nomencladores globales del sistema."}]
                    )

            # REGLA 2: Unicidad del Nombre en el Update
            if obj_in.name and obj_in.name.lower() != current_obj.name.lower():
                org_id = user_context.organization_id if user_context and user_context.organization_id is not None else TENANT_ORG_ID.get()
                existing = uow.session.query(Nomenclator).filter(
                    Nomenclator.name.ilike(obj_in.name),
                    Nomenclator.id != obj_id, # Excluir el actual
                    or_(Nomenclator.organization_id == org_id, Nomenclator.organization_id.is_(None))
                ).first()
                
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "name", "message": "Ya existe un nomenclador con este nombre en su empresa o a nivel global."}]
                    )

            # Actualización
            updated_obj = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)
            
            return updated_obj

        return cls._execute(action="Actualizar Nomenclador", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            current_obj = uow.session.query(Nomenclator).filter_by(id=obj_id).first()
            if not current_obj:
                cls._not_found(obj_id)

            # REGLA 1: Protección Anti-Borrado de Globales
            if current_obj.organization_id is None:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No tienes permisos para eliminar nomencladores globales del sistema."}]
                    )

            # Borrado (Soft o Hard dependiendo de la regla de integridad)
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            
            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, current_obj, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id)
            
            return result

        return cls._execute(action="Eliminar nomenclador", obj_id=obj_id, func=do_delete)