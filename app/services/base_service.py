from typing import Optional
from app.core.constans import DEFAULT_PAGE_SIZE
from app.core.logger import logger
from app.core.exceptions.exceptions import AppException, NotFoundException
from app.core.error_messages import (
    ERROR_NOT_FOUND, ERROR_DATABASE,
    SUCCESS_CREATE, SUCCESS_UPDATE, SUCCESS_DELETE
)
from app.db.unit_of_work import UnitOfWork
from sqlalchemy.exc import SQLAlchemyError
from app.core.security import UserContext

class BaseService:
    repository = None  # Subclases deben definirlo

    # ---------- helpers internos ----------
    @classmethod
    def _model_name(cls):
        return cls.repository.model.__name__

    @classmethod
    def _not_found(cls, obj_id):
        raise NotFoundException(
            detail=ERROR_NOT_FOUND.format(model=cls._model_name(), id=obj_id)
        )
    
    @classmethod
    def _log_audit(cls, session, obj, action: str, changes: dict = None, user_id: int = None):
        """Helper para registrar la auditoría genérica del sistema."""
        # Evitamos auditar los logs de auditoría o los historiales de leads para no hacer bucles
        ignored_models = ["LeadActivityHistory", "LeadStateHistory", "SystemAuditLog"]
        model_name = cls._model_name()
        
        if model_name in ignored_models:
            return

        from app.models.audit.system_audit_log import SystemAuditLog # Importación tardía para evitar ciclos

        audit = SystemAuditLog(
            organization_id=getattr(obj, "organization_id", None),
            entity_type=model_name,
            entity_id=obj.id,
            action=action,
            changes=changes,
            created_by=user_id
        )
        session.add(audit)

    @classmethod
    def _execute(
        cls,
        *,
        action: str,
        func,
        obj_id: int | None = None,
        success_msg: str | None = None
    ):
        model_name = cls._model_name()
        prefix = f"{model_name}({obj_id})" if obj_id else model_name

        logger.info(f"{action} {prefix}...")

        try:
            with UnitOfWork() as uow:
                result = func(uow)

                if result is None or result is False:
                    if obj_id:
                        cls._not_found(obj_id)

                if success_msg:
                    logger.info(success_msg.format(model=model_name, id=obj_id))

                return result

        except SQLAlchemyError as e:
            logger.error(f"{action} {model_name} falló. Detalle: {str(e)}")
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def get_all(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, only_active: bool = True, detailed: bool = False, search: str = None, **kwargs):
        return cls._execute(
            action=f"Obteniendo listado de {cls.repository.model.__name__}",
            func=lambda uow: cls.repository.get_all(
                session=uow.session,
                user_context=user_context,
                page=page,
                page_size=page_size,
                only_active=only_active,
                detailed=detailed,
                search=search,
                **kwargs
            )
        )

    @classmethod
    def get_by_id(cls, obj_id: int, user_context: Optional[UserContext] = None, detailed: bool = True):
        return cls._execute(
            action="Obteniendo",
            obj_id=obj_id,
            func=lambda uow: cls.repository.get_by_id(uow.session, obj_id, user_context=user_context, detailed=detailed)
        )

    @classmethod
    def create(cls, obj_data, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Guardamos el objeto
            new_obj = cls.repository.create(uow.session, obj_data, user_context=user_context)
            uow.session.flush() # Genera el ID del objeto
            
            # Formateamos el payload que envió el usuario
            payload = cls.repository._normalize_data(obj_data)
            
            # LOG DE AUDITORÍA
            cls._log_audit(uow.session, new_obj, action="CREATE", changes=payload, user_id=user_context.user.id if user_context else None)
            
            return new_obj
            
        return cls._execute(action="Creando", func=do_create, success_msg=SUCCESS_CREATE)

    @classmethod
    def update(cls, obj_id: int, obj_data, user_context: Optional[UserContext] = None):
        def do_update(uow):
            # 1. Obtener el objeto viejo (para comparar qué cambió)
            old_obj = cls.repository.get_by_id(uow.session, obj_id, user_context, detailed=False)
            if not old_obj:
                cls._not_found(obj_id)

            payload = cls.repository._normalize_data(obj_data)
            
            # 2. Armar el diff (viejo vs nuevo)
            changes = {}
            for key, new_val in payload.items():
                if hasattr(old_obj, key):
                    old_val = getattr(old_obj, key)
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}
            
            # 3. Actualizar la base de datos
            updated_obj = cls.repository.update(uow.session, obj_id, payload, user_context=user_context)
            uow.session.flush()
            
            # 4. LOG DE AUDITORÍA (Solo si realmente hubo cambios)
            if changes:
                cls._log_audit(uow.session, updated_obj, action="UPDATE", changes=changes, user_id=user_context.user.id if user_context else None)
            
            return updated_obj

        return cls._execute(action="Actualizando", obj_id=obj_id, func=do_update, success_msg=SUCCESS_UPDATE)

    @classmethod
    def delete(cls, obj_id: int, user_context: Optional[UserContext] = None):
        def do_delete(uow):
            # Necesitamos el objeto antes de borrarlo para tener su organization_id
            obj_to_delete = cls.repository.get_by_id(uow.session, obj_id, user_context, detailed=False)
            if not obj_to_delete:
                cls._not_found(obj_id)
                
            # Ejecutamos el borrado (Físico o Soft)
            result = cls.repository.delete(uow.session, obj_id, user_context=user_context)
            
            # LOG DE AUDITORÍA
            action = "SOFT_DELETE" if result.get("action") == "disabled" else "DELETE"
            cls._log_audit(uow.session, obj_to_delete, action=action, changes=None, user_id=user_context.user.id if user_context else None)
            
            return result

        return cls._execute(action="Eliminando", obj_id=obj_id, func=do_delete, success_msg=SUCCESS_DELETE)

    @classmethod
    def set_active(cls, obj_id: int, user_context: Optional[UserContext] = None):
        def do_activate(uow):
            # 1. Buscamos el objeto para saber su estado actual
            old_obj = cls.repository.get_by_id(uow.session, obj_id, user_context, detailed=False)
            if not old_obj:
                cls._not_found(obj_id)

            was_active = getattr(old_obj, "active", None)

            # 2. Ejecutamos la actualización
            updated_obj = cls.repository.update(uow.session, obj_id, {"active": True}, user_context=user_context)
            
            # 3. LOG DE AUDITORÍA (Solo logueamos si realmente estaba inactivo y lo activamos)
            if was_active is False:
                cls._log_audit(
                    session=uow.session, 
                    obj=updated_obj, 
                    action="ACTIVATE", 
                    changes={"active": {"old": False, "new": True}}, 
                    user_id=user_context.user.id if user_context else None
                )

            return updated_obj

        return cls._execute(
            action="Activando",
            obj_id=obj_id,
            func=do_activate,
            success_msg=SUCCESS_UPDATE
        )
