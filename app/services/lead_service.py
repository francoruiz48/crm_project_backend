from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.db.repository.lead_repository import LeadRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.unit_of_work import UnitOfWork
from app.services.lead_validation_logic import LeadValidationLogic

class LeadService(BaseService):
    repository = LeadRepository
    field_repository = LeadFieldRepository

    @classmethod
    def _prepare_context_dict(cls, values_in):
        """
        Convierte la lista de entrada en un diccionario {field_id: dato_real}.
        PRIORIDAD: Si viene nomenclator_item_id, se usa eso. Si no, se usa value.
        """
        data = {}
        for v in values_in:
            # Validamos si v es un diccionario o un objeto Pydantic
            if isinstance(v, dict):
                fid = v.get('field_id')
                val_text = v.get('value')
                nom_id = v.get('nomenclator_item_id')
            else:
                # Es un objeto (Pydantic)
                fid = getattr(v, 'field_id', None)
                val_text = getattr(v, 'value', None)
                nom_id = getattr(v, 'nomenclator_item_id', None)

            # LÓGICA CLAVE: Si hay ID de nomenclador, ese es el valor que importa para validar.
            # Ignoramos 'val_text' en este caso para evitar guardar copias hardcodeadas.
            if nom_id is not None:
                data[fid] = nom_id
            else:
                data[fid] = val_text
                
        return data

    @classmethod
    def _validate_data(cls, session, values_in, current_lead_id=None):
        # 1. Obtener definiciones de campos
        field_defs_list = cls.field_repository.get_all_active_with_rules(session)
        all_fields_defs = {f.id: f for f in field_defs_list}

        # 2. Preparar datos entrantes (usando la nueva lógica de prioridad ID)
        incoming_data = cls._prepare_context_dict(values_in)
        
        full_context = incoming_data.copy()

        # 3. Si es update, mezclar con datos existentes de la DB
        if current_lead_id:
            current_lead = cls.repository.get_by_id(session, current_lead_id)
            if current_lead:
                db_values = {}
                for v in current_lead.field_values:
                    # LÓGICA CLAVE DB: Si el registro guardado tiene nomenclator_item_id, 
                    # usamos ese ID. Si no, usamos el value (texto/numérico).
                    if v.nomenclator_item_id is not None:
                        db_values[v.field_id] = v.nomenclator_item_id
                    else:
                        db_values[v.field_id] = v.value
                
                # Los datos entrantes sobrescriben a los de la DB
                full_context = {**db_values, **incoming_data}

        # 4. Iterar y Validar
        for field in field_defs_list:
            value_to_validate = full_context.get(field.id)
            
            try:
                # Nota: LeadValidationLogic debe saber que si el campo es tipo Nomenclador,
                # 'value_to_validate' será un entero (ID), no un string.
                LeadValidationLogic.validate_field(
                    current_field=field,
                    raw_value=value_to_validate,
                    all_values=full_context,
                    all_fields_defs=all_fields_defs
                )

            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )
            
    class ItemProxy:
        def __init__(self, data_dict):
            self._data = data_dict
            # Mágia: Convertimos las claves del dict en atributos (obj.campo)
            for k, v in data_dict.items():
                setattr(self, k, v)
        
        # Cuando el Repo llame a .dict(exclude_unset=True), nosotros ignoramos
        # el flag y devolvemos todo el diccionario completo.
        def dict(self, **kwargs):
            return self._data

    @classmethod
    def _clean_input_for_saving(cls, values_in):
        cleaned_values = []
        for v in values_in:
            # 1. Convertimos el input (sea Pydantic o dict) a un diccionario puro
            if hasattr(v, 'model_dump'): # Pydantic v2
                item_dict = v.model_dump()
            elif hasattr(v, 'dict'): # Pydantic v1
                item_dict = v.dict()
            else:
                item_dict = dict(v)

            # 2. Aplicamos la lógica de negocio (Limpieza)
            nom_id = item_dict.get('nomenclator_item_id')
            
            if nom_id is not None:
                # Si hay ID de nomenclador, forzamos value a None
                item_dict['value'] = None
                # Aseguramos que el ID esté presente en el dict
                item_dict['nomenclator_item_id'] = nom_id
            
            # 3. Envolvemos el dict en el Proxy
            # Esto evita:
            #   a) AttributeError en upsert_children (porque tiene atributos)
            #   b) Que exclude_unset=True borre el campo (porque ItemProxy lo ignora)
            cleaned_values.append(cls.ItemProxy(item_dict))
                
        return cleaned_values

    @classmethod
    def create(cls, obj_in):
        with UnitOfWork() as uow:
            # 1. Validar
            cls._validate_data(uow.session, obj_in.values, current_lead_id=None)
            
            # 2. Limpiar datos (Forzar value=None si hay nomenclator_id)
            clean_values = cls._clean_input_for_saving(obj_in.values)

            # 3. Crear Lead
            lead = cls.repository.create(uow.session)
            
            # 4. Guardar valores
            cls.repository.upsert_values(uow.session, lead.id, clean_values)
            
            return cls.repository.get_by_id(uow.session, lead.id)

    @classmethod
    def update(cls, obj_id: int, obj_in):
        with UnitOfWork() as uow:
            if not cls.repository.get_by_id(uow.session, obj_id):
                cls._not_found(obj_id)

            # 1. Validar fusión
            cls._validate_data(uow.session, obj_in.values, current_lead_id=obj_id)

            # 2. Limpiar datos
            clean_values = cls._clean_input_for_saving(obj_in.values)

            # 3. Guardar
            cls.repository.upsert_values(uow.session, obj_id, clean_values)
            
            return cls.repository.get_by_id(uow.session, obj_id)