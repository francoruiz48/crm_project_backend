from typing import Optional
from app.core.constans import DeleteStrategy
from sqlalchemy.orm import aliased
from sqlalchemy import cast, Float, or_, and_, func, insert, delete
from app.db.repository.base_repository import BaseRepository
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.nomenclator_item import NomenclatorItem
from app.models.team import Team
from app.models.team_member import TeamMember
from app.schemas.lead_schema import LeadDetailedResponse, LeadResponse
from app.models.lead_field_value import LeadFieldValue, lead_field_value_leads_assoc
from app.models.lead_field import LeadField
from app.core.security import UserContext

# Atributos nativos del modelo Lead que pueden usarse como filtro en /search.
# No incluir campos sensibles de infraestructura (organization_id, etc.)
#
# Bug real encontrado 2026-08-10: created_by/updated_by quedaban afuera de este set a
# propósito, pero el frontend sí los expone como filtros nativos ("Usuario Creador"/
# "Usuario Modificador", ver nativeLeadFields.ts ids -7/-8). Al no estar acá, el filtro
# no entraba por la rama de filtros nativos (resuelta con resolve_fk_filter_value, que
# ya sabe resolver FKs como esta) y caía por descarte en la rama de filtros EAV/custom,
# que trata cualquier field_id no-nativo como uuid de un LeadField -- como "created_by"/
# "updated_by" no son uuid de ningún LeadField real, _resolve_custom_field_id devolvía el
# sentinel -1 y el filtro nunca matcheaba nada (0 resultados garantizados, sin importar
# los leads que hubiera). Son FKs reales (Lead.created_by/updated_by → user.id), así que
# alcanza con sumarlos acá para que se resuelvan igual que assigned_to_user_id.
LEAD_NATIVE_FILTER_FIELDS = {
    "campaign_id", "current_state_id", "contact_state_id",
    "team_id", "assigned_to_user_id", "active",
    "created_at", "updated_at", "created_by", "updated_by",
}

class LeadRepository(BaseRepository):
    model = Lead
    delete_strategy = DeleteStrategy.HARD_DELETE_ALWAYS
    schema_out = LeadResponse
    schema_out_detail = LeadDetailedResponse
    
    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
        (Lead.field_values, LeadFieldValue.field, LeadField.campaign),
        (Lead.field_values, LeadFieldValue.nomenclator_items) 
    ]

    #Helper para aplicar ordenamiento dinámico en get_all y search
    @classmethod
    def _apply_dynamic_ordering(cls, session, query, order_by: str, ascending: bool):
        """
        Maneja el ordenamiento nativo (ej: created_at) y el ordenamiento
        por campos dinámicos (LeadField custom).

        Bug real encontrado 2026-08-11 (reportado por el usuario: "el ordenar de lead no
        anda"): el CASO 2 de abajo solo reconocía `order_by` como field_id si era un string
        100% numérico (`"15"`). Pero el front (LeadTablePresentation.tsx::orderKey =
        column.nativeKey ?? column.id) manda el `public_uuid` del LeadField para cualquier
        columna custom -- ningún campo nativo usa esta rama (esos ya matchean por nombre de
        columna real en el CASO 1, vía `nativeKey`). Un uuid nunca pasa `.isdigit()`, así
        que CUALQUIER intento de ordenar por una columna custom caía siempre al fallback
        (id DESC) sin ningún error visible, ni para el front ni en los logs. Se agrega la
        resolución uuid -> id interno (mismo patrón que el resto del archivo, ver
        `_resolve_custom_field_id` en `search()`), antes de recién ahí caer al fallback.
        """
        if not order_by:
            return query.order_by(cls.model.id.desc())

        # CASO 1: Es un campo nativo de la tabla Lead (ej: id, created_at, active,
        # contact_state_id -- lo que el front manda vía `nativeKey` para columnas nativas)
        if hasattr(cls.model, order_by):
            column = getattr(cls.model, order_by)
            return query.order_by(column.asc() if ascending else column.desc())

        # CASO 2: Campo custom (LeadField) -- acepta tanto el id interno como string
        # numérico (compatibilidad hacia atrás / uso interno) como el public_uuid real
        # que manda el front (Fase 3/4, ver comentario de arriba).
        field_id = None
        if order_by.isdigit():
            field_id = int(order_by)
        else:
            from app.db.repository.lead_field_repository import LeadFieldRepository
            field_id = LeadFieldRepository.get_internal_id_by_public_uuid(session, order_by)

        if field_id is not None:
            # Hacemos un OUTER JOIN específico solo para traer el valor de este campo
            # Usamos un alias para no chocar con otros JOINs de LeadFieldValue en la búsqueda
            sort_lv = aliased(LeadFieldValue)
            query = query.outerjoin(
                sort_lv,
                and_(sort_lv.lead_id == cls.model.id, sort_lv.field_id == field_id)
            )

            # Ordenamos por el valor string (Postgres hará un orden alfabético por defecto)
            # Para números perfectos, idealmente el field_type debería definir el cast,
            # pero el orden alfabético de strings suele bastar para la grilla
            return query.order_by(sort_lv.value.asc() if ascending else sort_lv.value.desc())

        # Fallback: no matchea ninguna columna real ni ningún LeadField válido
        return query.order_by(cls.model.id.desc())

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        # Superadmin, owner o usuario con permiso explícito lead:view_all → sin filtro
        if user_context.is_superuser or user_context.is_owner:
            return query

        if "lead:view_all" in (user_context.permissions or []):
            return query

        consulted_by = user_context.user.id

        # Join para filtro de equipo
        query = query.outerjoin(Team, cls.model.team_id == Team.id) \
                     .outerjoin(TeamMember, and_(Team.id == TeamMember.team_id, TeamMember.user_id == consulted_by))

        # Join para filtro de campaña pública
        query = query.outerjoin(Campaign, cls.model.campaign_id == Campaign.id)

        security_condition = or_(
            Campaign.is_public.is_(True),                          # Campaña pública: visible para todos
            cls.model.assigned_to_user_id == consulted_by,        # Es mi lead directo
            cls.model.created_by == consulted_by,                  # Yo mismo lo creé
            and_(
                TeamMember.id.isnot(None),                         # Pertenezco al equipo del lead
                or_(
                    TeamMember.role == "MANAGER",                  # -> Y soy el jefe
                    Team.is_visibility_shared == True,             # -> O somos un equipo colaborativo
                    cls.model.assigned_to_user_id.is_(None)        # -> O está en mi equipo pero nadie lo tomó
                )
            )
        )

        return query.filter(security_condition)

    
    @classmethod
    def get_all(cls, session, user_context: Optional[UserContext] = None, only_active: bool = True, detailed: bool = False, search: str = None, search_fields: list = None, **kwargs):
        """
        Prepara los JOINs complejos para la búsqueda de Leads y delega 
        la seguridad, paginación y filtros estándar al BaseRepository.
        """
        query = session.query(cls.model)

        # Si hay búsqueda global, pre-armamos la query con sus JOINs
        if search:
            # Tipos de campo donde tiene sentido buscar texto libre
            TEXT_SEARCH_TYPES = ('STRING', 'SELECTOR')

            query = query.join(LeadFieldValue, cls.model.field_values)
            query = query.join(LeadField, LeadFieldValue.field)
            query = query.outerjoin(LeadFieldValue.nomenclator_items)

            conditions = [
                LeadFieldValue.value.ilike(f"%{search}%"),
                NomenclatorItem.value.ilike(f"%{search}%"),
            ]

            if search_fields:
                # Modo explícito: filtrar por nombres de campo específicos
                query = query.filter(LeadField.name.in_(search_fields), or_(*conditions))
            else:
                # Modo automático: solo campos STRING y SELECTOR
                query = query.filter(LeadField.field_type_code.in_(TEXT_SEARCH_TYPES), or_(*conditions))

            query = query.distinct()

        order_by = kwargs.pop('order_by', None)
        ascending = kwargs.pop('ascending', True)

        # Aplicamos nuestro ordenamiento especial EAV
        query = cls._apply_dynamic_ordering(session, query, order_by, ascending)

        # DELEGAMOS AL PADRE
        # Nota: Al atrapar 'search' y 'search_fields' en la firma de esta función,
        # evitamos que pasen en los **kwargs y que el padre intente buscar de nuevo.
        # `ascending` SÍ se reenvía a propósito (aunque `order_by` ya se consumió acá
        # arriba): BaseRepository.get_all() siempre agrega su propio order_by de
        # desempate por `id` cuando no recibe uno (ver default_sort_column="id") --
        # como SQLAlchemy acumula order_by en vez de reemplazarlo, ese desempate no
        # pisa el ordenamiento real ya aplicado arriba, pero si no le pasamos
        # `ascending` explícito, ese desempate quedaba siempre ascendente sin importar
        # lo que haya pedido el usuario. Pasándolo, el desempate por id respeta la
        # misma dirección que el ordenamiento principal.
        return super().get_all(
            session=session,
            user_context=user_context,
            only_active=only_active,
            detailed=detailed,
            base_query=query,
            ascending=ascending,
            **kwargs
        )

    @classmethod
    def search(cls, session, search_params, user_context: Optional[UserContext] = None, detailed: bool = False, page: int = 0, page_size: int = 0, order_by: str = None, ascending: bool = True, only_active: bool = True, campaign_id: Optional[int] = None, query: Optional[str] = None):
        db_query = session.query(cls.model)

        db_query = cls._apply_tenant_filter(db_query)

        # Inyectar seguridad de equipos mediante el Hook
        if user_context is not None and user_context.user is not None:
            db_query = cls.apply_security_filter(session, db_query, user_context)

        # Filtrar leads activos/inactivos (igual que en get_all)
        if only_active and hasattr(cls.model, "active"):
            db_query = db_query.filter(cls.model.active == True)

        # Filtrar por campaña (igual que en get_all). campaign_id llega como public_uuid
        # (el front ya no conoce el id interno) -- se resuelve antes de filtrar.
        if campaign_id is not None:
            campaign_id = cls.resolve_fk_filter_value(session, "campaign_id", campaign_id)
            db_query = db_query.filter(cls.model.campaign_id == campaign_id)

        # Búsqueda de texto libre (mismo criterio que get_all: campos STRING/SELECTOR,
        # ilike sobre LeadFieldValue.value y NomenclatorItem.value). Antes este parámetro
        # ni siquiera llegaba hasta acá -- el modo Tablero mandaba `query` pero el
        # controller/servicio lo descartaban en silencio, así que nunca filtraba nada.
        text_search_applied = False
        if query:
            TEXT_SEARCH_TYPES = ('STRING', 'SELECTOR')
            db_query = db_query.join(LeadFieldValue, cls.model.field_values)
            db_query = db_query.join(LeadField, LeadFieldValue.field)
            db_query = db_query.outerjoin(LeadFieldValue.nomenclator_items)
            db_query = db_query.filter(
                LeadField.field_type_code.in_(TEXT_SEARCH_TYPES),
                or_(
                    LeadFieldValue.value.ilike(f"%{query}%"),
                    NomenclatorItem.value.ilike(f"%{query}%"),
                )
            )
            db_query = db_query.distinct()
            text_search_applied = True

        # ── Filtros nativos (columnas directas del modelo) — se aplican con AND ──
        # Los campos nativos NO se agrupan con OR porque el tablero añade su propio
        # filtro de columna sobre el mismo campo (contact_state_id); si se ORaran
        # los leads aparecerían en todas las columnas.
        # El multi-select del usuario ya usa operator='in', que maneja varios valores
        # en un solo filtro sin necesidad de duplicar la fila.
        for f in search_params.filters:
            if not (isinstance(f.field_id, str) and f.field_id in LEAD_NATIVE_FILTER_FIELDS):
                continue
            column = getattr(cls.model, f.field_id)
            val = f.value
            # current_state_id/contact_state_id/team_id/assigned_to_user_id son FKs -- el
            # valor llega como public_uuid desde el front. campaign_id/active/created_at/
            # updated_at no son FKs (o son bool/fecha) y resolve_fk_filter_value los deja
            # pasar sin tocar.
            if f.operator == "in" and isinstance(val, list):
                val = [cls.resolve_fk_filter_value(session, f.field_id, v) for v in val]
            elif f.operator in ("eq", "neq"):
                val = cls.resolve_fk_filter_value(session, f.field_id, val)
            if f.operator == "eq": db_query = db_query.filter(column == val)
            elif f.operator == "neq": db_query = db_query.filter(column != val)
            elif f.operator == "in" and isinstance(val, list): db_query = db_query.filter(column.in_(val))
            elif f.operator == "between" and isinstance(val, list) and len(val) == 2: db_query = db_query.filter(column.between(val[0], val[1]))
            elif f.operator == "gt": db_query = db_query.filter(column > val)
            elif f.operator == "lt": db_query = db_query.filter(column < val)
            elif f.operator == "gte": db_query = db_query.filter(column >= val)
            elif f.operator == "lte": db_query = db_query.filter(column <= val)
            elif f.operator == "like": db_query = db_query.filter(column.contains(val))
            elif f.operator == "ilike": db_query = db_query.filter(column.ilike(f"%{val}%"))

        # ── Filtros EAV (campos custom) — OR merging dentro del mismo campo ───
        # Permite "Nombre contains 'Juan'" + "Nombre contains 'Pedro'" → OR.
        # Un JOIN separado por field_id distinto; condiciones del mismo field_id → OR.
        from collections import defaultdict
        from app.db.repository.lead_field_repository import LeadFieldRepository
        from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository

        raw_custom_filters = [
            f for f in search_params.filters
            if not (isinstance(f.field_id, str) and f.field_id in LEAD_NATIVE_FILTER_FIELDS) and f.field_id is not None
        ]

        # f.field_id llega como public_uuid de LeadField (Fase 3, ver backend/AGENTS.md §18),
        # pero lead_field_value.field_id es el id interno (entero). Antes se usaba el UUID tal
        # cual en el filtro, lo que rompía con "invalid input syntax for type integer" apenas
        # el usuario filtraba por un campo custom (ej. desde el listado de leads). Se resuelve
        # en bloque, igual que ya se hace en lead_service.py/lead_field_service.py/etc.
        uuid_field_ids = [f.field_id for f in raw_custom_filters if isinstance(f.field_id, str) and not f.field_id.lstrip("-").isdigit()]
        uuid_to_internal_id = LeadFieldRepository.get_internal_ids_by_public_uuids(session, uuid_field_ids) if uuid_field_ids else {}

        def _resolve_custom_field_id(fid):
            if isinstance(fid, int):
                return fid
            if isinstance(fid, str) and fid.lstrip("-").isdigit():
                return int(fid)
            # UUID no encontrado -> sentinel que no matchea ningún LeadField real,
            # en vez de dejar pasar el UUID crudo a la comparación de enteros.
            return uuid_to_internal_id.get(fid, cls._MISSING_FK_SENTINEL)

        eav_groups: dict = defaultdict(list)   # field_id (int, ya resuelto) → [LeadFilter]
        for f in raw_custom_filters:
            eav_groups[_resolve_custom_field_id(f.field_id)].append(f)

        # Mismo bug de fondo que field_id arriba, del lado del VALOR: para eq/in/neq sobre un
        # campo SELECTOR, f.value llega como public_uuid de NomenclatorItem (LeadFilters.tsx
        # arma value_ids con item.id, que a nivel API siempre es public_uuid -- ver
        # nomenclatorItemsService/getNomenclatorItems), pero NomenclatorItem.id es el id interno
        # (entero). Sin resolver, `NomenclatorItem.id == val` rompía con el mismo
        # "invalid input syntax for type integer" que field_id, apenas se filtraba un lead
        # por un campo Selector/Lista. Se resuelve en bloque, mismo helper que field_id.
        raw_item_uuids = set()
        for filters in eav_groups.values():
            for f in filters:
                if f.operator in ("eq", "neq") and isinstance(f.value, str) and not f.value.lstrip("-").isdigit():
                    raw_item_uuids.add(f.value)
                elif f.operator == "in" and isinstance(f.value, list):
                    raw_item_uuids.update(v for v in f.value if isinstance(v, str) and not v.lstrip("-").isdigit())
        item_uuid_to_internal_id = NomenclatorItemRepository.get_internal_ids_by_public_uuids(session, list(raw_item_uuids)) if raw_item_uuids else {}

        def _resolve_item_id(v):
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.lstrip("-").isdigit():
                return int(v)
            # UUID no encontrado -> sentinel que no matchea ningún NomenclatorItem real.
            return item_uuid_to_internal_id.get(v, cls._MISSING_FK_SENTINEL) if isinstance(v, str) else v

        # ── Filtros EAV (campos custom, un JOIN por field_id) ─────────────────
        for field_id, filters in eav_groups.items():
            lv_alias = aliased(LeadFieldValue)
            db_query = db_query.join(lv_alias, cls.model.field_values)

            db_val = lv_alias.value
            per_filter_conds = []   # condiciones no-rango del grupo → se combinan con OR
            # Bug real encontrado 2026-08-11 (reportado por el usuario -- filtro de rango NUMBER
            # "no estaría filtrando bien"): un filtro Desde/Hasta de NUMBER o DATE llega desde el
            # front como DOS LeadFilter separados sobre el mismo field_id (uno "gte", uno "lte" --
            # ver LeadFilters.tsx::onSubmit), que antes cae acá en el mismo grupo que
            # per_filter_conds y terminaba OR-eado con el resto (línea de abajo, value_cond).
            # Eso arma "valor >= Desde OR valor <= Hasta", que matchea casi cualquier valor en vez
            # de "Desde <= valor <= Hasta". El OR tiene sentido para el caso que originó ese
            # diseño (dos filas de texto: "contiene 'Juan'" OR "contiene 'Pedro'"), pero no para
            # gt/lt/gte/lte del mismo campo, que en la UI siempre representan los dos extremos de
            # UN rango y deben ANDearse entre sí.
            range_conds = []   # condiciones gt/lt/gte/lte del grupo → se combinan con AND

            for f in filters:
                val = f.value
                cond = None     # condición de valor para este filtro

                # ---------------------------------------------------------
                # 1. Operador BETWEEN (Rango)
                # ---------------------------------------------------------
                if f.operator == "between":
                    if not isinstance(val, list) or len(val) != 2:
                        continue
                    try:
                        val_min = float(val[0])
                        val_max = float(val[1])
                        db_val_num = cast(db_val, Float)
                        cond = and_(db_val_num >= val_min, db_val_num <= val_max)
                    except (ValueError, TypeError):
                        v_min = str(val[0]).lower()
                        v_max = str(val[1]).lower()
                        cond = and_(func.lower(db_val) >= v_min, func.lower(db_val) <= v_max)

                # ---------------------------------------------------------
                # 2. Operador IN (Lista)
                # ---------------------------------------------------------
                elif f.operator == "in":
                    if isinstance(val, list):
                        val_strs = [str(v).lower() for v in val]
                        cond_text = func.lower(db_val).in_(val_strs)
                        resolved_ids = [_resolve_item_id(v) for v in val]
                        cond_relation = lv_alias.nomenclator_items.any(NomenclatorItem.id.in_(resolved_ids))
                        cond = or_(cond_text, cond_relation)

                # ---------------------------------------------------------
                # 3. Operadores de Comparación (GT, LT, GTE, LTE)
                # ---------------------------------------------------------
                elif f.operator in ["gt", "lt", "gte", "lte"]:
                    try:
                        val_float = float(val)
                        db_val_num = cast(db_val, Float)
                        ops = {"gt": db_val_num > val_float, "lt": db_val_num < val_float,
                               "gte": db_val_num >= val_float, "lte": db_val_num <= val_float}
                        cond = ops[f.operator]
                    except (ValueError, TypeError):
                        val_str = str(val).lower()
                        db_val_lower = func.lower(db_val)
                        ops = {"gt": db_val_lower > val_str, "lt": db_val_lower < val_str,
                               "gte": db_val_lower >= val_str, "lte": db_val_lower <= val_str}
                        cond = ops[f.operator]

                # ---------------------------------------------------------
                # 4. Igualdad (EQ, NEQ)
                # ---------------------------------------------------------
                elif f.operator == "eq":
                    cond_text = func.lower(db_val) == str(val).lower()
                    cond_relation = lv_alias.nomenclator_items.any(NomenclatorItem.id == _resolve_item_id(val))
                    cond = or_(cond_text, cond_relation)

                elif f.operator == "neq":
                    # Bug real encontrado 2026-08-06 (al testear el fix de SELECTOR de arriba):
                    # LeadFieldValue.value queda NULL para campos SELECTOR (la selección real
                    # vive en la tabla M2M nomenclator_items, ver
                    # lead_field_value_repository.py). `NULL != X` evalúa a NULL en SQL (ni
                    # true ni false), así que el AND de abajo descartaba la fila SIEMPRE que
                    # el campo fuera un SELECTOR -- "neq" nunca devolvía nada. Se cubre ese
                    # caso tratando "sin valor de texto" como "no es igual" (no hay texto que
                    # comparar), dejando que cond_relation sea quien realmente decida para
                    # campos SELECTOR.
                    cond_text = or_(db_val.is_(None), func.lower(db_val) != str(val).lower())
                    cond_relation = ~lv_alias.nomenclator_items.any(NomenclatorItem.id == _resolve_item_id(val))
                    cond = and_(cond_text, cond_relation)

                # ---------------------------------------------------------
                # 5. Texto Parcial (LIKE, ILIKE)
                # ---------------------------------------------------------
                elif f.operator == "like":
                    cond = func.lower(db_val).contains(str(val).lower())

                elif f.operator == "ilike":
                    cond = db_val.ilike(f"%{val}%")

                if cond is not None:
                    if f.operator in ("gt", "lt", "gte", "lte"):
                        range_conds.append(cond)
                    else:
                        per_filter_conds.append(cond)

            # range_conds (Desde/Hasta) se ANDean entre sí; per_filter_conds (todo lo demás,
            # ej. múltiples "contiene") se sigue OR-eando como antes. Si un mismo campo tuviera
            # de los dos tipos a la vez (no lo arma la UI hoy), se combinan con AND -- cada
            # bloque configurado para el campo termina restringiendo más, no ampliando.
            combined = []
            if range_conds:
                combined.append(and_(*range_conds) if len(range_conds) > 1 else range_conds[0])
            if per_filter_conds:
                combined.append(or_(*per_filter_conds) if len(per_filter_conds) > 1 else per_filter_conds[0])

            if combined:
                field_cond = lv_alias.field_id == field_id
                value_cond = and_(*combined) if len(combined) > 1 else combined[0]
                db_query = db_query.filter(and_(field_cond, value_cond))

        # Si hubo JOINs EAV y/o búsqueda de texto libre, el query tiene filas duplicadas
        # (una por cada field_value que matchea). Reemplazamos el query por uno limpio
        # usando los IDs como subquery, así el ORDER BY y la paginación operan sobre
        # filas únicas sin duplicados.
        if eav_groups or text_search_applied:
            id_subq = db_query.order_by(False).with_entities(cls.model.id).distinct().subquery()
            db_query = session.query(cls.model).filter(cls.model.id.in_(id_subq))

        db_query = cls._apply_dynamic_ordering(session, db_query, order_by, ascending)

        # Paginación y Ejecución
        total, db_query = cls._paginate(db_query, page, page_size)
        items = cls._execute_read_query(db_query, detailed)
        
        return total, items


    @classmethod
    def find_duplicate(cls, session, campaign_id: int, primary_values: dict, exclude_id: int = None) -> bool:
        """
        Busca si existe algún Lead en la campaña que coincida EXACTAMENTE
        con TODOS los valores primarios pasados.
        primary_values = {field_id: 'valor', field_id_2: 'valor_2'}
        exclude_id: ID del lead actual (para no marcarse a sí mismo como duplicado en updates)
        """
        if not primary_values:
            return False

        # Empezamos buscando leads de esa campaña
        query = session.query(cls.model).filter(cls.model.campaign_id == campaign_id)

        query = cls._apply_tenant_filter(query)

        # Excluimos el lead actual (útil en updates)
        if exclude_id is not None:
            query = query.filter(cls.model.id != exclude_id)

        # Iteramos dinámicamente sobre cada campo primario (AND lógico)
        for f_id, val in primary_values.items():
            # Filtramos leads que tengan un valor asociado que coincida
            query = query.filter(
                cls.model.field_values.any(
                    and_(
                        LeadFieldValue.field_id == f_id,
                        LeadFieldValue.value == str(val) # Comparamos como string
                    )
                )
            )

        # Si existe al menos uno, es duplicado
        return query.first() is not None

    @classmethod
    def upsert_values(cls, session, lead_id: int, values: list):
        # 1. Obtener valores existentes
        existing_values = session.query(LeadFieldValue).filter(LeadFieldValue.lead_id == lead_id).all()
        existing_map = {v.field_id: v for v in existing_values}

        for item_proxy in values:
            field_id = item_proxy.field_id
            new_val_str = item_proxy.value
            
            # Recuperamos el objeto de la DB o creamos uno nuevo
            if field_id in existing_map:
                field_val_obj = existing_map[field_id]
                field_val_obj.value = new_val_str
            else:
                field_val_obj = LeadFieldValue(lead_id=lead_id, field_id=field_id, value=new_val_str)
                session.add(field_val_obj)
            
            # FLUSH CRÍTICO: Necesitamos que field_val_obj tenga ID para las relaciones M2M
            session.flush() 
            
            # -------------------------------------------------------------
            # A. NOMENCLADORES
            # -------------------------------------------------------------
            new_ids_list = getattr(item_proxy, 'nomenclator_ids_list', None)
            if new_ids_list is not None: # Solo si viene la lista (vacía o llena)
                if new_ids_list:
                    items_objs = session.query(NomenclatorItem).filter(NomenclatorItem.id.in_(new_ids_list)).all()
                    field_val_obj.nomenclator_items = items_objs
                else:
                    field_val_obj.nomenclator_items = []

            # -------------------------------------------------------------
            # B. LEADS RELACIONADOS
            # -------------------------------------------------------------
            related_ids = getattr(item_proxy, 'related_lead_ids_list', None)
            
            # Solo actuamos si related_ids no es None (es decir, es un campo tipo LEAD)
            if related_ids is not None:
                # 1. Limpiamos relaciones anteriores (Estrategia segura: Delete + Insert)
                # Esto es más eficiente que comparar conjuntos en Python para listas grandes
                session.execute(
                    delete(lead_field_value_leads_assoc)
                    .where(lead_field_value_leads_assoc.c.lead_field_value_id == field_val_obj.id)
                )
                
                # 2. Insertamos las nuevas (si hay)
                if related_ids:
                    insert_stmts = []
                    for rid in related_ids:
                        insert_stmts.append({
                            "lead_field_value_id": field_val_obj.id, # Ahora seguro tiene ID gracias al flush
                            "related_lead_id": rid
                        })
                    session.execute(insert(lead_field_value_leads_assoc), insert_stmts)

    @classmethod
    def has_leads_in_campaign(cls, session, campaign_id: int) -> bool:
        """Devuelve True si existe al menos un lead en la campaña."""
        query = session.query(cls.model.id).filter(cls.model.campaign_id == campaign_id)
        query = cls._apply_tenant_filter(query)
        return query.limit(1).first() is not None
