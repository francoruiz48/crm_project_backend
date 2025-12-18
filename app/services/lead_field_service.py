from app.models.nomenclator import Nomenclator
from app.services.base_service import BaseService
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.services.nomenclator_service import NomenclatorService
from app.services.validation_rule_service import ValidationRuleService
from app.db.repository.lead_field_repository import LeadFieldRepository
from fastapi import HTTPException

class LeadFieldService(BaseService):
    repository = LeadFieldRepository
    nomenclatorService = NomenclatorService
    
    @classmethod
    def create(cls, obj_in):
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
                
                # Si el usuario NO mandó nombre, usamos el de la plantilla
                if not data.get("name"):
                    data["name"] = template.name

                # Si el usuario NO mandó tipo, usamos el de la plantilla
                if not data.get("field_type_code"):
                    data["field_type_code"] = template.field_type_code

                # Preparamos las reglas para crearlas después
                rules_to_create = template.rules

            elif nomenclator_id:
                # Usamos uow.session para la consulta directa (Más eficiente y seguro)
                nomenclator = uow.session.query(Nomenclator).get(nomenclator_id)
                
                if not nomenclator:
                    raise HTTPException(404, f"El Nomenclador con ID {nomenclator_id} no existe.")

                # Autocompletado
                if not data.get("name"):
                    data["name"] = nomenclator.name
                
                # Los nomencladores siempre se guardan como referencias de texto o códigos
                if not data.get("field_type_code"):
                    data["field_type_code"] = "STRING"

            # -------------------------------------------------------
            # 2. VALIDACIONES DE INTEGRIDAD
            # -------------------------------------------------------
            # Como en el Schema 'name' y 'field_type' son opcionales (para permitir el template),
            # aquí debemos validar manualmente que NO queden vacíos al final.
            
            if not data.get("name"):
                raise HTTPException(400, "El nombre del campo es obligatorio.")

            if not data.get("field_type_code"):
                raise HTTPException(400, "El 'field_type_code' es obligatorio (o usa una plantilla válida).")

            # -------------------------------------------------------
            # 3. CREAR EL LEAD FIELD
            # -------------------------------------------------------
            new_field = cls.repository.create(uow.session, data)
            
            # Flush para obtener el ID del nuevo campo
            uow.session.flush() 

            # -------------------------------------------------------
            # 4. CREAR LAS VALIDACIONES ASOCIADAS
            # -------------------------------------------------------
            for rule_cfg in rules_to_create:
                rule_payload = rule_cfg.copy()
                
                # Vinculamos datos necesarios
                rule_payload["field_id"] = new_field.id
                #rule_payload["entity"] = "leads" 

                # Creamos la regla usando la misma sesión
                ValidationRuleService.create_within_session(uow.session, rule_payload)

            return new_field

        return cls._execute(
            action="Creando Campo de Lead",
            func=do_create,
            success_msg="Campo configurado exitosamente."
        )