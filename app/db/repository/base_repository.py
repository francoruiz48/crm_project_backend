import re
from typing import Dict, Any, Optional
from math import ceil
from sqlalchemy.orm import selectinload
from app.core.exceptions.exceptions import AppException, NotFoundException
from app.core.constans import DeleteStrategy, ADMIN_ORG_ID
from app.core.error_messages import ERROR_DATABASE, ERROR_NOT_FOUND
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, inspect, or_, distinct
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext
from fastapi.encoders import jsonable_encoder

class BaseRepository:
    model = None
    schema_out = None
    schema_out_detail = None
    relationships: list = []
    default_sort_column = "id"
    default_sort_asc = False

    # --- Delete Strategy ---
    # Ver DeleteStrategy en app/core/constans.py para documentación de cada variante.
    delete_strategy: str = DeleteStrategy.HARD_DELETE_ALWAYS
    delete_blockers: list = []   # relaciones que BLOQUEAN el hard delete (Variante E)

    # ===============================================================
    # Inyección automática de Tenant (Multi-empresa)
    # ===============================================================
    @classmethod
    def _apply_tenant_filter(cls, query, is_read_operation: bool = True):
        """
        is_read_operation:
          - True (Lectura): Trae registros del tenant actual O de la org admin (datos compartidos).
          - False (Escritura): Trae SOLO registros del tenant actual (nunca toca la org admin).
        """

        if hasattr(cls.model, "organization_id"):

            org_id = TENANT_ORG_ID.get()

            if org_id is not None:
                if is_read_operation:
                    # LECTURA: Ve los suyos + los de la org admin (nomencladores globales, etc.)
                    # Si ya estamos en la org admin, el OR es redundante pero correcto.
                    query = query.filter(
                        or_(
                            cls.model.organization_id == org_id,
                            cls.model.organization_id == ADMIN_ORG_ID,
                        )
                    )
                else:
                    # ESCRITURA: Solo puede tocar sus propios registros.
                    query = query.filter(cls.model.organization_id == org_id)

        return query

    # ----------------- Helpers internos -----------------
    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext):
        """
        MÉTODO HOOK (Template Method).
        Los repositorios hijos deben sobrescribir este método para inyectar 
        su lógica de seguridad específica (La Bóveda).
        Por defecto, devuelve la query intacta.
        """
        return query
    
    @classmethod
    def _paginate(cls, query, page: int = 0, page_size: int = 0):
        """
        Aplica paginación y devuelve (total, query_paginada).
        Si page o page_size son 0/None, devuelve (total, query_original).
        """
        # Usar COUNT(DISTINCT id) para no inflar el total cuando hay JOINs que duplican filas
        # (ej: filtros EAV que hacen JOIN sobre lead_field_values)
        total = query.order_by(False).with_entities(func.count(distinct(cls.model.id))).scalar()

        if page_size > 0:
            total_pages = ceil(total / page_size)
        else:
            total_pages = 0

        if page> total_pages and total_pages > 0:
            page = total_pages

        if page and page > 0 and page_size and page_size > 0:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
        
        return total, query
    
    @classmethod
    def _execute_read_query(cls, query, detailed: bool = False):
        """
        Ejecuta una query de lectura aplicando:
        1. Relaciones (si detailed=True)
        2. Manejo de Errores (Try/Except genérico)
        3. Conversión a Esquema Pydantic
        """
        try:
            # A. Aplicar relaciones si es detailed
            if detailed and cls.relationships:
                query = cls._apply_relationships(query)

            # B. Ejecutar
            result = query.all()

            # C. Seleccionar esquema
            selected_schema = (
                cls.schema_out_detail 
                if detailed and cls.schema_out_detail 
                else cls.schema_out
            )

            # D. Convertir
            return [selected_schema.model_validate(obj) for obj in result] if selected_schema else result

        except Exception as e:
            # Aquí mantenemos la consistencia del manejo de errores
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))
        
    @classmethod
    def _apply_relationships(cls, query):
        """
        Aplica relaciones al query. Soporta dos formatos en cls.relationships:
        1. Listas/Tuplas: [User.roles, Role.permissions] -> Genera selectinload en cadena.
        2. SQLAlchemy Options: selectinload(User.roles).selectinload(Role.permissions) -> Se aplica directo.
        """
        for item in cls.relationships:
            # CASO 1: Es una lista o tupla (Tu lógica original "automática")
            if isinstance(item, (list, tuple)):
                if not item:
                    continue
                # Iniciamos la cadena con el primer elemento
                option = selectinload(item[0])
                # Encadenamos el resto
                for rel in item[1:]:
                    option = option.selectinload(rel)
                query = query.options(option)
            
            # CASO 2: Es una opción directa de SQLAlchemy (Estrategia Avanzada)
            # Esto permite pasar 'selectinload(User.roles).selectinload(Role.permissions)'
            # o incluso 'joinedload(User.profile)'
            else:
                query = query.options(item)
                
        return query

    @staticmethod
    def _normalize_data(obj_data) -> Dict[str, Any]:
        """
        Convierte obj_data a dict puramente nativo (compatible con Postgres JSONB).
        Utiliza jsonable_encoder para asegurar un 'deep dump' que transforma 
        Enums, Datetimes y modelos Pydantic anidados en tipos primitivos puros.
        """
        if obj_data is None:
            return {}
            
        # jsonable_encoder hace todo el trabajo sucio automáticamente, 
        # sin importar si es Pydantic V1, V2, o un simple diccionario.
        return jsonable_encoder(obj_data, exclude_unset=True)
    
    @staticmethod
    def _handle_integrity_error(e: IntegrityError):
        """
        Parsea el error de base de datos para dar un mensaje legible.
        Ej original: Key (campaign_id)=(99) is not present in table "campaign".
        """
        error_msg = str(e.orig) # Obtenemos el error original del driver (psycopg2)
        
        # Buscamos el patrón: Key (nombre_campo)=(valor)
        # Esto funciona estándar en Postgres
        match = re.search(r'Key \((.*?)\)=\((.*?)\)', error_msg)
        
        if match and "is not present in table" in error_msg:
            field_name = match.group(1)
            value = match.group(2)
            detail = f"El valor '{value}' para el campo '{field_name}' no existe en la base de datos relacionada."
            raise AppException(detail=detail)
        if match and "already exists" in error_msg:
            field_name = match.group(1)
            detail = f"Ya existe un registro con el campo '{field_name}' igual a los datos proporcionados."
            raise AppException(detail=detail)
        if "update or delete on table" in error_msg and "violates foreign key constraint" in error_msg:
            match_table = re.search(r'on table "(.*?)"', error_msg)
            table_name = match_table.group(1) if match_table else "otra entidad"            
            detail = f"No se puede eliminar el registro porque está siendo utilizado en '{table_name}'."
            raise AppException(detail=detail)

        match_fk = re.search(r'Key \((.*?)\)=\((.*?)\) is not present in table', error_msg)
        if match_fk:
            field_name = match_fk.group(1)
            value = match_fk.group(2)
            raise AppException(detail=f"El valor '{value}' para '{field_name}' no existe.")

        match_dup = re.search(r'Key \((.*?)\)=\((.*?)\) already exists', error_msg)
        if match_dup:
            field_name = match_dup.group(1)
            value = match_dup.group(2)
            raise AppException(detail=f"Ya existe un registro con {field_name}='{value}'.")
        raise AppException(detail="Error de integridad de datos en la base de datos.")

    # ----------------- CRUD Genérico -----------------
    @classmethod
    def get_all(cls, session, user_context: Optional[UserContext] = None, only_active: bool = True, detailed: bool = False, base_query=None, **kwargs):
        """
        Trae todos los objetos con filtros dinámicos.
        Cualquier argumento extra (ej: campaign_id=1) se aplica como filtro "=" 
        si el modelo tiene ese atributo.
        """

        query = base_query if base_query is not None else session.query(cls.model)

        query = cls.apply_security_filter(session, query, user_context)

        query = cls._apply_tenant_filter(query)
            
        # 1. Filtro 'active' (Soft Delete)
        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        # 2. Filtros Dinámicos (kwargs)
        # Extraemos page/page_size primero para no confundirlos con columnas
        page = kwargs.pop('page', 0)
        page_size = kwargs.pop('page_size', 0)

        #Parametros de ordenamiento
        order_by = kwargs.pop('order_by', None)
        ascending = kwargs.pop('ascending', True)

        # Extraemos parámetros especiales de búsqueda
        search_query = kwargs.pop('search', None)
        search_fields = kwargs.pop('search_fields', [])

        start_date = kwargs.pop('start_date', None)
        end_date = kwargs.pop('end_date', None)
        date_field = kwargs.pop('date_field', 'created_at')

        if (start_date or end_date) and date_field and hasattr(cls.model, date_field):
            column = getattr(cls.model, date_field)
            if start_date:
                query = query.filter(column >= start_date)
            if end_date:
                end_date_str = end_date
                # Si envían solo la fecha (ej: "2026-05-14"), le sumamos la hora tope 
                # para que abarque todo el día completo y no corte a las 00:00:00.
                if len(end_date_str) == 10:
                    end_date_str += " 23:59:59.999999"
                query = query.filter(column <= end_date_str)

        creator_name = kwargs.pop('creator_name', None)
        creator_email = kwargs.pop('creator_email', None)
        updater_name = kwargs.pop('updater_name', None)
        updater_email = kwargs.pop('updater_email', None)
        # Filtro combinado: busca con OR entre nombre, apellido, email y "nombre apellido"
        # concatenado, en vez de exigir que el mismo texto matchee un único campo (como
        # pasaba con creator_name/creator_email por separado, que además se combinaban con
        # AND). Pensado para pantallas de auditoría, donde el usuario puede no acordarse si
        # buscaba por nombre, apellido o email — o el nombre pudo haber cambiado desde que
        # se generó el registro.
        creator_search = kwargs.pop('creator_search', None)
        updater_search = kwargs.pop('updater_search', None)

        if creator_name or creator_email or creator_search:
            # Importación local para evitar dependencias circulares en la inicialización
            from app.models.security_models import User

            # Hacemos un OUTER JOIN con la tabla de usuarios
            query = query.outerjoin(User, cls.model.created_by == User.id)

            if creator_name:
                query = query.filter(User.name.ilike(f"%{creator_name}%"))
            if creator_email:
                query = query.filter(User.email.ilike(f"%{creator_email}%"))
            if creator_search:
                like = f"%{creator_search}%"
                full_name = func.concat(User.name, ' ', User.last_name)
                query = query.filter(or_(
                    User.name.ilike(like),
                    User.last_name.ilike(like),
                    User.email.ilike(like),
                    full_name.ilike(like)
                ))

        if updater_name or updater_email or updater_search:
            from app.models.security_models import User

            query = query.outerjoin(User, cls.model.updated_by == User.id)

            if updater_name:
                query = query.filter(User.name.ilike(f"%{updater_name}%"))
            if updater_email:
                query = query.filter(User.email.ilike(f"%{updater_email}%"))
            if updater_search:
                like = f"%{updater_search}%"
                full_name = func.concat(User.name, ' ', User.last_name)
                query = query.filter(or_(
                    User.name.ilike(like),
                    User.last_name.ilike(like),
                    User.email.ilike(like),
                    full_name.ilike(like)
                ))

        for key, value in kwargs.items():
            if value is None:
                continue

            # Verificamos si la clave tiene el sufijo magico "__ilike"
            if "__ilike" in key:
                field_name = key.replace("__ilike", "") # Obtenemos el nombre real del campo
                print("ENTRE")
                if hasattr(cls.model, field_name):
                    column = getattr(cls.model, field_name)
                    # Aplicamos ilike con % automático para que sea "contiene"
                    query = query.filter(column.ilike(f"%{value}%"))
            
            # Comportamiento normal (Igualdad exacta)
            elif hasattr(cls.model, key):
                # Si `key` es una FK real (ej. campaign_id) y `value` viene como public_uuid
                # (el front ya no conoce el id interno), se resuelve acá antes de filtrar.
                # Ver resolve_fk_filter_value más abajo para el detalle.
                resolved_value = cls.resolve_fk_filter_value(session, key, value)
                query = query.filter(getattr(cls.model, key) == resolved_value)

        # Lógica para Búsqueda Global (OR)
        if search_query and search_fields:
            search_conditions = []
            for field in search_fields:
                if hasattr(cls.model, field):
                    column = getattr(cls.model, field)
                    # Preparamos la condición ILIKE
                    search_conditions.append(column.ilike(f"%{search_query}%"))
            
            # Si encontramos campos válidos, aplicamos un OR (uno u otro)
            if search_conditions:
                query = query.filter(or_(*search_conditions))

        # Si el Frontend NO envió un campo específico por el cual ordenar...
        if not order_by:
            order_by = cls.default_sort_column
            # Usamos la dirección por defecto del repositorio si no enviaron una
            if ascending is None:
                ascending = cls.default_sort_asc
        else:
            # Si el Frontend SÍ envió un campo (ej: order_by=name), pero no la dirección,
            # por convención general de APIs asumimos ascendente.
            if ascending is None:
                ascending = True

        if order_by and hasattr(cls.model, order_by):
            column = getattr(cls.model, order_by)
            # Aplicamos asc() o desc() según el flag
            query = query.order_by(column.asc() if ascending else column.desc())
        elif hasattr(cls.model, 'id'):
                query = query.order_by(cls.model.id.desc())

        # 3. Paginación y Ejecución
        total, query = cls._paginate(query, page, page_size)
        items = cls._execute_read_query(query, detailed)
        
        if page:
            return total, items
        return items

    # ----------------- Resolución de ID público (UUID) -----------------
    # El front solo conoce `public_uuid`; el resto de este archivo (y de los ~120
    # usos internos en los services, que resuelven FKs entre entidades) sigue
    # trabajando 100% con el `id` interno (int). Estos dos métodos son el único
    # punto de traducción UUID -> int, pensados para usarse en el borde de la API
    # (BaseService), nunca dentro de la lógica de negocio interna.
    @classmethod
    def get_internal_id_by_public_uuid(cls, session, public_uuid: str) -> Optional[int]:
        """Resuelve un public_uuid al id interno. None si no existe ninguna fila con ese UUID."""
        row = session.query(cls.model.id).filter(cls.model.public_uuid == public_uuid).first()
        return row[0] if row else None

    @classmethod
    def get_internal_ids_by_public_uuids(cls, session, public_uuids: list) -> Dict[str, int]:
        """Versión bulk: {public_uuid: id_interno} solo para los que existen."""
        if not public_uuids:
            return {}
        rows = session.query(cls.model.public_uuid, cls.model.id).filter(cls.model.public_uuid.in_(public_uuids)).all()
        return {row[0]: row[1] for row in rows}

    # ----------------- Resolución de FKs embebidas en filtros (Fase 3, parte de Fase 4 adelantada) -----------------
    # El front ahora solo conoce public_uuid, así que un filtro tipo ?campaign_id=<uuid>
    # (usado en GET_ALL de cualquier módulo, ej. GET /lead_fields?campaign_id=...) llega
    # con un UUID en vez del id interno que espera la columna FK real. Este helper genérico
    # resuelve cualquier columna FK por convención de SQLAlchemy (mira las foreign_keys
    # reales de la columna, no un mapa hardcodeado por nombre), sin necesidad de listar
    # a mano qué modelo referencia cada `*_id`. Se usa en get_all() de acá abajo, y lo pueden
    # llamar directo los repos con filtros custom (ej. LeadRepository.search()).
    _MISSING_FK_SENTINEL = -1  # id interno que nunca va a existir -> el filtro no matchea nada

    @classmethod
    def resolve_fk_filter_value(cls, session, column_name: str, value):
        """
        Si `value` ya es un id interno (int, o string numérica), lo devuelve tal cual.
        Si es un string no-numérico (asumimos public_uuid) y `column_name` es una FK real
        de cls.model, resuelve al id interno de la tabla referenciada. Si no se encuentra
        la fila, devuelve un sentinel que no matchea nada (en vez de dejar pasar el UUID
        crudo, que rompería con un error de tipo en la query SQL).
        """
        if value is None or isinstance(value, int):
            return value
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return int(value)
        if not isinstance(value, str):
            return value

        if not hasattr(cls.model, column_name):
            return value

        try:
            column = getattr(cls.model, column_name).property.columns[0]
        except Exception:
            return value

        if not column.foreign_keys:
            return value

        target_table = next(iter(column.foreign_keys)).column.table

        from app.db.base_sql import Base
        target_model = next(
            (m.class_ for m in Base.registry.mappers if m.class_.__tablename__ == target_table.name),
            None
        )
        if target_model is None or not hasattr(target_model, "public_uuid"):
            return value

        row = session.query(target_model.id).filter(target_model.public_uuid == value).first()
        return row[0] if row else cls._MISSING_FK_SENTINEL

    @classmethod
    def _resolve_fk_payload_fields(cls, session, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resuelve FKs embebidas en un payload de create/update (ej. campaign_id, team_id)
        de public_uuid a id interno, reusando resolve_fk_filter_value. Se llama desde
        create()/update() de acá abajo, sobre el dict ya normalizado (_normalize_data).

        A diferencia de los filtros de get_all, acá NO usamos el sentinel silencioso
        (-1) si el UUID no existe: dejamos pasar el valor original para que la FK real
        de Postgres lo rechace en el INSERT/UPDATE con un mensaje claro vía
        _handle_integrity_error, en vez de persistir -1 silenciosamente.

        OJO: esto solo alcanza a columnas FK reales de cls.model. Varios servicios con
        create()/update() propios (Lead, FieldAutomation, etc.) validan estos campos
        ANTES de llegar acá (ej. comparando obj_data.campaign_id contra Campaign.id a
        mano) y necesitan su propio fix -- ver backend/AGENTS.md para el catálogo de
        pendientes.
        """
        resolved = dict(data)
        for key, value in data.items():
            if value is None or not hasattr(cls.model, key):
                continue
            new_value = cls.resolve_fk_filter_value(session, key, value)
            if new_value == cls._MISSING_FK_SENTINEL:
                continue
            resolved[key] = new_value
        return resolved

    @classmethod
    def get_by_id(cls, session, obj_id: int, user_context: Optional[UserContext] = None, only_active: bool = False, detailed: bool = False):
        """
        Trae un objeto por id.
        Si detailed=True, carga relaciones y usa schema_out_detail.

        HISTORIAL: hasta 2026-07-28 este método ignoraba `detailed` para elegir el schema
        -- siempre devolvía schema_out_detail (solo el eager-load de relaciones estaba
        condicionado). Rompió puntualmente 3 call sites que leían `.creator`/`.updater`
        pasando detailed=False (o sin pasar nada, el default), porque ese acceso solo
        funcionaba DE CASUALIDAD gracias al bug (ver backend/AGENTS.md §18-bis/§18-ter).
        Al arreglarlo acá para que de verdad respete `detailed` (mismo criterio que
        _execute_read_query, usado por get_all), esos 3 call sites se actualizaron para
        pasar detailed=True explícito (campaign_service.py, lead_comment_service.py,
        lead_view_service.py) -- auditado el resto de los ~50 call sites de get_by_id en
        app/services sin encontrar otro caso que dependiera del bug (ver AGENTS.md).
        """
        try:

            query = session.query(cls.model)

            query = cls.apply_security_filter(session, query, user_context)

            query = cls._apply_tenant_filter(query)

            if detailed and cls.relationships:
                query = cls._apply_relationships(query)

            if only_active and hasattr(cls.model, "active"):
                query = query.filter(cls.model.active.is_(True))

            obj = query.filter(cls.model.id == obj_id).first()

            if not obj:
                return None

            selected_schema = (
                cls.schema_out_detail
                if detailed and cls.schema_out_detail
                else cls.schema_out
            )
            return selected_schema.model_validate(obj) if selected_schema else obj

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def create(cls, session, obj_data=None, user_context: Optional[UserContext] = None,):
        """Crea un objeto"""
        try:
            created_by = None
            is_super_admin = False
            is_owner = False
            
            if user_context is not None:
                created_by = user_context.user.id
                is_super_admin = user_context.is_superuser
                is_owner = user_context.is_owner

            data = cls._normalize_data(obj_data)
            data = cls._resolve_fk_payload_fields(session, data)

            if hasattr(cls.model, "organization_id"):
                org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()
                if org_id is not None:
                    data["organization_id"] = org_id

            if created_by is not None and hasattr(cls.model, "created_by"):
                data["created_by"] = created_by

            obj = cls.model(**data)
            session.add(obj)
            session.flush()  # flush para obtener ID antes de commit
            session.refresh(obj)
            return cls.schema_out_detail.model_validate(obj)

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def update(cls, session, obj_id: int, obj_data, user_context: Optional[UserContext] = None,):
        """Actualiza un objeto por id"""
        try:
            updated_by = None
            is_super_admin = False
            is_owner = False
            
            if user_context is not None:
                updated_by = user_context.user.id
                is_super_admin = user_context.is_superuser
                is_owner = user_context.is_owner

            data = cls._normalize_data(obj_data)
            data = cls._resolve_fk_payload_fields(session, data)
            query = session.query(cls.model).filter(cls.model.id == obj_id)
            # PASAMOS FALSE: Para asegurar que no pueda editar un registro global (NULL)
            query = cls._apply_tenant_filter(query, is_read_operation=False)
            obj = query.first()
            if not obj:
                return None
            
            if updated_by is not None and hasattr(cls.model, "updated_by"):
                data["updated_by"] = updated_by

            # IMPORTANTE: Prevenir que el usuario transfiera objetos a otra organización
            if "organization_id" in data:
                del data["organization_id"]

            for key, value in data.items():
                setattr(obj, key, value)

            session.flush()
            session.refresh(obj)
            return cls.schema_out_detail.model_validate(obj)

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    # ==========================================
    # HELPERS DE BORRADO
    # ==========================================
    @classmethod
    def _do_soft_delete(cls, session, obj, updated_by=None) -> Dict[str, str]:
        """Establece active=False. Retorna {"action": "disabled"}."""
        obj.active = False
        if updated_by is not None and hasattr(obj, "updated_by"):
            obj.updated_by = updated_by
        session.add(obj)
        session.flush()
        return {"action": "disabled"}

    @classmethod
    def _do_hard_delete(cls, session, obj) -> Dict[str, str]:
        """Elimina físicamente. Lanza AppException si hay FK violation."""
        try:
            with session.begin_nested():
                session.delete(obj)
                session.flush()
            return {"action": "deleted"}
        except IntegrityError as e:
            cls._handle_integrity_error(e)
        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def _check_blockers(cls, session, obj) -> list:
        """
        Verifica si hay registros en las relaciones de delete_blockers.
        Retorna lista de dicts {"relation": ..., "count": ...} para los que tienen hijos.
        """
        from sqlalchemy import inspect as sa_inspect
        blocked_by = []
        inst = sa_inspect(type(obj))
        for rel_name in cls.delete_blockers:
            if rel_name not in inst.relationships:
                continue
            rel_prop = inst.relationships[rel_name]
            child_model = rel_prop.mapper.class_
            pairs = rel_prop.synchronize_pairs
            if not pairs:
                continue
            local_col, remote_col = pairs[0]
            parent_val = getattr(obj, local_col.key)
            count = session.query(func.count()).select_from(child_model).filter(
                remote_col == parent_val
            ).scalar() or 0
            if count > 0:
                blocked_by.append({"relation": rel_name, "count": count})
        return blocked_by

    @classmethod
    def delete(cls, session, obj_id: int, user_context: Optional[UserContext] = None, force: bool = False) -> Dict[str, str]:
        """
        Elimina un objeto según la estrategia configurada en delete_strategy:
          HARD_DELETE_ALWAYS:      hard delete siempre
          SOFT_DELETE_ALWAYS:      soft delete siempre
          SOFT_DELETE_HARD_OPT:    soft por defecto, hard con force=True
          PROTECTED:               nunca borrable
          SMART_DELETE:            auto: sin blockers → hard delete, con blockers → soft delete
          HARD_DELETE_WITH_TOGGLE: hard delete (deactivate via endpoint separado)
        """
        strategy = cls.delete_strategy
        updated_by = user_context.user.id if user_context and user_context.user else None

        # D: Protegido
        if strategy == DeleteStrategy.PROTECTED:
            raise AppException(detail="Este registro está protegido y no puede ser eliminado.")

        query = session.query(cls.model).filter(cls.model.id == obj_id)
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        obj = query.first()
        if not obj:
            raise NotFoundException(detail=f"{cls.model.__name__} no encontrado.")

        # B: Siempre soft delete
        if strategy == DeleteStrategy.SOFT_DELETE_ALWAYS:
            return cls._do_soft_delete(session, obj, updated_by)

        # A: Hard delete, 409 si FK violation
        if strategy == DeleteStrategy.HARD_DELETE_ALWAYS:
            return cls._do_hard_delete(session, obj)

        # F: Hard delete (el toggle se maneja via deactivate())
        if strategy == DeleteStrategy.HARD_DELETE_WITH_TOGGLE:
            return cls._do_hard_delete(session, obj)

        # C: Soft por defecto, hard con force=True
        if strategy == DeleteStrategy.SOFT_DELETE_HARD_OPT:
            if not force:
                return cls._do_soft_delete(session, obj, updated_by)
            return cls._do_hard_delete(session, obj)

        # E: Auto-detect: sin blockers → hard delete, con blockers → soft delete
        if strategy == DeleteStrategy.SMART_DELETE:
            blocked = cls._check_blockers(session, obj)
            if not blocked:
                return cls._do_hard_delete(session, obj)
            return cls._do_soft_delete(session, obj, updated_by)

        # Fallback
        return cls._do_hard_delete(session, obj)

    @classmethod
    def deactivate(cls, session, obj_id: int, user_context: Optional[UserContext] = None) -> Dict[str, str]:
        """
        Establece active=False explícitamente.
        Disponible para estrategias B, C, E, F (cualquier entidad con campo active).
        """
        if not hasattr(cls.model, "active"):
            raise AppException(detail=f"{cls.model.__name__} no soporta desactivación.")
        updated_by = user_context.user.id if user_context and user_context.user else None
        query = session.query(cls.model).filter(cls.model.id == obj_id)
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        obj = query.first()
        if not obj:
            raise NotFoundException(detail=f"{cls.model.__name__} no encontrado.")
        return cls._do_soft_delete(session, obj, updated_by)

    # ----------------- Upsert relaciones One-to-Many -----------------
    @classmethod
    def upsert_children(
        cls,
        session,
        parent_model,
        parent_id: int,
        relation_name: str,
        items,
        key_attr: str,
        create_fn,
    ):
        try:
            # 1. Buscar al padre aplicando Tenant Filter
            parent_query = session.query(parent_model).filter(parent_model.id == parent_id)
            if hasattr(parent_model, "organization_id"):
                org_id = TENANT_ORG_ID.get()
                if org_id is not None:
                    parent_query = parent_query.filter(parent_model.organization_id == org_id)
            
            parent = parent_query.first()
            
            if not parent:
                raise NotFoundException(
                    detail=ERROR_NOT_FOUND.format(
                        model=parent_model.__name__, id=parent_id
                    )
                )

            children = getattr(parent, relation_name)
            
            existing = {str(getattr(c, key_attr)): c for c in children}

            for item in items:
                raw_key = getattr(item, key_attr)
                key = str(raw_key)
                
                # OJO: Aquí NO inyectamos el tenant al crear el hijo de forma automática, 
                # porque create_fn (lambda) o la relación de SQLAlchemy se encargará 
                # de propagar el organization_id / parent_id según cómo esté mapeado.
                
                if key in existing:
                    child_obj = existing[key]
                    
                    item_dict = item.dict()
                    if "organization_id" in item_dict:
                        del item_dict["organization_id"]

                    for attr, value in item_dict.items():
                        setattr(child_obj, attr, value)
                    
                    session.add(child_obj)
                else:
                    child = create_fn(item)
                    children.append(child)
                    session.add(child) 
            
            session.flush()
            session.refresh(parent)
        
        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)

        except Exception as e:
            session.rollback()
            if isinstance(e, AppException):
                raise e
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))
        
    @classmethod
    def bulk_delete(cls, session, obj_ids: list[int], user_context: Optional[UserContext] = None) -> Dict[str, list]:
        """
        Elimina masivamente un listado de IDs.
        Aplica la misma lógica de Soft Delete que la eliminación individual en caso de fallo.
        """
        # Hallazgo (2026-07-11): a diferencia de delete() (single), este método no
        # chequeaba delete_strategy == PROTECTED antes de hacer session.delete(obj)
        # más abajo — permitía bypasear por completo la protección vía el endpoint
        # masivo. Ver AGENTS.md / hallazgos_agente/organizaciones.md (hallazgo #15,
        # el caso concreto detectado fue POST /organizations/bulk-delete).
        if cls.delete_strategy == DeleteStrategy.PROTECTED:
            return {"deleted": [], "disabled": [], "failed": list(obj_ids)}

        updated_by = None
        if user_context is not None and user_context.user is not None:
            updated_by = user_context.user.id

        # 1. Buscamos los objetos que realmente existen y le pertenecen a la empresa
        query = session.query(cls.model).filter(cls.model.id.in_(obj_ids))
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        objs = query.all()

        results = {"deleted": [], "disabled": [], "failed": []}

        # 2. Separar los que no se encontraron (o no tienen permisos)
        valid_ids = [obj.id for obj in objs]
        for requested_id in obj_ids:
            if requested_id not in valid_ids:
                results["failed"].append(requested_id)

        if not objs:
            return results

        # 3. Iteramos aplicando transacciones anidadas (Savepoints)
        for obj in objs:
            obj_id = obj.id
            try:
                # begin_nested() crea un SAVEPOINT. Si falla, hace rollback SOLO de este objeto.
                with session.begin_nested():
                    session.delete(obj)
                    session.flush()
                results["deleted"].append(obj_id)

            except (IntegrityError, AppException) as e:
                # Ocurrió un error. Aplicamos estrategia: si es B/C/E intentamos soft delete.
                strategy = cls.delete_strategy
                obj_fresh = session.get(cls.model, obj_id)
                if obj_fresh and hasattr(obj_fresh, 'active') and strategy in (DeleteStrategy.SOFT_DELETE_ALWAYS, DeleteStrategy.SOFT_DELETE_HARD_OPT, DeleteStrategy.SMART_DELETE, DeleteStrategy.HARD_DELETE_WITH_TOGGLE):
                    obj_fresh.active = False
                    if updated_by is not None and hasattr(cls.model, "updated_by"):
                        obj_fresh.updated_by = updated_by
                    session.add(obj_fresh)
                    session.flush()
                    session.refresh(obj_fresh)
                    results["disabled"].append(obj_id)
                else:
                    results["failed"].append(obj_id)

        return results
    

    @classmethod
    def bulk_set_active(cls, session, obj_ids: list[int], user_context: Optional[UserContext] = None) -> Dict[str, list]:
        """
        Activa masivamente un listado de IDs.
        """
        updated_by = None
        if user_context is not None and user_context.user is not None:
            updated_by = user_context.user.id

        results = {"activated": [], "already_active": [], "failed": []}

        # Verificamos tempranamente si el modelo soporta la columna 'active'
        if not hasattr(cls.model, 'active'):
            results["failed"] = obj_ids
            return results

        # Buscamos los objetos aplicando el filtro de la empresa
        query = session.query(cls.model).filter(cls.model.id.in_(obj_ids))
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        objs = query.all()

        # Separar los que no se encontraron
        valid_ids = [obj.id for obj in objs]
        for requested_id in obj_ids:
            if requested_id not in valid_ids:
                results["failed"].append(requested_id)

        if not objs:
            return results

        # Iteramos con transacciones anidadas
        for obj in objs:
            obj_id = obj.id
            try:
                with session.begin_nested():
                    # Si ya está activo, no hacemos nada y lo informamos
                    if getattr(obj, 'active') is True:
                        results["already_active"].append(obj_id)
                    else:
                        obj.active = True
                        if updated_by is not None and hasattr(cls.model, "updated_by"):
                            obj.updated_by = updated_by
                        
                        session.add(obj)
                        session.flush()
                        results["activated"].append(obj_id)

            except Exception as e:
                # Si por algun motivo de base de datos falla la actualizacion
                results["failed"].append(obj_id)

        return results
