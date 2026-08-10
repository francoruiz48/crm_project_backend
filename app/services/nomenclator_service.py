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

    # ------------------------------------------------------------------
    # Helpers de la feature "nomencladores dependientes" (múltiples padres
    # válidos por catálogo, ver docs/nomencladores.md).
    # ------------------------------------------------------------------
    @classmethod
    def _resolve_parents(cls, session, parent_ids):
        """Busca los Nomenclator de parent_ids y valida que todos existan.
        No filtra por tenant a propósito: un catálogo de organización puede
        querer declarar como padre a un catálogo global (ADMIN_ORG_ID)."""
        if not parent_ids:
            return []
        parent_ids = list(dict.fromkeys(parent_ids))  # dedup preservando orden
        found = session.query(Nomenclator).filter(Nomenclator.id.in_(parent_ids)).all()
        found_ids = {n.id for n in found}
        missing = [pid for pid in parent_ids if pid not in found_ids]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "parent_nomenclator_ids", "message": f"Los siguientes catálogos padre no existen: {missing}."}]
            )
        return found

    @classmethod
    def _resolve_parent_uuids(cls, session, parent_uuids):
        """Resuelve una lista de public_uuid de Nomenclator (Fase 3, ver
        backend/AGENTS.md §18) a ids internos. No filtra por tenant a propósito
        (mismo motivo que _resolve_parents: un catálogo puede declarar como
        padre a un catálogo global de ADMIN_ORG_ID)."""
        if not parent_uuids:
            return []
        parent_uuids = list(dict.fromkeys(parent_uuids))  # dedup preservando orden
        uuid_to_id = cls.repository.get_internal_ids_by_public_uuids(session, parent_uuids)
        missing = [u for u in parent_uuids if u not in uuid_to_id]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "parent_nomenclator_ids", "message": f"Los siguientes catálogos padre no existen: {missing}."}]
            )
        return [uuid_to_id[u] for u in parent_uuids]

    @classmethod
    def _would_create_cycle(cls, session, node_id, candidate_parent_ids):
        """Devuelve True si asignarle candidate_parent_ids como padres a
        node_id formaría un ciclo (ej. A->B->A). Recorre hacia arriba desde
        cada candidato, revisando si en algún punto se vuelve a node_id."""
        visited = set()
        stack = list(candidate_parent_ids)
        while stack:
            current_id = stack.pop()
            if current_id == node_id:
                return True
            if current_id in visited:
                continue
            visited.add(current_id)
            current = session.query(Nomenclator).filter_by(id=current_id).first()
            if current:
                stack.extend(p.id for p in current.parent_nomenclators)
        return False

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

            # Feature de nomencladores dependientes: un catálogo recién creado
            # no puede formar un ciclo (nada lo referencia todavía), así que acá
            # solo hace falta validar que los padres declarados existan.
            # obj_in.parent_nomenclator_ids llega como lista de public_uuid; se resuelve acá.
            parent_internal_ids = cls._resolve_parent_uuids(uow.session, obj_in.parent_nomenclator_ids)
            parent_objs = cls._resolve_parents(uow.session, parent_internal_ids)

            create_data = obj_in.model_dump(exclude={"parent_nomenclator_ids"}, exclude_unset=True)
            new_obj = cls.repository.create(uow.session, create_data, user_context=user_context)
            uow.session.flush()

            if parent_objs:
                # new_obj.id es el public_uuid (repository.create() devuelve el schema Pydantic,
                # no el ORM crudo) -- se filtra por public_uuid en vez de id. Bug real encontrado
                # 2026-07-28 (mismo patrón que en los demás services): rompía la asignación de
                # padres a un nomenclador recién creado.
                db_obj = uow.session.query(Nomenclator).filter_by(public_uuid=new_obj.id).first()
                db_obj.parent_nomenclators = parent_objs
                uow.session.flush()
                uow.session.refresh(db_obj)
                new_obj = cls.repository.schema_out_detail.model_validate(db_obj)

            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=obj_in.model_dump(), user_id=user_id)

            return new_obj

        return cls._execute(action="Crear Nomenclador", func=do_create)

    @classmethod
    def update(cls, obj_id: str, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # Hallazgo #25: query cruda sin filtro de tenant. get_by_id sí lo aplica
            # (y en lectura deja pasar nomencladores globales de ADMIN_ORG_ID).
            current_obj = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context)
            if not current_obj:
                cls._not_found(obj_id)

            # Unicidad del nombre en el update
            if obj_in.name and obj_in.name.lower() != current_obj.name.lower():
                org_id = user_context.organization_id if user_context else None
                existing = uow.session.query(Nomenclator).filter(
                    Nomenclator.name.ilike(obj_in.name),
                    Nomenclator.id != internal_id,
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

            # Feature de nomencladores dependientes: si viene parent_nomenclator_ids,
            # reemplaza la lista COMPLETA de padres válidos (no hace merge).
            # obj_in.parent_nomenclator_ids llega como lista de public_uuid; se resuelve acá.
            parent_objs = None
            if obj_in.parent_nomenclator_ids is not None:
                parent_internal_ids = cls._resolve_parent_uuids(uow.session, obj_in.parent_nomenclator_ids)
                if internal_id in parent_internal_ids:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "parent_nomenclator_ids", "message": "Un catálogo no puede ser padre de sí mismo."}]
                    )
                if cls._would_create_cycle(uow.session, internal_id, parent_internal_ids):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "parent_nomenclator_ids", "message": "Esa combinación de padres formaría un ciclo entre catálogos."}]
                    )
                parent_objs = cls._resolve_parents(uow.session, parent_internal_ids)

            # parent_nomenclator_ids no es una columna real del modelo (es la
            # relación M2M parent_nomenclators) — se excluye acá para que el
            # update genérico no intente setearla como atributo suelto, y se
            # aplica aparte más abajo si vino.
            update_data = obj_in.model_dump(exclude={"parent_nomenclator_ids"}, exclude_unset=True)
            updated_obj = cls.repository.update(uow.session, internal_id, update_data, user_context=user_context)
            uow.session.flush()

            if parent_objs is not None:
                db_obj = uow.session.query(Nomenclator).filter_by(id=internal_id).first()
                db_obj.parent_nomenclators = parent_objs
                uow.session.flush()
                uow.session.refresh(db_obj)
                updated_obj = cls.repository.schema_out_detail.model_validate(db_obj)

            user_id = user_context.user.id if user_context and user_context.user else None
            cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=obj_in.model_dump(exclude_unset=True), user_id=user_id)

            return updated_obj

        return cls._execute(action="Actualizar Nomenclador", obj_id=obj_id, func=do_update)

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        def do_delete(uow):
            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            # Hallazgo #25: mismo fix que en update() — ver comentario ahí.
            current_obj = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context)
            if not current_obj:
                cls._not_found(obj_id)

            result = cls.repository.delete(uow.session, internal_id, user_context=user_context)

            user_id = user_context.user.id if user_context and user_context.user else None
            # internal_id explícito: si el borrado fue físico, la fila ya no está para resolver
            # uuid->id por query (ver backend/AGENTS.md §18-octies).
            cls._log_audit(uow.session, current_obj, action=SystemAuditLogAction.DELETED, changes=None, user_id=user_id, internal_id=internal_id)

            return result

        return cls._execute(action="Eliminar nomenclador", obj_id=obj_id, func=do_delete)