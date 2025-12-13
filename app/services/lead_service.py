from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.unit_of_work import UnitOfWork
from app.services.lead_validation_logic import LeadValidationLogic  # El servicio que creamos antes

class LeadService(BaseService):
    repository = LeadRepository
    field_repository = LeadFieldRepository

    @classmethod
    def _prepare_context_dict(cls, values_in):
        """Convierte la lista de entrada en un diccionario {field_id: value}"""
        # Asumiendo que values_in es una lista de Pydantic models o dicts
        data = {}
        for v in values_in:
            # Soportamos acceso por atributo (Pydantic) o por clave (dict)
            fid = getattr(v, 'field_id', None) or v.get('field_id')
            val = getattr(v, 'value', None) or v.get('value')
            data[fid] = val
        return data

    @classmethod
    def _validate_data(cls, session, values_in, current_lead_id=None):
        """
        Orquesta la validación:
        1. Obtiene definiciones de campos y reglas.
        2. Construye el contexto completo de datos (Incoming + Existing).
        3. Ejecuta el LeadValidationLogic.
        """
        # 1. Obtener definiciones de campos (metadata)
        field_defs = cls.field_repository.get_all_active_with_rules(session)

        # 2. Preparar los datos entrantes en formato dict
        incoming_data = cls._prepare_context_dict(values_in)
        
        # 3. Construir el contexto completo (Contexto = Datos BD + Datos Entrantes)
        full_context = incoming_data.copy()
        if current_lead_id:
            # Si es un UPDATE, necesitamos los valores actuales de la BD para 
            # validar reglas cruzadas (ej: si cambio fecha_fin, necesito saber la fecha_inicio actual)
            current_lead = cls.repository.get_by_id(session, current_lead_id)
            if current_lead:
                # Mezclamos: Primero los de BD, luego sobrescribimos con los nuevos
                db_values = {v.field_id: v.value for v in current_lead.field_values}
                full_context = {**db_values, **incoming_data}

        # 4. Iterar y Validar
        for field in field_defs:
            # Obtenemos el valor "final" que tendrá este campo
            value_to_validate = full_context.get(field.id)
            
            # Nota: Si es un UPDATE parcial y el campo no viene en el payload,
            # value_to_validate será el valor viejo (o None). 
            # La lógica de validación debe manejar esto.
            try:
                LeadValidationLogic.validate_field(
                    field=field,
                    raw_value=value_to_validate,
                    all_values=full_context
                )

            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )

    @classmethod
    def create(cls, obj_in):
        with UnitOfWork() as uow:
            # 1. Validar ANTES de crear nada
            cls._validate_data(uow.session, obj_in.values, current_lead_id=None)
            
            # 2. Proceder con la creación
            lead = cls.repository.create(uow.session)
            cls.repository.upsert_values(uow.session, lead.id, obj_in.values)
            
            return cls.repository.get_by_id(uow.session, lead.id)

    @classmethod
    def update(cls, obj_id: int, obj_in):
        with UnitOfWork() as uow:
            # 1. Verificar existencia
            if not cls.repository.get_by_id(uow.session, obj_id):
                cls._not_found(obj_id)

            # 2. Validar fusionando datos actuales con los nuevos
            cls._validate_data(uow.session, obj_in.values, current_lead_id=obj_id)

            # 3. Guardar
            cls.repository.upsert_values(uow.session, obj_id, obj_in.values)
            return cls.repository.get_by_id(uow.session, obj_id)