from fastapi import HTTPException, status
from app.core.error_messages import SUCCESS_CREATE, SUCCESS_UPDATE
from app.core.templates.rule_templates import STANDARD_RULES
from app.db.repository.validation_rule_repository import ValidationRuleRepository
from app.services.base_service import BaseService
from simpleeval import SimpleEval
from datetime import datetime

class ValidationRuleService(BaseService):
    repository = ValidationRuleRepository
        
    @classmethod
    def _validate_expression_syntax(cls, expression: str):
        if not expression:
            raise HTTPException(400, "La expresión no puede estar vacía.")

        # Variables dummy
        dummy_names = {
            "value": 1,
            "related": 1,
            "today": datetime.now(),
            "now": datetime.now(),
        }

        # Funciones dummy
        dummy_functions = {
            "len": len,
            "sum": sum,
            "abs": abs,
            "str": str
        }
        
        try:
            SimpleEval(names=dummy_names, functions=dummy_functions).eval(expression)
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
    def _build_expression_from_template(cls, code: str, params: dict) -> str:
        """
        Convierte (TEMPLATE, PARAMS) -> EXPRESSION STRING
        """
        template = STANDARD_RULES.get(code)
        if not template:
            raise HTTPException(400, f"El código de plantilla '{code}' no existe.")
        
        # Validar que vengan todos los parámetros necesarios
        for p in template.params:
            if p not in params:
                raise HTTPException(400, f"Falta el parámetro '{p}' para la plantilla '{code}'.")
        
        try:
            # Rellenamos el string. Ej: "value >= {limit}" -> "value >= 18"
            return template.expression_fmt.format(**params)
        except Exception as e:
            raise HTTPException(400, f"Error al generar expresión de plantilla: {str(e)}")

    @classmethod
    def create(cls, obj_data):
        def do_create(uow):
            # Helper robusto para obtener valores (soporta dict y objeto Pydantic)
            def get(k):
                if isinstance(obj_data, dict):
                    return obj_data.get(k)
                return getattr(obj_data, k, None)

            # Helper robusto para setear valores
            def set_val(k, v):
                if isinstance(obj_data, dict):
                    obj_data[k] = v
                else:
                    setattr(obj_data, k, v)

            expr = get("expression")
            tmpl_code = get("template_code")
            tmpl_params = get("template_params") or {}

            # --- LÓGICA DE PRE-LLENADO (NOMBRE Y MENSAJE) ---
            if tmpl_code:
                template = STANDARD_RULES.get(tmpl_code)
                if template:
                    # 1. Si el usuario no mandó nombre, usamos el del template
                    if not get("name"):
                        set_val("name", template.name)
                    
                    # 2. Si el usuario no mandó mensaje de error, usamos el del template formateado
                    if not get("error_message"):
                        # Intentamos obtener el mensaje base, fallback al nombre si no existe
                        base_msg = getattr(template, "error_message", None) or f"Error de validación ({template.name})"
                        
                        try:
                            # Intentamos formatear con los params (ej: "Minimo {min}")
                            formatted_msg = base_msg.format(**tmpl_params)
                            set_val("error_message", formatted_msg)
                        except Exception:
                            # Si falla el formateo (ej: faltan params), usamos el base
                            set_val("error_message", base_msg)
            # -----------------------------------------------

            # --- LÓGICA DE GENERACIÓN DE EXPRESIÓN ---
            if not expr and tmpl_code:
                # Generamos la expresión automáticamente
                expr = cls._build_expression_from_template(tmpl_code, tmpl_params)
                
                # Inyectamos la expresión generada en los datos a guardar
                set_val("expression", expr)
            # ---------------------------

            # Validar sintaxis (siempre, por seguridad)
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
            # 1. Obtener el objeto actual de la BD (Necesario para saber el estado previo)
            current_obj = cls.repository.get_by_id(uow.session, obj_id)
            if not current_obj:
                cls._not_found(obj_id)

            # Helper para extraer datos (soporta Dict y Pydantic)
            get = lambda k: getattr(obj_data, k, None) or (isinstance(obj_data, dict) and obj_data.get(k))

            # Datos entrantes
            new_expr = get("expression")
            new_tmpl_code = get("template_code")
            new_tmpl_params = get("template_params")

            # --- LÓGICA DE ACTUALIZACIÓN ---
            
            # ESCENARIO A: El usuario está actualizando el Template o sus Parámetros
            # (Ej: Cambió el valor mínimo de 18 a 21)
            if new_tmpl_code or new_tmpl_params:
                # Determinamos el código y params finales (mezclando nuevos con actuales)
                final_code = new_tmpl_code if new_tmpl_code is not None else current_obj.template_code
                
                # Para los params, si vienen nuevos, reemplazamos. Si no, usamos los viejos.
                final_params = new_tmpl_params if new_tmpl_params is not None else current_obj.template_params or {}

                if final_code:
                    # Regeneramos la expresión
                    generated_expr = cls._build_expression_from_template(final_code, final_params)
                    
                    # Actualizamos el payload
                    if isinstance(obj_data, dict):
                        obj_data["expression"] = generated_expr
                    else:
                        obj_data.expression = generated_expr
                    
                    # Importante: Asegurarnos que se guarden los nuevos params
                    # (Si obj_data es Pydantic, setear atributos; si es dict, setear claves)
                    # Aquí asumo que obj_data ya trae los nuevos valores si vinieron en el request.

            # ESCENARIO B: El usuario envió una 'expression' manual explícita
            # (Ej: Pasó de usar un template a escribir "value * 2 > 10")
            elif new_expr is not None:
                # Si escribe una expresión manual, debemos "desvincular" el template
                # para que el Frontend no intente mostrar el formulario de template incorrecto.
                if isinstance(obj_data, dict):
                    obj_data["template_code"] = None
                    obj_data["template_params"] = None
                else:
                    obj_data.template_code = None
                    obj_data.template_params = None

            # -------------------------------

            # 2. Validar sintaxis final (sea generada o manual)
            # Obtenemos la expresión final que se va a guardar
            final_expr_to_check = getattr(obj_data, "expression", None) or (isinstance(obj_data, dict) and obj_data.get("expression"))
            
            # Si no vino expresión nueva, usamos la de la BD para validar (o saltamos si confiamos en la BD)
            if final_expr_to_check:
                cls._validate_expression_syntax(final_expr_to_check)

            # 3. Guardar cambios
            return cls.repository.update(uow.session, obj_id, obj_data)

        return cls._execute(
            action="Actualizando Regla",
            obj_id=obj_id,
            func=do_update,
            success_msg=SUCCESS_UPDATE
        )