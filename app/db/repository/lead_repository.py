from sqlalchemy.orm import aliased
from sqlalchemy import cast, Float
from app.core.constans import DEFAULT_PAGE_SIZE
from app.db.repository.base_repository import BaseRepository
from app.models.lead import Lead
from app.schemas.lead_schema import LeadDetailedResponse, LeadResponse
from app.models.lead_field_value import LeadFieldValue
from app.models.lead_field import LeadField
from sqlalchemy import and_
from sqlalchemy import func

class LeadRepository(BaseRepository):
    model = Lead
    schema_out = LeadResponse
    schema_out_detail = LeadDetailedResponse
    
    relationships = [
        (Lead.field_values, LeadFieldValue.field, LeadField.field_type),
        (Lead.field_values, LeadFieldValue.field, LeadField.campaign),
    ]

    @classmethod
    def search(cls, session, search_params, detailed: bool = False, page: int = 0, page_size: int = 0):
        query = session.query(cls.model)

        for f in search_params.filters:
            lv_alias = aliased(LeadFieldValue)
            query = query.join(lv_alias, cls.model.field_values)
            
            conditions = [lv_alias.field_id == f.field_id]

            db_val = lv_alias.value 
            val = f.value           

            # ---------------------------------------------------------
            # 1. Operador BETWEEN (Rango)
            # ---------------------------------------------------------
            if f.operator == "between":
                if not isinstance(val, list) or len(val) != 2:
                    continue 
                
                try:
                    # Intento Numérico (Se mantiene igual)
                    val_min = float(val[0])
                    val_max = float(val[1])
                    db_val_num = cast(db_val, Float)
                    
                    conditions.append(db_val_num >= val_min)
                    conditions.append(db_val_num <= val_max)
                except (ValueError, TypeError):
                    # Fallback Texto: APLICAMOS LOWER()
                    # Convertimos inputs a minúsculas
                    v_min = str(val[0]).lower()
                    v_max = str(val[1]).lower()
                    
                    # Comparamos contra la columna en minúsculas
                    conditions.append(func.lower(db_val) >= v_min)
                    conditions.append(func.lower(db_val) <= v_max)

            # ---------------------------------------------------------
            # 2. Operador IN (Lista)
            # ---------------------------------------------------------
            elif f.operator == "in":
                if isinstance(val, list):
                    # Convertimos toda la lista de inputs a minúsculas
                    val_strs = [str(v).lower() for v in val]
                    # Comparamos contra la columna en minúsculas
                    conditions.append(func.lower(db_val).in_(val_strs))

            # ---------------------------------------------------------
            # 3. Operadores de Comparación (GT, LT, GTE, LTE)
            # ---------------------------------------------------------
            elif f.operator in ["gt", "lt", "gte", "lte"]:
                try:
                    # Intento Numérico (Se mantiene igual)
                    val_float = float(val)
                    db_val_num = cast(db_val, Float)
                    
                    if f.operator == "gt": conditions.append(db_val_num > val_float)
                    elif f.operator == "lt": conditions.append(db_val_num < val_float)
                    elif f.operator == "gte": conditions.append(db_val_num >= val_float)
                    elif f.operator == "lte": conditions.append(db_val_num <= val_float)
                
                except (ValueError, TypeError):
                    # Fallback Texto: APLICAMOS LOWER()
                    val_str = str(val).lower()
                    db_val_lower = func.lower(db_val)
                    
                    if f.operator == "gt": conditions.append(db_val_lower > val_str)
                    elif f.operator == "lt": conditions.append(db_val_lower < val_str)
                    elif f.operator == "gte": conditions.append(db_val_lower >= val_str)
                    elif f.operator == "lte": conditions.append(db_val_lower <= val_str)

            # ---------------------------------------------------------
            # 4. Operadores de Texto (EQ, NEQ, LIKE)
            # ---------------------------------------------------------
            elif f.operator == "eq": 
                # Ahora "Juan" es igual a "juan"
                conditions.append(func.lower(db_val) == str(val).lower())
            
            elif f.operator == "neq": 
                conditions.append(func.lower(db_val) != str(val).lower())
            
            elif f.operator == "like": 
                # 'like' estándar es case-sensitive en muchos DBs, forzamos lower
                # Ojo: ILIKE hace esto nativo, pero esto asegura compatibilidad
                conditions.append(func.lower(db_val).contains(str(val).lower()))
            
            elif f.operator == "ilike": 
                # ILIKE ya es case-insensitive por definición en Postgres
                conditions.append(db_val.ilike(f"%{val}%"))

            # Aplicamos los filtros de esta iteración
            query = query.filter(and_(*conditions))

        # Paginación y Ejecución
        total, query = cls._paginate(query, page, page_size)
        items = cls._execute_read_query(query, detailed)
        
        return total, items

    @classmethod
    def get_all(cls, session, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, 
                only_active: bool = True, detailed: bool = False, 
                campaign_id: int = None):

        query = session.query(cls.model)

        if campaign_id is not None:
            query = query.filter(cls.model.campaign_id == campaign_id)
        # --------------------------

        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        total, query = cls._paginate(query, page, page_size)
        
        return total, cls._execute_read_query(query, detailed)

    @classmethod
    def find_duplicate(cls, session, campaign_id: int, primary_values: dict) -> bool:
        """
        Busca si existe algún Lead en la campaña que coincida EXACTAMENTE
        con TODOS los valores primarios pasados.
        primary_values = {field_id: 'valor', field_id_2: 'valor_2'}
        """
        if not primary_values:
            return False

        # Empezamos buscando leads de esa campaña
        query = session.query(cls.model).filter(cls.model.campaign_id == campaign_id)

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
        cls.upsert_children(
            session=session,
            parent_model=Lead,
            parent_id=lead_id,
            relation_name="field_values",
            items=values,
            key_attr="field_id",
            # CORRECCIÓN AQUÍ:
            create_fn=lambda item: LeadFieldValue(
                lead_id=lead_id, 
                **item.dict()     
            )
        )

    @classmethod
    def has_leads_in_campaign(cls, session, campaign_id: int) -> bool:
        """Devuelve True si existe al menos un lead en la campaña."""
        # Usamos limit(1) para que sea ultra rápido, no necesitamos contar todos
        return session.query(cls.model.id).filter(cls.model.campaign_id == campaign_id).limit(1).first() is not None
