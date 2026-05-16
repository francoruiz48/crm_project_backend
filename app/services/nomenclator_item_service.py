from typing import Optional
from fastapi import HTTPException, status
from app.core.security import UserContext
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
from app.db.unit_of_work import UnitOfWork
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction

class NomenclatorItemService(BaseService):
    repository = NomenclatorItemRepository

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Obtener el padre para validaciones de contexto
            parent_nom = uow.session.query(Nomenclator).filter_by(id=obj_in.nomenclator_id).first()
            if not parent_nom:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "nomenclator_id", "message": "El nomenclador padre no existe."}]
                )

            # REGLA 1: Inyección en Globales
            if parent_nom.organization_id is None:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No puedes agregar items a un nomenclador global sin ser SuperAdmin."}]
                    )

            # REGLA 3: Unicidad del Valor dentro del Nomenclador
            if obj_in.value:
                existing = uow.session.query(NomenclatorItem).filter(
                    NomenclatorItem.nomenclator_id == obj_in.nomenclator_id,
                    NomenclatorItem.value.ilike(obj_in.value)
                ).first()
                
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "value", "message": "Este item ya existe dentro del nomenclador."}]
                    )

            # Creación
            new_item_response = cls.repository.create(uow.session, obj_in, user_context=user_context)
            
            # REGLA A (HERENCIA): Forzar globalidad si el padre es global
            if parent_nom.organization_id is None:
                # Buscamos la instancia real de SQLAlchemy usando el ID
                db_item = uow.session.query(NomenclatorItem).filter_by(id=new_item_response.id).first()
                db_item.organization_id = None
                uow.session.flush()
                uow.session.refresh(db_item)
                
                # Reconstruimos la respuesta Pydantic con los datos actualizados
                new_item_response = cls.repository.schema_out_detail.model_validate(db_item)

            uow.session.flush()
            
            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_item_response, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_id)
            
            return new_item_response

        return cls._execute(action="Crear Item", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            current_item = uow.session.query(NomenclatorItem).filter_by(id=obj_id).first()
            if not current_item:
                cls._not_found(obj_id)

            # REGLA 1: Protección Anti-Escritura de Globales
            if current_item.organization_id is None:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No tienes permisos para modificar items globales."}]
                    )

            # REGLA 2: Unicidad del Valor en Update
            if obj_in.value and obj_in.value.lower() != current_item.value.lower():
                existing = uow.session.query(NomenclatorItem).filter(
                    NomenclatorItem.nomenclator_id == current_item.nomenclator_id,
                    NomenclatorItem.value.ilike(obj_in.value),
                    NomenclatorItem.id != obj_id # Excluir actual
                ).first()
                
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "value", "message": "Este item ya existe dentro del nomenclador."}]
                    )

            # Actualización
            updated_item = cls.repository.update(uow.session, obj_id, obj_in, user_context=user_context)
            uow.session.flush()

            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_item, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)
            
            return updated_item

        return cls._execute(action="Actualizar Item", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None):
        def do_delete(uow):
            current_item = uow.session.query(NomenclatorItem).filter_by(id=obj_id).first()
            if not current_item:
                cls._not_found(obj_id)

            # REGLA 1: Protección Anti-Borrado de Globales
            if current_item.organization_id is None:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No tienes permisos para eliminar items globales."}]
                    )

            # Borrado
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            
            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, current_item, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id)
            
            return result

        return cls._execute(action="Eliminar Item", obj_id=obj_id, func=do_delete)