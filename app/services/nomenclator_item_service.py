from typing import Optional
from fastapi import HTTPException, status
from app.core.security import UserContext
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
from app.db.repository.nomenclator_repository import NomenclatorRepository
from app.db.unit_of_work import UnitOfWork
from app.models.nomenclator import Nomenclator
from app.models.nomenclator_item import NomenclatorItem
from app.services.base_service import BaseService
from app.core.constans import SystemAuditLogAction, ADMIN_ORG_ID

class NomenclatorItemService(BaseService):
    repository = NomenclatorItemRepository

    # ------------------------------------------------------------------
    # Helpers de la feature "nomencladores dependientes" (ver docs/nomencladores.md).
    # ------------------------------------------------------------------
    @classmethod
    def _resolve_and_validate_parent_items(cls, session, item_nomenclator: Nomenclator, parent_item_ids):
        """Busca los NomenclatorItem de parent_item_ids, valida que existan Y
        que cada uno pertenezca a un catálogo que esté declarado como padre
        válido del catálogo de este ítem (item_nomenclator.parent_nomenclators).
        Esto es lo que mantiene coherente el vínculo campo-a-campo con la
        estructura real de catálogos."""
        if not parent_item_ids:
            return []
        parent_item_ids = list(dict.fromkeys(parent_item_ids))
        found = session.query(NomenclatorItem).filter(NomenclatorItem.id.in_(parent_item_ids)).all()
        found_ids = {i.id for i in found}
        missing = [pid for pid in parent_item_ids if pid not in found_ids]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "parent_item_ids", "message": f"Los siguientes ítems padre no existen: {missing}."}]
            )

        allowed_parent_nomenclator_ids = {n.id for n in item_nomenclator.parent_nomenclators}
        invalid = [i for i in found if i.nomenclator_id not in allowed_parent_nomenclator_ids]
        if invalid:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{
                    "field": "parent_item_ids",
                    "message": (
                        f"El ítem '{invalid[0].value}' pertenece al catálogo {invalid[0].nomenclator_id}, "
                        f"que no está declarado como padre válido del catálogo {item_nomenclator.id} "
                        f"('{item_nomenclator.name}'). Agregalo primero a los padres del catálogo."
                    )
                }]
            )
        return found

    @classmethod
    def _resolve_parent_item_uuids(cls, session, parent_uuids):
        """Resuelve una lista de public_uuid de NomenclatorItem (Fase 3, ver
        backend/AGENTS.md §18) a ids internos."""
        if not parent_uuids:
            return []
        parent_uuids = list(dict.fromkeys(parent_uuids))  # dedup preservando orden
        uuid_to_id = cls.repository.get_internal_ids_by_public_uuids(session, parent_uuids)
        missing = [u for u in parent_uuids if u not in uuid_to_id]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "parent_item_ids", "message": f"Los siguientes ítems padre no existen: {missing}."}]
            )
        return [uuid_to_id[u] for u in parent_uuids]

    @classmethod
    def _would_create_cycle(cls, session, node_id, candidate_parent_ids):
        visited = set()
        stack = list(candidate_parent_ids)
        while stack:
            current_id = stack.pop()
            if current_id == node_id:
                return True
            if current_id in visited:
                continue
            visited.add(current_id)
            current = session.query(NomenclatorItem).filter_by(id=current_id).first()
            if current:
                stack.extend(p.id for p in current.parent_items)
        return False

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # obj_in.nomenclator_id llega como public_uuid (Fase 3, ver backend/AGENTS.md
            # §18); se resuelve acá porque las consultas de abajo son crudas.
            nomenclator_internal_id = NomenclatorRepository.get_internal_id_by_public_uuid(uow.session, obj_in.nomenclator_id)

            # Obtener el padre para validaciones de contexto
            parent_nom = uow.session.query(Nomenclator).filter_by(id=nomenclator_internal_id).first() if nomenclator_internal_id is not None else None
            if not parent_nom:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "nomenclator_id", "message": "El nomenclador padre no existe."}]
                )

            # REGLA 1: Inyección en Globales
            if parent_nom.organization_id == ADMIN_ORG_ID:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No puedes agregar items a un nomenclador global sin ser SuperAdmin."}]
                    )

            # REGLA 3: Unicidad del Valor dentro del Nomenclador
            if obj_in.value:
                existing = uow.session.query(NomenclatorItem).filter(
                    NomenclatorItem.nomenclator_id == nomenclator_internal_id,
                    NomenclatorItem.value.ilike(obj_in.value)
                ).first()

                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "value", "message": "Este item ya existe dentro del nomenclador."}]
                    )

            # Feature de nomencladores dependientes: validar padres declarados
            # (existencia + consistencia contra los padres válidos del catálogo).
            # Un ítem recién creado no puede formar un ciclo (nada lo referencia
            # todavía), así que acá no hace falta chequeo de ciclo.
            # obj_in.parent_item_ids llega como lista de public_uuid; se resuelve acá.
            parent_item_internal_ids = cls._resolve_parent_item_uuids(uow.session, obj_in.parent_item_ids)
            parent_item_objs = cls._resolve_and_validate_parent_items(
                uow.session, parent_nom, parent_item_internal_ids
            )

            # Creación (repository.create ya resuelve nomenclator_id de uuid a id interno
            # solo, vía el fix genérico _resolve_fk_payload_fields, pero lo dejamos explícito
            # para no depender de eso).
            create_data = obj_in.model_dump(exclude={"parent_item_ids"}, exclude_unset=True)
            create_data["nomenclator_id"] = nomenclator_internal_id
            new_item_response = cls.repository.create(uow.session, create_data, user_context=user_context)

            # new_item_response.id es el public_uuid (repository.create() devuelve el schema
            # Pydantic, no el ORM crudo) -- se filtra por public_uuid en vez de id. Bug real
            # encontrado 2026-07-28 (mismo patrón que en los demás services): rompía la herencia
            # de globalidad y la asignación de padres a un item recién creado.
            # REGLA A (HERENCIA): Forzar globalidad si el padre es global
            db_item = None
            if parent_nom.organization_id == ADMIN_ORG_ID:
                # Buscamos la instancia real de SQLAlchemy usando el public_uuid
                db_item = uow.session.query(NomenclatorItem).filter_by(public_uuid=new_item_response.id).first()
                db_item.organization_id = ADMIN_ORG_ID

            if parent_item_objs:
                db_item = db_item or uow.session.query(NomenclatorItem).filter_by(public_uuid=new_item_response.id).first()
                db_item.parent_items = parent_item_objs

            if db_item is not None:
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
    def update(cls, obj_id: str, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # Hallazgo #24: query cruda sin filtro de tenant. get_by_id sí lo aplica
            # (y en lectura deja pasar items globales de ADMIN_ORG_ID, que es lo que
            # necesita la REGLA 1 de abajo para detectar si el item es global).
            current_item = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context)
            if not current_item:
                cls._not_found(obj_id)

            # REGLA 1: Protección Anti-Escritura de Globales
            if current_item.organization_id == ADMIN_ORG_ID:
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
                    NomenclatorItem.id != internal_id # Excluir actual
                ).first()

                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "value", "message": "Este item ya existe dentro del nomenclador."}]
                    )

            # Feature de nomencladores dependientes: si viene parent_item_ids,
            # reemplaza la lista COMPLETA de ítems padre (no hace merge).
            parent_item_objs = None
            if obj_in.parent_item_ids is not None:
                # obj_in.parent_item_ids llega como lista de public_uuid; se resuelve acá.
                parent_item_internal_ids = cls._resolve_parent_item_uuids(uow.session, obj_in.parent_item_ids)
                if internal_id in parent_item_internal_ids:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "parent_item_ids", "message": "Un ítem no puede ser padre de sí mismo."}]
                    )
                if cls._would_create_cycle(uow.session, internal_id, parent_item_internal_ids):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "parent_item_ids", "message": "Esa combinación de padres formaría un ciclo entre ítems."}]
                    )
                item_nomenclator = uow.session.query(Nomenclator).filter_by(id=current_item.nomenclator_id).first()
                parent_item_objs = cls._resolve_and_validate_parent_items(
                    uow.session, item_nomenclator, parent_item_internal_ids
                )

            # Actualización
            update_data = obj_in.model_dump(exclude={"parent_item_ids"}, exclude_unset=True)
            updated_item = cls.repository.update(uow.session, internal_id, update_data, user_context=user_context)
            uow.session.flush()

            if parent_item_objs is not None:
                db_item = uow.session.query(NomenclatorItem).filter_by(id=internal_id).first()
                db_item.parent_items = parent_item_objs
                uow.session.flush()
                uow.session.refresh(db_item)
                updated_item = cls.repository.schema_out_detail.model_validate(db_item)

            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_item, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)

            return updated_item

        return cls._execute(action="Actualizar Item", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # Hallazgo #24: mismo fix que en update() — ver comentario ahí.
            current_item = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context)
            if not current_item:
                cls._not_found(obj_id)

            # REGLA 1: Protección Anti-Borrado de Globales
            if current_item.organization_id == ADMIN_ORG_ID:
                if not (user_context and getattr(user_context, 'is_superuser', False)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=[{"field": "general", "message": "No tienes permisos para eliminar items globales."}]
                    )

            # Borrado
            result = cls.repository.delete(uow.session, internal_id, user_context=user_context)
            
            # Auditoría
            user_id = user_context.user.id if user_context and user_context.user else None
            # internal_id explícito: si el borrado fue físico, la fila ya no está para resolver
            # uuid->id por query (ver backend/AGENTS.md §18-octies).
            cls._log_audit(uow.session, current_item, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id, internal_id=internal_id)
            
            return result

        return cls._execute(action="Eliminar Item", obj_id=obj_id, func=do_delete)