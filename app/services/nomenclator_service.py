from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from app.core.security import UserContext
from app.db.repository.nomenclator_repository import NomenclatorRepository
from app.db.unit_of_work import UnitOfWork
from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction, ADMIN_ORG_ID

class NomenclatorService(BaseService):
    repository = NomenclatorRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            org_id = user_context.organization_id if user_context else None

            # Unicidad del nombre dentro de la org actual y la org admin (datos compartidos)
            if obj_in.name:
                existing = uow.session.query(Nomenclator).filter(
                    Nomenclator.name.ilike(obj_in.name),
                    or_(
                        Nomenclator.organization_id == org_id,
                        Nomenclator.organization_id == ADMIN_ORG_ID,
                    )
                ).first()

                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "name", "message": "Ya existe un nomenclador con este nombre en su empresa o a nivel global."}]
                    )

            new_obj = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()

            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_id)

            return new_obj

        return cls._execute(action="Crear Nomenclador", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            # Hallazgo #25: query cruda sin filtro de tenant. get_by_id sí lo aplica
            # (y en lectura deja pasar nomencladores globales de ADMIN_ORG_ID).
            current_obj = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not current_obj:
                cls._not_found(obj_id)

            # Unicidad del nombre en el update
            if obj_in.name and obj_in.name.lower() != current_obj.name.lower():
                org_id = user_context.organization_id if user_context else None
                existing = uow.session.query(Nomenclator).filter(
                    Nomenclator.name.ilike(obj_in.name),
                    Nomenclator.id != obj_id,
                    or_(
                        Nomenclator.organization_id == org_id,
                        Nomenclator.organization_id == ADMIN_ORG_ID,
                    )
                ).first()

                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "name", "message": "Ya existe un nomenclador con este nombre en su empresa o a nivel global."}]
                    )

            updated_obj = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()

            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)

            return updated_obj

        return cls._execute(action="Actualizar Nomenclador", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            # Hallazgo #25: mismo fix que en update() — ver comentario ahí.
            current_obj = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not current_obj:
                cls._not_found(obj_id)

            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)

            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, current_obj, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id)

            return result

        return cls._execute(action="Eliminar nomenclador", obj_id=obj_id, func=do_delete)