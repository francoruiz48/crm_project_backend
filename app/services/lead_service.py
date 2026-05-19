from datetime import date, datetime
import re
from fastapi import HTTPException, UploadFile, status
from app.core.constans import ALLOWED_DOCUMENT_TYPES, ALLOWED_IMAGE_TYPES, DATE_FORMAT, DATE_TIME_FORMAT, DEFAULT_PAGE_SIZE, NOMENCLATOR_FIELD_TYPES, SystemAuditLogAction
from app.core.exceptions.exceptions import ValidationError 
from app.models.lead import Lead
from app.models.audit.lead_activity_history import LeadActivityHistory
from app.services.automation_engine import AutomationEngine
from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.unit_of_work import UnitOfWork
from app.services.lead_validation_logic import LeadValidationLogic
from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
from app.services.storage_service import StorageService
from app.db.repository.campaign_repository import CampaignRepository
from app.db.repository.lead_state_repository import LeadStateRepository
from app.db.repository.lead_state_transition_repository import LeadStateTransitionRepository
from app.db.repository.audit.lead_state_history_repository import LeadStateHistoryRepository
from app.core.security import UserContext
from app.services.routing_rule_evaluator_service import RoutingRuleEvaluatorService
from typing import List, Optional

class LeadService(BaseService):
    repository = LeadRepository
    field_repository = LeadFieldRepository
    campaign_repository = CampaignRepository
    state_repository = LeadStateRepository
    state_transition_repository = LeadStateTransitionRepository
    state_history_repository = LeadStateHistoryRepository

    class ItemProxy:
        def __init__(self, data_dict):
            self._data = data_dict
            for k, v in data_dict.items():
                setattr(self, k, v)
        
        def dict(self, **kwargs): return self._data
        def model_dump(self, **kwargs): return self._data
        def __getitem__(self, item): return self._data.get(item)


    # ---------------------------------------------------------
    # Helpers de Lógica de Negocio
    # ---------------------------------------------------------

    @classmethod
    def _log_activity(cls, session, lead_id: int, activity_type: str, details: dict, user_id: int = None):
        """
        Guarda un registro en la línea de tiempo del Lead.
        activity_type puede ser: 'CREATED', 'FIELD_UPDATED', 'NOTE_ADDED', etc.
        """
        activity = LeadActivityHistory(
            lead_id=lead_id,
            activity_type=activity_type,
            details=details,
            created_by=user_id
        )
        session.add(activity)

    @classmethod
    def _convert_value_by_type(cls, value, field_def):
        if value is None: return None
        type_code = field_def.field_type_code
        try:
            if type_code == "INT": return int(value)
            if type_code == "NUMBER": return float(value)
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
            if field.nomenclator_id is not None: continue
            current_val = input_data.get(field.id)
            if (current_val is None or current_val == ""):
                if field.default_value and not field.required:
                    input_data[field.id] = field.default_value
        return input_data

    @classmethod
    def _check_duplicates(cls, session, campaign_id: int, input_data: dict, field_defs_list: list, errors: list):
        """
        Verifica duplicados y agrega el error a la lista si encuentra uno.
        """
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
            # Reportamos el error en el primer campo primary para referencia visual
            first_primary = primary_fields[0]
            errors.append({
                "field": first_primary.name,
                "message": "Ya existe un Lead con estos datos identificatorios."
            })

    @classmethod
    def _translate_value_for_history(cls, session, field_def, raw_val):
        """
        Convierte IDs crudos de Nomencladores o Leads en sus nombres legibles
        para guardarlos en el historial del frontend.
        """
        if raw_val is None or raw_val == "" or raw_val == []:
            return ""

        is_list = isinstance(raw_val, list)
        val_list = raw_val if is_list else [raw_val]
        
        # 1. Traducción de Nomencladores
        if field_def.field_type_code in NOMENCLATOR_FIELD_TYPES:
            from app.models.nomenclator_item import NomenclatorItem
            items = session.query(NomenclatorItem).filter(NomenclatorItem.id.in_(val_list)).all()
            
            # Mapeamos para mantener el orden o simplemente extraemos nombres
            names = [item.value for item in items]
            return names if is_list else (names[0] if names else "")

        # 2. Traducción de Leads Relacionados (usando title_order)
        elif field_def.field_type_code == "LEAD":
            from app.models.lead_field import LeadField
            from app.models.lead_field_value import LeadFieldValue
            
            # Buscamos todos los valores de los leads vinculados que tengan title_order
            values = session.query(LeadFieldValue, LeadField).join(
                LeadField, LeadFieldValue.field_id == LeadField.id
            ).filter(
                LeadFieldValue.lead_id.in_(val_list),
                LeadField.title_order.isnot(None)
            ).order_by(LeadFieldValue.lead_id, LeadField.title_order.asc()).all()
            
            # Agrupamos los valores encontrados por lead_id
            lead_titles = {lid: [] for lid in val_list}
            for fv, f in values:
                if fv.value:
                    lead_titles[fv.lead_id].append(fv.value)
            
            display_names = []
            for lid in val_list:
                parts = lead_titles.get(lid, [])
                if parts:
                    display_names.append(" ".join(parts))
                else:
                    # Fallback si el lead vinculado no tiene campos con title_order
                    display_names.append("Lead vinculado")
                    
            return display_names if is_list else (display_names[0] if display_names else "")

        # 3. Si es texto, número, fecha, etc., devolver tal cual
        return raw_val

    # ---------------------------------------------------------
    # HELPER DE MÁSCARAS (Modificado para no lanzar excepción)
    # ---------------------------------------------------------
    @classmethod
    def _validate_mask(cls, value: str, mask: str, field_name: str, errors: list):
        if not mask or value is None:
            return

        regex_pattern = "^"
        for char in mask:
            if char == "#": regex_pattern += r"\d"
            elif char == "A": regex_pattern += r"[a-zA-Z]"
            elif char == "*": regex_pattern += r"[a-zA-Z0-9]"
            else: regex_pattern += re.escape(char)
        regex_pattern += "$"

        val_str = str(value)
        if not re.match(regex_pattern, val_str):
            errors.append({
                "field": field_name,
                "message": f"El formato no es válido. Se requiere: {mask}"
            })

    # -------------------------------------------------------------------------
    # VALIDACIÓN DE DEFINICIÓN (Requerido y Tipos)
    # -------------------------------------------------------------------------
    @classmethod
    def _check_field_definition(cls, field, value, errors: list):
        """
        Valida tipos básicos y requeridos. Agrega errores a la lista 'errors'.
        Retorna True si la validación básica pasó, False si falló (para detener validaciones posteriores en ese campo).
        """
        is_mandatory = field.required or field.is_primary
        is_empty = value is None or (isinstance(value, str) and not value.strip())

        if is_empty:
            if is_mandatory:
                errors.append({"field": field.name, "message": "Este campo es obligatorio."})
                return False # Detener chequeos adicionales si está vacío
            return True # Campo vacío opcional, todo ok

        if field.input_mask:
            cls._validate_mask(value, field.input_mask, field.name, errors)

        type_code = field.field_type.code
        err_msg = None

        if type_code == "INT":
            if isinstance(value, bool): err_msg = "Se espera un número entero."
            elif isinstance(value, float) and not value.is_integer(): err_msg = "Se espera un número entero, no decimal."
            else:
                try: int(value)
                except (ValueError, TypeError): err_msg = "Valor inválido para número entero."
        
        elif type_code == "NUMBER":
            try: float(value)
            except (ValueError, TypeError): err_msg = "Valor inválido para número decimal."
        
        elif type_code == "BOOL":
            s_val = str(value).lower()
            if s_val not in ("true", "false", "1", "0"): err_msg = "Se espera Verdadero o Falso."
        
        elif type_code == "DATE":
            try: datetime.strptime(str(value), "%Y-%m-%d")
            except ValueError: err_msg = f"Formato inválido. Use {DATE_FORMAT}"
        
        elif type_code == "DATE_TIME":
            try: datetime.strptime(str(value), DATE_TIME_FORMAT)
            except ValueError: err_msg = f"Formato inválido. Use {DATE_TIME_FORMAT}"

        if err_msg:
            errors.append({"field": field.name, "message": err_msg})
            return False
        
        return True

    @classmethod
    def _validate_processed_data(cls, uow, full_context, field_defs_list, errors: list, current_lead_id=None):
        all_defs = {f.id: f for f in field_defs_list}
        
        for field in field_defs_list:
            val = full_context.get(field.id)

            # --- Validaciones de Nomencladores ---
            if field.field_type_code in NOMENCLATOR_FIELD_TYPES:
                if val is None:
                    if field.required: 
                        errors.append({"field": field.name, "message": "Campo obligatorio."})
                    continue

                items_ids = val if isinstance(val, list) else [val]
                
                if field.field_subtype_code == f"{field.field_type_code}_SINGLE":
                    if len(items_ids) > 1:
                        errors.append({"field": field.name, "message": "Solo se permite una opción."})
                        continue
                
                if not all(isinstance(x, int) for x in items_ids):
                    errors.append({"field": field.name, "message": "IDs de opción inválidos."})
                    continue

            # --- Validaciones de Leads Relacionados ---
            elif field.field_type_code == "LEAD":
                if val is None: 
                    if field.required: 
                        errors.append({"field": field.name, "message": "Campo obligatorio."})
                    continue
                
                val_list = val if isinstance(val, list) else [val]
                val_list = list(set(val_list)) # Deduplicar
                full_context[field.id] = val_list 
                
                if current_lead_id and current_lead_id in val_list:
                    errors.append({"field": field.name, "message": "Un lead no puede relacionarse consigo mismo."})
                    continue

                for x in val_list:
                    if not isinstance(x, int): 
                        errors.append({"field": field.name, "message": "ID de lead inválido."})
                        continue
                    
                    related_lead = uow.session.query(Lead).filter_by(id=x).first()
                    if related_lead is None:
                        errors.append({"field": field.name, "message": f"El lead relacionado ({x}) no existe."})
                    elif field.related_campaign_id != related_lead.campaign_id:
                        errors.append({"field": field.name, "message": f"El lead ({x}) no pertenece a la campaña correcta."})
            
            # --- Validaciones Genéricas ---
            else:
                # Paso 1: Definición básica (retorna False si falla algo crítico)
                is_valid_type = cls._check_field_definition(field, val, errors)

                # Paso 2: Reglas complejas (Solo si el tipo básico es válido)
                if is_valid_type:

                    is_empty = val is None or (isinstance(val, str) and not str(val).strip())

                    if not is_empty:
                        try:
                            LeadValidationLogic.validate_rules(
                                current_field=field,
                                raw_value=val,
                                all_values=full_context,
                                all_fields_defs=all_defs
                            )
                        except ValidationError as ve:
                            # Atrapamos el error individual y lo agregamos a la lista
                            errors.append({"field": field.name, "message": ve.message})
                        except ValueError as ve:
                            errors.append({"field": field.name, "message": str(ve)})

    @classmethod
    def _reconstruct_items_for_repo(cls, processed_data: dict, field_defs_list: list):
        items_for_repo = []
        for fid, val in processed_data.items():
            field_def = next((f for f in field_defs_list if f.id == fid), None)
            if not field_def: continue
            
            item_dict = {'field_id': fid}
            
            if field_def.field_type_code in NOMENCLATOR_FIELD_TYPES:
                ids_list = val if isinstance(val, list) else [val]
                item_dict['nomenclator_ids_list'] = ids_list if val else []
                item_dict['value'] = None
            elif field_def.field_type_code == "LEAD":
                ids_list = val if isinstance(val, list) else [val]
                item_dict['value'] = None
                item_dict['nomenclator_ids_list'] = []
                item_dict['related_lead_ids_list'] = ids_list if val else []
            else:
                item_dict['value'] = str(val) if val is not None else None
                item_dict['nomenclator_ids_list'] = []
            
            items_for_repo.append(cls.ItemProxy(item_dict))
        return items_for_repo

    # ---------------------------------------------------------
    # HELPER DE ARCHIVOS (Con manejo de errores en lista)
    # ---------------------------------------------------------
    @classmethod
    def _handle_file_uploads(cls, context_data: dict, files_map: dict[int, UploadFile], field_defs_list: list, errors: list, is_simulation: bool = False):
        if not files_map: return context_data

        fields_by_id = {f.id: f for f in field_defs_list}

        for field_id, file in files_map.items():
            field_def = fields_by_id.get(field_id)
            
            if not field_def:
                errors.append({"field": f"ID_{field_id}", "message": "Se intentó subir archivo para un campo inexistente."})
                continue
            
            if field_def.field_type_code != "FILE":
                errors.append({"field": field_def.name, "message": "Este campo no acepta archivos."})
                continue

            allowed_types = []
            if field_def.field_subtype_code == "FILE_IMAGE":
                allowed_types = ALLOWED_IMAGE_TYPES
            elif field_def.field_subtype_code == "FILE_DOCUMENT":
                allowed_types = ALLOWED_DOCUMENT_TYPES
            else:
                allowed_types = ALLOWED_IMAGE_TYPES + ALLOWED_DOCUMENT_TYPES

            try:
                # Validar
                StorageService.validate_file(file, allowed_types)
                
                if is_simulation:
                    context_data[field_id] = f"simulated_path/{file.filename}"
                else:
                    path = StorageService.upload_file(file, folder="leads")
                    context_data[field_id] = path
                
            except ValidationError as ve:
                errors.append({"field": field_def.name, "message": ve.message})
            except Exception as e:
                # Errores técnicos los reportamos como genéricos o asociados al campo
                errors.append({"field": field_def.name, "message": f"Error técnico subiendo archivo: {str(e)}"})

        return context_data

    @classmethod
    def _enrich_lead_with_urls(cls, lead):
        if not lead: return lead
        
        # 1. Enriquecer la URL de la foto de perfil nativa
        if hasattr(lead, 'picture_url') and lead.picture_url:
            # Asumiendo que get_public_url no duplica el dominio si ya lo tiene
            lead.picture_url = StorageService.get_public_url(lead.picture_url)

        # 2. Enriquecer los campos dinámicos tipo FILE
        if not lead.field_values: return lead
        for fv in lead.field_values:
            if fv.field and fv.field.field_type_code == "FILE":
                if fv.value: 
                    fv.value = StorageService.get_public_url(fv.value)
        return lead


    # ---------------------------------------------------------
    # LÓGICA CENTRAL DE PREPARACIÓN
    # ---------------------------------------------------------
    @classmethod
    def _prepare_creation_data(cls, uow, obj_in, files_map, created_by, is_simulation=False):
        """
        Ejecuta lógica. Retorna tuple. Si hay errores, lanza HTTPException con la lista.
        """
        errors = [] # ACUMULADOR DE ERRORES

        campaign_id = obj_in.campaign_id
        all_field_defs = cls.field_repository.get_all_active_with_rules(uow.session, campaign_id=campaign_id)
        
        # 1. Validación inicial de existencia de campos
        defs_map = {f.id: f for f in all_field_defs}
        incoming_field_ids = [v.get('field_id') if isinstance(v, dict) else v.field_id for v in obj_in.values]
        
        for fid in incoming_field_ids:
            field_def = defs_map.get(fid)
            if not field_def: 
                errors.append({"field": f"ID_{fid}", "message": "El campo no existe en el sistema."})
                continue
            if field_def.campaign_id != campaign_id: 
                errors.append({"field": field_def.name, "message": "Este campo no pertenece a la campaña seleccionada."})

        # Si hay errores estructurales graves, fallamos antes de seguir
        if errors:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

        current_campaign_defs = [f for f in all_field_defs if f.campaign_id == campaign_id]

        if not current_campaign_defs:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "general", "message": "La campaña no tiene campos configurados."}])
        
        # 2. Input -> Dict
        context_data = cls._prepare_context_dict(obj_in.values)

        # 3. Archivos (Pasamos la lista de errores)
        if files_map:
            context_data = cls._handle_file_uploads(context_data, files_map, current_campaign_defs, errors, is_simulation=is_simulation)

        # 4. Completar y Default
        context_data = cls._fill_missing_fields(context_data, current_campaign_defs)
        context_data = cls._apply_defaults(context_data, current_campaign_defs)

        # 5. INYECCIÓN DEL MOTOR DE AUTOMATIZACIÓN
        event = "ON_CREATE" if not is_simulation else "SIMULATION" 
        context_data, automation_audit = AutomationEngine.run(
            session=uow.session, 
            campaign_id=campaign_id, 
            context_data=context_data, 
            event=event
        )

        # 6. Calcular (Los cálculos suelen ser seguros, si fallan dan None)
        context_data = cls._evaluate_calculated_fields(context_data, current_campaign_defs)

        # 7. Chequear Duplicados (Agrega a errors si falla)
        cls._check_duplicates(uow.session, campaign_id, context_data, current_campaign_defs, errors)
        
        # 8. Validar Reglas y Tipos (Agrega a errors si falla)
        cls._validate_processed_data(uow, context_data, current_campaign_defs, errors, current_lead_id=None)
        
        # --- VERIFICACIÓN FINAL ---
        if errors:
            # Lanzamos la excepción con la LISTA de errores
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

        # 9. Preparar estructura
        clean_values = cls._reconstruct_items_for_repo(context_data, current_campaign_defs)
        
        return clean_values, context_data, current_campaign_defs

    # ---------------------------------------------------------
    # Métodos CRUD Públicos
    # ---------------------------------------------------------

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None, files_map: dict = None, avatar_file: UploadFile = None):
        # NOTA: Ya no necesitamos try/except ValidationError globales envolventes, 
        # porque _prepare_creation_data gestiona la lista y lanza HTTPException.
        with UnitOfWork() as uow:
            # Usamos la lógica compartida
            created_by = user_context.user.id if user_context else None

            clean_values, context_data, current_campaign_defs = cls._prepare_creation_data(uow, obj_in, files_map, created_by=created_by, is_simulation=False)
            
            campaign = cls.campaign_repository.get_by_id(uow.session, obj_in.campaign_id, user_context=user_context)
            if not campaign:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "La campaña no existe."}])

            #Validamos y obtenemos el estado inicial para asignarlo al lead. Si no hay estado inicial, la campaña no tiene un flujo válido.
            initial_state = cls.state_repository.get_all(uow.session, user_context=user_context, lead_flow_id=campaign.lead_flow_id, is_initial=True)
            initial_state = initial_state[0] if initial_state else None
            if not initial_state:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "general", "message": "La campaña no tiene un flujo de estados válido (falta configurar un estado inicial)."}]
                )
            
            from app.models.lead_contact_state import LeadContactState
            initial_contact_state = uow.session.query(LeadContactState).filter_by(
                organization_id=campaign.organization_id,
                is_initial=True,
                active=True
            ).first()
            
            #Ejecución de Motor de enrutamiento
            assigned_team_id = RoutingRuleEvaluatorService.evaluate(
                session = uow.session,
                campaign_id = campaign.id,
                organization_id = campaign.organization_id,
                context_data = context_data,
                field_defs_list = current_campaign_defs,
                lead_obj = None, # Aún no existe, se asigna antes de crear
            )

            # Si el frontend manda un string directo (ej. URL ya subida)
            picture_url = getattr(obj_in, 'picture_url', None)

            if avatar_file:
                StorageService.validate_file(avatar_file, ALLOWED_IMAGE_TYPES)
                picture_url = StorageService.upload_file(avatar_file, folder="avatars")

            # Persistencia Real (Ahora inyectamos el current_state_id)
            lead_data = {
                'campaign_id': obj_in.campaign_id,
                'current_state_id': initial_state.id,
                'contact_state_id': initial_contact_state.id if initial_contact_state else None,
                'team_id': assigned_team_id,
                'picture_url': picture_url
            }

            lead = cls.repository.create(uow.session, lead_data, user_context=user_context)
            cls.repository.upsert_values(uow.session, lead.id, clean_values)
            lead_id = lead.id

            #Agregamos las etiquetas si vienen en el input
            if hasattr(obj_in, 'tag_ids') and obj_in.tag_ids is not None:
                # Buscamos el objeto REAL de SQLAlchemy para que las relaciones ORM se guarden
                lead_db = uow.session.query(Lead).filter_by(id=lead_id).first()
                cls._assign_tags(uow.session, lead_db, obj_in.tag_ids, campaign.organization_id)

            uow.session.flush()

            state_history_data = {
                "lead_id": lead_id,
                "from_state_id": None,
                "to_state_id": initial_state.id,
                "notes": "Ingreso al sistema"
            }
            cls.state_history_repository.create(uow.session, state_history_data, user_context=user_context)

            cls._log_activity(
                session=uow.session,
                lead_id=lead_id,
                activity_type="LEAD_CREATED",
                details={"message": "Lead creado e ingresado a la campaña."},
                user_id=created_by
            )

            cls._log_audit(uow.session, lead, action=SystemAuditLogAction.CREATED, changes=None, user_id=created_by)
        
        return cls.get_by_id(lead_id, detailed=True)

    @classmethod
    def bulk_assign(cls, lead_ids: list[int], target_team_id: int = None, target_user_id: int = None, user_context: Optional[UserContext] = None):
        """
        Reasigna un lote de leads a un equipo o usuario específico.
        """

        def do_bulk(uow):
            leads = uow.session.query(Lead).filter(Lead.id.in_(lead_ids)).all()
            updated_by = user_context.user.id if user_context and user_context.user else None
            if not leads:
                return []
            
            for lead in leads:
                old_team = lead.team_id
                old_user = lead.assigned_to_user_id

                # Solo actualizamos si se envió un valor nuevo
                if target_team_id is not None:
                    lead.team_id = target_team_id
                if target_user_id is not None:
                    lead.assigned_to_user_id = target_user_id
                
                # 1. Timeline del Lead
                cls._log_activity(
                    session=uow.session,
                    lead_id=lead.id,
                    activity_type="LEAD_REASSIGNED",
                    details={"new_team_id": lead.team_id, "new_user_id": lead.assigned_to_user_id},
                    user_id=updated_by
                )
                
                # 2. Auditoría Global del Sistema
                cls._log_audit(
                    session=uow.session,
                    obj=lead,
                    action=SystemAuditLogAction.UPDATED,
                    changes={
                        "team_id": {"old": old_team, "new": lead.team_id},
                        "assigned_to_user_id": {"old": old_user, "new": lead.assigned_to_user_id}
                    },
                    user_id=updated_by
                )
                
            return leads
            
        return cls._execute(action="Reasignación Masiva", func=do_bulk, success_msg="Leads reasignados con éxito.")

    @classmethod
    def change_state(cls, obj_id: int, new_state_id: int, notes: str = None, user_context: Optional[UserContext] = None):
        """
        Cambia el estado de un lead verificando que la transición sea permitida en el flujo.
        Registra el evento en el historial.
        """
        with UnitOfWork() as uow:
            lead = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not lead:
                cls._not_found(obj_id)

            current_state_id = lead.current_state_id

            # 1. Validar que no estemos moviéndolo al mismo estado
            if current_state_id == new_state_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "new_state_id", "message": "El lead ya se encuentra en este estado."}]
                )
            
            campaign = cls.campaign_repository.get_by_id(uow.session, lead.campaign_id, user_context=user_context)

            # 2. Validar que el salto esté permitido en la campaña
            if current_state_id is not None:
                transition = cls.state_transition_repository.get_all(
                    uow.session, 
                    lead_flow_id=campaign.lead_flow_id, 
                    from_state_id=current_state_id, 
                    to_state_id=new_state_id,
                    user_context=user_context
                )

                if not transition:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, 
                        detail=[{"field": "new_state_id", "message": "Transición no permitida. No hay una ruta válida hacia este estado."}]
                    )

            # 3. Actualizar el estado actual del Lead
            cls.repository.update(uow.session, obj_id, {"current_state_id": new_state_id}, user_context=user_context)

            # 4. Inyectar el historial
            history_data = {
                "lead_id": lead.id,
                "from_state_id": current_state_id,
                "to_state_id": new_state_id,
                "notes": notes
            }
            cls.state_history_repository.create(uow.session, history_data, user_context=user_context)

            # Pasamos 'lead' y formateamos el old vs new
            diff_state = {"current_state_id": {"old": current_state_id, "new": new_state_id}}
            cls._log_audit(uow.session, lead, action=SystemAuditLogAction.UPDATED, changes=diff_state, user_id=user_context.user.id if user_context else None)

        # Devolvemos el Lead actualizado para el Frontend
        return cls.get_by_id(obj_id, detailed=True)

    @classmethod
    def simulate_create(cls, obj_in, user_context: Optional[UserContext] = None, files_map: dict = None):
        with UnitOfWork() as uow:
            created_by = user_context.user.id if user_context else None
            clean_values, context_data, field_defs = cls._prepare_creation_data(uow, obj_in, files_map, created_by, is_simulation=True)
            
            # Para la simulación (que no guarda en DB), podemos usar el ContextVar directamente 
            # para armar el objeto dummy con el ID correcto.
            from app.core.context import TENANT_ORG_ID
            dummy_org_id = TENANT_ORG_ID.get() or 0

            simulated_values = []
            fields_map = {f.id: f for f in field_defs}
            dummy_lead_id = -1 

            for item_proxy in clean_values:
                data = item_proxy._data
                fid = data['field_id']
                field_def = fields_map.get(fid)
                val_display = data.get('value')
                
                simulated_values.append({
                    "id": -1 * fid,
                    "lead_id": dummy_lead_id,
                    "field_id": fid,
                    "value": val_display,
                    "nomenclator_items": [], 
                    "related_leads": [],
                    "field": {
                        "id": field_def.id,
                        "name": field_def.name,
                        "field_type": {"code": field_def.field_type_code},
                        "campaign_id": field_def.campaign_id,
                        "organization_id": dummy_org_id,
                        "lead_field_section": {
                            "id": field_def.lead_field_section_id,
                            "name": "Simulated Section",
                            "organization_id": dummy_org_id
                        } if field_def.lead_field_section_id else None,
                        "active": True
                    }
                })

            return {
                "id": dummy_lead_id,
                "campaign_id": obj_in.campaign_id,
                "organization_id": dummy_org_id,
                "active": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "field_values": simulated_values,
                "created_by": created_by
            }

    @classmethod
    def update(cls, obj_id: int, obj_in, files_map: dict = None, user_context: Optional[UserContext] = None, avatar_file: UploadFile = None):
        errors = [] 
        
        with UnitOfWork() as uow:
            current_lead = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not current_lead: cls._not_found(obj_id)
            
            # Logica de Tags
            if "tag_ids" in obj_in.model_fields_set:
                lead_db = uow.session.query(Lead).filter_by(id=obj_id).first()
                cls._assign_tags(
                    session=uow.session, 
                    lead_obj=lead_db, 
                    tag_ids=obj_in.tag_ids, 
                    org_id=current_lead.organization_id 
                )

            # Update base
            lead_data = obj_in.model_dump(exclude_unset=True, exclude={"values", "tag_ids"})

            if avatar_file:
                StorageService.validate_file(avatar_file, ALLOWED_IMAGE_TYPES)
                picture_url = StorageService.upload_file(avatar_file, folder="avatars")
                lead_data["picture_url"] = picture_url

            if lead_data:
                cls.repository.update(uow.session, obj_id, lead_data, user_context=user_context)

            if obj_in.values is not None:
                all_field_defs = cls.field_repository.get_all_active_with_rules(uow.session, campaign_id=current_lead.campaign_id)
                current_campaign_defs = [f for f in all_field_defs if f.campaign_id == current_lead.campaign_id]
                
                defs_map = {f.id: f for f in current_campaign_defs}
                
                # Validaciones previas
                incoming_ids = [v.get('field_id') if isinstance(v, dict) else v.field_id for v in obj_in.values]
                for fid in incoming_ids:
                    if fid not in defs_map: 
                        errors.append({"field": f"ID_{fid}", "message": "Campo no existe o no pertenece a esta campaña."})
                        continue
                    if defs_map[fid].campaign_id != current_lead.campaign_id: 
                        errors.append({"field": defs_map[fid].name, "message": "El campo no pertenece a esta campaña."})

                if errors:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

                incoming_data = cls._prepare_context_dict(obj_in.values)

                if files_map:
                    incoming_data = cls._handle_file_uploads(incoming_data, files_map, current_campaign_defs, errors)
                
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

                #INYECCIÓN DEL MOTOR DE AUTOMATIZACIÓN (ON_UPDATE)
                full_context, automation_audit = AutomationEngine.run(
                    session=uow.session,
                    campaign_id=current_lead.campaign_id,
                    context_data=full_context,
                    event="ON_UPDATE"
                )

                #Calcular los campos calculados con el contexto completo (DB + incoming)
                full_context = cls._evaluate_calculated_fields(full_context, current_campaign_defs)
                #Validar reglas 
                cls._validate_processed_data(uow, full_context, current_campaign_defs, errors, current_lead_id=obj_id)
                
                if errors:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

                for field in current_campaign_defs:
                    if field.field_type_code == "CALCULATED" and field.id in full_context:
                        incoming_data[field.id] = full_context[field.id]

                for auto_fid, auto_data in automation_audit.items():
                    incoming_data[auto_fid] = auto_data["new_value"]


                # --- HISTORIAL DEL LEAD ---
                changes = {}           # Para auditoría interna (Logs técnicos con IDs)
                history_changes = {}   # Para el usuario final (Legible, sin IDs)
                
                def _norm_for_compare(val):
                    if isinstance(val, list): return sorted([str(x) for x in val])
                    if val is None: return ""
                    if isinstance(val, float): return str(round(val, 4))
                    return str(val).strip()

                for fid, new_val in incoming_data.items():
                    field_def = defs_map.get(fid)
                    if not field_def: continue
                    
                    old_val = db_values.get(fid)

                    # Comparamos si el valor realmente cambió
                    if _norm_for_compare(old_val) != _norm_for_compare(new_val):
                        # 1. Guardamos el cambio técnico crudo
                        changes[fid] = {
                            "field_name": field_def.name,
                            "old_value": old_val,
                            "new_value": new_val
                        }
                        
                        # 2. Traducimos para el timeline del usuario
                        display_old = cls._translate_value_for_history(uow.session, field_def, old_val)
                        display_new = cls._translate_value_for_history(uow.session, field_def, new_val)
                        
                        history_change_data = {
                            "field_name": field_def.name,
                            "old_value": display_old,
                            "new_value": display_new
                        }

                        if fid in automation_audit:
                            history_change_data["source_rule"] = automation_audit[fid]["source_rule"]

                        history_changes[fid] = history_change_data

                # Persistencia
                clean_values = cls._reconstruct_items_for_repo(incoming_data, current_campaign_defs)
                cls.repository.upsert_values(uow.session, obj_id, clean_values)

                user_id = user_context.user.id if user_context else None

                # Registro duro del sistema (con IDs)
                cls._log_audit(uow.session, current_lead, action=SystemAuditLogAction.UPDATED, changes=changes, user_id=user_id)

                # Registro visual del front (Nombres legibles, "Juan Pérez" en lugar de [14])
                if history_changes:
                    cls._log_activity(
                        session=uow.session,
                        lead_id=obj_id,
                        activity_type="FIELDS_UPDATED",
                        details={"changes": history_changes},
                        user_id=user_id
                    )

        return cls.get_by_id(obj_id, detailed=True)

    @classmethod
    def search(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, detailed: bool = False, search_req=None, order_by=None, ascending: bool = True):
        def do_search(uow):
            total, items = cls.repository.search(
                session=uow.session, user_context=user_context,
                page=page,
                page_size=page_size,
                search_params=search_req,
                detailed=detailed,
                order_by=order_by,
                ascending=ascending
            )
            
            for item in items:
                cls._enrich_lead_with_urls(item)
                
            return total, items

        return cls._execute(
            action="Buscando Leads",
            func=do_search
        )
    
    @classmethod
    def get_all(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, only_active: bool = True, detailed: bool = False, query=None, **kwargs):
        total, items = cls._execute(
            action=f"Obteniendo listado de leads",
            func=lambda uow: cls.repository.get_all(
                session=uow.session, user_context=user_context,
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
    def get_by_id(cls, obj_id: int, user_context: Optional[UserContext] = None, detailed: bool = True):
        lead = cls._execute(
            action="Obteniendo",
            obj_id=obj_id,
            func=lambda uow: cls.repository.get_by_id(uow.session, obj_id, user_context=user_context, detailed=detailed)
        )
        
        return cls._enrich_lead_with_urls(lead)
    
    @classmethod
    def _assign_tags(cls, session, lead_obj, tag_ids: list[int], org_id: int):
        """
        Asigna etiquetas a un lead. Si tag_ids es una lista vacía, borra las asociaciones.
        Verifica que todas las etiquetas pertenezcan a la organización del lead.
        """
        from app.models.tag import Tag
        
        if tag_ids is None or not tag_ids:
            lead_obj.tags = [] # Borramos todas las etiquetas asociadas
            return

        # Buscamos solo las etiquetas que coinciden con los IDs y pertenecen a la empresa
        tags = session.query(Tag).filter(
            Tag.id.in_(tag_ids),
            Tag.organization_id == org_id,
            Tag.active == True
        ).all()
        
        # Validación de seguridad: ¿Encontró la misma cantidad de etiquetas que enviaron?
        # Usamos set() por si el front mandó IDs duplicados por error en el array
        if len(tags) != len(set(tag_ids)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, 
                detail=[{"field": "tag_ids", "message": "Una o más etiquetas no existen o no pertenecen a tu organización."}]
            )
            
        # Asignación directa: SQLAlchemy se encarga de hacer los INSERT/DELETE en la tabla intermedia
        lead_obj.tags = tags