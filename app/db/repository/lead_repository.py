from typing import Optional
from sqlalchemy.orm import aliased
from sqlalchemy import cast, Float, or_, and_, func, insert, delete
from app.db.repository.base_repository import BaseRepository
from app.models.lead import Lead
from app.models.nomenclator_item import NomenclatorItem
from app.models.team import Team
from app.models.team_member import TeamMember
from app.schemas.lead_schema import LeadDetailedResponse, LeadResponse
from app.models.lead_field_value import LeadFieldValue, lead_field_value_leads_assoc
from app.models.lead_field import LeadField
from app.core.security import UserContext

# Atributos nativos del modelo Lead que pueden usarse como filtro en /search.
# No incluir campos sensibles de infraestructura (organization_id, created_by, etc.)
LEAD_NATIVE_FILTER_FIELDS = {
    "campaign_id", "current_state_id", "contact_state_id",
    "team_id", "assigned_to_user_id", "active",
}

class LeadRepository(BaseRepository):
    model = Lead
    schema_out = LeadResponse
    schema_out_detail = LeadDetailedResponse
    
    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
        (Lead.field_values, LeadFieldValue.field, LeadField.campaign),
        (Lead.field_values, LeadFieldValue.nomenclator_items) 
    ]

    #Helper para aplicar ordenamiento dinámico en get_all y search
    @classmethod
    def _apply_dynamic_ordering(cls, query, order_by: str, ascending: bool):
        """
        Maneja el ordenamiento nativo (ej: created_at) y el ordenamiento 
        por campos dinámicos (ej: order_by='15' donde 15 es un field_id).
        """
        if not order_by:
            return query.order_by(cls.model.id.desc())

        # CASO 1: Es un campo nativo de la tabla Lead (ej: id, created_at, active)
        if hasattr(cls.model, order_by):
            column = getattr(cls.model, order_by)
            return query.order_by(column.asc() if ascending else column.desc())

        # CASO 2: Es un campo dinámico (Asumimos que el string es el field_id)
        if order_by.isdigit():
            field_id = int(order_by)
            
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

        # Fallback si no machea nada
        return query.order_by(cls.model.id.desc())

    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext = None):
        if user_context is None or user_context.user is None:
            return query

        if user_context.is_superuser or user_context.is_owner:
            return query

        consulted_by = user_context.user.id

        query = query.outerjoin(Team, cls.model.team_id == Team.id) \
                     .outerjoin(TeamMember, and_(Team.id == TeamMember.team_id, TeamMember.user_id == consulted_by))

        security_condition = or_(
            cls.model.team_id.is_(None),                 # 1. Huérfano general
            cls.model.assigned_to_user_id == consulted_by,    # 2. Es mi lead directo
            cls.model.created_by == consulted_by,             # 3. Yo mismo lo creé
            and_(
                TeamMember.id.isnot(None),               # 4. Pertenezco al equipo del lead
                or_(
                    TeamMember.role == "MANAGER",        # -> Y soy el jefe
                    Team.is_visibility_shared == True,   # -> O somos un equipo colaborativo
                    cls.model.assigned_to_user_id.is_(None) # -> O está en mi equipo pero nadie lo tomó
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
            query = query.join(LeadFieldValue, cls.model.field_values)
            conditions = [LeadFieldValue.value.ilike(f"%{search}%")]

            query = query.outerjoin(LeadFieldValue.nomenclator_items)
            conditions.append(NomenclatorItem.value.ilike(f"%{search}%"))

            if search_fields:
                query = query.join(LeadField, LeadFieldValue.field)
                query = query.filter(
                    LeadField.name.in_(search_fields),
                    or_(*conditions)
                )
            else:
                query = query.filter(or_(*conditions))

            query = query.distinct()

        order_by = kwargs.pop('order_by', None)
        ascending = kwargs.pop('ascending', True)

        # Aplicamos nuestro ordenamiento especial EAV
        query = cls._apply_dynamic_ordering(query, order_by, ascending)

        # DELEGAMOS AL PADRE
        # Nota: Al atrapar 'search' y 'search_fields' en la firma de esta función, 
        # evitamos que pasen en los **kwargs y que el padre intente buscar de nuevo.
        return super().get_all(
            session=session,
            user_context=user_context,
            only_active=only_active,
            detailed=detailed,
            base_query=query,
            **kwargs
        )

    @classmethod
    def search(cls, session, search_params, user_context: Optional[UserContext] = None, detailed: bool = False, page: int = 0, page_size: int = 0, order_by: str = None, ascending: bool = True):
        query = session.query(cls.model)

        query = cls._apply_tenant_filter(query)

        # Inyectar seguridad de equipos mediante el Hook
        if user_context is not None and user_context.user is not None:
            query = cls.apply_security_filter(session, query, user_context)

        for f in search_params.filters:

            # Si el field_id es un string y está en la whitelist de campos nativos filtrables
            if isinstance(f.field_id, str) and f.field_id in LEAD_NATIVE_FILTER_FIELDS:
                column = getattr(cls.model, f.field_id)
                val = f.value
                
                if f.operator == "eq": query = query.filter(column == val)
                elif f.operator == "neq": query = query.filter(column != val)
                elif f.operator == "in" and isinstance(val, list): query = query.filter(column.in_(val))
                elif f.operator == "between" and isinstance(val, list) and len(val) == 2: query = query.filter(column.between(val[0], val[1]))
                elif f.operator == "gt": query = query.filter(column > val)
                elif f.operator == "lt": query = query.filter(column < val)
                elif f.operator == "gte": query = query.filter(column >= val)
                elif f.operator == "lte": query = query.filter(column <= val)
                elif f.operator == "like": query = query.filter(column.contains(val))
                elif f.operator == "ilike": query = query.filter(column.ilike(f"%{val}%"))
                
                # Continuamos con el siguiente filtro, ignorando la lógica EAV para este
                continue

            lv_alias = aliased(LeadFieldValue)
            query = query.join(lv_alias, cls.model.field_values)
            
            # Condición base: El valor debe pertenecer al campo correcto
            field_condition = lv_alias.field_id == f.field_id
            
            # Acumulador de condiciones para este filtro (AND interno)
            # Empezamos solo con el field_id, luego agregamos la condición de valor
            conditions = [field_condition]

            db_val = lv_alias.value 
            val = f.value           

            # ---------------------------------------------------------
            # 1. Operador BETWEEN (Rango) - Generalmente solo para Text/Number/Date
            # ---------------------------------------------------------
            if f.operator == "between":
                if not isinstance(val, list) or len(val) != 2:
                    continue 
                
                try:
                    # Intento Numérico
                    val_min = float(val[0])
                    val_max = float(val[1])
                    db_val_num = cast(db_val, Float)
                    
                    conditions.append(db_val_num >= val_min)
                    conditions.append(db_val_num <= val_max)
                except (ValueError, TypeError):
                    # Fallback Texto / Fechas
                    v_min = str(val[0]).lower()
                    v_max = str(val[1]).lower()
                    
                    conditions.append(func.lower(db_val) >= v_min)
                    conditions.append(func.lower(db_val) <= v_max)

            # ---------------------------------------------------------
            # 2. Operador IN (Lista) - AQUI CAMBIA PARA SOPORTAR MULTIPLES
            # ---------------------------------------------------------
            elif f.operator == "in":
                if isinstance(val, list):
                    # A. Búsqueda en Texto (Normalizamos a string minúsculas)
                    val_strs = [str(v).lower() for v in val]
                    cond_text = func.lower(db_val).in_(val_strs)

                    # B. Búsqueda en Relación Nomenclador (Many-to-Many)
                    # "Existe algún item en la lista del lead cuyo ID esté en la lista de búsqueda"
                    cond_relation = lv_alias.nomenclator_items.any(NomenclatorItem.id.in_(val))

                    # Aplicamos OR: O está en el texto O está en la relación
                    conditions.append(or_(cond_text, cond_relation))

            # ---------------------------------------------------------
            # 3. Operadores de Comparación (GT, LT, GTE, LTE)
            # ---------------------------------------------------------
            elif f.operator in ["gt", "lt", "gte", "lte"]:
                try:
                    val_float = float(val)
                    db_val_num = cast(db_val, Float)
                    
                    if f.operator == "gt": conditions.append(db_val_num > val_float)
                    elif f.operator == "lt": conditions.append(db_val_num < val_float)
                    elif f.operator == "gte": conditions.append(db_val_num >= val_float)
                    elif f.operator == "lte": conditions.append(db_val_num <= val_float)
                
                except (ValueError, TypeError):
                    val_str = str(val).lower()
                    db_val_lower = func.lower(db_val)
                    
                    if f.operator == "gt": conditions.append(db_val_lower > val_str)
                    elif f.operator == "lt": conditions.append(db_val_lower < val_str)
                    elif f.operator == "gte": conditions.append(db_val_lower >= val_str)
                    elif f.operator == "lte": conditions.append(db_val_lower <= val_str)

            # ---------------------------------------------------------
            # 4. Operadores de Igualdad (EQ, NEQ) - CAMBIA PARA SOPORTAR ID UNICO
            # ---------------------------------------------------------
            elif f.operator == "eq": 
                # A. Texto exacto
                cond_text = func.lower(db_val) == str(val).lower()
                
                # B. Relación (El Lead tiene este ID seleccionado en su lista)
                cond_relation = lv_alias.nomenclator_items.any(NomenclatorItem.id == val)
                
                conditions.append(or_(cond_text, cond_relation))
            
            elif f.operator == "neq": 
                # A. Distinto texto
                cond_text = func.lower(db_val) != str(val).lower()
                
                # B. Relación (No tiene este ID)
                # Nota: Negar .any() es "no tiene ninguno que coincida"
                cond_relation = ~lv_alias.nomenclator_items.any(NomenclatorItem.id == val)
                
                conditions.append(and_(cond_text, cond_relation))
            
            # ---------------------------------------------------------
            # 5. Operadores de Texto Parcial (LIKE, ILIKE)
            # ---------------------------------------------------------
            elif f.operator == "like": 
                # Solo aplica a columna valor texto
                conditions.append(func.lower(db_val).contains(str(val).lower()))
            
            elif f.operator == "ilike": 
                conditions.append(db_val.ilike(f"%{val}%"))

            # Aplicamos los filtros de esta iteración (AND con los joins anteriores)
            query = query.filter(and_(*conditions))
        
        query = cls._apply_dynamic_ordering(query, order_by, ascending)

        # Paginación y Ejecución
        total, query = cls._paginate(query, page, page_size)
        items = cls._execute_read_query(query, detailed)
        
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
    
