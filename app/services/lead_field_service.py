from fastapi import HTTPException, status
from app.core.exceptions.exceptions import ValidationError
from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.nomenclator_service import NomenclatorService
from app.services.validation_rule_service import ValidationRuleService
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository
from app.models.lead_field_type import LeadFieldType
from app.core.constans import DEFAULT_PAGE_SIZE, NOMENCLATOR_FIELD_TYPES
from app.models.lead_field_value import LeadFieldValue
from app.core.error_messages import SUCCESS_UPDATE
from app.models.lead_field import LeadField
from app.db.repository.campaign_repository import CampaignRepository
from app.core.templates.field_rules_map import DEFAULT_SUBTYPE_RULES, DEFAULT_TYPE_RULES
from sqlalchemy.orm import selectinload
from app.models.lead import Lead
from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
from datetime import date, datetime
from app.core.constans import DATE_FORMAT, DATE_TIME_FORMAT

class LeadFieldService(BaseService):
    repository = LeadFieldRepository
    nomenclatorService = NomenclatorService
    campaign_repository = CampaignRepository
    
    # =========================================================================
    # HELPERS DE VALIDACIÓN (CHECKERS)
    # =========================================================================

    @classmethod
    def _check_name_uniqueness(cls, session, campaign_id: int, name: str, errors: list, exclude_id: int = None):
        """
        Verifica duplicados de nombre. Agrega error a la lista si falla.
        """
        if not name: return 
        existing = cls.repository.get_all(session=session, only_active=True, detailed=True, campaign_id=campaign_id, name=name)
        
        if existing:
            if exclude_id is None or existing[0].id != exclude_id:
                errors.append({"field": "name", "message": "Ya existe un campo activo con este nombre en la campaña."})

    @classmethod
    def _check_order_uniqueness(cls, session, campaign_id: int, order: int, errors: list, exclude_id: int = None):
        """
        Verifica colisión de orden. Agrega error a la lista si falla.
        """
        if order is None: return
        collision = cls.repository.get_all(session=session, only_active=True, detailed=True, campaign_id=campaign_id, order=order)
        
        if collision:
            if exclude_id is None or collision[0].id != exclude_id:
                errors.append({"field": "order", "message": f"El orden {order} ya está ocupado por el campo '{collision[0].name}'."})

    @classmethod
    def _check_historic_constraints(cls, session, field: LeadField, new_required: bool, new_primary: bool, errors: list):
        """
        Valida integridad histórica. Agrega errores a la lista.
        """
        # A. Validación de REQUIRED retroactivo
        if new_required is True and not field.required:
            has_nulls = session.query(LeadFieldValue).filter(
                LeadFieldValue.field_id == field.id,
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
    # CREATE
    # =========================================================================

    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):
            errors = []
            
            data = obj_in.model_dump(exclude_unset=True)

            # --- 1. VALIDACIÓN DE CONTEXTO (Bloqueante) ---
            campaign_id = data.get("campaign_id")
            if not campaign_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "El ID de campaña es obligatorio."}])

            campaign = cls.campaign_repository.get_by_id(uow.session, campaign_id)
            if not campaign:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": f"La campaña {campaign_id} no existe."}])
        

            # --- 2. EXTRACCIÓN DE DATOS ---
            template_code = data.get("field_template_code")
            field_type_code = data.get("field_type_code")
            subtype_code = data.get("field_subtype_code")
            nomenclator_id = data.get("nomenclator_id")
            calc_expr = data.get("calculation_expression")
            name = data.get("name")

            # --- 3. LÓGICA DE TEMPLATE (Pre-llenado) ---
            rules_to_create = []
            if template_code:
                template = STANDARD_FIELD_TEMPLATES.get(template_code)
                if not template:
                    errors.append({"field": "field_template_code", "message": f"La plantilla '{template_code}' no existe."})
                else:
                    if not name:
                        data["name"] = template.name
                        name = template.name # Actualizar variable local
                    
                    # Sobrescribimos el tipo con el del template
                    data["field_type_code"] = template.field_type_code
                    data["field_template_name"] = template.name
                    field_type_code = template.field_type_code
                    rules_to_create = template.rules

            elif nomenclator_id:
                # Si viene de nomenclador y no tiene nombre, usamos el del nomenclador
                nomenclator = uow.session.query(Nomenclator).get(nomenclator_id)
                if not nomenclator:
                    errors.append({"field": "nomenclator_id", "message": f"El Nomenclador {nomenclator_id} no existe."})
                elif not name:
                    data["name"] = nomenclator.name
                    name = nomenclator.name

            # --- 4. VALIDACIONES DE TIPO (Acumulativas) ---
            
            # 4.1 Existencia de Type Code
            if not field_type_code:
                errors.append({"field": "field_type_code", "message": "El tipo de campo es obligatorio (o use una plantilla)."})
                # Si no hay tipo, muchas validaciones subsiguientes fallarán o no tienen sentido.
                # Cortamos aquí si es crítico, o continuamos con cuidado. 
                # Para robustez, cortamos si no hay tipo base.
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            field_type = uow.session.query(LeadFieldType).filter_by(code=field_type_code).first()
            if not field_type:
                errors.append({"field": "field_type_code", "message": f"El tipo '{field_type_code}' no existe."})
            else:
                # Validar Subtipos
                has_subtypes = len(field_type.subtypes) > 0
                if has_subtypes and not subtype_code:
                    errors.append({"field": "field_subtype_code", "message": "Este tipo de campo requiere un subtipo."})
                
                if subtype_code:
                    valid_subtype = any(s.code == subtype_code for s in field_type.subtypes)
                    if not valid_subtype:
                        errors.append({"field": "field_subtype_code", "message": f"El subtipo '{subtype_code}' no es válido para '{field_type_code}'."})

            # 4.2 Lógica Nomenclador
            if nomenclator_id:
                if field_type_code not in NOMENCLATOR_FIELD_TYPES:
                    errors.append({"field": "field_type_code", "message": f"Para usar un nomenclador, el tipo debe ser uno de {NOMENCLATOR_FIELD_TYPES}."})
            
            # 4.3 Lógica LEAD
            if field_type_code == "LEAD":
                if not data.get("related_campaign_id"):
                    errors.append({"field": "related_campaign_id", "message": "Requerido para campos tipo LEAD."})
            else:
                if data.get("related_campaign_id"):
                    errors.append({"field": "field_type_code", "message": "No puede asignar 'related_campaign_id' si el tipo no es LEAD."})

            # 4.4 Lógica CALCULATED
            if field_type_code == "CALCULATED":
                if not calc_expr:
                    errors.append({"field": "calculation_expression", "message": "Requerido para campos CALCULATED."})
                else:
                    data["required"] = False
                    data["is_primary"] = False
            else:
                if calc_expr:
                    errors.append({"field": "field_type_code", "message": "No puede asignar fórmula si el campo no es CALCULATED."})

            # --- 5. VALIDACIONES DE INTEGRIDAD ---
            
            if not name:
                errors.append({"field": "name", "message": "El nombre del campo es obligatorio."})
            else:
                cls._check_name_uniqueness(uow.session, campaign_id, name, errors)

            # Validar constraints con leads existentes
            has_existing_leads = LeadRepository.has_leads_in_campaign(uow.session, campaign_id)
            if has_existing_leads:
                if data.get("required") is True:
                    errors.append({"field": "required", "message": "No se puede crear campo 'Required' en campaña con leads existentes."})
                if data.get("is_primary") is True:
                    errors.append({"field": "is_primary", "message": "No se puede crear campo 'Primary' en campaña con leads existentes."})

            # Validar Orden
            order = data.get("order")
            if order is None:
                max_order = cls.repository.get_max_order(uow.session, campaign_id)
                data["order"] = max_order + 1
            else:
                cls._check_order_uniqueness(uow.session, campaign_id, order, errors)

            # --- 6. CHECK FINAL ---
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # --- 7. PERSISTENCIA ---
            try:
                new_field = cls.repository.create(uow.session, data, created_by)
                uow.session.flush()

                # Backfill
                if has_existing_leads:
                    is_nomenclator = nomenclator_id is not None
                    LeadFieldValueRepository.initialize_values_for_new_field(
                        session=uow.session,
                        campaign_id=campaign_id,
                        new_field_id=new_field.id,
                        default_value=new_field.default_value,
                        is_nomenclator=is_nomenclator
                    )

                # Reglas de Template
                for rule_cfg in rules_to_create:
                    rule_payload = rule_cfg.copy()
                    rule_payload["field_id"] = new_field.id
                    ValidationRuleService.create_within_session(
                        session=uow.session, 
                        obj_data=rule_payload,
                        created_by=created_by,
                        field_type_code=new_field.field_type_code
                    )

                # Reglas Implícitas (Si no es template)
                if not template_code:
                    implicit_rules = DEFAULT_TYPE_RULES.get(field_type_code, []).copy()
                    if subtype_code:
                        implicit_rules.extend(DEFAULT_SUBTYPE_RULES.get(subtype_code, []))
                    
                    for rule_cfg in implicit_rules:
                        rule_payload = rule_cfg.copy()
                        rule_payload["field_id"] = new_field.id
                        origin = subtype_code if rule_cfg in DEFAULT_SUBTYPE_RULES.get(subtype_code, []) else field_type_code
                        rule_payload["name"] = f"Auto-Rule ({origin})" 
                        
                        ValidationRuleService.create_within_session(
                            session=uow.session,
                            obj_data=rule_payload,
                            created_by=created_by,
                            field_type_code=new_field.field_type_code
                        )

                return new_field

            except Exception as e:
                # Error interno de base de datos no controlado
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=[{"field": "general", "message": f"Error interno: {str(e)}"}])

        return cls._execute(
            action="Creando Campo de Lead",
            func=do_create,
            success_msg="Campo configurado exitosamente."
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    @classmethod
    def update(cls, obj_id: int, obj_in):
        def do_update(uow):
            errors = []
            current_field = cls.repository.get_by_id(uow.session, obj_id, detailed=False)
            if not current_field: cls._not_found(obj_id)

            data = obj_in.model_dump(exclude_unset=True)

            # 1. Inmutabilidad de Tipo
            new_type = data.get("field_type_code")
            if new_type and new_type != current_field.field_type_code:
                errors.append({"field": "field_type_code", "message": "No se puede cambiar el tipo de dato de un campo existente."})

            # Inmutabilidad de Plantilla (Template)
            if "field_template_code" in data:
                if data["field_template_code"] != current_field.field_template_code:
                    errors.append({
                        "field": "field_template_code", 
                        "message": "No se puede modificar ni asignar una plantilla a un campo ya creado."
                    })

            # 2. Validar Unicidad de Nombre
            new_name = data.get("name")
            if new_name and new_name != current_field.name:
                cls._check_name_uniqueness(uow.session, current_field.campaign_id, new_name, errors, exclude_id=obj_id)

            # 3. Validar Unicidad de Orden
            new_order = data.get("order")
            if new_order is not None and new_order != current_field.order:
                cls._check_order_uniqueness(uow.session, current_field.campaign_id, new_order, errors, exclude_id=obj_id)

            # 4. Validar Restricciones Históricas
            new_required = data.get("required")
            new_primary = data.get("is_primary")
            
            if (new_required is not None) or (new_primary is not None):
                check_req = new_required if new_required is not None else current_field.required
                check_pri = new_primary if new_primary is not None else current_field.is_primary
                cls._check_historic_constraints(uow.session, current_field, check_req, check_pri, errors)

            # 5. Validación LEAD relacionado
            if not "related_campaign_id" in data and current_field.related_campaign is not None:
                if "related_campaign_id" in data and data["related_campaign_id"] is None:
                     errors.append({"field": "related_campaign_id", "message": "El campo es obligatorio para tipo LEAD."})

            if "related_campaign_id" in data:
                new_rel_id = data["related_campaign_id"]
                old_rel_id = current_field.related_campaign.id if current_field.related_campaign else None
                
                if new_rel_id != old_rel_id:
                    if new_rel_id is None and current_field.field_type_code == "LEAD":
                        errors.append({"field": "related_campaign_id", "message": "El campo es obligatorio."})

                    has_data = uow.session.query(LeadFieldValue).filter(
                        LeadFieldValue.field_id == obj_id
                    ).first()

                    if has_data:
                        errors.append({"field": "related_campaign_id", "message": "No se puede cambiar la campaña relacionada porque ya existen leads con datos."})

            # 6. Validación de cálculo
            new_expr = data.get("calculation_expression")
            
            if new_expr and current_field.field_type_code != "CALCULATED":
                errors.append({"field": "calculation_expression", "message": "Solo campos CALCULATED aceptan fórmulas."})

            if current_field.field_type_code == "CALCULATED" and "calculation_expression" in data:
                if not new_expr:
                    errors.append({"field": "calculation_expression", "message": "No se puede eliminar la expresión de un campo calculado."})

            # --- CHECK FINAL ---
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            #Detectamos cambio en formula y recalculamos campos CALCULATED afectados
            expression_changed = False
            if current_field.field_type_code == "CALCULATED":
                if new_expr and new_expr != current_field.calculation_expression:
                    expression_changed = True

            updated_field = cls.repository.update(uow.session, obj_id, data)

            if expression_changed:
                cls._recalculate_leads_formula(uow, updated_field)
            # ===============================================================

            return updated_field

        return cls._execute(
            action="Actualizando LeadField",
            func=do_update,
            success_msg=f"LeadField({obj_id}) actualizado correctamente."
        )

    # =========================================================================
    # SET ACTIVE (Reactivar)
    # =========================================================================

    @classmethod
    def set_active(cls, field_id: int):
        def do_reactivate(uow):
            errors = []
            field = uow.session.get(LeadField, field_id)
            if not field: cls._not_found(field_id)
            if field.active: return field

            # 1. Validar Nombre
            cls._check_name_uniqueness(uow.session, field.campaign_id, field.name, errors, exclude_id=field_id)
            
            # Si hay error de nombre, fallamos aquí mismo
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # 2. Validar Orden (Auto-Fix)
            # Aquí usamos el checker pero controlamos nosotros el error para no fallar
            order_errors = []
            cls._check_order_uniqueness(uow.session, field.campaign_id, field.order, order_errors, exclude_id=field_id)
            
            if order_errors:
                # Conflicto detectado -> Auto-fix
                max_order = cls.repository.get_max_order(uow.session, field.campaign_id)
                field.order = max_order + 1

            field.active = True
            uow.session.add(field)
            return field

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