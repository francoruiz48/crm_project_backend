from typing import Optional
import unicodedata
from fastapi import HTTPException, status
from app.models.lead_field_section import LeadFieldSection
from app.models.nomenclator import Nomenclator
from app.db.unit_of_work import UnitOfWork
from app.services.base_service import BaseService
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.nomenclator_service import NomenclatorService
from app.services.validation_rule_service import ValidationRuleService
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository
from app.models.lead_field_type import LeadFieldType
from app.core.constans import NOMENCLATOR_FIELD_TYPES, SystemAuditLogAction
from app.models.lead_field_value import LeadFieldValue
from app.core.error_messages import SUCCESS_UPDATE
from app.models.lead_field import LeadField
from app.db.repository.campaign_repository import CampaignRepository
from app.db.repository.nomenclator_repository import NomenclatorRepository
from app.core.templates.field_rules_map import DEFAULT_SUBTYPE_RULES, DEFAULT_TYPE_RULES,STANDARD_INPUT_MASKS, DEFAULT_TYPE_MASKS, DEFAULT_SUBTYPE_MASKS
from sqlalchemy.orm import selectinload
from app.models.lead import Lead
from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
from datetime import date, datetime
from app.core.constans import DATE_TIME_FORMAT
from app.core.security import UserContext
from app.schemas.lead_field_schema import LeadFieldOrderList
from app.core.context import TENANT_ORG_ID
from app.db.repository.lead_field_section_repository import LeadFieldSectionRepository

# Auto-asignación "inteligente" de title_order/subtitle_order al crear un campo (ver
# LeadFieldService._maybe_auto_assign_order y sus dos wrappers). Match EXACTO de nombre (con
# sinónimos, incluyendo variantes en inglés), sin importar mayúsculas/tildes — a propósito no es
# un "contains", para no matchear de más (ej. "Nombre de la empresa" no dispara nada).
AUTO_TITLE_ORDER_NAMES = {
    "nombre": 1, "nombres": 1, "name": 1, "first name": 1, "firstname": 1,
    "apellido": 2, "apellidos": 2, "lastname": 2, "last name": 2, "surname": 2,
}
AUTO_SUBTITLE_ORDER_NAMES = {
    "cargo": 1, "puesto": 1, "position": 1, "job title": 1, "jobtitle": 1,
    "empresa": 2, "compañía": 2, "company": 2, "organización": 2,
}

class LeadFieldService(BaseService):
    repository = LeadFieldRepository
    nomenclatorService = NomenclatorService
    campaign_repository = CampaignRepository
    section_repository = LeadFieldSectionRepository
    
    # =========================================================================
    # HELPERS DE VALIDACIÓN (CHECKERS)
    # =========================================================================

    @classmethod
    def _normalize_field_name(cls, name: str) -> str:
        """Minúsculas y sin tildes, para matchear nombres de campo sin importar cómo se hayan tipeado."""
        return "".join(
            c for c in unicodedata.normalize("NFD", name.strip().lower())
            if unicodedata.category(c) != "Mn"
        )

    @classmethod
    def _maybe_auto_assign_order(cls, session, campaign_id: int, name: Optional[str], data: dict,
                                  data_key: str, model_column, synonym_map: dict):
        """
        Helper genérico detrás de _maybe_auto_assign_title_order/_maybe_auto_assign_subtitle_order.
        Si el usuario no especificó `data_key` (title_order/subtitle_order) a mano, y el nombre
        del campo matchea EXACTO (sin importar mayúsculas/tildes) con algún sinónimo del mapa, se
        autoasigna el slot correspondiente — pero SOLO si ESE slot puntual todavía no está ocupado
        por otro campo activo, para no pisar nunca una configuración manual ya hecha. El chequeo
        es por slot, no por campaña completa: así "Nombre"/"Apellido" (o "Cargo"/"Empresa") se
        pueden ir creando en pasos separados, el caso más común, sin que el primero bloquee al
        segundo. Solo aplica al crear el campo, no si luego se lo renombra.
        """
        if data.get(data_key) is not None or not name:
            return

        auto_order = synonym_map.get(cls._normalize_field_name(name))
        if auto_order is None:
            return

        slot_taken = session.query(LeadField.id).filter(
            LeadField.campaign_id == campaign_id,
            model_column == auto_order,
            LeadField.active == True
        ).first() is not None

        if not slot_taken:
            data[data_key] = auto_order

    @classmethod
    def _maybe_auto_assign_title_order(cls, session, campaign_id: int, name: Optional[str], data: dict):
        cls._maybe_auto_assign_order(session, campaign_id, name, data, "title_order", LeadField.title_order, AUTO_TITLE_ORDER_NAMES)

    @classmethod
    def _maybe_auto_assign_subtitle_order(cls, session, campaign_id: int, name: Optional[str], data: dict):
        cls._maybe_auto_assign_order(session, campaign_id, name, data, "subtitle_order", LeadField.subtitle_order, AUTO_SUBTITLE_ORDER_NAMES)

    @classmethod
    def _check_name_uniqueness(cls, session, campaign_id: int, name: str, errors: list, exclude_id: int = None):
        """
        Verifica duplicados de nombre. Agrega error a la lista si falla.

        Bug real encontrado 2026-08-01 (código frágil, sin impacto real hasta ahora -- ver
        backend/AGENTS.md §52): antes usaba `cls.repository.get_all()`, que devuelve schemas
        Pydantic (`.id` = public_uuid, Fase 3), y comparaba ese `.id` contra `exclude_id` (id
        interno, int) -- una comparación string-vs-int que siempre da True, así que la
        exclusión del propio campo nunca funcionaba de verdad. No se notaba porque los dos
        call sites que pasan `exclude_id` (update() y set_active()) tienen una guarda previa
        que hace que el campo propio nunca pueda aparecer en `existing` para empezar. Se pasa
        a una query directa al ORM (mismo patrón que tag_service.py/lead_flow_service.py) para
        que la exclusión compare ids reales contra ids reales.
        """
        if not name: return
        query = session.query(LeadField).filter(
            LeadField.campaign_id == campaign_id,
            LeadField.name == name,
            LeadField.active == True,
        )
        if exclude_id is not None:
            query = query.filter(LeadField.id != exclude_id)
        if query.first():
            errors.append({"field": "name", "message": "Ya existe un campo activo con este nombre en la campaña."})

    @classmethod
    def _check_order_uniqueness(cls, session, campaign_id: int, order: int, errors: list, exclude_id: int = None):
        """
        Verifica colisión de orden. Agrega error a la lista si falla.

        Mismo bug y mismo fix que _check_name_uniqueness (ver comentario ahí, backend/AGENTS.md §52).
        """
        if order is None: return
        query = session.query(LeadField).filter(
            LeadField.campaign_id == campaign_id,
            LeadField.order == order,
            LeadField.active == True,
        )
        if exclude_id is not None:
            query = query.filter(LeadField.id != exclude_id)
        collision = query.first()
        if collision:
            errors.append({"field": "order", "message": f"El orden {order} ya está ocupado por el campo '{collision.name}'."})

    @classmethod
    def _check_historic_constraints(cls, session, field, field_internal_id: int, new_required: bool, new_primary: bool, errors: list):
        """
        Valida integridad histórica. Agrega errores a la lista.

        Bug real encontrado 2026-07-30: `field` es el resultado de `cls.repository.get_by_id()`,
        que devuelve el schema Pydantic (no el ORM) -- su `.id` es el public_uuid (Fase 3), no
        el id interno. La query de abajo comparaba `LeadFieldValue.field_id` (columna Integer)
        contra ese uuid, rompiendo con un DataError de Postgres en CUALQUIER intento de marcar
        un campo como requerido (quedaba enmascarado como un 400 genérico con detail en texto
        plano, en vez del formato estructurado de `errors`). Se agrega `field_internal_id`
        explícito (el caller ya lo tiene resuelto) en vez de confiar en `field.id`.
        """
        # A. Validación de REQUIRED retroactivo
        if new_required is True and not field.required:
            has_nulls = session.query(LeadFieldValue).join(
                Lead, LeadFieldValue.lead_id == Lead.id
            ).filter(
                LeadFieldValue.field_id == field_internal_id,
                Lead.active == True,
                (LeadFieldValue.value == None) | (LeadFieldValue.value == "")
            ).first()

            if has_nulls:
                errors.append({"field": "required", "message": "No se puede marcar como requerido porque existen registros antiguos con valor vacío."})

        # B. Validación de PRIMARY retroactivo
        if new_primary is True and not field.is_primary:
            has_leads = LeadRepository.has_leads_in_campaign(session, field.campaign_id)
            if has_leads:
                errors.append({"field": "is_primary", "message": "No se puede marcar como 'Primary' porque ya existen Leads en esta campaña."})

    # =========================================================================
    # HELPERS: NOMENCLADORES DEPENDIENTES (ver docs/nomencladores.md)
    # =========================================================================

    @classmethod
    def _validate_depends_on_field(
        cls, session, campaign_id: int, own_nomenclator_id: Optional[int], own_field_type_code: Optional[str],
        depends_on_field_id: int, errors: list, exclude_field_id: int = None
    ):
        """Valida que depends_on_field_id sea un campo válido para que ESTE
        campo dependa de él: ambos deben ser de tipo nomenclador, de la misma
        campaña, y el catálogo del campo padre tiene que estar declarado como
        padre válido del catálogo de este campo (Nomenclator.parent_nomenclators).
        No hace chequeo de ciclos acá — eso lo maneja el caller, que sabe si
        hace falta (solo en update, un campo nuevo no puede formar ciclos)."""
        if not own_nomenclator_id or own_field_type_code not in NOMENCLATOR_FIELD_TYPES:
            errors.append({"field": "depends_on_field_id", "message": "Solo un campo de tipo nomenclador (SELECTOR/CHECKBOX) puede depender de otro campo."})
            return None

        if exclude_field_id is not None and depends_on_field_id == exclude_field_id:
            errors.append({"field": "depends_on_field_id", "message": "Un campo no puede depender de sí mismo."})
            return None

        parent_field = session.query(LeadField).filter_by(id=depends_on_field_id).first()
        if not parent_field:
            errors.append({"field": "depends_on_field_id", "message": "El campo del que depende no existe."})
            return None
        if parent_field.campaign_id != campaign_id:
            errors.append({"field": "depends_on_field_id", "message": "El campo del que depende debe ser de la misma campaña."})
            return None
        if not parent_field.nomenclator_id:
            errors.append({"field": "depends_on_field_id", "message": "El campo del que depende también debe ser de tipo nomenclador."})
            return None

        own_nomenclator = session.query(Nomenclator).filter_by(id=own_nomenclator_id).first()
        allowed_parent_nomenclator_ids = {n.id for n in own_nomenclator.parent_nomenclators} if own_nomenclator else set()
        if parent_field.nomenclator_id not in allowed_parent_nomenclator_ids:
            errors.append({
                "field": "depends_on_field_id",
                "message": "El catálogo del campo del que depende no está declarado como padre válido del catálogo de este campo. Agregalo primero a los padres del catálogo."
            })
            return None

        return parent_field

    @classmethod
    def _would_create_field_dependency_cycle(cls, session, node_id: int, candidate_parent_id: int) -> bool:
        """Recorre depends_on_field_id hacia arriba desde candidate_parent_id;
        si en algún punto se llega de nuevo a node_id, asignarlo como padre
        formaría un ciclo (permite cadenas de más de un nivel, ej. A->B->C)."""
        current_id = candidate_parent_id
        visited = set()
        while current_id is not None:
            if current_id == node_id:
                return True
            if current_id in visited:
                break
            visited.add(current_id)
            current = session.query(LeadField).filter_by(id=current_id).first()
            current_id = current.depends_on_field_id if current else None
        return False

    # =========================================================================
    # CREATE
    # =========================================================================

    @classmethod
    def create_within_session(cls, session, obj_in, user_context: Optional[UserContext] = None):
        errors = []
        data = obj_in.model_dump(exclude_unset=True)
        org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()

        # --- 1. VALIDACIÓN DE CONTEXTO (Bloqueante) ---
        # Todas las FKs de este método llegan como public_uuid (Fase 3, ver backend/AGENTS.md
        # §18); se resuelven a id interno acá, una por una, antes de cualquier uso.
        campaign_uuid = data.get("campaign_id")
        if not campaign_uuid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "El ID de campaña es obligatorio."}])

        campaign_id = cls.campaign_repository.get_internal_id_by_public_uuid(session, campaign_uuid)
        campaign = cls.campaign_repository.get_by_id(session, campaign_id, user_context=user_context) if campaign_id is not None else None
        if not campaign:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": f"La campaña {campaign_uuid} no existe o no tiene acceso."}])
        data["campaign_id"] = campaign_id

        # --- 2. EXTRACCIÓN DE DATOS ---
        template_code = data.get("field_template_code")
        mask_template_code = data.pop("mask_template_code", None)
        field_type_code = data.get("field_type_code")
        subtype_code = data.get("field_subtype_code")
        nomenclator_uuid = data.get("nomenclator_id")
        nomenclator_id = NomenclatorRepository.get_internal_id_by_public_uuid(session, nomenclator_uuid) if nomenclator_uuid else None
        if nomenclator_uuid and nomenclator_id is not None:
            data["nomenclator_id"] = nomenclator_id
        calc_expr = data.get("calculation_expression")
        name = data.get("name")
        current_mask = data.get("input_mask")
        section_uuid = data.get("lead_field_section_id")

        # --- Validar Sección ---
        if section_uuid:
            section_id = LeadFieldSectionRepository.get_internal_id_by_public_uuid(session, section_uuid)
            section = cls.section_repository.get_by_id(session, section_id, user_context=user_context) if section_id is not None else None
            if not section:
                errors.append({"field": "lead_field_section_id", "message": "La sección no existe o no pertenece a su empresa."})
            else:
                data["lead_field_section_id"] = section_id
        else:
            # Buscamos la sección más antigua (ID más bajo) de la organización
            section = session.query(LeadFieldSection).filter(
                LeadFieldSection.organization_id == org_id,
                LeadFieldSection.active == True
            ).order_by(LeadFieldSection.id.asc()).first()

            if section:
                # ¡IMPORTANTE! Actualizamos el payload para que se guarde este ID
                data["lead_field_section_id"] = section.id
            else:
                # Fallback de seguridad extremo por si algo falló en la creación de la org
                errors.append({"field": "lead_field_section_id", "message": "Su organización no tiene una sección por defecto configurada."})

        # --- Validar Campaña Relacionada ---
        rel_campaign_uuid = data.get("related_campaign_id")
        rel_campaign_id = cls.campaign_repository.get_internal_id_by_public_uuid(session, rel_campaign_uuid) if rel_campaign_uuid else None
        if rel_campaign_uuid:
            rel_campaign = cls.campaign_repository.get_by_id(session, rel_campaign_id, user_context=user_context) if rel_campaign_id is not None else None
            if not rel_campaign:
                errors.append({"field": "related_campaign_id", "message": "La campaña relacionada no existe o no tiene acceso a ella."})
            else:
                data["related_campaign_id"] = rel_campaign_id

        # --- 3. LÓGICA DE TEMPLATE ---
        rules_to_create = []
        if template_code:
            template = STANDARD_FIELD_TEMPLATES.get(template_code)
            if not template:
                errors.append({"field": "field_template_code", "message": f"La plantilla '{template_code}' no existe."})
            else:
                if not name:
                    data["name"] = template.name
                    name = template.name
                data["field_type_code"] = template.field_type_code
                data["field_template_name"] = template.name
                field_type_code = template.field_type_code
                rules_to_create = template.rules

                if template.input_mask and not current_mask:
                    data["input_mask"] = template.input_mask
                    current_mask = template.input_mask

        elif nomenclator_uuid:
            nomenclator = cls.nomenclatorService.repository.get_by_id(session, nomenclator_id, user_context=user_context) if nomenclator_id is not None else None
            if not nomenclator:
                errors.append({"field": "nomenclator_id", "message": f"El Nomenclador no existe o no tienes acceso."})
            elif not name:
                data["name"] = nomenclator.name
                name = nomenclator.name

        # --- 3.5. ASIGNACIÓN INTELIGENTE DE INPUT MASK ---
        if not current_mask:
            if mask_template_code:
                if mask_template_code in STANDARD_INPUT_MASKS:
                    data["input_mask"] = STANDARD_INPUT_MASKS[mask_template_code]["mask"]
                else:
                    errors.append({"field": "mask_template_code", "message": f"Plantilla de máscara '{mask_template_code}' no válida."})
            else:
                if subtype_code and subtype_code in DEFAULT_SUBTYPE_MASKS:
                    data["input_mask"] = DEFAULT_SUBTYPE_MASKS[subtype_code]
                elif field_type_code in DEFAULT_TYPE_MASKS:
                    data["input_mask"] = DEFAULT_TYPE_MASKS[field_type_code]

        # --- 4. VALIDACIONES DE TIPO ---
        if not field_type_code:
            errors.append({"field": "field_type_code", "message": "El tipo de campo es obligatorio (o use una plantilla)."})
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

        field_type = session.query(LeadFieldType).filter_by(code=field_type_code).first()
        if not field_type:
            errors.append({"field": "field_type_code", "message": f"El tipo '{field_type_code}' no existe."})
        else:
            # SELECTOR y FILE obligan a elegir subtipo explícitamente.
            # El resto de los tipos lo tienen como opcional; DATE usa DATE_ONLY como fallback
            # semántico (no hay "DATE plano").
            if not subtype_code:
                if field_type_code in ["SELECTOR", "FILE"]:
                    errors.append({"field": "field_subtype_code", "message": f"El tipo '{field_type_code}' requiere que seleccione un subtipo explícitamente."})
                elif field_type_code == "DATE":
                    subtype_code = "DATE_ONLY"
                    data["field_subtype_code"] = "DATE_ONLY"

            # Validación estándar si ya tenemos el subtype_code (enviado o auto-asignado)
            if subtype_code:
                valid_subtype = any(s.code == subtype_code for s in field_type.subtypes)
                if not valid_subtype:
                    errors.append({"field": "field_subtype_code", "message": f"El subtipo '{subtype_code}' no es válido para '{field_type_code}'."})

        if nomenclator_id and field_type_code not in NOMENCLATOR_FIELD_TYPES:
            errors.append({"field": "field_type_code", "message": f"Para usar un nomenclador, el tipo debe ser uno de {NOMENCLATOR_FIELD_TYPES}."})

        # Feature de nomencladores dependientes: no hace falta chequeo de ciclo
        # acá — un campo recién creado todavía no es ancestro de nada.
        # depends_on_field_id llega como public_uuid de LeadField; se resuelve acá. Si no
        # resuelve, se pasa None y _validate_depends_on_field ya reporta "no existe" solo
        # (su propio session.query(...).filter_by(id=None) no encuentra nada).
        depends_on_field_uuid = data.get("depends_on_field_id")
        depends_on_field_id = cls.repository.get_internal_id_by_public_uuid(session, depends_on_field_uuid) if depends_on_field_uuid else None
        if depends_on_field_uuid:
            data["depends_on_field_id"] = depends_on_field_id
            cls._validate_depends_on_field(session, campaign_id, nomenclator_id, field_type_code, depends_on_field_id, errors)

        if field_type_code == "LEAD" and not rel_campaign_id:
            errors.append({"field": "related_campaign_id", "message": "Requerido para campos tipo LEAD."})
        elif rel_campaign_id and field_type_code != "LEAD":
            errors.append({"field": "field_type_code", "message": "No puede asignar 'related_campaign_id' si el tipo no es LEAD."})

        # Proteger default_value: no tiene sentido para campos de selección o relacionales
        if data.get("default_value") is not None:
            if field_type_code in NOMENCLATOR_FIELD_TYPES or field_type_code == "LEAD":
                errors.append({"field": "default_value", "message": f"El campo tipo '{field_type_code}' no acepta valor por defecto. Los valores seleccionables se gestionan desde el nomenclador."})
                data.pop("default_value", None)

        if field_type_code == "CALCULATED":
            if not calc_expr:
                errors.append({"field": "calculation_expression", "message": "Requerido para campos CALCULATED."})
            else:
                data["required"] = False
                data["is_primary"] = False
        elif calc_expr:
            errors.append({"field": "field_type_code", "message": "No puede asignar fórmula si el campo no es CALCULATED."})

        # --- 5. VALIDACIONES DE INTEGRIDAD ---
        if not name:
            errors.append({"field": "name", "message": "El nombre del campo es obligatorio."})
        else:
            cls._check_name_uniqueness(session, campaign_id, name, errors=errors)
            cls._maybe_auto_assign_title_order(session, campaign_id, name, data)
            cls._maybe_auto_assign_subtitle_order(session, campaign_id, name, data)

        has_existing_leads = LeadRepository.has_leads_in_campaign(session, campaign_id)
        if has_existing_leads:
            if data.get("required") is True:
                errors.append({"field": "required", "message": "No se puede crear campo 'Required' en campaña con leads existentes."})
            if data.get("is_primary") is True:
                errors.append({"field": "is_primary", "message": "No se puede crear campo 'Primary' en campaña con leads existentes."})

        order = data.get("order")
        if order is None:
            max_order = cls.repository.get_max_order(session, campaign_id)
            data["order"] = max_order + 1
        else:
            cls._check_order_uniqueness(session, campaign_id, order, errors)

        is_vis = data.get("is_visible", True)
        is_req = data.get("required", False)
        is_pri = data.get("is_primary", False)

        if not is_vis:
            if is_req:
                errors.append({"field": "required", "message": "Un campo oculto (is_visible=False) no puede ser obligatorio."})
            if is_pri:
                errors.append({"field": "is_primary", "message": "Un campo oculto no puede marcarse como identificador principal."})

        # --- 6. CHECK FINAL ---
        if errors:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

        # --- 7. PERSISTENCIA ---
        try:
            new_field = cls.repository.create(session, data)
            session.flush()

            # new_field.id es el public_uuid (repository.create() devuelve el schema Pydantic,
            # no el ORM crudo) -- se resuelve acá al id interno antes de usarlo como FK real.
            # Bug real encontrado 2026-07-28 (mismo patrón que organization_service.py,
            # lead_service.py y team_service.py): rompía el backfill de LeadFieldValue y la
            # creación de reglas de validación de plantilla al dar de alta un campo nuevo.
            new_field_internal_id = cls.repository.get_internal_id_by_public_uuid(session, new_field.id)

            if has_existing_leads:
                is_nomenclator = nomenclator_id is not None
                LeadFieldValueRepository.initialize_values_for_new_field(
                    session=session,
                    campaign_id=campaign_id,
                    new_field_id=new_field_internal_id,
                    default_value=new_field.default_value,
                    is_nomenclator=is_nomenclator
                )

            #Reglas de template
            for rule_cfg in rules_to_create:
                rule_payload = rule_cfg.copy()
                rule_payload["field_id"] = new_field_internal_id
                ValidationRuleService.create_within_session(
                    session=session, 
                    obj_data=rule_payload,
                    user_context=user_context,
                    field_type_code=new_field.field_type_code
                )

            if not template_code:
                implicit_rules = DEFAULT_TYPE_RULES.get(field_type_code, []).copy()
                if subtype_code:
                    implicit_rules.extend(DEFAULT_SUBTYPE_RULES.get(subtype_code, []))
                
                for rule_cfg in implicit_rules:
                    rule_payload = rule_cfg.copy()
                    rule_payload["field_id"] = new_field_internal_id
                    origin = subtype_code if rule_cfg in DEFAULT_SUBTYPE_RULES.get(subtype_code, []) else field_type_code
                    rule_payload["name"] = f"Auto-Rule ({origin})" 
                    
                    ValidationRuleService.create_within_session(
                        session=session,
                        obj_data=rule_payload,
                        user_context=user_context,
                        field_type_code=new_field.field_type_code
                    )

            cls._log_audit(session, new_field, action=SystemAuditLogAction.CREATED, changes=data, user_id=user_context.user.id if user_context and user_context.user else None)
            return new_field

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=[{"field": "general", "message": f"Error interno: {str(e)}"}])

    @classmethod
    def create(cls, obj_in, user_context: Optional[UserContext] = None):
        def do_create(uow):
            return cls.create_within_session(uow.session, obj_in, user_context)

        return cls._execute(
            action="Creando Campo de Lead", 
            func=do_create, 
            success_msg="Campo configurado exitosamente."
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    @classmethod
    def update(cls, obj_id: str, obj_in, user_context: Optional[UserContext] = None):
        def do_update(uow):
            errors = []
            # obj_id llega como public_uuid; se resuelve una única vez al id interno,
            # que es lo que siguen esperando cls.repository y los helpers _check_*/_validate_*.
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            current_field = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=False)
            if not current_field: cls._not_found(obj_id)

            data = obj_in.model_dump(exclude_unset=True)

            # 1. Validar Unicidad de Nombre
            new_name = data.get("name")
            if new_name and new_name != current_field.name:
                cls._check_name_uniqueness(uow.session, current_field.campaign_id, new_name, errors, exclude_id=internal_id)

            # 2. Validar Unicidad de Orden
            new_order = data.get("order")
            if new_order is not None and new_order != current_field.order:
                cls._check_order_uniqueness(uow.session, current_field.campaign_id, new_order, errors, exclude_id=internal_id)

            # 3. Validar Restricciones Históricas
            new_required = data.get("required")
            new_primary = data.get("is_primary")
            if (new_required is not None) or (new_primary is not None):
                check_req = new_required if new_required is not None else current_field.required
                check_pri = new_primary if new_primary is not None else current_field.is_primary
                cls._check_historic_constraints(uow.session, current_field, internal_id, check_req, check_pri, errors)

            # --- 4. NUEVA SEGURIDAD: Validar Sección si cambia ---
            # data["lead_field_section_id"] llega como public_uuid de LeadFieldSection (Fase 3,
            # ver backend/AGENTS.md §18); current_field.lead_field_section.id YA es ese mismo
            # uuid (objeto anidado del Response), así que la comparación de arriba es válida
            # directamente. La query de abajo sí necesita el id interno resuelto.
            if "lead_field_section_id" in data and data["lead_field_section_id"] != current_field.lead_field_section.id:
                org_id = user_context.organization_id if user_context else TENANT_ORG_ID.get()
                new_section_id = LeadFieldSectionRepository.get_internal_id_by_public_uuid(uow.session, data["lead_field_section_id"])
                section = uow.session.query(LeadFieldSection).filter(
                    LeadFieldSection.id == new_section_id,
                    LeadFieldSection.organization_id == org_id
                ).first() if new_section_id is not None else None
                if not section:
                    errors.append({"field": "lead_field_section_id", "message": "La sección no existe o no pertenece a su empresa."})
                else:
                    data["lead_field_section_id"] = new_section_id

            # 4b. Validar restricciones de campo CALCULATED
            if current_field.field_type_code == "CALCULATED":
                if data.get("required") is True:
                    errors.append({"field": "required", "message": "Un campo CALCULATED no puede ser obligatorio."})
                if data.get("is_primary") is True:
                    errors.append({"field": "is_primary", "message": "Un campo CALCULATED no puede ser identificador principal."})

            # 4c. Validar combinación is_visible + required/is_primary
            effective_visible = data["is_visible"] if "is_visible" in data else current_field.is_visible
            effective_required = data["required"] if "required" in data else current_field.required
            effective_primary = data["is_primary"] if "is_primary" in data else current_field.is_primary

            if not effective_visible:
                if effective_required:
                    errors.append({"field": "required", "message": "Un campo oculto (is_visible=False) no puede ser obligatorio."})
                if effective_primary:
                    errors.append({"field": "is_primary", "message": "Un campo oculto no puede marcarse como identificador principal."})

            # 5. Validación de cálculo (La estructura nos protege, solo re-evaluamos)
            new_expr = data.get("calculation_expression")
            if new_expr and current_field.field_type_code != "CALCULATED":
                errors.append({"field": "calculation_expression", "message": "Solo campos CALCULATED aceptan fórmulas."})
            if current_field.field_type_code == "CALCULATED" and "calculation_expression" in data:
                if not new_expr:
                    errors.append({"field": "calculation_expression", "message": "No se puede eliminar la expresión de un campo calculado."})

            # 6. Proteger default_value para tipos que no lo soportan
            if "default_value" in data and data["default_value"] is not None:
                field_type_code = current_field.field_type_code
                if field_type_code in NOMENCLATOR_FIELD_TYPES or field_type_code == "LEAD":
                    errors.append({"field": "default_value", "message": f"El campo tipo '{field_type_code}' no acepta valor por defecto. Los valores seleccionables se gestionan desde el nomenclador."})
                    data.pop("default_value", None)

            # 7. Feature de nomencladores dependientes (ver docs/nomencladores.md).
            # No mandar el campo = no tocar. Mandar null = desvincular (no
            # necesita validación). Mandar un id = validar + chequear ciclo.
            if "depends_on_field_id" in data and data["depends_on_field_id"] is not None:
                # data["depends_on_field_id"] llega como public_uuid de LeadField; se resuelve
                # acá porque los helpers de ciclo/validación esperan el id interno.
                new_depends_on = cls.repository.get_internal_id_by_public_uuid(uow.session, data["depends_on_field_id"])
                data["depends_on_field_id"] = new_depends_on
                if new_depends_on is not None and cls._would_create_field_dependency_cycle(uow.session, internal_id, new_depends_on):
                    errors.append({"field": "depends_on_field_id", "message": "Esa dependencia formaría un ciclo entre campos."})
                else:
                    cls._validate_depends_on_field(
                        uow.session, current_field.campaign_id, current_field.nomenclator_id,
                        current_field.field_type_code, new_depends_on, errors, exclude_field_id=internal_id
                    )

            # --- CHECK FINAL ---
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            expression_changed = False
            if current_field.field_type_code == "CALCULATED":
                if new_expr and new_expr != current_field.calculation_expression:
                    expression_changed = True

            changes = {}
            for key, new_val in data.items():
                if key == "lead_field_section_id":
                    old_val = current_field.lead_field_section.id
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}
                elif hasattr(current_field, key):
                    old_val = getattr(current_field, key)
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}

            updated_field = cls.repository.update(uow.session, internal_id, data, user_context=user_context)
            uow.session.flush() 

            if expression_changed:
                cls._recalculate_leads_formula(uow, updated_field)
            
            if changes:
                cls._log_audit(uow.session, updated_field, action=SystemAuditLogAction.UPDATED, changes=changes, user_id=user_context.user.id if user_context else None)

            return updated_field

        return cls._execute(
            action="Actualizando LeadField",
            func=do_update,
            success_msg=f"LeadField({obj_id}) actualizado correctamente."
        )

    # =========================================================================
    # DELETE / DEACTIVATE — bloqueo si hay campos dependientes
    # =========================================================================
    # Feature de nomencladores dependientes (ver docs/nomencladores.md):
    # decisión del usuario, no se puede borrar ni desactivar un campo mientras
    # otro campo activo tenga depends_on_field_id apuntando a él — quedaría
    # una dependencia colgando de un campo inexistente/inactivo. Mismo patrón
    # de UnitOfWork + super() que CampaignService (hallazgo #19).

    @classmethod
    def _assert_no_active_dependents(cls, obj_id: str, user_context: Optional[UserContext], action_label: str):
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            current_field = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context)
            if not current_field:
                cls._not_found(obj_id)
            db_field = uow.session.query(LeadField).filter_by(id=internal_id).first()
            dependents = [f.name for f in db_field.dependent_fields if f.active] if db_field else []
            if dependents:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{
                        "field": "general",
                        "message": f"No se puede {action_label} este campo: dependen de él los campos {', '.join(dependents)}. Desvincúlelos primero."
                    }]
                )

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        cls._assert_no_active_dependents(obj_id, user_context, "eliminar")
        return super().delete(obj_id, user_context=user_context, force=force)

    @classmethod
    def deactivate(cls, obj_id: str, user_context: Optional[UserContext] = None):
        cls._assert_no_active_dependents(obj_id, user_context, "desactivar")
        return super().deactivate(obj_id, user_context=user_context)

    # =========================================================================
    # SET ACTIVE (Reactivar)
    # =========================================================================

    @classmethod
    def set_active(cls, field_id: str, user_context: Optional[UserContext] = None):
        def do_reactivate(uow):
            errors = []

            # field_id llega como public_uuid; se resuelve una vez al id interno.
            internal_id = cls._resolve_id(uow.session, field_id)
            if internal_id is None:
                cls._not_found(field_id)

            # --- 1. SEGURIDAD: Usamos el repositorio para validar acceso (Devuelve Pydantic) ---
            secure_check = cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=False)
            if not secure_check:
                cls._not_found(field_id)

            if secure_check.active:
                return secure_check

            # --- 2. ORM: Buscamos la instancia real de SQLAlchemy para poder modificarla ---
            from app.models.lead_field import LeadField
            field_db = uow.session.query(LeadField).filter_by(id=internal_id).first()

            # 3. Validar Nombre
            cls._check_name_uniqueness(uow.session, field_db.campaign_id, field_db.name, errors, exclude_id=internal_id)
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # 4. Validar Orden (Auto-Fix)
            order_errors = []
            cls._check_order_uniqueness(uow.session, field_db.campaign_id, field_db.order, order_errors, exclude_id=internal_id)

            if order_errors:
                max_order = cls.repository.get_max_order(uow.session, field_db.campaign_id)
                field_db.order = max_order + 1

            was_active = field_db.active
            field_db.updated_by = user_context.user.id if user_context and user_context.user else None
            field_db.active = True

            # No hace falta uow.session.add() porque field_db ya está vinculado a la sesión
            uow.session.flush()

            if not was_active:
                cls._log_audit(
                    uow.session,
                    field_db,
                    action=SystemAuditLogAction.ACTIVATED,
                    changes={"active": {"old": False, "new": True}},
                    user_id=user_context.user.id if user_context and user_context.user else None
                )

            # Retornamos el objeto ya formateado limpiamente por el repositorio
            return cls.repository.get_by_id(uow.session, internal_id, user_context=user_context, detailed=True)

        return cls._execute(
            action="Activando Campo",
            obj_id=field_id,
            func=do_reactivate,
            success_msg=SUCCESS_UPDATE
        )
    

    # -----------------------------------------------------------------------
    # HELPERS PARA RECALCULAR FÓRMULAS MASIVAMENTE
    # -----------------------------------------------------------------------

    #Existe la misma función en lead_service, pero la repetimos aquí para no acoplar servicios. Es un helper específico de campos calculados, no tiene sentido que LeadService lo conozca.
    @classmethod
    def _convert_value_for_context(cls, value, field_def):
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
    def _recalculate_leads_formula(cls, uow, field_def: LeadField):
        """
        Busca todos los leads de la campaña y recalcula el valor de este campo
        específico aplicando la nueva fórmula en masa.
        """
        # 1. Obtener todos los campos de la campaña para tipar correctamente los contextos
        all_fields = cls.repository.get_all_active_with_rules(uow.session, campaign_id=field_def.campaign_id)
        fields_by_id = {f.id: f for f in all_fields}

        # 2. Obtener todos los leads de la campaña con sus valores
        leads = uow.session.query(Lead).options(
            selectinload(Lead.field_values)
        ).filter(Lead.campaign_id == field_def.campaign_id).all()

        for lead in leads:
            # 3. Reconstruir contexto matemático del lead
            context = {}
            for fv in lead.field_values:
                val = fv.value
                if val is None:
                    continue # Nomencladores complejos u otros nulos se ignoran
                
                f_def = fields_by_id.get(fv.field_id)
                if f_def:
                    typed_val = cls._convert_value_for_context(val, f_def)
                    context[f_def.name] = typed_val

            # 4. Evaluar la nueva fórmula
            evaluator = ExcelFormulaEvaluatorService(context=context)
            try:
                new_calc_val = evaluator.evaluate(field_def.calculation_expression)
            except Exception:
                new_calc_val = None # Si la fórmula falla para este lead en específico, asignamos nulo

            # 5. Guardar/Actualizar el valor en la base de datos
            existing_fv = next((fv for fv in lead.field_values if fv.field_id == field_def.id), None)
            
            if existing_fv:
                existing_fv.value = str(new_calc_val) if new_calc_val is not None else None
            else:
                new_fv = LeadFieldValue(
                    lead_id=lead.id, 
                    field_id=field_def.id, 
                    value=str(new_calc_val) if new_calc_val is not None else None
                )
                uow.session.add(new_fv)


    @classmethod
    def reorder(cls, obj_in: LeadFieldOrderList, user_context: Optional[UserContext] = None):
        def do_reorder(uow):
            # obj_in.campaign_id llega como public_uuid (Fase 3, ver backend/AGENTS.md §18);
            # se resuelve acá porque las queries de abajo son crudas.
            campaign_id = cls.campaign_repository.get_internal_id_by_public_uuid(uow.session, obj_in.campaign_id)

            # 1. Validar campaña y acceso
            campaign = cls.campaign_repository.get_by_id(uow.session, campaign_id, user_context=user_context) if campaign_id is not None else None
            if not campaign:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"field": "campaign_id", "message": "Campaña no encontrada o sin acceso."})

            # 2. Obtener TODOS los campos activos de esta campaña
            # Traemos los objetos SQLAlchemy para poder modificarlos
            db_fields = uow.session.query(LeadField).filter(
                LeadField.campaign_id == campaign_id,
                LeadField.active == True
            )
            # Aplicamos el filtro de seguridad del repositorio manualmente si es necesario
            db_fields = cls.repository.apply_security_filter(uow.session, db_fields, user_context).all()

            db_fields_map = {f.id: f for f in db_fields}

            # 3. Mapeo de lo que viene del request. item.field_id llega como public_uuid de
            # LeadField; se resuelve contra los propios db_fields de esta campaña (evita que
            # un uuid válido pero de otra campaña cuele silenciosamente).
            uuid_to_field_id = {f.public_uuid: f.id for f in db_fields}
            incoming_orders = {}
            for item in obj_in.orders:
                resolved_id = uuid_to_field_id.get(item.field_id)
                if resolved_id is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail={"field": "field_id", "message": f"El campo {item.field_id} no pertenece a esta campaña o no está activo."}
                    )
                incoming_orders[resolved_id] = item.order

            # 4. VALIDACIÓN DE INTEGRIDAD: Universo completo
            # Verificamos colisiones entre los que cambian y los que se quedan quietos
            check_duplicate_orders = {}
            for f_id, field_obj in db_fields_map.items():
                # Si viene en el request, usamos el nuevo order, sino el que ya tenía en DB
                target_order = incoming_orders.get(f_id, field_obj.order)
                
                if target_order in check_duplicate_orders:
                    other_name = check_duplicate_orders[target_order]
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, 
                        detail={"field": "order", "message": f"El orden {target_order} se repite entre '{field_obj.name}' y '{other_name}'."}
                    )
                
                check_duplicate_orders[target_order] = field_obj.name

            # 5. ACTUALIZACIÓN FÍSICA
            updated_count = 0
            for f_id, new_order in incoming_orders.items():
                if f_id not in db_fields_map:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST, 
                        detail={"field": "field_id", "message": f"El campo {f_id} no pertenece a esta campaña o no está activo."}
                    )
                
                field_instance = db_fields_map[f_id]
                
                if field_instance.order != new_order:
                    old_val = field_instance.order
                    # Actualización del atributo en la instancia de SQLAlchemy
                    field_instance.order = new_order
                    
                    # Auditoría (Usando el ID del usuario directamente en el log, no en el objeto)
                    cls._log_audit(
                        uow.session, 
                        field_instance, 
                        action=SystemAuditLogAction.UPDATED, 
                        changes={"order": {"old": old_val, "new": new_order}},
                        user_id=user_context.user.id if user_context and user_context.user else None
                    )
                    updated_count += 1
            
            uow.session.flush()
            return {"message": f"Se actualizó el orden de {updated_count} campos.", "campaign_id": campaign_id}

        return cls._execute(
            action="Reordenando campos de Lead",
            func=do_reorder
        )
