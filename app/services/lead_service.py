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
from app.db.repository.team_repository import TeamRepository
from app.db.repository.security_repositories.user_repository import UserRepository
from app.db.repository.lead_contact_state_repository import LeadContactStateRepository
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
    def _resolve_value_field_ids(cls, session, values_in):
        """
        `values[].field_id` llega como public_uuid del LeadField -- a diferencia de
        campaign_id/team_id/assigned_to_user_id/contact_state_id (todos migrados a public_uuid
        desde Fase 3, ver LeadCreate/LeadUpdate), este campo específico nunca se había migrado
        ni en el schema (LeadFieldValueBase.field_id seguía siendo `int`) ni acá: el frontend
        manda `field.id` (uuid, LeadForm.tsx) pero el resto de este archivo compara `field_id`
        directo contra `LeadField.id` (int) -- rompía con 422 "Input should be a valid integer"
        en CUALQUIER creación/actualización de Lead con campos dinámicos, no solo en tests (ver
        backend/AGENTS.md §18-decies). Se resuelve acá, una vez, mutando cada item en el lugar
        (soporta dict y objeto Pydantic, mismo patrón que el resto del archivo) para que el resto
        del código -- que ya compara contra ids internos -- no tenga que cambiar.
        """
        for v in values_in:
            is_dict = isinstance(v, dict)
            raw_fid = v.get('field_id') if is_dict else getattr(v, 'field_id', None)
            if raw_fid is None:
                continue
            # Ya es un id interno (ej. algún caller interno que arma los values a mano) -- no
            # hay nada que resolver.
            if isinstance(raw_fid, int) or (isinstance(raw_fid, str) and raw_fid.lstrip('-').isdigit()):
                resolved = int(raw_fid)
            else:
                resolved = cls.field_repository.get_internal_id_by_public_uuid(session, raw_fid)
                if resolved is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": f"ID_{raw_fid}", "message": "El campo no existe en el sistema."}]
                    )
            if is_dict:
                v['field_id'] = resolved
            else:
                v.field_id = resolved
        return values_in

    @classmethod
    def _resolve_value_nomenclator_ids(cls, session, values_in, defs_map: dict):
        """
        Bug real encontrado 2026-07-30 (mismo patrón y misma causa que _resolve_value_field_ids
        de arriba): para campos SELECTOR/CHECKBOX, `value` es una lista de ids de
        NomenclatorItem -- pero desde Fase 4 NomenclatorItem.id que devuelve la API es
        public_uuid, no el id interno. LeadFieldValueBase.value seguía esperando List[int],
        así que cualquier alta/edición real de un campo de este tipo (mandando los ids reales
        que da la API) rompía con 422. Requiere `defs_map` (field_id interno -> LeadField) ya
        armado por el caller para saber qué campos son de este tipo.

        Debe llamarse DESPUÉS de _resolve_value_field_ids (necesita field_id ya resuelto a int).
        """
        from app.core.constans import NOMENCLATOR_FIELD_TYPES
        from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository

        for v in values_in:
            is_dict = isinstance(v, dict)
            fid = v.get('field_id') if is_dict else getattr(v, 'field_id', None)
            field_def = defs_map.get(fid)
            if field_def is None or field_def.field_type_code not in NOMENCLATOR_FIELD_TYPES:
                continue

            raw_val = v.get('value') if is_dict else getattr(v, 'value', None)
            if raw_val is None:
                continue

            was_list = isinstance(raw_val, list)
            items = raw_val if was_list else [raw_val]

            resolved_items = []
            for item in items:
                if isinstance(item, int) or (isinstance(item, str) and item.lstrip('-').isdigit()):
                    resolved_items.append(int(item))
                else:
                    resolved = NomenclatorItemRepository.get_internal_id_by_public_uuid(session, item)
                    if resolved is None:
                        raise HTTPException(
                            status.HTTP_400_BAD_REQUEST,
                            detail=[{"field": field_def.name, "message": f"La opción seleccionada ('{item}') no existe."}]
                        )
                    resolved_items.append(resolved)

            new_val = resolved_items if was_list else (resolved_items[0] if resolved_items else None)
            if is_dict:
                v['value'] = new_val
            else:
                v.value = new_val
        return values_in

    @classmethod
    def _resolve_value_lead_ids(cls, session, values_in, defs_map: dict):
        """
        Bug real encontrado 2026-08-01, mismo patrón y misma causa que
        _resolve_value_field_ids/_resolve_value_nomenclator_ids de arriba: para campos tipo LEAD
        (relaciones entre leads), `value` es una lista de ids de Lead relacionado -- pero la API
        siempre devuelve/espera public_uuid para Lead.id (Fase 1-4), nunca el id interno. Como acá
        nunca se resolvía, `_validate_processed_data` (más abajo) exigía `isinstance(x, int)`
        sobre esos valores y SIEMPRE fallaba con "ID de lead inválido" para cualquier request real
        contra la API (que solo puede mandar uuid, ya que es lo único que expone). Es decir: nunca
        fue posible relacionar leads a través de la API real, solo en tests que insertaban el id
        interno a mano bypaseando la API. Se resuelve acá, mismo criterio que nomencladores.

        Debe llamarse DESPUÉS de _resolve_value_field_ids (necesita field_id ya resuelto a int).
        """
        for v in values_in:
            is_dict = isinstance(v, dict)
            fid = v.get('field_id') if is_dict else getattr(v, 'field_id', None)
            field_def = defs_map.get(fid)
            if field_def is None or field_def.field_type_code != "LEAD":
                continue

            raw_val = v.get('value') if is_dict else getattr(v, 'value', None)
            if raw_val is None:
                continue

            was_list = isinstance(raw_val, list)
            items = raw_val if was_list else [raw_val]

            resolved_items = []
            for item in items:
                if isinstance(item, int) or (isinstance(item, str) and item.lstrip('-').isdigit()):
                    resolved_items.append(int(item))
                else:
                    resolved = LeadRepository.get_internal_id_by_public_uuid(session, item)
                    # Si no existe, dejamos pasar un id imposible (-1) en vez de cortar acá: el
                    # chequeo real de existencia + mensaje "El lead relacionado (...) no existe"
                    # ya lo hace _validate_processed_data más abajo, y así evitamos duplicar
                    # lógica de error entre las dos funciones.
                    resolved_items.append(resolved if resolved is not None else -1)

            new_val = resolved_items if was_list else (resolved_items[0] if resolved_items else None)
            if is_dict:
                v['value'] = new_val
            else:
                v.value = new_val
        return values_in

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

    @classmethod
    def _translate_native_value_for_history(cls, session, attr: str, raw_val):
        """
        Igual que `_translate_value_for_history` pero para los 4 campos nativos escribibles
        (ver `app/core/native_lead_fields.py`), que no tienen un `LeadField` asociado del que
        colgar la traducción. Resuelve el ID a un nombre legible para el timeline del lead.
        """
        if raw_val is None:
            return ""
        try:
            if attr == "current_state_id":
                from app.models.lead_state import LeadState
                obj = session.query(LeadState).filter_by(id=raw_val).first()
                return obj.name if obj else raw_val
            if attr == "contact_state_id":
                from app.models.lead_contact_state import LeadContactState
                obj = session.query(LeadContactState).filter_by(id=raw_val).first()
                return obj.name if obj else raw_val
            if attr == "team_id":
                from app.models.team import Team
                obj = session.query(Team).filter_by(id=raw_val).first()
                return obj.name if obj else raw_val
            if attr == "assigned_to_user_id":
                from app.models.security_models import User
                obj = session.query(User).filter_by(id=raw_val).first()
                return f"{obj.name} {obj.last_name}" if obj else raw_val
        except Exception:
            return raw_val
        return raw_val

    @classmethod
    def _apply_native_automation_writeback(cls, uow, obj_id: int, native_ctx_before: dict, automation_audit: dict, user_context: Optional[UserContext] = None):
        """
        Dado el resultado de `AutomationEngine.run` (`automation_audit`, keyed por field_id) y el
        contexto nativo previo a esa corrida (`native_ctx_before`, ver `build_native_context_from_lead`),
        aplica sobre la fila real del lead los cambios de campos nativos ESCRIBIBLES (Etapa/Estado/
        Equipo/Usuario asignado) que una automatización haya decidido, con el mismo chequeo liviano
        de existencia/organización que ya se documentó en `native_lead_fields.py` (sin validar
        transición de flujo permitida ni pertenencia a equipo -- a pedido explícito del usuario, una
        automatización es un update crudo en la base de datos).

        Extraído de `update()` para poder reusarlo desde cualquier otro método que persista un
        cambio de campo nativo por fuera del PUT genérico (`change_state`, `change_contact_state`,
        `bulk_assign`) -- antes esos métodos escribían directo con `repository.update`/`setattr` y
        jamás corrían el motor de automatizaciones, por lo que una regla "Al actualizar registro"
        nunca se disparaba si el cambio entraba por esas puertas (reportado por el usuario 2026-07-25).

        Devuelve (changes, history_changes) -- dicts listos para mergear/loguear vía `_log_audit`/
        `_log_activity`, vacíos si no hubo ningún cambio nativo escribible aplicable.
        """
        from app.core.native_lead_fields import NATIVE_LEAD_FIELDS, WRITABLE_NATIVE_FIELD_IDS

        changed_nids = [nid for nid in WRITABLE_NATIVE_FIELD_IDS if nid in automation_audit]
        changes = {}
        history_changes = {}
        if not changed_nids:
            return changes, history_changes

        lead_orm = uow.session.query(Lead).filter_by(id=obj_id).first()
        if not lead_orm:
            return changes, history_changes

        native_updates = {}
        for nid in changed_nids:
            attr = NATIVE_LEAD_FIELDS[nid].attr
            new_val = automation_audit[nid]["new_value"]
            old_val = native_ctx_before.get(nid)
            if new_val == old_val:
                continue

            if new_val is not None:
                valid = True
                if attr == "current_state_id":
                    state_obj = cls.state_repository.get_by_id(uow.session, new_val, user_context=user_context)
                    campaign_obj = cls.campaign_repository.get_by_id(uow.session, lead_orm.campaign_id, user_context=user_context)
                    valid = bool(state_obj) and bool(campaign_obj) and state_obj.lead_flow_id == campaign_obj.lead_flow_id
                elif attr == "contact_state_id":
                    from app.models.lead_contact_state import LeadContactState as _LeadContactState
                    valid = bool(uow.session.query(_LeadContactState).filter_by(
                        id=new_val, organization_id=lead_orm.organization_id, active=True).first())
                elif attr == "team_id":
                    from app.models.team import Team as _Team
                    valid = bool(uow.session.query(_Team).filter_by(
                        id=new_val, organization_id=lead_orm.organization_id).first())
                elif attr == "assigned_to_user_id":
                    from app.models.security_models import UserOrganization as _UserOrganization
                    valid = bool(uow.session.query(_UserOrganization).filter_by(
                        user_id=new_val, organization_id=lead_orm.organization_id, active=True).first())
                if not valid:
                    continue

            native_updates[attr] = new_val
            field_label = NATIVE_LEAD_FIELDS[nid].name
            change_key = f"native_{attr}"
            changes[change_key] = {"field_name": field_label, "old_value": old_val, "new_value": new_val}
            history_changes[change_key] = {
                "field_name": field_label,
                "old_value": cls._translate_native_value_for_history(uow.session, attr, old_val),
                "new_value": cls._translate_native_value_for_history(uow.session, attr, new_val),
                "source_rule": automation_audit[nid]["source_rule"],
            }

        if native_updates:
            for attr, val in native_updates.items():
                setattr(lead_orm, attr, val)

        return changes, history_changes

    @classmethod
    def _run_native_change_automations(cls, uow, lead_orm, event: str, user_context: Optional[UserContext] = None):
        """
        Corre el motor de Automatizaciones de Campos a partir de un cambio de campo nativo que
        NO pasó por `update()` (`change_state`, `change_contact_state`, `bulk_assign`: todos
        escriben directo con `repository.update`/`setattr` y nunca invocaban el motor). Se llama
        DESPUÉS de aplicar el cambio directo sobre `lead_orm` (mismo objeto/sesión), para que la
        condición de la regla vea el valor nuevo como "estado actual" (ej. Estado=Rechazado ->
        Etapa=No interesado se dispara al guardar el Estado, no antes).

        `lead_orm` debe ser un objeto ORM real (no Pydantic) de la sesión activa, con `field_values`
        accesible (se usa para incluir los campos custom en el contexto de evaluación de condiciones,
        aunque acá no se estén editando).

        Devuelve (changes, history_changes) iguales a `_apply_native_automation_writeback`, vacíos
        si no hay ninguna regla aplicable para este evento/campaña.
        """
        from app.core.native_lead_fields import build_native_context_from_lead

        db_values = {}
        for v in (getattr(lead_orm, "field_values", None) or []):
            val = getattr(v, "value", None)
            if val is None:
                if getattr(v, "nomenclator_items", None):
                    val = [item.id for item in v.nomenclator_items]
                elif getattr(v, "related_leads", None):
                    val = [l.id for l in v.related_leads]
                elif getattr(v, "nomenclator_item_id", None):
                    val = v.nomenclator_item_id
            db_values[v.field_id] = val

        native_ctx_before = build_native_context_from_lead(lead_orm)
        full_context = {**db_values, **native_ctx_before}

        _, automation_audit = AutomationEngine.run(
            session=uow.session,
            campaign_id=lead_orm.campaign_id,
            context_data=full_context,
            event=event,
        )

        if not automation_audit:
            return {}, {}

        return cls._apply_native_automation_writeback(uow, lead_orm.id, native_ctx_before, automation_audit, user_context)

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

    @classmethod
    def _redact_inaccessible_related_leads(cls, lead, accessible_campaign_ids: set):
        """
        Un campo tipo LEAD puede apuntar a un lead de OTRA campaña, a la que el usuario que está
        viendo este lead no necesariamente tiene acceso (is_public/TeamCampaignAccess). Sin este
        chequeo, `LeadFieldValue.related_leads` (relación lazy="joined", sin ningún filtro de
        permisos) expone en la respuesta TODOS los datos del lead relacionado, sin importar la
        campaña — una fuga real entre campañas.

        OJO: para cuando este método corre, `lead`/`fv`/`related` YA NO son objetos ORM. El
        repositorio (BaseRepository._execute_read_query, vía schema_out/schema_out_detail) ya
        convirtió todo a los schemas Pydantic (LeadResponse/LeadDetailedResponse → ... →
        RelatedLeadResponse) ANTES de que el service llegue a verlos — LeadRepository.get_all,
        get_by_id y search hacen esa conversión ellos mismos, no queda como ORM "hasta el final"
        como en otros services. Por eso acá mutamos directamente los modelos Pydantic (son
        mutables por default); no hay objetos ORM que tocar ni riesgo de autoflush.
        """
        if not lead or not lead.field_values: return lead
        for fv in lead.field_values:
            for related in (fv.related_leads or []):
                if related.campaign_id in accessible_campaign_ids:
                    continue
                related.restricted = True
                #No se manda ningún dato del lead relacionado salvo los campos marcados como
                #title_order (para poder mostrar igual un nombre identificable, ej. Nombre +
                #Apellido, sin filtrar el resto de sus datos). Se ordenan por title_order para
                #que el frontend pueda unirlos directamente sin tener que reordenar.
                title_values = [rfv for rfv in related.field_values if rfv.field and rfv.field.title_order is not None]
                title_values.sort(key=lambda rfv: rfv.field.title_order)
                related.field_values = title_values
        return lead


    # ---------------------------------------------------------
    # LÓGICA CENTRAL DE PREPARACIÓN
    # ---------------------------------------------------------
    @classmethod
    def _prepare_creation_data(cls, uow, obj_in, files_map, created_by, campaign, campaign_internal_id, is_simulation=False, native_ctx: dict = None):
        """
        Ejecuta lógica. Retorna tuple. Si hay errores, lanza HTTPException con la lista.
        Recibe el objeto 'campaign' ya validado para evitar re-queries y errores semánticos.

        native_ctx: valores de campos nativos (Etapa/Estado/Equipo/Usuario asignado, con los IDs
        negativos de `app/core/native_lead_fields.py`) ya conocidos al momento de la creación
        (estado inicial del flujo, team_id/assigned_to_user_id del request). Se mezclan en
        `context_data` ANTES de correr el motor de automatizaciones para que una regla "Al crear
        registro" pueda leerlos o sobreescribirlos -- el caller (`create`/`simulate_create`) es
        responsable de tomar los valores resultantes de `context_data` (pueden haber sido
        mutados) para armar el Lead final.
        """
        errors = [] # ACUMULADOR DE ERRORES

        # campaign ya viene validada y resuelta por el caller (create/simulate_create), que también
        # nos pasa campaign_internal_id explícito -- NO usar campaign.id acá: desde Fase 3,
        # CampaignRepository.get_by_id() devuelve el schema Pydantic, cuyo .id es el public_uuid
        # de la campaña (string), no el id interno que necesita el resto de esta función. Bug real
        # encontrado 2026-07-28: rompía create()/simulate_create() completos (ver AGENTS.md).
        campaign_id = campaign_internal_id
        all_field_defs = cls.field_repository.get_all_active_with_rules(uow.session, campaign_id=campaign_id)

        # obj_in.values[].field_id llega como public_uuid del LeadField -- se resuelve acá, antes
        # de armar defs_map/incoming_field_ids (ambos comparan contra el id interno). Cubre tanto
        # create() como simulate_create() (los dos llaman a esta función). Ver
        # _resolve_value_field_ids y backend/AGENTS.md §18-decies.
        cls._resolve_value_field_ids(uow.session, obj_in.values)

        # 1. Validación inicial de existencia de campos
        defs_map = {f.id: f for f in all_field_defs}

        # Ver _resolve_value_nomenclator_ids -- resuelve uuids de NomenclatorItem en `value`
        # para campos SELECTOR/CHECKBOX, ahora que defs_map (con field_type_code) ya existe.
        cls._resolve_value_nomenclator_ids(uow.session, obj_in.values, defs_map)

        # Ver _resolve_value_lead_ids -- resuelve uuids de Lead relacionado en `value`
        # para campos tipo LEAD, mismo criterio que nomencladores.
        cls._resolve_value_lead_ids(uow.session, obj_in.values, defs_map)

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

        # 4bis. Campos nativos conocidos a esta altura (ver docstring) -- se mezclan recién acá,
        # después de defaults/fill, para no interferir con esos pasos (que solo miran los ids
        # positivos de current_campaign_defs).
        if native_ctx:
            context_data.update(native_ctx)

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
            # obj_in.campaign_id llega como public_uuid desde Fase 3 (el front ya no conoce el
            # id interno de Campaign) -- se resuelve acá antes de buscar el objeto.
            campaign_internal_id = cls.campaign_repository.get_internal_id_by_public_uuid(uow.session, obj_in.campaign_id)
            campaign = cls.campaign_repository.get_by_id(uow.session, campaign_internal_id, user_context=user_context) if campaign_internal_id is not None else None
            if not campaign:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "La campaña no existe."}])

            # 2. Validar que team_id y assigned_to_user_id pertenecen al org
            # (mismo motivo: son public_uuid de Team/User, se resuelven a id interno acá)
            from app.models.team import Team
            from app.models.security_models import UserOrganization
            org_id = campaign.organization_id
            team_internal_id = None
            if obj_in.team_id is not None:
                team_internal_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.team_id)
                team = uow.session.query(Team).filter_by(id=team_internal_id, organization_id=org_id).first()
                if not team:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "team_id", "message": "El equipo no existe o no pertenece a esta organización."}])
            user_internal_id = None
            if obj_in.assigned_to_user_id is not None:
                user_internal_id = UserRepository.get_internal_id_by_public_uuid(uow.session, obj_in.assigned_to_user_id)
                membership = uow.session.query(UserOrganization).filter_by(user_id=user_internal_id, organization_id=org_id, active=True).first()
                if not membership:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "assigned_to_user_id", "message": "El usuario no existe o no pertenece a esta organización."}])

            # 3. Validar flujo de estados (se mueve antes de _prepare_creation_data para poder
            # ofrecerle a las automatizaciones "Al crear registro" el valor de Etapa/Estado ya
            # calculado -- y permitir que una regla los sobreescriba en el mismo alta).
            initial_state = cls.state_repository.get_all(uow.session, user_context=user_context, lead_flow_id=campaign.lead_flow_id, is_initial=True)
            initial_state = initial_state[0] if initial_state else None
            if not initial_state:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "general", "message": "La campaña no tiene un flujo de estados válido (falta configurar un estado inicial)."}]
                )
            # Bug real encontrado 2026-07-30: state_repository.get_all() devuelve schemas Pydantic
            # (no objetos ORM), así que initial_state.id es el public_uuid del estado, no su id
            # interno. Todo el resto de esta función usa este valor como FK cruda (contexto nativo
            # del motor de automatizaciones/ruteo, fallback de current_state_id) -- hay que
            # resolverlo acá al id interno real antes de usarlo. Sin este fix, el motor de ruteo
            # nunca podía matchear condiciones nativas de current_state_id sobre un lead recién
            # creado en su estado inicial (comparaba un id interno crudo contra un uuid).
            initial_state_internal_id = cls.state_repository.get_internal_id_by_public_uuid(uow.session, initial_state.id)

            from app.models.lead_contact_state import LeadContactState
            initial_contact_state = uow.session.query(LeadContactState).filter_by(
                organization_id=campaign.organization_id,
                is_initial=True,
                active=True
            ).first()

            # 4. Campos nativos conocidos a esta altura (ver `native_lead_fields.py`), para que el
            # motor de automatizaciones pueda leerlos/sobreescribirlos.
            from app.core.native_lead_fields import NATIVE_LEAD_FIELDS_BY_ATTR
            id_etapa = NATIVE_LEAD_FIELDS_BY_ATTR["current_state_id"].id
            id_estado = NATIVE_LEAD_FIELDS_BY_ATTR["contact_state_id"].id
            id_equipo = NATIVE_LEAD_FIELDS_BY_ATTR["team_id"].id
            id_asignado = NATIVE_LEAD_FIELDS_BY_ATTR["assigned_to_user_id"].id
            automation_native_ctx = {
                id_etapa: initial_state_internal_id,
                id_estado: initial_contact_state.id if initial_contact_state else None,
                id_equipo: team_internal_id,
                id_asignado: user_internal_id,
            }

            # 5. Procesar campos y validaciones (recibe campaign para evitar re-queries)
            clean_values, context_data, current_campaign_defs = cls._prepare_creation_data(
                uow, obj_in, files_map, created_by=created_by, campaign=campaign,
                campaign_internal_id=campaign_internal_id, is_simulation=False,
                native_ctx=automation_native_ctx,
            )

            # 6. Valores finales de los campos nativos, posiblemente sobreescritos por una
            # automatización "Al crear registro". Se aplica acá un chequeo liviano de existencia
            # (no de "transición permitida" -- a pedido explícito del usuario, una automatización
            # escribe estos campos como un UPDATE directo) para no terminar con una FK rota si la
            # regla apunta a un ID que no existe o no pertenece a esta organización/flujo.
            final_current_state_id = context_data.get(id_etapa, initial_state_internal_id)
            if final_current_state_id != initial_state_internal_id:
                state_obj = cls.state_repository.get_by_id(uow.session, final_current_state_id, user_context=user_context)
                if not state_obj or state_obj.lead_flow_id != campaign.lead_flow_id:
                    final_current_state_id = initial_state_internal_id

            final_contact_state_id = context_data.get(id_estado, automation_native_ctx[id_estado])
            if final_contact_state_id and final_contact_state_id != automation_native_ctx[id_estado]:
                cs_obj = uow.session.query(LeadContactState).filter_by(id=final_contact_state_id, organization_id=campaign.organization_id, active=True).first()
                if not cs_obj:
                    final_contact_state_id = automation_native_ctx[id_estado]

            final_team_id = context_data.get(id_equipo, team_internal_id)
            if final_team_id and final_team_id != team_internal_id:
                from app.models.team import Team as _Team
                team_obj = uow.session.query(_Team).filter_by(id=final_team_id, organization_id=org_id).first()
                if not team_obj:
                    final_team_id = team_internal_id

            final_assigned_user_id = context_data.get(id_asignado, user_internal_id)
            if final_assigned_user_id and final_assigned_user_id != user_internal_id:
                from app.models.security_models import UserOrganization as _UserOrganization
                membership_obj = uow.session.query(_UserOrganization).filter_by(user_id=final_assigned_user_id, organization_id=org_id, active=True).first()
                if not membership_obj:
                    final_assigned_user_id = user_internal_id

            # 7. Motor de enrutamiento (determina equipo automático) -- alimentado con los valores
            # YA resueltos (posteriores a la automatización), no los originales del request.
            native_ctx: dict = {
                "__native__current_state_id": final_current_state_id,
                "__native__campaign_id":      campaign_internal_id,
            }
            if final_assigned_user_id is not None:
                native_ctx["__native__assigned_to_user_id"] = final_assigned_user_id
            if final_team_id is not None:
                native_ctx["__native__team_id"] = final_team_id

            assigned_team_id = RoutingRuleEvaluatorService.evaluate(
                session=uow.session,
                campaign_id=campaign_internal_id,
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

            # Próximo número de referencia legible para el usuario (ej. "L-0001"), pedido
            # 2026-08-01 (ver backend/AGENTS.md §50). SELECT... FOR UPDATE bloquea la fila
            # de Organization hasta el commit de este UnitOfWork, así que dos altas simultáneas
            # de la misma organización no pueden terminar con el mismo lead_number.
            from app.models.organization import Organization
            org_row = uow.session.query(Organization).filter_by(id=org_id).with_for_update().first()
            org_row.lead_counter = (org_row.lead_counter or 0) + 1
            next_lead_number = org_row.lead_counter

            # El routing engine tiene prioridad; si no asignó equipo, se usa el ya resuelto arriba
            lead_data = {
                'campaign_id': campaign_internal_id,
                'current_state_id': final_current_state_id,
                'contact_state_id': final_contact_state_id,
                'team_id': assigned_team_id if assigned_team_id is not None else final_team_id,
                'assigned_to_user_id': final_assigned_user_id,
                'picture_url': picture_url,
                'lead_number': next_lead_number,
            }

            lead = cls.repository.create(uow.session, lead_data, user_context=user_context)
            # lead.id es el public_uuid (repository.create() devuelve el schema Pydantic, no el
            # ORM crudo) -- se resuelve acá al id interno antes de usarlo en cualquier operación
            # raw (upsert_values, queries, historial, actividad). Bug real encontrado 2026-07-28
            # (mismo patrón que organization_service.py/team_service.py/lead_field_service.py):
            # rompía el guardado de valores de campos, tags, historial de estado y actividad de
            # TODO lead creado por la API -- era la causa de los errores masivos
            # "invalid input syntax for type integer" sobre lead_field_value.lead_id vistos en
            # el log de Postgres. cls.get_by_id() al final sigue necesitando el public_uuid.
            lead_public_uuid = lead.id
            lead_id = cls.repository.get_internal_id_by_public_uuid(uow.session, lead_public_uuid)
            cls.repository.upsert_values(uow.session, lead_id, clean_values)

            #Agregamos las etiquetas si vienen en el input
            if hasattr(obj_in, 'tag_ids') and obj_in.tag_ids is not None:
                # Buscamos el objeto REAL de SQLAlchemy para que las relaciones ORM se guarden
                lead_db = uow.session.query(Lead).filter_by(id=lead_id).first()
                cls._assign_tags(uow.session, lead_db, obj_in.tag_ids, campaign.organization_id)

            uow.session.flush()

            state_history_data = {
                "lead_id": lead_id,
                "from_state_id": None,
                "to_state_id": final_current_state_id,
                "notes": "Ingreso al sistema" if final_current_state_id == initial_state_internal_id
                    else "Ingreso al sistema (Etapa ajustada por una automatización)"
            }
            cls.state_history_repository.create(uow.session, state_history_data, user_context=user_context)

            cls._log_activity(
                session=uow.session,
                lead_id=lead_id,
                activity_type="LEAD_CREATED",
                details={"message": "Lead creado e ingresado a la campaña."},
                user_id=created_by
            )

            cls._log_audit(uow.session, lead, action=SystemAuditLogAction.CREATED, changes=None, user_id=created_by, internal_id=lead_id)

        return cls.get_by_id(lead_public_uuid, detailed=True)

    @classmethod
    def bulk_assign(cls, lead_ids: list[str], target_team_id: str = None, target_user_id: str = None,
                    clear_team: bool = False, clear_user: bool = False, user_context: Optional[UserContext] = None):
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

            # lead_ids/target_team_id/target_user_id llegan como public_uuid desde Fase 3 (el
            # frontend ya no conoce ningún id interno). Este endpoint (PATCH /leads/bulk-assign)
            # había quedado deliberadamente sin migrar en Fase 2 (ver backend/AGENTS.md §17)
            # asumiendo que el caller igual podía conseguir ids internos -- eso dejó de ser
            # cierto. Se resuelven acá (necesitan session) con nombres nuevos para no chocar con
            # el shadowing de closures de Python (asignar a los parámetros originales dentro de
            # esta función anidada rompería con UnboundLocalError).
            uuid_to_internal_lead = cls.repository.get_internal_ids_by_public_uuids(uow.session, lead_ids)
            internal_lead_ids = list(uuid_to_internal_lead.values())
            internal_target_team_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, target_team_id) if target_team_id is not None else None
            internal_target_user_id = UserRepository.get_internal_id_by_public_uuid(uow.session, target_user_id) if target_user_id is not None else None

            # --- Validar que team y user destino pertenecen al org del contexto ---
            if internal_target_team_id is not None:
                team = uow.session.query(Team).filter_by(id=internal_target_team_id, organization_id=org_id).first()
                if not team:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "target_team_id", "message": "El equipo destino no existe o no pertenece a esta organización."}]
                    )

            if internal_target_user_id is not None:
                membership = uow.session.query(UserOrganization).filter_by(
                    user_id=internal_target_user_id, organization_id=org_id, active=True
                ).first()
                if not membership:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "target_user_id", "message": "El usuario destino no existe o no pertenece a esta organización."}]
                    )

            # Validar que el usuario destino pertenezca al equipo destino (si se envían ambos)
            if internal_target_team_id is not None and internal_target_user_id is not None:
                from app.models.team_member import TeamMember as TM
                member_in_team = uow.session.query(TM).filter_by(
                    team_id=internal_target_team_id, user_id=internal_target_user_id
                ).first()
                if not member_in_team:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "target_user_id", "message": "El usuario destino no pertenece al equipo destino."}]
                    )

            # --- Filtrar leads por tenant y permisos de usuario para prevenir IDOR ---
            leads_query = uow.session.query(Lead).filter(
                Lead.id.in_(internal_lead_ids),
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
            if internal_target_team_id is not None:
                all_team_ids.add(internal_target_team_id)
            if internal_target_user_id is not None:
                all_user_ids.add(internal_target_user_id)

            teams_map = {
                t.id: t.name for t in uow.session.query(Team).filter(Team.id.in_(all_team_ids)).all()
            } if all_team_ids else {}
            users_map = {
                u.id: f"{u.name} {u.last_name}" for u in uow.session.query(User).filter(User.id.in_(all_user_ids)).all()
            } if all_user_ids else {}

            for lead in leads:
                old_team = lead.team_id
                old_user = lead.assigned_to_user_id

                # Solo actualizamos si se envió un valor nuevo, o si se pidió explícitamente desasignar
                # (clear_team/clear_user) — target_team_id/target_user_id en None por sí solo significa
                # "no tocar este campo", no "vaciarlo".
                if clear_team:
                    lead.team_id = None
                elif internal_target_team_id is not None:
                    lead.team_id = internal_target_team_id
                if clear_user:
                    lead.assigned_to_user_id = None
                elif internal_target_user_id is not None:
                    lead.assigned_to_user_id = internal_target_user_id

                # Motor de Automatizaciones de Campos: bulk-assign tampoco pasaba por update(),
                # así que una regla "Al actualizar registro" que lea/escriba Equipo/Usuario
                # asignado nunca se disparaba al reasignar desde acá. Se corre DESPUÉS de aplicar
                # la reasignación, para que la condición de la regla vea el valor ya actualizado.
                automation_changes, automation_history_changes = cls._run_native_change_automations(
                    uow, lead, event="ON_UPDATE", user_context=user_context
                )

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
                assign_changes = {
                    "team_id": {"old": old_team, "new": lead.team_id},
                    "assigned_to_user_id": {"old": old_user, "new": lead.assigned_to_user_id}
                }
                assign_changes.update(automation_changes)
                cls._log_audit(
                    session=uow.session,
                    obj=lead,
                    action=SystemAuditLogAction.UPDATED,
                    changes=assign_changes,
                    user_id=updated_by
                )

                # 3. Si la regla disparada modificó otros campos nativos (ej. Etapa/Estado), se
                # registra aparte en el timeline -- mismo activity_type que usa update() para
                # cambios de campo que vienen de una automatización.
                if automation_history_changes:
                    cls._log_activity(
                        session=uow.session,
                        lead_id=lead.id,
                        activity_type="FIELDS_UPDATED",
                        details={"changes": automation_history_changes},
                        user_id=updated_by
                    )

            # Hallazgo (bug reportado por el usuario): antes se devolvían los objetos `Lead` de
            # SQLAlchemy tal cual, y FastAPI los convertía a `LeadResponse` recién al serializar la
            # respuesta — momento en el que `UnitOfWork.__exit__` ya cerró la sesión (commit+close).
            # Como `LeadResponse` incluye relaciones (`team`, `assigned_to_user`, `creator`,
            # `updater`) que acá nunca se tocan directamente (solo se leen/escriben los IDs), quedaban
            # sin cargar en el objeto — y SQLAlchemy no puede lazy-cargarlas en un objeto ya desconectado
            # de la sesión (DetachedInstanceError). El cambio SÍ se guardaba en la base (por eso al
            # refrescar la página aparecía bien), pero la respuesta HTTP fallaba con 500 igual.
            # Se convierte a Pydantic acá, con la sesión todavía abierta, igual que hace
            # `base_repository.py` en el resto de la app (ver `get_all`/`get_by_id`).
            return [cls.repository.schema_out.model_validate(lead) for lead in leads]

        return cls._execute(action="Reasignación Masiva", func=do_bulk, success_msg="Leads reasignados con éxito.")

    @classmethod
    def change_state(cls, obj_id: str, new_state_id: str, notes: str = None, user_context: Optional[UserContext] = None):
        """
        Cambia el estado de un lead verificando que la transición sea permitida en el flujo.
        Registra el evento en el historial.
        """
        with UnitOfWork() as uow:
            # obj_id/new_state_id llegan como public_uuid (Lead y LeadState respectivamente) desde
            # Fase 3 -- este endpoint quedó deliberadamente sin migrar en Fase 2 (ver
            # backend/AGENTS.md §17) asumiendo que el caller igual podía conseguir el id interno,
            # pero eso dejó de ser cierto: el frontend ya no conoce ningún id interno. Se resuelven
            # acá y se SHADOWEAN las mismas variables con el id interno -- de acá para abajo el
            # resto del método sigue exactamente igual que antes. La única excepción es el
            # `cls.get_by_id` del final, que necesita el UUID público original (se guarda aparte).
            public_obj_id = obj_id
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            obj_id = internal_id

            internal_state_id = cls.state_repository.get_internal_id_by_public_uuid(uow.session, new_state_id)
            if internal_state_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "new_state_id", "message": "El estado no existe."}])
            new_state_id = internal_state_id

            lead = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not lead:
                cls._not_found(public_obj_id)

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
                # Bug real encontrado 2026-07-30 (mismo patrón que create(), ver comentario ahí):
                # initial_state.id es un public_uuid (schema Pydantic), pero new_state_id ya fue
                # resuelto al id interno más arriba -- comparar directo siempre daba False y
                # rechazaba con 400 incluso cuando el destino SÍ era el estado inicial del flujo.
                initial_state_internal_id = (
                    cls.state_repository.get_internal_id_by_public_uuid(uow.session, initial_state.id)
                    if initial_state else None
                )
                if not initial_state or new_state_id != initial_state_internal_id:
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

            # Motor de Automatizaciones de Campos: este selector dedicado no pasa por update(),
            # así que sin esto una regla "Al actualizar registro" nunca se disparaba al cambiar
            # Etapa acá (reportado por el usuario 2026-07-25). Se corre DESPUÉS de guardar, para
            # que la condición de la regla vea la Etapa ya actualizada.
            lead_orm = uow.session.query(Lead).filter_by(id=obj_id).first()
            automation_changes, automation_history_changes = cls._run_native_change_automations(
                uow, lead_orm, event="ON_UPDATE", user_context=user_context
            )

            # 4. Inyectar el historial
            # lead.id es el public_uuid (lead viene de repository.get_by_id(), que devuelve el
            # schema Pydantic) -- usamos obj_id (ya resuelto al id interno más arriba) en vez de
            # lead.id. Bug real encontrado 2026-07-28, mismo patrón que en create().
            history_data = {
                "lead_id": obj_id,
                "from_state_id": current_state_id,
                "to_state_id": new_state_id,
                "notes": notes
            }
            cls.state_history_repository.create(uow.session, history_data, user_context=user_context)

            # Pasamos 'lead' y formateamos el old vs new
            diff_state = {"current_state_id": {"old": current_state_id, "new": new_state_id}}
            diff_state.update(automation_changes)
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

            # Si la regla disparada modificó otros campos nativos (ej. Equipo/Usuario asignado),
            # se registra aparte en el timeline -- mismo activity_type que usa update() para
            # cambios de campo que vienen de una automatización.
            if automation_history_changes:
                cls._log_activity(
                    session=uow.session,
                    lead_id=obj_id,
                    activity_type="FIELDS_UPDATED",
                    details={"changes": automation_history_changes},
                    user_id=user_context.user.id if user_context else None
                )

        # Devolvemos el Lead actualizado para el Frontend
        return cls.get_by_id(public_obj_id, detailed=True)

    @classmethod
    def change_contact_state(cls, obj_id: str, new_contact_state_id: str, notes: str = None, user_context: Optional[UserContext] = None):
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
            # Mismo motivo/patrón que en change_state: obj_id/new_contact_state_id llegan como
            # public_uuid (Lead/LeadContactState) desde Fase 3, se resuelven y se shadowean acá.
            public_obj_id = obj_id
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            obj_id = internal_id

            from app.db.repository.lead_contact_state_repository import LeadContactStateRepository
            internal_contact_state_id = LeadContactStateRepository.get_internal_id_by_public_uuid(uow.session, new_contact_state_id)
            if internal_contact_state_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "new_contact_state_id", "message": "El estado de contacto no existe."}])
            new_contact_state_id = internal_contact_state_id

            lead = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)
            if not lead:
                cls._not_found(public_obj_id)

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

            # Motor de Automatizaciones de Campos: este selector dedicado no pasa por update(),
            # así que sin esto una regla "Al actualizar registro" nunca se disparaba al cambiar
            # Estado acá -- exactamente el caso reportado por el usuario 2026-07-25 (Estado=Rechazado
            # -> Etapa=No interesado). Se corre DESPUÉS de guardar, para que la condición de la
            # regla vea el Estado ya actualizado.
            lead_orm = uow.session.query(Lead).filter_by(id=obj_id).first()
            automation_changes, automation_history_changes = cls._run_native_change_automations(
                uow, lead_orm, event="ON_UPDATE", user_context=user_context
            )

            updated_by = user_context.user.id if user_context else None

            diff = {"contact_state_id": {"old": current_contact_state_id, "new": new_contact_state_id}}
            diff.update(automation_changes)
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

            # Si la regla disparada modificó otros campos nativos (ej. Etapa/Equipo/Usuario
            # asignado), se registra aparte en el timeline -- mismo activity_type que usa update()
            # para cambios de campo que vienen de una automatización.
            if automation_history_changes:
                cls._log_activity(
                    session=uow.session,
                    lead_id=obj_id,
                    activity_type="FIELDS_UPDATED",
                    details={"changes": automation_history_changes},
                    user_id=updated_by
                )

        # Devolvemos el Lead actualizado para el Frontend
        return cls.get_by_id(public_obj_id, detailed=True)

    @classmethod
    def simulate_create(cls, obj_in, user_context: Optional[UserContext] = None, files_map: dict = None):
        with UnitOfWork() as uow:
            created_by = user_context.user.id if user_context else None

            from app.core.context import TENANT_ORG_ID
            dummy_org_id = TENANT_ORG_ID.get() or 0

            # obj_in.campaign_id/team_id/assigned_to_user_id llegan como public_uuid desde Fase 3
            # (mismo motivo que en create() más arriba).
            campaign_internal_id = cls.campaign_repository.get_internal_id_by_public_uuid(uow.session, obj_in.campaign_id)
            campaign = cls.campaign_repository.get_by_id(uow.session, campaign_internal_id, user_context=user_context) if campaign_internal_id is not None else None
            if not campaign:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "La campaña no existe."}])

            # Validar org membership de team_id y assigned_to_user_id (igual que en create)
            from app.models.team import Team
            from app.models.security_models import UserOrganization
            org_id = campaign.organization_id
            if obj_in.team_id is not None:
                team_internal_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.team_id)
                team = uow.session.query(Team).filter_by(id=team_internal_id, organization_id=org_id).first()
                if not team:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "team_id", "message": "El equipo no existe o no pertenece a esta organización."}])
            if obj_in.assigned_to_user_id is not None:
                user_internal_id = UserRepository.get_internal_id_by_public_uuid(uow.session, obj_in.assigned_to_user_id)
                membership = uow.session.query(UserOrganization).filter_by(user_id=user_internal_id, organization_id=org_id, active=True).first()
                if not membership:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "assigned_to_user_id", "message": "El usuario no existe o no pertenece a esta organización."}])

            clean_values, context_data, field_defs = cls._prepare_creation_data(uow, obj_in, files_map, created_by, campaign=campaign, campaign_internal_id=campaign_internal_id, is_simulation=True)

            states = cls.state_repository.get_all(uow.session, user_context=user_context, lead_flow_id=campaign.lead_flow_id, is_initial=True)
            initial_state = states[0] if states else None
            if not initial_state:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "general", "message": "La campaña no tiene un estado inicial configurado."}])
            # Bug real encontrado 2026-07-30 (mismo patrón que create()): initial_state.id es un
            # public_uuid -- el campo plano current_state_id de LeadResponse sigue siendo int
            # (Fase 4 no lo migró), así que hay que resolverlo acá. El nested "current_state.id"
            # de más abajo sí debe quedar como uuid -- ese no se toca.
            initial_state_internal_id = cls.state_repository.get_internal_id_by_public_uuid(uow.session, initial_state.id)

            dummy_lead_id = -1
            fields_map = {f.id: f for f in field_defs}

            # Bug real encontrado 2026-08-01: este dict se arma a mano (el Lead simulado no se
            # persiste, así que no hay fila real de la que sacar un public_uuid) e id/field_values[].id
            # seguían siendo los ints negativos de antes de la migración a public_uuid (Fase 1-4) --
            # LeadResponse.id/LeadFieldValueResponse.id son `str` desde entonces, así que CUALQUIER
            # llamada a POST /leads/simulate rompía con ResponseValidationError real (no era un bug
            # de test). Fix: sentinel strings fijos para el Lead/field_value simulados (no persisten,
            # no tiene sentido un uuid real o generado al vuelo -- decisión confirmada con el
            # usuario, ver backend/AGENTS.md). field.id sí usa field_def.public_uuid real: el
            # LeadField SÍ existe en la base, a diferencia del Lead/LeadFieldValue simulados.
            simulated_values = []
            for item_proxy in clean_values:
                data = item_proxy._data
                fid = data['field_id']
                field_def = fields_map.get(fid)

                simulated_values.append({
                    "id": f"simulated-{field_def.public_uuid}" if field_def else "simulated",
                    "active": True,
                    "lead_id": dummy_lead_id,
                    "field_id": fid,
                    "value": data.get('value'),
                    "nomenclator_items": [],
                    "related_leads": [],
                    "field": {
                        "id": field_def.public_uuid,
                        "active": True,
                        "name": field_def.name,
                        "order": field_def.order,
                        "field_type_code": field_def.field_type_code,
                        "field_subtype_code": getattr(field_def, 'field_subtype_code', None),
                        "title_order": getattr(field_def, 'title_order', None),
                    } if field_def else None
                })

            return {
                "id": "simulated",
                "active": True,
                "campaign_id": campaign_internal_id,
                "organization_id": dummy_org_id,
                "current_state_id": initial_state_internal_id,
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
    def update(cls, obj_id: str, obj_in, files_map: dict = None, user_context: Optional[UserContext] = None, avatar_file: UploadFile = None):
        errors = []

        with UnitOfWork() as uow:
            # obj_id llega como public_uuid; se resuelve una única vez al id interno,
            # que es lo que sigue esperando cls.repository y el resto de este método.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            current_lead = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context)
            if not current_lead: cls._not_found(obj_id)

            # Validar que contact_state_id pertenece al org
            # obj_in.contact_state_id llega como public_uuid de LeadContactState desde Fase 3.
            # BaseRepository.update() ya resuelve el mismo campo genéricamente (vía
            # _resolve_fk_payload_fields) antes del UPDATE real, pero acá necesitamos el id
            # interno ADEMÁS para esta validación manual, que corre antes de esa llamada.
            if obj_in and obj_in.contact_state_id is not None:
                from app.models.lead_contact_state import LeadContactState
                contact_state_internal_id = LeadContactStateRepository.get_internal_id_by_public_uuid(uow.session, obj_in.contact_state_id)
                contact_state = uow.session.query(LeadContactState).filter_by(
                    id=contact_state_internal_id,
                    organization_id=current_lead.organization_id,
                    active=True
                ).first()
                if not contact_state:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "contact_state_id", "message": "El estado de contacto no existe o no pertenece a esta organización."}])

            # Logica de Tags
            if obj_in and "tag_ids" in obj_in.model_fields_set:
                lead_db = uow.session.query(Lead).filter_by(id=internal_id).first()
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
                cls.repository.update(uow.session, internal_id, lead_data, user_context=user_context)

            if obj_in and obj_in.values is not None:
                # obj_in.values[].field_id llega como public_uuid del LeadField -- se resuelve
                # acá antes de comparar contra defs_map (id interno). Ver _resolve_value_field_ids
                # y backend/AGENTS.md §18-decies.
                cls._resolve_value_field_ids(uow.session, obj_in.values)

                all_field_defs = cls.field_repository.get_all_active_with_rules(uow.session, campaign_id=current_lead.campaign_id)
                current_campaign_defs = [f for f in all_field_defs if f.campaign_id == current_lead.campaign_id]

                defs_map = {f.id: f for f in current_campaign_defs}

                # Ver _resolve_value_nomenclator_ids -- resuelve uuids de NomenclatorItem en
                # `value` para campos SELECTOR/CHECKBOX, ahora que defs_map ya existe.
                cls._resolve_value_nomenclator_ids(uow.session, obj_in.values, defs_map)

                # Ver _resolve_value_lead_ids -- resuelve uuids de Lead relacionado en `value`
                # para campos tipo LEAD, mismo criterio que nomencladores.
                cls._resolve_value_lead_ids(uow.session, obj_in.values, defs_map)

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
                # Bug real encontrado 2026-07-30: current_lead viene de cls.repository.get_by_id()
                # -- devuelve el schema Pydantic (LeadDetailedResponse), no el ORM crudo. Sus
                # nomenclator_items[].id son public_uuid (Fase 4), pero el resto de esta función
                # (validación, motor de automatizaciones -- ver APPEND_TO_LIST/REMOVE_FROM_LIST en
                # automation_engine.py) siempre trabajó con los ids internos crudos de
                # NomenclatorItem. Hay que resolverlos acá antes de usarlos como "old_value".
                from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
                all_item_uuids = [
                    item.id
                    for v in current_lead.field_values
                    if getattr(v, "value", None) is None and getattr(v, "nomenclator_items", None)
                    for item in v.nomenclator_items
                ]
                item_uuid_to_internal = NomenclatorItemRepository.get_internal_ids_by_public_uuids(uow.session, all_item_uuids)

                # Bug real encontrado 2026-08-01, mismo patrón exacto que item_uuid_to_internal
                # de arriba (para NomenclatorItem): `current_lead.field_values[].related_leads[].id`
                # también es public_uuid (RelatedLeadResponse, Fase 1-4), pero antes se usaba tal
                # cual como "old_value" en db_values -- comparado/mezclado más abajo con
                # incoming_data (que desde _resolve_value_lead_ids ya trae ids internos). Rompía
                # con DataError de Postgres en _translate_value_for_history (`lead_id IN (uuid)`)
                # en cualquier update() de un Lead con un campo LEAD ya poblado.
                all_related_lead_uuids = [
                    l.id
                    for v in current_lead.field_values
                    if getattr(v, "value", None) is None and getattr(v, "related_leads", None)
                    for l in v.related_leads
                ]
                related_lead_uuid_to_internal = LeadRepository.get_internal_ids_by_public_uuids(uow.session, all_related_lead_uuids)

                db_values = {}
                for v in current_lead.field_values:
                    val = getattr(v, "value", None)
                    if val is None:
                        if hasattr(v, "nomenclator_items") and v.nomenclator_items:
                            val = [item_uuid_to_internal.get(item.id) for item in v.nomenclator_items]
                        elif hasattr(v, "related_leads") and v.related_leads:
                            val = [related_lead_uuid_to_internal.get(l.id) for l in v.related_leads]
                        elif hasattr(v, "nomenclator_item_id") and v.nomenclator_item_id:
                            val = v.nomenclator_item_id
                    db_values[v.field_id] = val

                full_context = {**db_values, **incoming_data}

                # Campos nativos (Etapa/Estado/Equipo/Usuario asignado/fechas/creador/modificador)
                # disponibles para que una regla "Al actualizar registro" los lea o sobreescriba.
                #
                # Bug real encontrado 2026-08-11: build_native_context_from_lead() espera un
                # objeto ORM real (lee getattr(lead, "created_by"/"updated_by", None) -- ver su
                # propio docstring y el de _run_native_change_automations, que sí usa el ORM).
                # Acá se le pasaba `current_lead`, que es el schema Pydantic devuelto por
                # cls.repository.get_by_id() (LeadResponse). Desde el 2026-08-04 ese schema ya
                # NO expone `created_by`/`updated_by` como int (se sacaron a propósito, ver
                # lead_schema.py -- quedan solo como `creator`/`updater` con public_uuid), así
                # que getattr(...) siempre devolvía None para esos dos campos nativos. Cualquier
                # condición de automatización sobre "Usuario Creador" (-7) o "Usuario
                # Modificación" (-8) en un ON_UPDATE nunca podía matchear (is_empty → False),
                # sin ningún error visible. Se resuelve consultando el ORM real acá.
                from app.core.native_lead_fields import build_native_context_from_lead
                lead_orm_for_native_ctx = uow.session.query(Lead).filter_by(id=internal_id).first()
                native_ctx_before = build_native_context_from_lead(lead_orm_for_native_ctx)
                full_context.update(native_ctx_before)

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
                cls._check_duplicates(uow.session, current_lead.campaign_id, full_context, current_campaign_defs, errors, exclude_lead_id=internal_id)

                # Validar reglas
                cls._validate_processed_data(uow, full_context, current_campaign_defs, errors, current_lead_id=internal_id)

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

                # --- CAMPOS NATIVOS ESCRIBIBLES MODIFICADOS POR AUTOMATIZACIONES ---
                # (Etapa/Estado/Equipo/Usuario asignado). Extraído a un helper compartido
                # (`_apply_native_automation_writeback`) que también usan `change_state`,
                # `change_contact_state` y `bulk_assign` -- ver ese método para el detalle de
                # la validación liviana que reemplaza a "transición permitida"/"pertenece al equipo".
                native_changes, native_history_changes = cls._apply_native_automation_writeback(
                    uow, internal_id, native_ctx_before, automation_audit, user_context
                )
                changes.update(native_changes)
                history_changes.update(native_history_changes)

                # Persistencia
                clean_values = cls._reconstruct_items_for_repo(incoming_data, current_campaign_defs)
                cls.repository.upsert_values(uow.session, internal_id, clean_values)

                user_id = user_context.user.id if user_context else None

                # Si hubo cambios reales en los field values, forzamos el "touch" del Lead.
                # upsert_values() solo modifica filas de lead_field_value (con su propio
                # updated_at), por lo que sin esto lead.updated_at quedaba desactualizado.
                if changes:
                    lead_obj = uow.session.query(Lead).filter_by(id=internal_id).first()
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
                        lead_id=internal_id,
                        activity_type="FIELDS_UPDATED",
                        details={"changes": history_changes},
                        user_id=user_id
                    )

        # obj_id sigue siendo el public_uuid original -- get_by_id (ya migrado) lo vuelve a resolver.
        return cls.get_by_id(obj_id, detailed=True)

    @classmethod
    def search(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, detailed: bool = False, search_req=None, order_by=None, ascending: bool = True, only_active: bool = True, campaign_id: Optional[int] = None, query: Optional[str] = None):
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
                campaign_id=campaign_id,
                query=query
            )

            accessible_campaign_ids = CampaignRepository.get_accessible_campaign_ids(uow.session, user_context)
            for item in items:
                cls._enrich_lead_with_urls(item)
                cls._redact_inaccessible_related_leads(item, accessible_campaign_ids)

            return total, items

        return cls._execute(
            action="Buscando Leads",
            func=do_search
        )
    
    @classmethod
    def get_all(cls, user_context: Optional[UserContext] = None, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE, only_active: bool = True, detailed: bool = False, query=None, **kwargs):
        def _fetch(uow):
            total, items = cls.repository.get_all(
                session=uow.session, user_context=user_context,
                page=page,
                page_size=page_size,
                only_active=only_active,
                detailed=detailed,
                search=query,
                **kwargs
            )
            # Se calcula acá adentro (con la sesión todavía abierta) para poder redactar leads
            # relacionados de otras campañas sin acceso, ver _redact_inaccessible_related_leads.
            accessible_campaign_ids = CampaignRepository.get_accessible_campaign_ids(uow.session, user_context)
            return total, items, accessible_campaign_ids

        total, items, accessible_campaign_ids = cls._execute(
            action=f"Obteniendo listado de leads",
            func=_fetch
        )

        for item in items:
                cls._enrich_lead_with_urls(item)
                cls._redact_inaccessible_related_leads(item, accessible_campaign_ids)

        return total, items

    @classmethod
    def get_by_id(cls, obj_id: str, user_context: Optional[UserContext] = None, detailed: bool = True):
        def _fetch(uow):
            # obj_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                return None
            lead = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=detailed)
            if lead is None: return None  # Deja que _execute dispare el 404 de siempre
            accessible_campaign_ids = CampaignRepository.get_accessible_campaign_ids(uow.session, user_context)
            return lead, accessible_campaign_ids

        lead, accessible_campaign_ids = cls._execute(
            action="Obteniendo",
            obj_id=obj_id,
            func=_fetch
        )

        cls._redact_inaccessible_related_leads(lead, accessible_campaign_ids)
        return cls._enrich_lead_with_urls(lead)
    
    @classmethod
    def _assign_tags(cls, session, lead_obj, tag_ids: list[str], org_id: int):
        """
        Asigna etiquetas a un lead. Si tag_ids es una lista vacía, borra las asociaciones.
        Verifica que todas las etiquetas pertenezcan a la organización del lead.

        tag_ids son public_uuid de Tag (desde Fase 3 el front ya no conoce el id interno --
        TagResponse hereda BaseResponse). Se filtra directo por Tag.public_uuid en vez de
        resolver a id interno primero, porque de cualquier forma necesitamos volver a traer
        los objetos Tag completos para asignarlos a la relación.
        """
        from app.models.tag import Tag

        if tag_ids is None or not tag_ids:
            lead_obj.tags = [] # Borramos todas las etiquetas asociadas
            return

        # Buscamos solo las etiquetas que coinciden con los UUID y pertenecen a la empresa
        tags = session.query(Tag).filter(
            Tag.public_uuid.in_(tag_ids),
            Tag.organization_id == org_id
        ).all()

        if len(tags) != len(set(tag_ids)):
            found_uuids = {t.public_uuid for t in tags}
            missing_uuids = [i for i in tag_ids if i not in found_uuids]
            raise HTTPException(
                status_code=400,
                detail=[{"field": "tag_ids", "message": f"Las etiquetas {missing_uuids} no existen o no pertenecen a tu organización."}]
            )

        lead_obj.tags = tags
