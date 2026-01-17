from datetime import date, datetime
import re
from fastapi import HTTPException, UploadFile, status
from app.core.constans import ALLOWED_DOCUMENT_TYPES, ALLOWED_IMAGE_TYPES, DATE_FORMAT, DATE_TIME_FORMAT, DEFAULT_PAGE_SIZE, NOMENCLATOR_FIELD_TYPES
# Asegúrate de que ValidationError esté importado correctamente desde tu archivo de excepciones
from app.core.exceptions.exceptions import ValidationError 
from app.models.lead import Lead
from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.unit_of_work import UnitOfWork
from app.services.lead_validation_logic import LeadValidationLogic
from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
from app.services.storage_service import StorageService


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
        
        def model_dump(self, **kwargs):
            return self._data
        
        def __getitem__(self, item):
            return self._data.get(item)
        

    # ---------------------------------------------------------
    # Helpers de Lógica de Negocio
    # ---------------------------------------------------------

    @classmethod
    def _convert_value_by_type(cls, value, field_def):
        if value is None:
            return None
            
        type_code = field_def.field_type_code

        try:
            if type_code == "INT":
                return int(value)
            
            if type_code == "NUMBER":
                return float(value)
            
            if type_code == "BOOL":
                if isinstance(value, bool): return value
                return str(value).lower() in ("true", "1", "yes", "si")

            if type_code == "DATE":
                if isinstance(value, (datetime, date)): return value
                return datetime.strptime(str(value), "%Y-%m-%d").date()
            
            if type_code == "DATE_TIME":
                if isinstance(value, datetime): return value
                return datetime.strptime(str(value), DATE_TIME_FORMAT)

            return value

        except (ValueError, TypeError):
            # Si falla la conversión, devolvemos el valor original
            # Las validaciones posteriores (check_field_definition) atraparán el error con mensaje limpio
            return value

    @classmethod
    def _evaluate_calculated_fields(cls, input_data: dict, field_defs_list: list):
        calculated_fields = [f for f in field_defs_list if f.field_type_code == "CALCULATED"]
        if not calculated_fields: return input_data

        fields_by_id = {f.id: f for f in field_defs_list}
        
        context = {}
        for fid, val in input_data.items():
            field_def = fields_by_id.get(fid)
            if field_def:
                typed_value = cls._convert_value_by_type(val, field_def)
                context[field_def.name] = typed_value

        evaluator = ExcelFormulaEvaluatorService(context=context)

        for field in calculated_fields:
            if not field.calculation_expression: continue
            try:
                result = evaluator.evaluate(field.calculation_expression)
                input_data[field.id] = result
                context[field.name] = result
            except Exception:
                # Si falla el cálculo, lo dejamos pasar o seteamos None,
                # para no bloquear todo el proceso por una fórmula
                input_data[field.id] = None

        return input_data

    @classmethod
    def _prepare_context_dict(cls, values_in):
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
        for field in field_defs_list:
            if field.id not in input_data:
                input_data[field.id] = None
        return input_data

    @classmethod
    def _apply_defaults(cls, input_data: dict, field_defs_list: list):
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
            # Aquí podríamos intentar identificar cuál campo causó el duplicado, 
            # pero suele ser una combinación. Devolvemos error general o al primer primary.
            first_primary_name = primary_fields[0].name
            raise ValidationError(
                "Ya existe un Lead con estos datos identificatorios.", 
                field=first_primary_name # Asignamos el error al primer campo primary para que se vea ahí
            )
        
    # ---------------------------------------------------------
    # HELPER DE MÁSCARAS
    # ---------------------------------------------------------
    @classmethod
    def _validate_mask(cls, value: str, mask: str, field_name: str):
        if not mask or value is None:
            return

        regex_pattern = "^"
        for char in mask:
            if char == "#":
                regex_pattern += r"\d"
            elif char == "A":
                regex_pattern += r"[a-zA-Z]"
            elif char == "*":
                regex_pattern += r"[a-zA-Z0-9]"
            else:
                regex_pattern += re.escape(char)
        regex_pattern += "$"

        val_str = str(value)
        if not re.match(regex_pattern, val_str):
            raise ValidationError(
                f"El formato no es válido. Se requiere: {mask}", 
                field=field_name
            )

    # -------------------------------------------------------------------------
    # VALIDACIÓN DE DEFINICIÓN (Requerido y Tipos)
    # -------------------------------------------------------------------------
    @classmethod
    def _check_field_definition(cls, field, value):
        is_mandatory = field.required or field.is_primary
        is_empty = value is None or (isinstance(value, str) and not value.strip())

        if is_empty:
            if is_mandatory:
                raise ValidationError(f"Este campo es obligatorio.", field=field.name)
            return 

        if field.input_mask:
            cls._validate_mask(value, field.input_mask, field.name)

        type_code = field.field_type.code
        
        if type_code == "INT":
            if isinstance(value, bool):
                raise ValidationError("Se espera un número entero.", field=field.name)
            if isinstance(value, float) and not value.is_integer():
                 raise ValidationError("Se espera un número entero, no decimal.", field=field.name)
            try:
                int(value)
            except (ValueError, TypeError):
                raise ValidationError("Valor inválido para número entero.", field=field.name)
        
        elif type_code == "NUMBER":
            try:
                float(value)
            except (ValueError, TypeError):
                raise ValidationError("Valor inválido para número decimal.", field=field.name)
        
        elif type_code == "BOOL":
            s_val = str(value).lower()
            if s_val not in ("true", "false", "1", "0"):
                raise ValidationError("Se espera Verdadero o Falso.", field=field.name)
        
        elif type_code == "DATE":
            try:
                datetime.strptime(str(value), "%Y-%m-%d")
            except ValueError:
                raise ValidationError(f"Formato inválido. Use {DATE_FORMAT}", field=field.name)
        
        elif type_code == "DATE_TIME":
            try:
                datetime.strptime(str(value), DATE_TIME_FORMAT)
            except ValueError:
                raise ValidationError(f"Formato inválido. Use {DATE_TIME_FORMAT}", field=field.name)

    @classmethod
    def _validate_processed_data(cls, uow, full_context, field_defs_list, current_lead_id=None):
        all_defs = {f.id: f for f in field_defs_list}
        
        for field in field_defs_list:
            val = full_context.get(field.id)

            # Validaciones de Nomencladores y Leads Relacionados
            if field.field_type_code in NOMENCLATOR_FIELD_TYPES:
                if val is None:
                    if field.required: raise ValidationError("Campo obligatorio.", field=field.name)
                    continue

                items_ids = val if isinstance(val, list) else [val]
                
                if field.field_subtype_code == f"{field.field_type_code}_SINGLE":
                    if len(items_ids) > 1:
                        raise ValidationError("Solo se permite una opción.", field=field.name)
                
                if not all(isinstance(x, int) for x in items_ids):
                    raise ValidationError("IDs de opción inválidos.", field=field.name)

            if field.field_type_code == "LEAD":
                if val is None: 
                    if field.required: raise ValidationError("Campo obligatorio.", field=field.name)
                    continue
                
                val_list = val if isinstance(val, list) else [val]
                # Deduplicar
                val_list = list(set(val_list))
                full_context[field.id] = val_list # Guardamos lista limpia
                
                # 1. Validar Auto-referencia
                if current_lead_id and current_lead_id in val_list:
                    raise ValidationError("Un lead no puede relacionarse consigo mismo.", field=field.name)

                # 2. Validar Existencia
                for x in val_list:
                    if not isinstance(x, int): raise ValidationError("ID de lead inválido.", field=field.name)
                    
                    related_lead = uow.session.query(Lead).filter_by(id=x).first()
                    if related_lead is None:
                        raise ValidationError(f"El lead relacionado ({x}) no existe.", field=field.name)
                    elif field.related_campaign_id != related_lead.campaign_id:
                        raise ValidationError(f"El lead ({x}) no pertenece a la campaña correcta.", field=field.name)
            
            # Paso 1: Validar definición básica (Tipos, máscaras, required simple)
            cls._check_field_definition(field, val)

            # Paso 2: Validar reglas complejas (ValidationRuleService)
            # Nota: validation_rule_service debería lanzar ValidationError con 'field' seteado si falla.
            try:
                LeadValidationLogic.validate_rules(
                    current_field=field,
                    raw_value=val,
                    all_values=full_context,
                    all_fields_defs=all_defs
                )
            except ValidationError as ve:
                # Si viene de logic, ya trae el field, lo re-lanzamos tal cual
                raise ve
            except ValueError as ve:
                # Si viene un ValueError genérico, lo convertimos y asignamos al campo actual
                raise ValidationError(str(ve), field=field.name)
            

    @classmethod
    def _reconstruct_items_for_repo(cls, processed_data: dict, field_defs_list: list):
        items_for_repo = []
        for fid, val in processed_data.items():
            field_def = next((f for f in field_defs_list if f.id == fid), None)
            if not field_def: continue
            
            item_dict = {'field_id': fid}
            
            if field_def.field_type_code in NOMENCLATOR_FIELD_TYPES:
                ids_list = val if isinstance(val, list) else [val]
                if not val: ids_list = []
                
                item_dict['nomenclator_ids_list'] = ids_list 
                item_dict['value'] = None
            elif field_def.field_type_code == "LEAD":
                ids_list = val if isinstance(val, list) else [val]
                if not val: ids_list = []
                
                item_dict['value'] = None
                item_dict['nomenclator_ids_list'] = []
                item_dict['related_lead_ids_list'] = ids_list
            else:
                if val is not None:
                    item_dict['value'] = str(val) 
                else:
                    item_dict['value'] = None
                item_dict['nomenclator_ids_list'] = []
            
            items_for_repo.append(cls.ItemProxy(item_dict))
        return items_for_repo

    # ---------------------------------------------------------
    # HELPER DE ARCHIVOS
    # ---------------------------------------------------------
    @classmethod
    def _handle_file_uploads(cls, context_data: dict, files_map: dict[int, UploadFile], field_defs_list: list):
        if not files_map: return context_data

        fields_by_id = {f.id: f for f in field_defs_list}

        for field_id, file in files_map.items():
            field_def = fields_by_id.get(field_id)
            
            if not field_def:
                # Error general (no de campo específico porque el ID no existe)
                raise ValidationError(f"Se intentó subir archivo para un campo inexistente (ID: {field_id})")
            
            if field_def.field_type_code != "FILE":
                raise ValidationError("Este campo no acepta archivos.", field=field_def.name)

            allowed_types = []
            if field_def.field_subtype_code == "FILE_IMAGE":
                allowed_types = ALLOWED_IMAGE_TYPES
            elif field_def.field_subtype_code == "FILE_DOCUMENT":
                allowed_types = ALLOWED_DOCUMENT_TYPES
            else:
                allowed_types = ALLOWED_IMAGE_TYPES + ALLOWED_DOCUMENT_TYPES

            try:
                StorageService.validate_file(file, allowed_types)
                path = StorageService.upload_file(file, folder="leads")
                context_data[field_id] = path
                
            except ValidationError as ve:
                # Asignamos el error al campo específico
                raise ValidationError(ve.message, field=field_def.name)
            except Exception as e:
                raise HTTPException(500, f"Error al subir archivo: {str(e)}")

        return context_data

    @classmethod
    def _enrich_lead_with_urls(cls, lead):
        if not lead or not lead.field_values: return lead

        for fv in lead.field_values:
            if fv.field and fv.field.field_type_code == "FILE":
                if fv.value: 
                    fv.value = StorageService.get_public_url(fv.value)
        return lead

    # ---------------------------------------------------------
    # Métodos CRUD Públicos
    # ---------------------------------------------------------

    @classmethod
    def create(cls, obj_in, created_by=None, files_map: dict = None):
        campaign_id = obj_in.campaign_id
        
        try:
            with UnitOfWork() as uow:
                all_field_defs = cls.field_repository.get_all_active_with_rules(uow.session)
                
                # 1. Validación inicial de existencia de campos
                defs_map = {f.id: f for f in all_field_defs}
                incoming_field_ids = [v.get('field_id') if isinstance(v, dict) else v.field_id for v in obj_in.values]
                
                for fid in incoming_field_ids:
                    field_def = defs_map.get(fid)
                    if not field_def: 
                        # Error general si el ID no existe
                        raise ValidationError(f"El campo con ID {fid} no existe en el sistema.")
                    if field_def.campaign_id != campaign_id: 
                        # Error asociado al campo específico (nombre)
                        raise ValidationError(f"Este campo no pertenece a la campaña seleccionada.", field=field_def.name)

                current_campaign_defs = [f for f in all_field_defs if f.campaign_id == campaign_id]

                if not current_campaign_defs:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail="La campaña no tiene campos configurados."
                    )
                
                # 2. Input -> Dict
                context_data = cls._prepare_context_dict(obj_in.values)

                # 3. Archivos
                if files_map:
                    context_data = cls._handle_file_uploads(context_data, files_map, current_campaign_defs)

                # 4. Completar y Default
                context_data = cls._fill_missing_fields(context_data, current_campaign_defs)
                context_data = cls._apply_defaults(context_data, current_campaign_defs)

                # 5. Calcular
                context_data = cls._evaluate_calculated_fields(context_data, current_campaign_defs)

                # 6. Chequear Duplicados (Lanza ValidationError con field si falla)
                cls._check_duplicates(uow.session, campaign_id, context_data, current_campaign_defs)
                
                # 7. Validar Reglas (Lanza ValidationError con field si falla)
                cls._validate_processed_data(uow, context_data, current_campaign_defs)
                
                # 8. Persistir
                clean_values = cls._reconstruct_items_for_repo(context_data, current_campaign_defs)
                
                lead = cls.repository.create(uow.session, {'campaign_id': campaign_id}, created_by=created_by)
                cls.repository.upsert_values(uow.session, lead.id, clean_values)
                lead_id = lead.id
            
            return cls.get_by_id(lead_id, detailed=True)

        # --- CAPTURA DE ERRORES ESTRUCTURADA ---
        except ValidationError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail={"message": ve.message, "field": ve.field}
            )
        except ValueError as ve:
            # Fallback para errores genéricos
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(ve), "field": None})

    @classmethod
    def update(cls, obj_id: int, obj_in, files_map: dict = None):
        try:
            with UnitOfWork() as uow:
                current_lead = cls.repository.get_by_id(uow.session, obj_id)
                if not current_lead: cls._not_found(obj_id)
                
                # Update base
                lead_data = obj_in.model_dump(exclude_unset=True, exclude={"values"})
                if lead_data:
                    cls.repository.update(uow.session, obj_id, lead_data)

                if obj_in.values is not None:
                    field_defs = cls.field_repository.get_all_active_with_rules(uow.session)
                    defs_map = {f.id: f for f in field_defs}
                    
                    # Validaciones previas
                    incoming_ids = [v.get('field_id') if isinstance(v, dict) else v.field_id for v in obj_in.values]
                    for fid in incoming_ids:
                        if fid not in defs_map: raise ValidationError(f"Campo {fid} no existe.")
                        # Validación de campaña cruzada
                        if defs_map[fid].campaign_id != current_lead.campaign_id: 
                             raise ValidationError("El campo no pertenece a esta campaña.", field=defs_map[fid].name)

                    incoming_data = cls._prepare_context_dict(obj_in.values)

                    if files_map:
                        incoming_data = cls._handle_file_uploads(incoming_data, files_map, field_defs)
                    
                    # Reconstruir estado actual DB
                    db_values = {}
                    for v in current_lead.field_values:
                        val = getattr(v, "value", None)
                        if val is None:
                            if hasattr(v, "nomenclator_items") and v.nomenclator_items:
                                val = [item.id for item in v.nomenclator_items]
                            elif hasattr(v, "related_leads") and v.related_leads:
                                val = [l.id for l in v.related_leads]
                            elif hasattr(v, "nomenclator_item_id") and v.nomenclator_item_id:
                                val = v.nomenclator_item_id
                        db_values[v.field_id] = val
                    
                    full_context = {**db_values, **incoming_data}
                    
                    # Calcular y Validar
                    full_context = cls._evaluate_calculated_fields(full_context, field_defs)
                    
                    # Importante: Pasar current_lead_id para excluirse a sí mismo en validaciones unique/related
                    cls._validate_processed_data(uow, full_context, field_defs, current_lead_id=obj_id)
                    
                    clean_values = cls._reconstruct_items_for_repo(incoming_data, field_defs)
                    cls.repository.upsert_values(uow.session, obj_id, clean_values)

            return cls.get_by_id(obj_id, detailed=True)

        except ValidationError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail={"message": ve.message, "field": ve.field}
            )
        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(ve), "field": None})

    @classmethod
    def search(cls, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, detailed: bool = False, search_req=None):
        def do_search(uow):
            total, items = cls.repository.search(
                session=uow.session,
                page=page,
                page_size=page_size,
                search_params=search_req,
                detailed=detailed
            )
            
            for item in items:
                cls._enrich_lead_with_urls(item)
                
            return total, items

        return cls._execute(
            action="Buscando Leads",
            func=do_search
        )
    
    @classmethod
    def get_all(cls, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, only_active: bool = True, detailed: bool = False, query=None, **kwargs):
        total, items = cls._execute(
            action=f"Obteniendo listado de leads",
            func=lambda uow: cls.repository.get_all(
                session=uow.session,
                page=page,
                page_size=page_size,
                only_active=only_active,
                detailed=detailed,
                search=query,
                **kwargs
            ))

        for item in items:
                cls._enrich_lead_with_urls(item)
                
        return total, items

    @classmethod
    def get_by_id(cls, obj_id: int, detailed: bool = True):
        lead = cls._execute(
            action="Obteniendo",
            obj_id=obj_id,
            func=lambda uow: cls.repository.get_by_id(uow.session, obj_id, detailed=detailed)
        )
        
        return cls._enrich_lead_with_urls(lead)
