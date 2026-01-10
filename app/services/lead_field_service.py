from fastapi import HTTPException, status
from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.nomenclator_service import NomenclatorService
from app.services.validation_rule_service import ValidationRuleService
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository # <--- IMPORTANTE
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository
from app.models.lead_field_type import LeadFieldType # <--- IMPORTANTE

class LeadFieldService(BaseService):
    repository = LeadFieldRepository
    nomenclatorService = NomenclatorService
    
    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):

            try:
                data = obj_in.model_dump(exclude_unset=True)
                
                template_code = data.get("field_template_code")
                type_code = data.get("field_type_code")
                subtype_code = data.get("field_subtype_code")
                nomenclator_id = data.get("nomenclator_id")

                if nomenclator_id:
                    if not type_code:
                        data["field_type_code"] = "NOMENCLATOR"
                        type_code = "NOMENCLATOR"
                    elif type_code != "NOMENCLATOR":
                        raise ValueError(
                            "Si especificas 'nomenclator_id', el 'field_type_code' debe ser 'NOMENCLATOR'."
                        )

                if type_code:
                    field_type = uow.session.query(LeadFieldType).filter_by(code=type_code).first()
                    
                    if not field_type:
                        raise ValueError(f"El tipo '{type_code}' no existe.")

                    # 2. Verificamos si tiene subtipos asociados en la BD
                    has_subtypes = len(field_type.subtypes) > 0

                    # 3. Regla: Si tiene subtipos en BD, es obligatorio elegir uno
                    if has_subtypes and not subtype_code:
                        raise ValueError(
                            f"El tipo '{type_code}' requiere especificar un subtipo (field_subtype_code)."
                        )
                    
                    # 4. Validar coherencia si envió un subtipo
                    if subtype_code:
                        # Verifica que el subtipo exista y pertenezca al padre
                        valid_subtype = any(s.code == subtype_code for s in field_type.subtypes)
                        if not valid_subtype:
                            raise ValueError(f"El subtipo '{subtype_code}' no es válido para '{type_code}'.")


                rules_to_create = []

                # -------------------------------------------------------
                # 1. LÓGICA DE PLANTILLA (Si existe)
                # -------------------------------------------------------
                if template_code:
                    template = STANDARD_FIELD_TEMPLATES.get(template_code)
                    if not template:
                        raise ValueError(f"La plantilla '{template_code}' no existe.")
                    
                    if not data.get("name"):
                        data["name"] = template.name

                    if not data.get("field_type_code"):
                        data["field_type_code"] = template.field_type_code

                    # Preparamos las reglas para crearlas después
                    rules_to_create = template.rules

                elif nomenclator_id:
                    # Usamos uow.session para la consulta directa
                    nomenclator = uow.session.query(Nomenclator).get(nomenclator_id)
                    
                    if not nomenclator:
                        raise ValueError(f"El Nomenclador con ID {nomenclator_id} no existe.")

                    if not data.get("name"):
                        data["name"] = nomenclator.name
                    
                    if not data.get("field_type_code"):
                        # Generalmente un nomenclador se referencia como entero (ID) o string, 
                        # mantenemos tu lógica de default a STRING si no se especifica.
                        data["field_type_code"] = "STRING"


                # -------------------------------------------------------
                # 2. VALIDACIONES DE INTEGRIDAD (Básicas)
                # -------------------------------------------------------
                if not data.get("name"):
                    raise ValueError("El nombre del campo es obligatorio.")

                if not data.get("field_type_code"):
                    raise ValueError("El 'field_type_code' es obligatorio (o usa una plantilla válida).")

                # -------------------------------------------------------
                # 3. RESTRICCIONES HISTÓRICAS
                # -------------------------------------------------------
                # Verificamos si ya hay leads en la campaña ANTES de crear el campo
                campaign_id = data.get("campaign_id")
                has_existing_leads = False
                
                if campaign_id:
                    has_existing_leads = LeadRepository.has_leads_in_campaign(uow.session, campaign_id)

                if has_existing_leads:
                    # Regla: No se puede agregar Required en campaña con datos
                    if data.get("required") is True:
                        raise ValueError(
                            "No se puede crear un campo 'Required' porque ya existen Leads en esta campaña (no se puede garantizar cumplimiento retroactivo)."
                        )
                    
                    # Regla: No se puede agregar Primary en campaña con datos
                    if data.get("is_primary") is True:
                        raise ValueError(
                            "No se puede crear un campo 'Primary' porque ya existen Leads en esta campaña (no se puede garantizar unicidad retroactiva)."
                        )

                order = data.get("order")
                if order is None:
                    # Caso A: Automático (al final de la lista)
                    max_order = cls.repository.get_max_order(uow.session, campaign_id)
                    data["order"] = max_order + 1
                else:
                    # Caso B: Manual (validar colisión)
                    if cls.repository.order_exists(uow.session, campaign_id, order):
                        raise ValueError(
                            f"El número de orden {order} ya está ocupado por otro campo en esta campaña."
                        )
            except ValueError as ve:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al intentar validar el campo del lead.")
    

            try:
                # -------------------------------------------------------
                # 4. CREAR EL LEAD FIELD
                # -------------------------------------------------------
                new_field = cls.repository.create(uow.session, data, created_by)
                
                # Flush para obtener el ID del nuevo campo necesario para el backfill y reglas
                uow.session.flush()

                # -------------------------------------------------------
                # 5. RELLENO (BACKFILL)
                # -------------------------------------------------------
                if has_existing_leads:
                    # Determinamos si es un campo de nomenclador para saber dónde guardar el default
                    is_nomenclator = nomenclator_id is not None
                    
                    # Ejecutamos el INSERT masivo
                    LeadFieldValueRepository.initialize_values_for_new_field(
                        session=uow.session,
                        campaign_id=campaign_id,
                        new_field_id=new_field.id,
                        default_value=new_field.default_value,
                        is_nomenclator=is_nomenclator
                    )

                # -------------------------------------------------------
                # 6. CREAR LAS VALIDACIONES ASOCIADAS (Template)
                # -------------------------------------------------------
                for rule_cfg in rules_to_create:
                    rule_payload = rule_cfg.copy()
                    rule_payload["field_id"] = new_field.id
                    ValidationRuleService.create_within_session(uow.session, rule_payload, created_by)

                return new_field
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al intentar crear el campo del lead.")
                
        return cls._execute(
            action="Creando Campo de Lead",
            func=do_create,
            success_msg="Campo configurado exitosamente."
        )