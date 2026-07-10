from typing import Optional
from fastapi import HTTPException, status
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from sqlalchemy import func
from app.models.lead_contact_state import LeadContactState
from app.db.repository.lead_contact_state_repository import LeadContactStateRepository
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction

class LeadContactStateService(BaseService):
    repository = LeadContactStateRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            org_id = user_context.organization_id if user_context and getattr(user_context, 'organization_id', None) is not None else TENANT_ORG_ID.get()

            # REGLA: Unicidad del Nombre en SU organización
            if obj_in.name:
                existing = uow.session.query(LeadContactState).filter(
                    LeadContactState.name.ilike(obj_in.name),
                    LeadContactState.organization_id == org_id
                ).first()
                if existing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "name", "message": "Ya existe un estado de contacto con este nombre."}]
                    )
                
            # REGLA: Único estado inicial por organización
            if getattr(obj_in, 'is_initial', False):
                existing_initial = uow.session.query(LeadContactState).filter(
                    LeadContactState.organization_id == org_id,
                    LeadContactState.is_initial == True
                ).first()
                if existing_initial:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "is_initial", "message": "Ya existe un estado inicial en la organización. Desmarque el actual antes de asignar uno nuevo."}]
                    )
                
            max_order = uow.session.query(func.max(cls.repository.model.order)).filter(
                cls.repository.model.organization_id == org_id
            ).scalar()

            # 4. Lógica de incremento: Si max_order es None (no hay estados), da 0. +1 = 1.
            obj_in.order = (max_order or 0) + 1

            new_obj = cls.repository.create(uow.session, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and getattr(user_context, 'user', None) else None
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_id)
            return new_obj

        return cls._execute(action="Crear Estado de Contacto", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            current_obj = uow.session.query(LeadContactState).filter_by(id=obj_id).first()
            if not current_obj:
                cls._not_found(obj_id)

            # org_id se calcula una sola vez acá arriba porque lo usan tanto la Regla 1
            # como la Regla 2, sin importar qué combinación de campos venga en el PUT.
            org_id = user_context.organization_id if user_context and getattr(user_context, 'organization_id', None) is not None else TENANT_ORG_ID.get()

            # REGLA 1: Unicidad en Update
            if obj_in.name and obj_in.name.lower() != current_obj.name.lower():
                existing = uow.session.query(LeadContactState).filter(
                    LeadContactState.name.ilike(obj_in.name),
                    LeadContactState.id != obj_id,
                    LeadContactState.organization_id == org_id
                ).first()
                if existing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "name", "message": "Ya existe un estado de contacto con este nombre."}]
                    )
            
            # REGLA 2: Único estado inicial
            is_initial_in = getattr(obj_in, 'is_initial', None)
            if is_initial_in is True and not current_obj.is_initial:
                existing_initial = uow.session.query(LeadContactState).filter(
                    LeadContactState.organization_id == org_id,
                    LeadContactState.is_initial == True,
                    LeadContactState.id != obj_id
                ).first()
                if existing_initial:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "is_initial", "message": f"El estado '{existing_initial.name}' ya es el inicial. Desmárquelo primero."}]
                    )
            
            # REGLA 3 (Seguridad extra): Evitar que desmarque el único estado inicial
            elif is_initial_in is False and current_obj.is_initial:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "is_initial", "message": "No puede quitar el estado inicial. Asigne otro estado de contacto como inicial primero."}]
                )

            updated_obj = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()
            
            user_id = user_context.user.id if user_context and getattr(user_context, 'user', None) else None
            cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)
            return updated_obj

        return cls._execute(action="Actualizar Estado de Contacto", obj_id=obj_id, func=do_update)