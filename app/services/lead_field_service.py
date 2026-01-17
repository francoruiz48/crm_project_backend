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

class LeadFieldService(BaseService):
    repository = LeadFieldRepository
    nomenclatorService = NomenclatorService
    
    # =========================================================================
    # HELPERS DE VALIDACIÓN
    # =========================================================================

    @classmethod
    def _validate_name_uniqueness(cls, session, campaign_id: int, name: str, exclude_id: int = None):
        """
        Verifica que no exista otro campo ACTIVO con el mismo nombre en la campaña.
        Si exclude_id se provee (update/reactivate), ignora ese ID.
        """

        existing = cls.repository.get_all(session=session, only_active=True, detailed=True, campaign_id=campaign_id, name=name)
        
        if existing:
            # Si encontramos uno y NO es el mismo que estamos editando/activando
            if exclude_id is None or existing[0].id != exclude_id:
                raise ValidationError(f"Ya existe un campo activo con el mismo en esta campaña.", "name")

    @classmethod
    def _validate_order_uniqueness(cls, session, campaign_id: int, order: int, exclude_id: int = None):
        """
        Verifica que el número de orden no esté ocupado.
        """
        # Buscamos si existe algun campo con ese order y campaign_id
        # Nota: Necesitarás asegurarte que tu repo tenga un método similar o usar query directa
        collision = cls.repository.get_all(session=session, only_active=True, detailed=True, campaign_id=campaign_id, order=order)
        
        if collision:
            if exclude_id is None or collision[0].id != exclude_id:
                raise ValidationError(f"El número de orden {order} ya está ocupado por el campo {collision[0].name}.", "order")

    @classmethod
    def _validate_historic_constraints(cls, session, field: LeadField, new_required: bool, new_primary: bool):
        """
        Valida que los cambios no rompan la integridad de datos existentes (Leads).
        """
        # A. Validación de REQUIRED retroactivo
        if new_required is True and not field.required:
            has_nulls = session.query(LeadFieldValue).filter(
                LeadFieldValue.field_id == field.id,
                (LeadFieldValue.value == None) | (LeadFieldValue.value == "")
            ).first()

            if has_nulls:
                raise ValidationError("No se puede marcar como requerido porque existen registros antiguos con valor vacío.", "required")

        # B. Validación de PRIMARY retroactivo
        if new_primary is True and not field.is_primary:
            has_leads = LeadRepository.has_leads_in_campaign(session, field.campaign_id)
            if has_leads:
                raise ValidationError("No se puede marcar como 'Primary' porque ya existen Leads en esta campaña (no se garantiza unicidad retroactiva).", "is_primary")


    @classmethod
    def create(cls, obj_in, created_by=None):
        def do_create(uow):

            try:
                data = obj_in.model_dump(exclude_unset=True)

                template_code = data.get("field_template_code")
                field_type_code = data.get("field_type_code")
                subtype_code = data.get("field_subtype_code")
                nomenclator_id = data.get("nomenclator_id")
                calc_expr = data.get("calculation_expression")

                if nomenclator_id:
                    if field_type_code:
                        if field_type_code not in NOMENCLATOR_FIELD_TYPES:
                            raise ValidationError(
                                f"Debe corresponder a las opciones {NOMENCLATOR_FIELD_TYPES} cuando se especifica 'nomenclator_id'.", "field_type_code"
                            )
                    else:
                        raise ValidationError(
                            "Si especificas 'nomenclator_id', el 'field_type_code' debe ser uno de {NOMENCLATOR_FIELD_TYPES}.", "field_type_code"
                        )
                
                if field_type_code == "LEAD":
                    if not data.get("related_campaign_id"):
                        raise ValidationError("El campo es obligatorio.", "related_campaign_id")
                else:
                    if data.get("related_campaign_id"):
                        raise ValidationError("Si especifica 'related_campaign_id' entonces 'field_type_code' debe ser LEAD.", "field_type_code")

                if field_type_code:
                    field_type = uow.session.query(LeadFieldType).filter_by(code=field_type_code).first()
                    
                    if not field_type:
                        raise ValidationError(f"El tipo '{field_type_code}' no existe.", "field_type_code")

                    # 2. Verificamos si tiene subtipos asociados en la BD
                    has_subtypes = len(field_type.subtypes) > 0

                    # 3. Regla: Si tiene subtipos en BD, es obligatorio elegir uno
                    if has_subtypes and not subtype_code:
                        raise ValidationError(
                            f"El campo es obligatorio.", "field_subtype_code"
                        )
                    
                    # 4. Validar coherencia si envió un subtipo
                    if subtype_code:
                        # Verifica que el subtipo exista y pertenezca al padre
                        valid_subtype = any(s.code == subtype_code for s in field_type.subtypes)
                        if not valid_subtype:
                            raise ValidationError(f"El subtipo '{subtype_code}' no es válido para '{field_type_code}'.", "field_subtype_code")


                rules_to_create = []

                # -------------------------------------------------------
                # 1. LÓGICA DE PLANTILLA (Si existe)
                # -------------------------------------------------------
                if template_code:
                    template = STANDARD_FIELD_TEMPLATES.get(template_code)
                    if not template:
                        raise ValidationError(f"La plantilla '{template_code}' no existe.", "field_template_code")
                    
                    if not data.get("name"):
                        data["name"] = template.name

                    data["field_type_code"] = template.field_type_code

                    # Preparamos las reglas para crearlas después
                    rules_to_create = template.rules

                elif nomenclator_id:
                    # Usamos uow.session para la consulta directa
                    nomenclator = uow.session.query(Nomenclator).get(nomenclator_id)
                    
                    if not nomenclator:
                        raise ValidationError(f"El Nomenclador con ID {nomenclator_id} no existe.", "nomenclator_id")

                    if not data.get("name"):
                        data["name"] = nomenclator.name
                
                if field_type_code == "CALCULATED":
                    if not calc_expr:
                        raise ValidationError("Los campos de tipo 'CALCULATED' requieren una expresión de cálculo ('calculation_expression').", "calculation_expression")
                    else:
                        #Establecemos que no sea requerido para que luego no nos pida el dato al ser calculado.
                        data["required"] = False
                        data["is_primary"] = False
                else:
                    if calc_expr:
                         raise ValidationError("No se puede asignar una expresión de cálculo a un campo que no sea 'CALCULATED'.", "field_type_code")

                # -------------------------------------------------------
                # 2. VALIDACIONES DE INTEGRIDAD (Básicas)
                # -------------------------------------------------------
                if not data.get("name"): raise ValidationError("El nombre del campo es obligatorio.", "name")

                if not data.get("field_type_code"): raise ValidationError("El campo es obligatorio (o usa una plantilla válida).", "field_type_code")

                name = data.get("name")
                campaign_id = data.get("campaign_id")
                
                # 1. Validar Nombre Único
                if name and campaign_id:
                    cls._validate_name_uniqueness(uow.session, campaign_id, name)
                
                # 2. Validar Restricciones si hay Leads (Required / Primary)
                has_existing_leads = False
                if campaign_id:
                    has_existing_leads = LeadRepository.has_leads_in_campaign(uow.session, campaign_id)
                
                if has_existing_leads:
                    if data.get("required") is True: raise ValidationError("No se puede crear Required con Leads existentes.", "required")
                    if data.get("is_primary") is True: raise ValidationError("No se puede crear Primary con Leads existentes.", "is_primary")


                # 3. Validar Orden
                order = data.get("order")
                if order is None:
                    max_order = cls.repository.get_max_order(uow.session, campaign_id)
                    data["order"] = max_order + 1
                else:
                    # Usamos el helper
                    cls._validate_order_uniqueness(uow.session, campaign_id, order)

            except ValidationError as ve:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail={"message": ve.message, "field": ve.field}
                )
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al intentar validar el campo del lead. Detalle: " + str(e))
    

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
                    
                    ValidationRuleService.create_within_session(
                        session=uow.session, 
                        obj_data=rule_payload, 
                        created_by=created_by,
                        field_type_code=new_field.field_type_code 
                    )

                return new_field
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno al intentar crear el campo del lead. Detalle: " + str(e))
                
        return cls._execute(
            action="Creando Campo de Lead",
            func=do_create,
            success_msg="Campo configurado exitosamente."
        )
    

    @classmethod
    def update(cls, obj_id: int, obj_in):
        """
        Sobrescribimos update para validar cambios ilegales (Tipo de dato y Required retroactivo).
        """
        def do_update(uow):
            current_field = cls.repository.get_by_id(uow.session, obj_id, detailed=False)
            if not current_field: cls._not_found(obj_id)

            data = obj_in.model_dump(exclude_unset=True)

            try:
                # 1. Inmutabilidad de Tipo
                new_type = data.get("field_type_code")
                if new_type and new_type != current_field.field_type_code:
                    raise ValidationError("No se puede cambiar el tipo de dato de un campo existente.", "field_type_code")

                # 2. Validar Unicidad de Nombre (Si cambió)
                new_name = data.get("name")
                if new_name and new_name != current_field.name:
                    cls._validate_name_uniqueness(uow.session, current_field.campaign_id, new_name, exclude_id=obj_id)

                # 3. Validar Unicidad de Orden (Si cambió)
                new_order = data.get("order")
                if new_order is not None and new_order != current_field.order:
                    cls._validate_order_uniqueness(uow.session, current_field.campaign_id, new_order, exclude_id=obj_id)

                # 4. Validar Restricciones Históricas (Required / Primary)
                new_required = data.get("required")
                new_primary = data.get("is_primary")
                
                # Solo validamos si vienen en el payload y son True (o diferentes al actual)
                if (new_required is not None) or (new_primary is not None):
                     # Preparamos los valores finales para pasar al validador
                     check_req = new_required if new_required is not None else current_field.required
                     check_pri = new_primary if new_primary is not None else current_field.is_primary
                     
                     cls._validate_historic_constraints(uow.session, current_field, check_req, check_pri)

                if not "related_campaign_id" in data and current_field.related_campaign is not None:
                    raise ValidationError("El campo es obligatorio.", "related_campaign_id")

                if "related_campaign_id" in data:
                    new_rel_id = data["related_campaign_id"]
                    old_rel_id = current_field.related_campaign.id
                    
                    if new_rel_id != old_rel_id:
                        
                        # A. Prohibido dejar null un campo tipo LEAD
                        if new_rel_id is None and current_field.field_type_code == "LEAD":
                            raise ValidationError("El campo es obligatorio.", "related_campaign_id")

                        # B. Verificar si hay datos existentes (Integridad)
                        # Buscamos si existe al menos UN valor de lead asociado a este campo.
                        # Si existe, significa que hay leads "usando" esta configuración.
                        has_data = uow.session.query(LeadFieldValue).filter(
                            LeadFieldValue.field_id == obj_id
                        ).first()

                        if has_data:
                            raise ValidationError(
                                f"No se puede cambiar la campaña relacionada (de {old_rel_id} a {new_rel_id}) "
                                "porque ya existen leads con datos/asociaciones en este campo.", "related_campaign_id"
                            )

                # 5. Validación de calculo
                new_expr = data.get("calculation_expression")
                
                # Caso 1: Intentan poner fórmula a un campo que NO es calculado
                if new_expr and current_field.field_type_code != "CALCULATED":
                    raise ValidationError("No se puede asignar una expresión de cálculo a este campo porque no es de tipo 'CALCULATED'.", "calculation_expression")

                # Caso 2: Es calculado y le quieren borrar la fórmula (enviando string vacío o None explícito)
                # Nota: 'calculation_expression' en DB es nullable, pero por regla de negocio no queremos calculados rotos.
                if current_field.field_type_code == "CALCULATED" and "calculation_expression" in data:
                    if not new_expr: # Si es None o ""
                        raise ValidationError("No se puede eliminar la expresión de un campo 'CALCULATED'.", "calculation_expression")

            except ValidationError as ve:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail={"message": ve.message, "field": ve.field}
                )

            return cls.repository.update(uow.session, obj_id, data)

        return cls._execute(
            action="Actualizando LeadField",
            func=do_update,
            success_msg=f"LeadField({obj_id}) actualizado correctamente."
        )
    

    @classmethod
    def set_active(cls, field_id: int):
        """
        Reactiva un campo eliminado. 
        Maneja colisiones de Nombre (Error) y colisiones de Orden (Auto-fix).
        """
        def do_reactivate(uow):
            # Usar .get() de SQLAlchemy para evitar filtros automáticos de soft-delete si tu repo los tiene
            field = uow.session.get(LeadField, field_id)
            
            if not field:
                cls._not_found(field_id)
            
            if field.active:
                return field

            try:
                # 1. Validar Nombre: Si el nombre está ocupado, NO podemos reactivar.
                cls._validate_name_uniqueness(uow.session, field.campaign_id, field.name, exclude_id=field_id)
                
                # 2. Validar Orden: 
                # Estrategia: Si el orden antiguo está ocupado, NO fallamos. 
                # Simplemente lo movemos al final de la lista. Es mejor UX que obligar al usuario a reordenar todo.
                try:
                    cls._validate_order_uniqueness(uow.session, field.campaign_id, field.order, exclude_id=field_id)
                except ValidationError:
                    # Conflicto de orden detectado -> Asignar nuevo orden al final
                    max_order = cls.repository.get_max_order(uow.session, field.campaign_id)
                    field.order = max_order + 1
                    # (Opcional) Podrías agregar un log o warning aquí indicando que el orden cambió.

            except ValidationError as ve:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail={"message": ve.message, "field": ve.field}
                )

            field.active = True
            uow.session.add(field)
            return field

        return cls._execute(
            action="Activando Campo",
            obj_id=field_id,
            func=do_reactivate,
            success_msg=SUCCESS_UPDATE
        )