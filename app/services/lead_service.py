from datetime import date, datetime
import re
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func
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
        seen_ids = set()
        for v in values_in:
            if isinstance(v, dict):
                fid = v.get('field_id')
                val = v.get('nomenclator_item_id') or v.get('value')
            else:
                fid = getattr(v, 'field_id', None)
                val = getattr(v, 'nomenclator_item_id', None) or getattr(v, 'value', None)
            if fid in seen_ids:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": f"ID_{fid}", "message": "El campo fue enviado más de una vez en el mismo request."}]
                )
            seen_ids.add(fid)
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
    def _check_duplicates(cls, session, campaign_id: int, input_data: dict, field_defs_list: list, errors: list, exclude_lead_id: int = None):
        """
        Verifica duplicados y agrega el error a la lista si encuentra uno.
        exclude_lead_id: excluye el lead actual de la búsqueda (para updates).
        """
        primary_fields = [f for f in field_defs_list if f.is_primary and f.nomenclator_id is None]
        if not primary_fields: return

        values_to_check = {}
        for field in primary_fields:
            val = input_data.get(field.id)
            if val is not None and val != "" and not isinstance(val, bool):
                values_to_check[field.id] = val

        if not values_to_check: return

        is_dup = cls.repository.find_duplicate(session, campaign_id, values_to_check, exclude_id=exclude_lead_id)
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

        val_str = str(value).strip()
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

                # Validar que los IDs pertenecen al nomenclador del campo
                if field.nomenclator_id is not None:
                    from app.models.nomenclator_item import NomenclatorItem
                    valid_items = uow.session.query(NomenclatorItem.id).filter(
                        NomenclatorItem.id.in_(items_ids),
                        NomenclatorItem.nomenclator_id == field.nomenclator_id,
                        NomenclatorItem.active == True
                    ).all()
                    valid_ids = {row.id for row in valid_items}
                    invalid_ids = [x for x in items_ids if x not in valid_ids]
                    if invalid_ids:
                        errors.append({"field": field.name, "message": "Una o más opciones seleccionadas no son válidas para este campo."})
                        continue

                # Feature de nomencladores dependientes (ver docs/nomencladores.md):
                # si este campo depende de otro, cada ítem elegido tiene que
                # tener como padre alguno de los ítems elegidos en el campo
                # padre (semántica OR si el padre es de selección múltiple).
                # full_context ya trae el valor persistido del padre si no vino
                # en este request puntual (merge db_values + incoming_data más
                # arriba) — decisión del usuario: validar contra ese valor, no
                # ignorar la coherencia solo porque el padre no vino explícito.
                if getattr(field, "depends_on_field_id", None):
                    parent_val = full_context.get(field.depends_on_field_id)
                    parent_ids = parent_val if isinstance(parent_val, list) else ([parent_val] if parent_val is not None else [])
                    parent_ids = [x for x in parent_ids if x is not None]
                    if not parent_ids:
                        parent_name = all_defs.get(field.depends_on_field_id).name if all_defs.get(field.depends_on_field_id) else "el campo del que depende"
                        errors.append({"field": field.name, "message": f"Este campo depende de '{parent_name}', que todavía no tiene un valor asignado."})
                        continue

                    from app.models.nomenclator_item import nomenclator_item_parent_association
                    valid_child_rows = uow.session.query(nomenclator_item_parent_association.c.item_id).filter(
                        nomenclator_item_parent_association.c.item_id.in_(items_ids),
                        nomenclator_item_parent_association.c.parent_item_id.in_(parent_ids)
                    ).all()
                    valid_child_ids = {row.item_id for row in valid_child_rows}
                    mismatched = [x for x in items_ids if x not in valid_child_ids]
                    if mismatched:
                        parent_name = all_defs.get(field.depends_on_field_id).name if all_defs.get(field.depends_on_field_id) else "el campo del que depende"
                        errors.append({"field": field.name, "message": f"Una o más opciones seleccionadas no son hijas del valor elegido en '{parent_name}'."})
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

                    from app.core.context import TENANT_ORG_ID
                    org_id = TENANT_ORG_ID.get()
                    related_lead = uow.session.query(Lead).filter_by(id=x, organization_id=org_id).first()
                    if related_lead is None:
                        # Respuesta genérica: no revelamos si el lead existe en otro tenant
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
    # HELPER DE ARCHIVOS (Dos fases: validar primero, subir después)
    # ---------------------------------------------------------
    @classmethod
    def _validate_file_uploads(cls, context_data: dict, files_map: dict, field_defs_list: list, errors: list) -> dict:
        """
        Fase 1: valida tipo y tamaño de cada archivo sin subirlos.
        Marca context_data con un placeholder para que las validaciones de requerido pasen.
        Retorna un dict {field_id: file} con los archivos que pasaron validación.
        """
        if not files_map: return {}

        fields_by_id = {f.id: f for f in field_defs_list}
        pending = {}

        for field_id, file in files_map.items():
            field_def = fields_by_id.get(field_id)

            if not field_def:
                errors.append({"field": f"ID_{field_id}", "message": "Se intentó subir archivo para un campo inexistente."})
                continue

            if field_def.field_type_code != "FILE":
                errors.append({"field": field_def.name, "message": "Este campo no acepta archivos."})
                continue

            if field_def.field_subtype_code == "FILE_IMAGE":
                allowed_types = ALLOWED_IMAGE_TYPES
            elif field_def.field_subtype_code == "FILE_DOCUMENT":
                allowed_types = ALLOWED_DOCUMENT_TYPES
            else:
                allowed_types = ALLOWED_IMAGE_TYPES + ALLOWED_DOCUMENT_TYPES

            try:
                StorageService.validate_file(file, allowed_types)
                context_data[field_id] = "__pending_upload__"  # placeholder: campo no vacío
                pending[field_id] = file
            except ValidationError as ve:
                errors.append({"field": field_def.name, "message": ve.message})
            except Exception as e:
                errors.append({"field": field_def.name, "message": f"Archivo inválido: {str(e)}"})

        return pending

    @classmethod
    def _execute_file_uploads(cls, context_data: dict, pending_files: dict, folder: str = "leads"):
        """
        Fase 2: sube los archivos pre-validados y reemplaza los placeholders con paths reales.
        Solo llamar después de que todas las validaciones de negocio hayan pasado.
        """
        for field_id, file in pending_files.items():
            path = StorageService.upload_file(file, folder=folder)
            context_data[field_id] = path
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
    def _prepare_creation_data(cls, uow, obj_in, files_map, created_by, campaign, is_simulation=False):
        """
        Ejecuta lógica. Retorna tuple. Si hay errores, lanza HTTPException con la lista.
        Recibe el objeto 'campaign' ya validado para evitar re-queries y errores semánticos.
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

        # 3. Archivos — Fase 1: solo validar, no subir todavía
        pending_files = {}
        if files_map:
            if is_simulation:
                for fid, file in files_map.items():
                    context_data[fid] = f"simulated_path/{file.filename}"
            else:
                pending_files = cls._validate_file_uploads(context_data, files_map, current_campaign_defs, errors)

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
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

        # 9. Archivos — Fase 2: subir ahora que todo está validado
        if pending_files:
            cls._execute_file_uploads(context_data, pending_files, folder="leads")

        # 10. Preparar estructura
        clean_values = cls._reconstruct_items_for_repo(context_data, current_campaign_defs)

        return clean_values, context_data, current_campaign_defs

    # ---------------------------------------------------------
    # Métodos CRUD Públicos
    # ---------------------------------------------------------

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None, files_map: dict = None, avatar_file: UploadFile = None):
        with UnitOfWork() as uow:
            created_by = user_context.user.id if user_context else None

            # 1. Validar campaña primero para dar el error correcto si no existe
            campaign = cls.campaign_repository.get_by_id(uow.session, obj_in.campaign_id, user_context=user_context)
            if not campaign:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "La campaña no existe."}])

            # 2. Validar que team_id y assigned_to_user_id pertenecen al org
            from app.models.team import Team
            from app.models.security_models import UserOrganization
            org_id = campaign.organization_id
            if obj_in.team_id is not None:
                team = uow.session.query(Team).filter_by(id=obj_in.team_id, organization_id=org_id).first()
                if not team:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "team_id", "message": "El equipo no existe o no pertenece a esta organización."}])
            if obj_in.assigned_to_user_id is not None:
                membership = uow.session.query(UserOrganization).filter_by(user_id=obj_in.assigned_to_user_id, organization_id=org_id, active=True).first()
                if not membership:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "assigned_to_user_id", "message": "El usuario no existe o no pertenece a esta organización."}])

            # 3. Procesar campos y validaciones (recibe campaign para evitar re-queries)
            clean_values, context_data, current_campaign_defs = cls._prepare_creation_data(uow, obj_in, files_map, created_by=created_by, campaign=campaign, is_simulation=False)

            # 4. Validar flujo de estados
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

            # 5. Motor de enrutamiento (determina equipo automático)
            # Inyectamos los campos nativos conocidos al momento de creación
            # (lead_obj no existe aún, por eso se enriquece manualmente)
            native_ctx: dict = {
                "__native__current_state_id": initial_state.id,
                "__native__campaign_id":      campaign.id,
            }
            if obj_in.assigned_to_user_id is not None:
                native_ctx["__native__assigned_to_user_id"] = obj_in.assigned_to_user_id
            if obj_in.team_id is not None:
                native_ctx["__native__team_id"] = obj_in.team_id

            assigned_team_id = RoutingRuleEvaluatorService.evaluate(
                session=uow.session,
                campaign_id=campaign.id,
                organization_id=campaign.organization_id,
                context_data={**context_data, **native_ctx},
                field_defs_list=current_campaign_defs,
                lead_obj=None,
            )

            # Si el frontend manda un string directo (ej. URL ya subida)
            picture_url = getattr(obj_in, 'picture_url', None)

            if avatar_file:
                StorageService.validate_file(avatar_file, ALLOWED_IMAGE_TYPES)
                picture_url = StorageService.upload_file(avatar_file, folder="avatars")

            # El routing engine tiene prioridad; si no asignó equipo, se usa el del frontend
            lead_data = {
                'campaign_id': obj_in.campaign_id,
                'current_state_id': initial_state.id,
                'contact_state_id': initial_contact_state.id if initial_contact_state else None,
                'team_id': assigned_team_id if assigned_team_id is not None else obj_in.team_id,
                'assigned_to_user_id': obj_in.assigned_to_user_id,
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
        from app.models.team import Team
        from app.models.security_models import UserOrganization
        from app.core.context import TENANT_ORG_ID

        # --- Límite de tamaño para prevenir DoS ---
        MAX_BULK_ASSIGN = 200
        if len(lead_ids) > MAX_BULK_ASSIGN:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "lead_ids", "message": f"No se pueden reasignar más de {MAX_BULK_ASSIGN} leads a la vez."}]
            )

        def do_bulk(uow):
            org_id = TENANT_ORG_ID.get()

            # --- Validar que team y user destino pertenecen al org del contexto ---
            if target_team_id is not None:
                team = uow.session.query(Team).filter_by(id=target_team_id, organization_id=org_id).first()
                if not team:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "target_team_id", "message": "El equipo destino no existe o no pertenece a esta organización."}]
                    )

            if target_user_id is not None:
                membership = uow.session.query(UserOrganization).filter_by(
                    user_id=target_user_id, organization_id=org_id, active=True
                ).first()
                if not membership:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "target_user_id", "message": "El usuario destino no existe o no pertenece a esta organización."}]
                    )

            # Validar que el usuario destino pertenezca al equipo destino (si se envían ambos)
            if target_team_id is not None and target_user_id is not None:
                from app.models.team_member import TeamMember as TM
                member_in_team = uow.session.query(TM).filter_by(
                    team_id=target_team_id, user_id=target_user_id
                ).first()
                if not member_in_team:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "target_user_id", "message": "El usuario destino no pertenece al equipo destino."}]
                    )

            # --- Filtrar leads por tenant y permisos de usuario para prevenir IDOR ---
            leads_query = uow.session.query(Lead).filter(
                Lead.id.in_(lead_ids),
                Lead.organization_id == org_id
            )
            leads_query = cls.repository.apply_security_filter(uow.session, leads_query, user_context)
            leads = leads_query.all()
            updated_by = user_context.user.id if user_context and user_context.user else None
            if not leads:
                return []

            # Hallazgo (auditoría): antes se guardaba solo new_team_id/new_user_id crudos en el
            # timeline del lead, obligando al frontend a resolverlos (y ni siquiera lo hacía).
            # Se resuelven acá los nombres de equipo/usuario (viejo y nuevo) en un solo batch,
            # para no hacer una query por lead dentro del loop.
            from app.models.security_models import User

            all_team_ids = {lead.team_id for lead in leads if lead.team_id is not None}
            all_user_ids = {lead.assigned_to_user_id for lead in leads if lead.assigned_to_user_id is not None}
            if target_team_id is not None:
                all_team_ids.add(target_team_id)
            if target_user_id is not None:
                all_user_ids.add(target_user_id)

            teams_map = {
                t.id: t.name for t in uow.session.query(Team).filter(Team.id.in_(all_team_ids)).all()
            } if all_team_ids else {}
            users_map = {
                u.id: f"{u.name} {u.last_name}" for u in uow.session.query(User).filter(User.id.in_(all_user_ids)).all()
            } if all_user_ids else {}

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
                    details={
                        "previous_team_id": old_team,
                        "previous_team_name": teams_map.get(old_team),
                        "previous_user_id": old_user,
                        "previous_user_name": users_map.get(old_user),
                        "new_team_id": lead.team_id,
                        "new_team_name": teams_map.get(lead.team_id),
                        "new_user_id": lead.assigned_to_user_id,
                        "new_user_name": users_map.get(lead.assigned_to_user_id),
                    },
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

            # Lock de fila para evitar race conditions en cambios concurrentes
            uow.session.query(Lead).filter(Lead.id == obj_id).with_for_update().first()

            current_state_id = lead.current_state_id

            # 1. Validar que no estemos moviéndolo al mismo estado
            if current_state_id == new_state_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, 
                    detail=[{"field": "new_state_id", "message": "El lead ya se encuentra en este estado."}]
                )
            
            campaign = cls.campaign_repository.get_by_id(uow.session, lead.campaign_id, user_context=user_context)

            # 2. Validar que el salto esté permitido en la campaña
            if current_state_id is None:
                # Si el lead no tiene estado, solo puede ir al estado inicial del flujo
                initial_states = cls.state_repository.get_all(
                    uow.session, user_context=user_context,
                    lead_flow_id=campaign.lead_flow_id, is_initial=True
                )
                initial_state = initial_states[0] if initial_states else None
                if not initial_state or new_state_id != initial_state.id:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "new_state_id", "message": "Un lead sin estado solo puede transicionar al estado inicial del flujo."}]
                    )
            else:
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

            # Registrar en la línea de tiempo visible del lead
            # Hallazgo (auditoría): antes se guardaba solo from_state_id/to_state_id crudos,
            # obligando al frontend a hacer un fetch aparte de los estados del flujo y
            # buscarlos por id. Se resuelve nombre/color acá, en el momento del cambio,
            # para que quede "congelado" en el historial aunque el estado se renombre después.
            from_state = cls.state_repository.get_by_id(uow.session, current_state_id, user_context=user_context) if current_state_id else None
            to_state = cls.state_repository.get_by_id(uow.session, new_state_id, user_context=user_context)
            cls._log_activity(
                session=uow.session,
                lead_id=obj_id,
                activity_type="STATE_CHANGED",
                details={
                    "from_state_id": current_state_id,
                    "from_state_name": from_state.name if from_state else None,
                    "from_state_color": from_state.color if from_state else None,
                    "to_state_id": new_state_id,
                    "to_state_name": to_state.name if to_state else None,
                    "to_state_color": to_state.color if to_state else None,
                    "notes": notes
                },
                user_id=user_context.user.id if user_context else None
            )

        # Devolvemos el Lead actualizado para el Frontend
        return cls.get_by_id(obj_id, detailed=True)

    @classmethod
    def change_contact_state(cls, obj_id: int, new_contact_state_id: int, notes: str = None, user_context: Optional[UserContext] = None):
        """
        Cambia el estado de contacto de un lead. A diferencia del estado de flujo, no tiene
        transiciones restringidas (se puede pasar a cualquier estado de contacto activo de
        la organización).

        Hallazgo: antes esto se hacía a través del PUT genérico de leads (`contact_state_id`
        como un campo más) y no dejaba ningún rastro de auditoría — ni en el timeline visible
        del lead ni en el log técnico general. Se agrega este método dedicado, en el mismo
        patrón que `change_state`, para que quede registrado igual.
        """
        from app.models.lead_contact_state import LeadContactState

        with UnitOfWork() as uow:
            lead = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not lead:
                cls._not_found(obj_id)

            current_contact_state_id = lead.contact_state_id

            if current_contact_state_id == new_contact_state_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "new_contact_state_id", "message": "El lead ya se encuentra en este estado de contacto."}]
                )

            new_contact_state = uow.session.query(LeadContactState).filter_by(
                id=new_contact_state_id, organization_id=lead.organization_id, active=True
            ).first()
            if not new_contact_state:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "new_contact_state_id", "message": "El estado de contacto no existe o no pertenece a esta organización."}]
                )

            current_contact_state = None
            if current_contact_state_id:
                current_contact_state = uow.session.query(LeadContactState).filter_by(id=current_contact_state_id).first()

            cls.repository.update(uow.session, obj_id, {"contact_state_id": new_contact_state_id}, user_context=user_context)

            updated_by = user_context.user.id if user_context else None

            diff = {"contact_state_id": {"old": current_contact_state_id, "new": new_contact_state_id}}
            cls._log_audit(uow.session, lead, action=SystemAuditLogAction.UPDATED, changes=diff, user_id=updated_by)

            cls._log_activity(
                session=uow.session,
                lead_id=obj_id,
                activity_type="CONTACT_STATE_CHANGED",
                details={
                    "from_contact_state_id": current_contact_state_id,
                    "from_contact_state_name": current_contact_state.name if current_contact_state else None,
                    "from_contact_state_color": current_contact_state.color if current_contact_state else None,
                    "to_contact_state_id": new_contact_state_id,
                    "to_contact_state_name": new_contact_state.name,
                    "to_contact_state_color": new_contact_state.color,
                    "notes": notes
                },
                user_id=updated_by
            )

        # Devolvemos el Lead actualizado para el Frontend
        return cls.get_by_id(obj_id, detailed=True)

    @classmethod
    def simulate_create(cls, obj_in, user_context: Optional[UserContext] = None, files_map: dict = None):
        with UnitOfWork() as uow:
            created_by = user_context.user.id if user_context else None

            from app.core.context import TENANT_ORG_ID
            dummy_org_id = TENANT_ORG_ID.get() or 0

            campaign = cls.campaign_repository.get_by_id(uow.session, obj_in.campaign_id, user_context=user_context)
            if not campaign:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "La campaña no existe."}])

            # Validar org membership de team_id y assigned_to_user_id (igual que en create)
            from app.models.team import Team
            from app.models.security_models import UserOrganization
            org_id = campaign.organization_id
            if obj_in.team_id is not None:
                team = uow.session.query(Team).filter_by(id=obj_in.team_id, organization_id=org_id).first()
                if not team:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "team_id", "message": "El equipo no existe o no pertenece a esta organización."}])
            if obj_in.assigned_to_user_id is not None:
                membership = uow.session.query(UserOrganization).filter_by(user_id=obj_in.assigned_to_user_id, organization_id=org_id, active=True).first()
                if not membership:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "assigned_to_user_id", "message": "El usuario no existe o no pertenece a esta organización."}])

            clean_values, context_data, field_defs = cls._prepare_creation_data(uow, obj_in, files_map, created_by, campaign=campaign, is_simulation=True)

            states = cls.state_repository.get_all(uow.session, user_context=user_context, lead_flow_id=campaign.lead_flow_id, is_initial=True)
            initial_state = states[0] if states else None
            if not initial_state:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "general", "message": "La campaña no tiene un estado inicial configurado."}])

            dummy_lead_id = -1
            fields_map = {f.id: f for f in field_defs}

            simulated_values = []
            for item_proxy in clean_values:
                data = item_proxy._data
                fid = data['field_id']
                field_def = fields_map.get(fid)

                simulated_values.append({
                    "id": -1 * fid,
                    "active": True,
                    "lead_id": dummy_lead_id,
                    "field_id": fid,
                    "value": data.get('value'),
                    "nomenclator_items": [],
                    "related_leads": [],
                    "field": {
                        "id": field_def.id,
                        "active": True,
                        "name": field_def.name,
                        "order": field_def.order,
                        "field_type_code": field_def.field_type_code,
                        "field_subtype_code": getattr(field_def, 'field_subtype_code', None),
                        "title_order": getattr(field_def, 'title_order', None),
                    } if field_def else None
                })

            return {
                "id": dummy_lead_id,
                "active": True,
                "campaign_id": obj_in.campaign_id,
                "organization_id": dummy_org_id,
                "current_state_id": initial_state.id,
                "current_state": {
                    "id": initial_state.id,
                    "active": True,
                    "lead_flow_id": initial_state.lead_flow_id,
                    "name": initial_state.name,
                    "color": getattr(initial_state, 'color', None),
                    "category": initial_state.category,
                    "is_initial": initial_state.is_initial,
                    "order": getattr(initial_state, 'order', None),
                    "position_x": getattr(initial_state, 'position_x', 0.0),
                    "position_y": getattr(initial_state, 'position_y', 0.0),
                    "organization_id": dummy_org_id,
                },
                "contact_state": None,
                "tags": [],
                "field_values": simulated_values,
            }

    @classmethod
    def update(cls, obj_id: int, obj_in, files_map: dict = None, user_context: Optional[UserContext] = None, avatar_file: UploadFile = None):
        errors = [] 
        
        with UnitOfWork() as uow:
            current_lead = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not current_lead: cls._not_found(obj_id)

            # Validar que contact_state_id pertenece al org
            if obj_in and obj_in.contact_state_id is not None:
                from app.models.lead_contact_state import LeadContactState
                contact_state = uow.session.query(LeadContactState).filter_by(
                    id=obj_in.contact_state_id,
                    organization_id=current_lead.organization_id,
                    active=True
                ).first()
                if not contact_state:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "contact_state_id", "message": "El estado de contacto no existe o no pertenece a esta organización."}])

            # Logica de Tags
            if obj_in and "tag_ids" in obj_in.model_fields_set:
                lead_db = uow.session.query(Lead).filter_by(id=obj_id).first()
                cls._assign_tags(
                    session=uow.session,
                    lead_obj=lead_db,
                    tag_ids=obj_in.tag_ids,
                    org_id=current_lead.organization_id
                )

            # Update base (campos nativos del lead)
            lead_data = obj_in.model_dump(exclude_unset=True, exclude={"values", "tag_ids"}) if obj_in else {}

            if avatar_file:
                StorageService.validate_file(avatar_file, ALLOWED_IMAGE_TYPES)
                picture_url = StorageService.upload_file(avatar_file, folder="avatars")
                lead_data["picture_url"] = picture_url

            if lead_data:
                cls.repository.update(uow.session, obj_id, lead_data, user_context=user_context)

            if obj_in and obj_in.values is not None:
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

                # Archivos — Fase 1: validar sin subir
                pending_files = {}
                if files_map:
                    pending_files = cls._validate_file_uploads(incoming_data, files_map, current_campaign_defs, errors)

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

                # INYECCIÓN DEL MOTOR DE AUTOMATIZACIÓN (ON_UPDATE)
                full_context, automation_audit = AutomationEngine.run(
                    session=uow.session,
                    campaign_id=current_lead.campaign_id,
                    context_data=full_context,
                    event="ON_UPDATE"
                )

                # Calcular los campos calculados con el contexto completo (DB + incoming)
                full_context = cls._evaluate_calculated_fields(full_context, current_campaign_defs)

                # Chequear duplicados en primary fields (excluimos el lead actual)
                cls._check_duplicates(uow.session, current_lead.campaign_id, full_context, current_campaign_defs, errors, exclude_lead_id=obj_id)

                # Validar reglas
                cls._validate_processed_data(uow, full_context, current_campaign_defs, errors, current_lead_id=obj_id)

                if errors:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

                # Archivos — Fase 2: subir ahora que todo está validado
                if pending_files:
                    cls._execute_file_uploads(incoming_data, pending_files, folder="leads")
                    # Sincronizar paths reales en full_context para el historial
                    for fid in pending_files:
                        full_context[fid] = incoming_data[fid]

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

                # Si hubo cambios reales en los field values, forzamos el "touch" del Lead.
                # upsert_values() solo modifica filas de lead_field_value (con su propio
                # updated_at), por lo que sin esto lead.updated_at quedaba desactualizado.
                if changes:
                    lead_obj = uow.session.query(Lead).filter_by(id=obj_id).first()
                    if lead_obj:
                        lead_obj.updated_at = func.now()
                        if user_id is not None:
                            lead_obj.updated_by = user_id

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
    def search(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, detailed: bool = False, search_req=None, order_by=None, ascending: bool = True, only_active: bool = True, campaign_id: Optional[int] = None):
        def do_search(uow):
            total, items = cls.repository.search(
                session=uow.session, user_context=user_context,
                page=page,
                page_size=page_size,
                search_params=search_req,
                detailed=detailed,
                order_by=order_by,
                ascending=ascending,
                only_active=only_active,
                campaign_id=campaign_id
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
            Tag.organization_id == org_id
        ).all()

        if len(tags) != len(set(tag_ids)):
            found_ids = {t.id for t in tags}
            missing_ids = [i for i in tag_ids if i not in found_ids]
            raise HTTPException(
                status_code=400,
                detail=[{"field": "tag_ids", "message": f"Las etiquetas {missing_ids} no existen o no pertenecen a tu organización."}]
            )

        lead_obj.tags = tags
