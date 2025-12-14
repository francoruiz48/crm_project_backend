from fastapi import HTTPException, status
from app.core.error_messages import SUCCESS_CREATE, SUCCESS_UPDATE
from app.db.repository.validation_rule_repository import ValidationRuleRepository
from app.services.base_service import BaseService
from simpleeval import SimpleEval
from datetime import datetime

class ValidationRuleService(BaseService):
    repository = ValidationRuleRepository
        
    @classmethod
    def _validate_expression_syntax(cls, expression: str):
        """
        Prueba si la expresión es sintácticamente válida para el motor SimpleEval.
        """
        if not expression:
            raise HTTPException(400, "La expresión no puede estar vacía.")

        # Contexto dummy para probar que la fórmula 'compile'
        dummy_context = {
            "value": 1,           # Asumimos número por defecto (lo más común)
            "related": 1,         # Dummy por si usa comparaciones
            "today": datetime.now(), 
            "now": datetime.now(),
            "len": len,
        }
        
        try:
            # Solo evaluamos sintaxis. No nos importa el resultado (True/False) aquí.
            SimpleEval(names=dummy_context).eval(expression)
        except SyntaxError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Error de sintaxis en la expresión. Verifica paréntesis y operadores."
            )
        except Exception:
            # Si falla por TypeError (ej: len(1)), es aceptable en esta etapa 
            # porque en runtime 'value' podría ser un string.
            # Lo importante es que SimpleEval no haya lanzado error de parseo.
            pass

    @classmethod
    def create(cls, obj_data):
        def do_create(uow):
            # 1. Extraer la expresión
            expr = getattr(obj_data, "expression", None) or obj_data.get("expression")

            # 2. Validar sintaxis (Obligatorio)
            cls._validate_expression_syntax(expr)

            # 3. Crear (Ya no hay validaciones de tipos ni unicidad compleja)
            return cls.repository.create(uow.session, obj_data)

        return cls._execute(
            action="Creando Regla",
            func=do_create,
            success_msg=SUCCESS_CREATE
        )

    @classmethod
    def update(cls, obj_id: int, obj_data):
        def do_update(uow):
            # Extracción segura
            get = lambda k: getattr(obj_data, k, None) or (obj_data.get(k) if isinstance(obj_data, dict) else None)
            
            new_expr = get("expression")

            # 1. Si están intentando cambiar la fórmula, validamos la nueva sintaxis
            if new_expr is not None:
                 cls._validate_expression_syntax(new_expr)

            # 2. Actualizar directo
            # Nota: Ya no necesitamos chequear field_id vs rule_type_code porque
            # la lógica de negocio ahora es puramente dinámica.
            return cls.repository.update(uow.session, obj_id, obj_data)

        return cls._execute(
            action="Actualizando Regla",
            obj_id=obj_id,
            func=do_update,
            success_msg=SUCCESS_UPDATE
        )