from datetime import datetime
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.unit_of_work import UnitOfWork
from app.services.lead_validation_logic import LeadValidationLogic

class LeadService(BaseService):
    repository = LeadRepository
    field_repository = LeadFieldRepository

    # ---------------------------------------------------------
    # Clase Auxiliar (ItemProxy)
    # ---------------------------------------------------------
    class ItemProxy:
        def __init__(self, data_dict):
            self._data = data_dict
            for k, v in data_dict.items():
                setattr(self, k, v)
        
        def dict(self, **kwargs):
            return self._data

    # ---------------------------------------------------------
    # Helpers de Lógica de Negocio
    # ---------------------------------------------------------

    @classmethod
    def _prepare_context_dict(cls, values_in):
        """Convierte Input List -> Dict {field_id: valor_real}"""
        data = {}
        for v in values_in:
            if isinstance(v, dict):
                fid = v.get('field_id')
                val = v.get('nomenclator_item_id') or v.get('value')
            else:
                fid = getattr(v, 'field_id', None)
                val = getattr(v, 'nomenclator_item_id', None) or getattr(v, 'value', None)
            
            data[fid] = val
        return data

    @classmethod
    def _fill_missing_fields(cls, input_data: dict, field_defs_list: list):
        """
        [NUEVO] Asegura que el diccionario tenga entradas para TODOS los campos 
        de la campaña. Si falta alguno en el input, lo crea con valor None.
        """
        for field in field_defs_list:
            if field.id not in input_data:
                # Inyectamos el campo faltante con valor nulo
                input_data[field.id] = None
        return input_data

    @classmethod
    def _apply_defaults(cls, input_data: dict, field_defs_list: list):
        """
        Aplica default_value si el valor es None/Vacío, no es Nomenclador y no es Required.
        """
        for field in field_defs_list:
            if field.nomenclator_id is not None:
                continue

            current_val = input_data.get(field.id)

            if (current_val is None or current_val == ""):
                if field.default_value and not field.required:
                    input_data[field.id] = field.default_value
        
        return input_data

    @classmethod
    def _check_duplicates(cls, session, campaign_id: int, input_data: dict, field_defs_list: list):
        primary_fields = [f for f in field_defs_list if f.is_primary and f.nomenclator_id is None]
        if not primary_fields: return

        values_to_check = {}
        for field in primary_fields:
            val = input_data.get(field.id)
            if val is not None and val != "":
                values_to_check[field.id] = val
        
        if len(values_to_check) < len(primary_fields): return 

        is_dup = cls.repository.find_duplicate(session, campaign_id, values_to_check)
        if is_dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un Lead en esta campaña con los mismos datos identificatorios."
            )

    # -------------------------------------------------------------------------
    # VALIDACIÓN DE DEFINICIÓN (Requerido y Tipos)
    # -------------------------------------------------------------------------
    @classmethod
    def _check_field_definition(cls, field, value):
        """
        Valida restricciones estáticas: Required, Is Primary y TIPO DE DATO.
        """
        # 1. Validar Obligatoriedad
        is_mandatory = field.required or field.is_primary
        # Consideramos vacío si es None o string vacía (espacios cuentan como vacío)
        is_empty = value is None or (isinstance(value, str) and not value.strip())

        if is_empty:
            if is_mandatory:
                raise ValueError(f"El campo '{field.name}' es obligatorio.")
            return # Si está vacío y no es obligatorio, no validamos tipo (se guarda null)

        # 2. Validar Integridad de Tipos (Basic Type Check)
        type_code = field.field_type.code
        
        # [MEJORA] Validaciones estrictas con mensajes claros
        if type_code == "INT":
            try:
                # Intentamos convertir. Si es "Pedro", fallará.
                int(value)
            except (ValueError, TypeError):
                raise ValueError(f"El campo '{field.name}' espera un número entero (INT), pero recibió '{value}'.")
        
        elif type_code == "NUMBER":
            try:
                float(value)
            except (ValueError, TypeError):
                raise ValueError(f"El campo '{field.name}' espera un número decimal, pero recibió '{value}'.")
        
        elif type_code == "BOOL":
            # Aceptamos True/False nativos o strings "true"/"false"/"1"/"0"
            s_val = str(value).lower()
            if s_val not in ("true", "false", "1", "0"):
                raise ValueError(f"El campo '{field.name}' espera un booleano (true/false), pero recibió '{value}'.")
        
        elif type_code == "DATE":
            try:
                # Asumimos formato ISO YYYY-MM-DD
                datetime.strptime(str(value), "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"El campo '{field.name}' espera formato de fecha YYYY-MM-DD, pero recibió '{value}'.")

    @classmethod
    def _validate_processed_data(cls, full_context, field_defs_list):
        all_defs = {f.id: f for f in field_defs_list}
        
        for field in field_defs_list:
            val = full_context.get(field.id)
            try:
                # Paso 1: Validar definición básica
                cls._check_field_definition(field, val)

                # Paso 2: Validar reglas complejas
                LeadValidationLogic.validate_rules(
                    current_field=field,
                    raw_value=val,
                    all_values=full_context,
                    all_fields_defs=all_defs
                )

            except ValueError as e:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))

    @classmethod
    def _reconstruct_items_for_repo(cls, processed_data: dict, field_defs_list: list):
        items_for_repo = []
        for fid, val in processed_data.items():
            field_def = next((f for f in field_defs_list if f.id == fid), None)
            if not field_def: continue
            
            item_dict = {'field_id': fid}
            
            if field_def.nomenclator_id is not None:
                item_dict['nomenclator_item_id'] = val
                item_dict['value'] = None
            else:
                item_dict['nomenclator_item_id'] = None
                item_dict['value'] = val
            
            items_for_repo.append(cls.ItemProxy(item_dict))
        return items_for_repo

    # ---------------------------------------------------------
    # Métodos CRUD Públicos
    # ---------------------------------------------------------

    @classmethod
    def create(cls, obj_in):
        campaign_id = obj_in.campaign_id
        with UnitOfWork() as uow:
            # 1. Obtener definiciones de la campaña
            all_field_defs = cls.field_repository.get_all_active_with_rules(uow.session)
            
            # Validación: Campos pertenecen a la campaña
            defs_map = {f.id: f for f in all_field_defs}
            incoming_field_ids = [v.get('field_id') if isinstance(v, dict) else v.field_id for v in obj_in.values]
            
            for fid in incoming_field_ids:
                field_def = defs_map.get(fid)
                if not field_def: raise HTTPException(status.HTTP_400_BAD_REQUEST, f"ID {fid} no existe.")
                if field_def.campaign_id != campaign_id: raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El campo {fid} no es de la campaña {campaign_id}.")

            # Filtramos solo los campos de ESTA campaña
            current_campaign_defs = [f for f in all_field_defs if f.campaign_id == campaign_id]
            
            # 2. Input -> Dict
            context_data = cls._prepare_context_dict(obj_in.values)

            # 3. [NUEVO] Rellenar campos faltantes con None
            # Esto asegura que si el user no manda un campo opcional, lo tengamos en el dict como None
            context_data = cls._fill_missing_fields(context_data, current_campaign_defs)

            # 4. Aplicar Defaults (Ahora verá los Nones creados arriba y aplicará default si corresponde)
            context_data = cls._apply_defaults(context_data, current_campaign_defs)

            # 5. Chequear Duplicados
            cls._check_duplicates(uow.session, campaign_id, context_data, current_campaign_defs)
            
            # 6. Validar (Ahora checkeará tipos estrictos y requeridos sobre todos los campos)
            cls._validate_processed_data(context_data, current_campaign_defs)
            
            # 7. Preparar para guardar (incluye los campos que el usuario no mandó)
            clean_values = cls._reconstruct_items_for_repo(context_data, current_campaign_defs)
            
            # 8. Guardar
            lead = cls.repository.create(uow.session, {'campaign_id': campaign_id})
            cls.repository.upsert_values(uow.session, lead.id, clean_values)
            
            return cls.repository.get_by_id(uow.session, lead.id)

    @classmethod
    def update(cls, obj_id: int, obj_in):
        with UnitOfWork() as uow:
            if not cls.repository.get_by_id(uow.session, obj_id): cls._not_found(obj_id)
            field_defs = cls.field_repository.get_all_active_with_rules(uow.session)
            
            incoming_data = cls._prepare_context_dict(obj_in.values)
            
            current_lead = cls.repository.get_by_id(uow.session, obj_id)
            db_values = {}
            for v in current_lead.field_values:
                val = v.nomenclator_item_id if v.nomenclator_item_id is not None else v.value
                db_values[v.field_id] = val
            
            # En Update NO rellenamos campos faltantes con None, porque es una actualización parcial.
            # Solo sobrescribimos lo que el usuario envía.
            full_context = {**db_values, **incoming_data}
            
            cls._validate_processed_data(full_context, field_defs)
            
            clean_values = cls._reconstruct_items_for_repo(incoming_data, field_defs)
            cls.repository.upsert_values(uow.session, obj_id, clean_values)
            return cls.repository.get_by_id(uow.session, obj_id)
        
    @classmethod
    def get_all(cls, only_active: bool = True, detailed: bool = False, campaign_id: int = None):
        return cls._execute(
            action="Obteniendo Leads",
            func=lambda uow: cls.repository.get_all(
                session=uow.session, 
                only_active=only_active, 
                detailed=detailed, 
                campaign_id=campaign_id
            )
        )