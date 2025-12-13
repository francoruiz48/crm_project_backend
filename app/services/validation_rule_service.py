from fastapi import HTTPException, status
from app.core.error_messages import SUCCESS_CREATE, SUCCESS_UPDATE
from app.db.repository.validation_rule_repository import ValidationRuleRepository
from app.services.base_service import BaseService


class ValidationRuleService(BaseService):
    repository = ValidationRuleRepository

    # Helper privado para reutilizar la lógica de validación dentro del UoW
    @classmethod
    def _validate_applicability(cls, session, rule_type_code: str, field_id: int):
        is_compatible = cls.repository.is_rule_type_compatible_with_field(
            session, rule_type_code, field_id
        )
        if not is_compatible:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La regla '{rule_type_code}' no es compatible con el campo ID {field_id}."
            )

    @classmethod
    def create(cls, obj_data):
        # Definimos la función que se ejecutará DENTRO de la transacción (UnitOfWork)
        def do_create(uow):
            # 1. Extraer datos (asumiendo que obj_data es un Pydantic schema o dict)
            # Usamos getattr para seguridad si es objeto, o acceso directo si es dict
            r_code = getattr(obj_data, "rule_type_code", None) or obj_data.get("rule_type_code")
            f_id = getattr(obj_data, "field_id", None) or obj_data.get("field_id")

            # 2. Validar usando la sesión actual del UoW
            cls._validate_applicability(uow.session, r_code, f_id)

            # 3. Crear usando el método del padre/repositorio
            return cls.repository.create(uow.session, obj_data)

        # Ejecutamos usando el wrapper del BaseService
        return cls._execute(
            action="Creando",
            func=do_create,
            success_msg=SUCCESS_CREATE
        )

    @classmethod
    def update(cls, obj_id: int, obj_data):
        def do_update(uow):
            # 1. Obtener los datos a actualizar
            r_code = getattr(obj_data, "rule_type_code", None) or (obj_data.get("rule_type_code") if isinstance(obj_data, dict) else None)
            f_id = getattr(obj_data, "field_id", None) or (obj_data.get("field_id") if isinstance(obj_data, dict) else None)

            # Lógica extra para UPDATE:
            # Si en el update cambian el tipo de regla o el campo, debemos re-validar.
            # Si solo cambian el "value" (ej: cambiar el maximo de 10 a 20), no hace falta revalidar tipos,
            # PERO si envían uno de los dos, necesitamos el otro para validar la paridad.
            
            if r_code or f_id:
                # Caso complejo: Si falta uno de los dos datos en el payload (porque es un PATCH parcial),
                # debemos buscar el registro actual en la BD para completar la validación.
                current_obj = cls.repository.get_by_id(uow.session, obj_id)
                if not current_obj:
                    cls._not_found(obj_id) # Lanza error si no existe
                
                # Usar el nuevo valor si existe, sino el actual de la BD
                code_to_check = r_code if r_code else current_obj.rule_type_code
                id_to_check = f_id if f_id else current_obj.field_id
                
                cls._validate_applicability(uow.session, code_to_check, id_to_check)

            # 2. Proceder al update normal
            return cls.repository.update(uow.session, obj_id, obj_data)

        return cls._execute(
            action="Actualizando",
            obj_id=obj_id,
            func=do_update,
            success_msg=SUCCESS_UPDATE
        )