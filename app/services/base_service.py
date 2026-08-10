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
from app.core.constans import SystemAuditLogAction
from app.core.context import TENANT_ORG_ID

class BaseService:
    repository = None  # Subclases deben definirlo

    # ---------- helpers internos ----------
    @classmethod
    def _model_name(cls):
        return cls.repository.model.__name__ if cls.repository else "General"

    @classmethod
    def _not_found(cls, obj_id):
        raise NotFoundException(
            detail=ERROR_NOT_FOUND.format(model=cls._model_name(), id=obj_id)
        )

    @classmethod
    def _resolve_id(cls, session, obj_uuid: str) -> Optional[int]:
        """
        Traduce el public_uuid (lo único que envía el front) al id interno (int) que
        espera BaseRepository puertas adentro. Único punto de traducción de esta capa
        -- de acá para abajo (repository, y todo el resto del backend) sigue siendo int.
        """
        return cls.repository.get_internal_id_by_public_uuid(session, obj_uuid)

    @classmethod
    def _log_audit(cls, session, obj, action: str, changes: dict = None, user_id: int = None, internal_id: int = None):
        """Helper para registrar la auditoría genérica del sistema."""
        # Evitamos auditar los logs de auditoría o los historiales de leads para no hacer bucles
        ignored_models = ["LeadActivityHistory", "LeadStateHistory", "SystemAuditLog"]
        model_name = cls._model_name()

        if model_name in ignored_models:
            return

        from app.models.audit.system_audit_log import SystemAuditLog # Importación tardía para evitar ciclos

        # `obj` puede ser el modelo ORM crudo (services con create()/update() propios que
        # arman el diff a mano, ej. lead_field_service.py) o el schema Pydantic que devuelven
        # BaseRepository.create()/update() (cls.schema_out_detail.model_validate(...), usado
        # por el flujo genérico y por delete()/deactivate()/set_active() vía get_by_id()).
        # En el ORM crudo, `.id` es el id interno (int) y `.public_uuid` existe como columna
        # real. En el schema Pydantic, `.id` YA es el public_uuid (str, alias de Fase 3) y no
        # expone el id interno en absoluto. Antes esto insertaba el uuid crudo en
        # entity_id (columna Integer) para CUALQUIER create/update -- bug encontrado en el
        # audit de get_by_id, ver backend/AGENTS.md §18-ter. Ahora se guardan ambos: el id
        # interno en entity_id (uso interno) y el uuid real en entity_uuid (lo único que
        # expone la API, ver system_audit_log_schema.py).
        #
        # OJO: distinguir ORM-crudo vs Pydantic con `hasattr(obj, "public_uuid")` es poco
        # confiable -- algunos schemas Response redeclaran `public_uuid` como campo propio
        # además del `id` heredado (ej. WebFormResponse, ver web_form_schema.py), así que un
        # objeto Pydantic también puede tener ese atributo y caer por error en la rama de ORM
        # crudo, insertando el uuid como si fuera el id interno (mismo crash de antes, ver
        # backend/AGENTS.md §18-octies). `_sa_instance_state` es la marca que SQLAlchemy pone
        # en toda instancia mapeada, nunca presente en un modelo Pydantic -- es la forma
        # correcta de detectar "esto es una fila ORM cruda".
        if hasattr(obj, "_sa_instance_state"):
            entity_internal_id = obj.id
            entity_uuid = obj.public_uuid
        else:
            entity_uuid = obj.id
            # Si el caller ya conoce el id interno (ej. lo resolvió antes de borrar la fila en
            # delete()), lo usamos directo. Si no, lo resolvemos por query -- pero OJO: esto
            # falla si la fila ya fue borrada físicamente antes de este punto (devuelve None y
            # `entity_id` NOT NULL revienta, ver backend/AGENTS.md §18-octies). Por eso todos los
            # `delete()` (genérico y overrides) ahora pasan `internal_id` explícito.
            entity_internal_id = internal_id if internal_id is not None else cls.repository.get_internal_id_by_public_uuid(session, obj.id)

        # Si el modelo auditado no tiene organization_id propio (ej. LeadComment,
        # FieldAutomation, TeamMember), la fila de auditoría quedaba con
        # organization_id=NULL y el filtro de tenant de lectura la volvía invisible
        # por API para cualquier organización (ver docs/auditoria.md §7).
        obj_org_id = getattr(obj, "organization_id", None)

        if obj_org_id is None:
            if model_name == "Organization":
                # Caso especial: la propia Organization recién creada/tocada es su
                # mejor "dueña" de auditoría (no depende del header de la request).
                # OJO: organization_id es Integer -- usar entity_internal_id (resuelto
                # arriba), no obj.id (que en el schema Pydantic ya es el uuid público).
                obj_org_id = entity_internal_id
            else:
                # Fallback: la organización activa del request. OJO: system_audit_log.organization_id
                # tiene FK real contra organization.id (no es solo nullable) — X-Organization-Id
                # puede traer un valor que todavía no existe como fila real (ej. al crear una
                # organización nueva, o al promover a superadmin), así que hay que confirmar que
                # exista antes de usarlo, o el INSERT revienta con IntegrityError y aborta la
                # operación completa (bug real detectado en producción el 2026-07-10, ver AGENTS.md).
                candidate_org_id = TENANT_ORG_ID.get()
                if candidate_org_id is not None:
                    from app.models.organization import Organization
                    if session.query(Organization.id).filter_by(id=candidate_org_id).first():
                        obj_org_id = candidate_org_id

        audit = SystemAuditLog(
            organization_id=obj_org_id,
            entity_type=model_name,
            entity_id=entity_internal_id,
            entity_uuid=entity_uuid,
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
        obj_id: str | None = None,
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
    def get_by_id(cls, obj_id: str, user_context: Optional[UserContext] = None, detailed: bool = True):
        def do_get(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                return None
            return cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=detailed)

        return cls._execute(action="Obteniendo", obj_id=obj_id, func=do_get)

    @classmethod
    def create(cls, obj_data, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # Guardamos el objeto
            new_obj = cls.repository.create(uow.session, obj_data, user_context=user_context)
            uow.session.flush() # Genera el ID del objeto
            
            # Formateamos el payload que envió el usuario
            payload = cls.repository._normalize_data(obj_data)
            
            # LOG DE AUDITORÍA
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=payload, user_id=user_context.user.id if user_context else None)
            
            return new_obj
            
        return cls._execute(action="Creando", func=do_create, success_msg=SUCCESS_CREATE)

    @classmethod
    def update(cls, obj_id: str, obj_data, user_context: Optional[UserContext] = None):
        def do_update(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # 1. Obtener el objeto viejo (para comparar qué cambió)
            old_obj = cls.repository.get_by_id(uow.session, internal_id, user_context, detailed=False)
            if not old_obj:
                cls._not_found(obj_id)

            payload = cls.repository._normalize_data(obj_data)
            old_data = cls.repository._normalize_data(old_obj)

            # 2. Armar el diff (viejo vs nuevo)
            # BUG encontrado en el audit de get_by_id (backend/AGENTS.md §18-bis): old_data es un
            # dict (jsonable_encoder), no un objeto -- `hasattr(old_data, key)` sobre un dict
            # nunca es True para los campos reales (solo lo es para métodos de dict como "get"/
            # "items"/"keys", que además devolverían el método en vez del valor). Esto hacía que
            # `changes` diera SIEMPRE vacío y el `if changes:` de más abajo nunca disparara --
            # las acciones UPDATED de cualquier entidad que use este update() genérico (sin
            # override propio) jamás quedaban en el audit log. Se corrige comparando contra las
            # keys del dict.
            changes = {}
            for key, new_val in payload.items():
                if key in old_data:
                    old_val = old_data[key]
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}

            # 3. Actualizar la base de datos
            updated_obj = cls.repository.update(uow.session, internal_id, payload, user_context=user_context)
            uow.session.flush()
            
            # 4. LOG DE AUDITORÍA (Solo si realmente hubo cambios)
            if changes:
                cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=changes, user_id=user_context.user.id if user_context else None, internal_id=internal_id)
            
            return updated_obj

        return cls._execute(action="Actualizando", obj_id=obj_id, func=do_update, success_msg=SUCCESS_UPDATE)

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # Necesitamos el objeto antes de borrarlo para tener su organization_id
            obj_to_delete = cls.repository.get_by_id(uow.session, internal_id, user_context, detailed=False)
            if not obj_to_delete:
                cls._not_found(obj_id)

            # Ejecutamos el borrado (Físico o Soft)
            result = cls.repository.delete(uow.session, internal_id, user_context=user_context, force=force)
            
            # LOG DE AUDITORÍA
            action = SystemAuditLogAction.DISABLED if result.get("action") == "disabled" else SystemAuditLogAction.DELETED
            # internal_id explícito: si fue borrado físico, la fila ya no existe y resolver
            # el id interno por query (uuid -> id) ya no encontraría nada (ver backend/AGENTS.md
            # §18-octies). Como ya lo resolvimos arriba, se lo pasamos directo a _log_audit.
            cls._log_audit(uow.session, obj_to_delete, action=action, changes=None, user_id=user_context.user.id if user_context else None, internal_id=internal_id)
            
            return result

        return cls._execute(action="Eliminando", obj_id=obj_id, func=do_delete, success_msg=SUCCESS_DELETE)
    


    @classmethod
    def deactivate(cls, obj_id: str, user_context: Optional[UserContext] = None):
        """Establece active=False explícitamente (sin borrar el registro)."""
        def do_deactivate(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            obj_to_deactivate = cls.repository.get_by_id(uow.session, internal_id, user_context, detailed=False)
            if not obj_to_deactivate:
                cls._not_found(obj_id)

            result = cls.repository.deactivate(uow.session, internal_id, user_context=user_context)

            cls._log_audit(
                uow.session, obj_to_deactivate,
                action=SystemAuditLogAction.DISABLED,
                changes={"active": {"old": True, "new": False}},
                user_id=user_context.user.id if user_context else None,
                internal_id=internal_id
            )
            return result

        return cls._execute(action="Desactivando", obj_id=obj_id, func=do_deactivate, success_msg=SUCCESS_UPDATE)

    @classmethod
    def bulk_delete(cls, obj_ids: list[str], user_context: Optional[UserContext] = None):
        def do_bulk_delete(uow):
            # 0. Traducimos los UUID públicos a ids internos (los que no existan quedan afuera del mapa)
            uuid_to_id = cls.repository.get_internal_ids_by_public_uuids(uow.session, obj_ids)
            not_found_uuids = [u for u in obj_ids if u not in uuid_to_id]
            internal_ids = list(uuid_to_id.values())

            # 1. Buscamos los objetos ANTES de borrarlos para poder auditar
            objs_query = uow.session.query(cls.repository.model).filter(
                cls.repository.model.id.in_(internal_ids)
            )
            objs_query = cls.repository.apply_security_filter(uow.session, objs_query, user_context)
            objs_query = cls.repository._apply_tenant_filter(objs_query, is_read_operation=False)
            objs_to_delete = objs_query.all()

            if not objs_to_delete:
                return {"deleted": [], "disabled": [], "failed": obj_ids}

            # 2. Ejecutamos la acción masiva en la DB (en ids internos)
            result = cls.repository.bulk_delete(uow.session, internal_ids, user_context=user_context)

            # 3. LOG DE AUDITORÍA
            user_id = user_context.user.id if user_context and user_context.user else None

            for obj in objs_to_delete:
                if obj.id in result["deleted"]:
                    cls._log_audit(uow.session, obj, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id)
                elif obj.id in result["disabled"]:
                    cls._log_audit(uow.session, obj, action=SystemAuditLogAction.DISABLED, changes=None, user_id=user_id)

            # 4. Traducimos el resultado (ids internos) de vuelta a UUID público antes de devolverlo
            id_to_uuid = {v: k for k, v in uuid_to_id.items()}
            return {
                "deleted": [id_to_uuid[i] for i in result["deleted"]],
                "disabled": [id_to_uuid[i] for i in result["disabled"]],
                "failed": [id_to_uuid.get(i, i) for i in result["failed"]] + not_found_uuids,
            }

        return cls._execute(action="Eliminando masivamente", func=do_bulk_delete, success_msg="Operación masiva finalizada.")

    @classmethod
    def set_active(cls, obj_id: str, user_context: Optional[UserContext] = None):
        def do_activate(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # 1. Buscamos el objeto para saber su estado actual
            old_obj = cls.repository.get_by_id(uow.session, internal_id, user_context, detailed=False)
            if not old_obj:
                cls._not_found(obj_id)

            was_active = getattr(old_obj, "active", None)

            # 2. Ejecutamos la actualización
            updated_obj = cls.repository.update(uow.session, internal_id, {"active": True}, user_context=user_context)
            
            # 3. LOG DE AUDITORÍA (Solo logueamos si realmente estaba inactivo y lo activamos)
            if was_active is False:
                cls._log_audit(
                    session=uow.session,
                    obj=updated_obj,
                    action=SystemAuditLogAction.ACTIVATED,
                    changes={"active": {"old": False, "new": True}},
                    user_id=user_context.user.id if user_context else None,
                    internal_id=internal_id
                )

            return updated_obj

        return cls._execute(
            action="Activando",
            obj_id=obj_id,
            func=do_activate,
            success_msg=SUCCESS_UPDATE
        )
    
    @classmethod
    def bulk_set_active(cls, obj_ids: list[str], user_context: Optional[UserContext] = None):
        def do_bulk_activate(uow):
            if not hasattr(cls.repository.model, 'active'):
                raise AppException(detail=f"El modelo {cls._model_name()} no soporta activación.")

            # 0. Traducimos los UUID públicos a ids internos
            uuid_to_id = cls.repository.get_internal_ids_by_public_uuids(uow.session, obj_ids)
            not_found_uuids = [u for u in obj_ids if u not in uuid_to_id]
            internal_ids = list(uuid_to_id.values())

            # 1. Buscamos los objetos
            objs_query = uow.session.query(cls.repository.model).filter(
                cls.repository.model.id.in_(internal_ids)
            )
            objs_query = cls.repository.apply_security_filter(uow.session, objs_query, user_context)
            objs_query = cls.repository._apply_tenant_filter(objs_query, is_read_operation=False)
            objs_to_activate = objs_query.all()

            if not objs_to_activate:
                return {"activated": [], "already_active": [], "failed": obj_ids}

            # 2. Ejecutamos la acción masiva (en ids internos)
            result = cls.repository.bulk_set_active(uow.session, internal_ids, user_context=user_context)

            # 3. LOG DE AUDITORÍA (Solo para los que realmente se activaron)
            user_id = user_context.user.id if user_context and user_context.user else None

            for obj in objs_to_activate:
                if obj.id in result["activated"]:
                    cls._log_audit(
                        session=uow.session,
                        obj=obj,
                        action=SystemAuditLogAction.ACTIVATED,
                        changes={"active": {"old": False, "new": True}},
                        user_id=user_id
                    )

            # 4. Traducimos el resultado de vuelta a UUID público
            id_to_uuid = {v: k for k, v in uuid_to_id.items()}
            return {
                "activated": [id_to_uuid[i] for i in result["activated"]],
                "already_active": [id_to_uuid[i] for i in result["already_active"]],
                "failed": [id_to_uuid.get(i, i) for i in result["failed"]] + not_found_uuids,
            }

        return cls._execute(
            action="Activando masivamente",
            func=do_bulk_activate,
            success_msg="Operación masiva de activación finalizada."
        )
