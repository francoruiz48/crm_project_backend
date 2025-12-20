from fastapi import HTTPException, status
from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.nomenclator_service import NomenclatorService
from app.services.validation_rule_service import ValidationRuleService
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.lead_repository import LeadRepository # <--- IMPORTANTE
from app.db.repository.lead_field_value_repository import LeadFieldValueRepository # <--- IMPORTANTE

class LeadFieldService(BaseService):
    repository = LeadFieldRepository
    nomenclatorService = NomenclatorService
    
    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):
            # Convertimos a dict excluyendo nulos
            data = obj_in.dict(exclude_unset=True)
            
            template_code = data.get("field_template_code")
            nomenclator_id = data.get("nomenclator_id")
            rules_to_create = []

            # -------------------------------------------------------
            # 1. LÓGICA DE PLANTILLA (Si existe)
            # -------------------------------------------------------
            if template_code:
                template = STANDARD_FIELD_TEMPLATES.get(template_code)
                if not template:
                    raise HTTPException(400, f"La plantilla '{template_code}' no existe.")
                
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
                    raise HTTPException(404, f"El Nomenclador con ID {nomenclator_id} no existe.")

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
                raise HTTPException(400, "El nombre del campo es obligatorio.")

            if not data.get("field_type_code"):
                raise HTTPException(400, "El 'field_type_code' es obligatorio (o usa una plantilla válida).")

            # -------------------------------------------------------
            # 3. NUEVA LÓGICA: RESTRICCIONES HISTÓRICAS
            # -------------------------------------------------------
            # Verificamos si ya hay leads en la campaña ANTES de crear el campo
            campaign_id = data.get("campaign_id")
            has_existing_leads = False
            
            if campaign_id:
                has_existing_leads = LeadRepository.has_leads_in_campaign(uow.session, campaign_id)

            if has_existing_leads:
                # Regla: No se puede agregar Required en campaña con datos
                if data.get("required") is True:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No se puede crear un campo 'Requerido' porque ya existen Leads en esta campaña (inconsistencia de datos históricos)."
                    )
                
                # Regla: No se puede agregar Primary en campaña con datos
                if data.get("is_primary") is True:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No se puede crear un campo 'Primary' porque ya existen Leads en esta campaña (no se puede garantizar unicidad retroactiva)."
                    )

            # -------------------------------------------------------
            # 4. CREAR EL LEAD FIELD
            # -------------------------------------------------------
            new_field = cls.repository.create(uow.session, data, created_by)
            
            # Flush para obtener el ID del nuevo campo necesario para el backfill y reglas
            uow.session.flush() 

            # -------------------------------------------------------
            # 5. NUEVA LÓGICA: RELLENO (BACKFILL)
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

        return cls._execute(
            action="Creando Campo de Lead",
            func=do_create,
            success_msg="Campo configurado exitosamente."
        )