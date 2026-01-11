import re
from fastapi import HTTPException, status
from app.core.error_messages import SUCCESS_CREATE, SUCCESS_UPDATE
from app.core.templates.rule_templates import STANDARD_RULES
from app.db.repository.validation_rule_repository import ValidationRuleRepository
from app.services.base_service import BaseService
from simpleeval import SimpleEval
from datetime import datetime

from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService

class ValidationRuleService(BaseService):
    repository = ValidationRuleRepository
    
    @classmethod
    def _validate_expression_syntax(cls, expression: str):
        if not expression:
            raise HTTPException(400, "La expresión no puede estar vacía.")

        # Contexto Dummy para probar la fórmula
        dummy_context = {
            "value": 10,       # Simulamos un número
            "VALUE": 10,
            "Edad": 18,        # Simulamos otros campos
            "Nombre": "Test",
            "Monto": 100.50
        }

        evaluator = ExcelFormulaEvaluatorService(context=dummy_context)
        
        # Ejecutamos "en seco"
        result = evaluator.evaluate(expression)

        # El motor devuelve strings "#ERROR: ..." si falla
        if isinstance(result, str) and result.startswith("#ERROR"):
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Sintaxis inválida para fórmula Excel: {result}"
            )

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
    def create_within_session(cls, session, obj_data, created_by=None):
        """
        Lógica pura de negocio. 
        Toma los datos de entrada, aplica la plantilla si existe, y prepara el objeto final.
        """
        # --- HELPERS (Para soportar tanto Dict como Pydantic Model) ---
        def get(k):
            if isinstance(obj_data, dict): return obj_data.get(k)
            return getattr(obj_data, k, None)

        def set_val(k, v):
            if isinstance(obj_data, dict): obj_data[k] = v
            else: setattr(obj_data, k, v)
        # -------------------------------------------------------------

        expr = get("expression")
        tmpl_code = get("template_code")
        tmpl_params = get("template_params") or {}

        # 1. SI SE USA PLANTILLA: Generar los datos derivados
        if tmpl_code:
            template = STANDARD_RULES.get(tmpl_code)
            if not template:
                 raise HTTPException(400, f"El template '{tmpl_code}' no existe.")

            # A. Autocompletar NOMBRE (si no viene definido por el usuario)
            if not get("name"):
                set_val("name", template.name)
            
            # B. Autocompletar MENSAJE DE ERROR (si no viene definido)
            if not get("error_message"):
                # Obtenemos el mensaje base del template
                base_msg = getattr(template, "error_message", None) or f"Error de validación ({template.name})"
                try:
                    # Intentamos inyectar los parámetros en el mensaje (ej: "Mínimo {min}")
                    formatted_msg = base_msg.format(**tmpl_params)
                    set_val("error_message", formatted_msg)
                except Exception:
                    # Si falla el formato (ej: params incompletos en el mensaje), usamos el base
                    set_val("error_message", base_msg)

            # C. Generar la EXPRESIÓN MATEMÁTICA (si no viene manual)
            if not expr:
                generated_expr = cls._build_expression_from_template(tmpl_code, tmpl_params)
                set_val("expression", generated_expr)
                # Actualizamos la variable local para la validación siguiente
                expr = generated_expr

        # 2. VALIDAR SINTAXIS (Siempre, sea manual o generada)
        cls._validate_expression_syntax(expr)

        # 3. CREAR EN BD (Usando la sesión compartida)
        return cls.repository.create(session, obj_data, created_by)

    @classmethod
    def create(cls, obj_data, created_by=None):
        # Wrapper público que inicia la transacción
        def do_create(uow):
            return cls.create_within_session(uow.session, obj_data, created_by)

        return cls._execute(
            action="Creando Regla",
            func=do_create,
            success_msg=SUCCESS_CREATE
        )

    @classmethod
    def update(cls, obj_id: int, obj_data):
        def do_update(uow):
            # 1. Obtener estado previo
            current_obj = cls.repository.get_by_id(uow.session, obj_id)
            if not current_obj:
                cls._not_found(obj_id)

            # Helpers de acceso
            get = lambda k: getattr(obj_data, k, None) or (isinstance(obj_data, dict) and obj_data.get(k))
            
            # Helper para modificar el obj_data entrante
            def set_val(k, v):
                if isinstance(obj_data, dict): obj_data[k] = v
                else: setattr(obj_data, k, v)

            # Datos entrantes
            new_expr = get("expression")
            new_tmpl_code = get("template_code")
            new_tmpl_params = get("template_params")

            # --- ESCENARIO A: Actualización de Parámetros del Template ---
            # (El usuario cambia el 'min' de 18 a 21, pero sigue usando el template)
            if new_tmpl_code or new_tmpl_params:
                final_code = new_tmpl_code if new_tmpl_code is not None else current_obj.template_code
                final_params = new_tmpl_params if new_tmpl_params is not None else current_obj.template_params or {}

                if final_code:
                    # Regeneramos la expresión basada en los nuevos params
                    generated_expr = cls._build_expression_from_template(final_code, final_params)
                    set_val("expression", generated_expr)
            
            # --- ESCENARIO B: Edición Manual de la Expresión ("Eject") ---
            # (El usuario escribe una fórmula a mano, rompiendo el vínculo con el template)
            elif new_expr is not None:
                # Borramos la referencia al template para evitar confusión en el UI
                set_val("template_code", None)
                set_val("template_params", None)

            # -----------------------------------------------------------

            # 2. Validar sintaxis final
            final_expr = get("expression")
            if final_expr:
                cls._validate_expression_syntax(final_expr)

            # 3. Guardar cambios
            return cls.repository.update(uow.session, obj_id, obj_data)

        return cls._execute(
            action="Actualizando Regla",
            obj_id=obj_id,
            func=do_update,
            success_msg=SUCCESS_UPDATE
        )