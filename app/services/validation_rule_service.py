from app.core.error_messages import SUCCESS_CREATE, SUCCESS_UPDATE
from app.core.templates.rule_templates import STANDARD_RULES
from app.db.repository.validation_rule_repository import ValidationRuleRepository
from app.services.base_service import BaseService
from datetime import date, datetime
from app.core.exceptions.exceptions import ValidationError
from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService
from app.db.repository.lead_field_repository import LeadFieldRepository

class ValidationRuleService(BaseService):
    repository = ValidationRuleRepository
    lead_field_repository = LeadFieldRepository
    
    @classmethod
    def _get_dummy_value_for_type(cls, field_type_code: str):
        if not field_type_code: return 10
        code = field_type_code.upper()
        if code == "DATE": return date.today()
        elif code == "DATE_TIME": return datetime.now()
        elif code in ("STRING", "TEXT", "CHAR", "EMAIL"): return "dummy_text"
        elif code == "BOOL": return True
        else: return 10

    @classmethod
    def _validate_expression_syntax(cls, expression: str, field_type_code: str = None):
        if not expression:
            raise ValidationError("La expresión no puede estar vacía.", field="expression")

        dummy_val = cls._get_dummy_value_for_type(field_type_code)

        dummy_context = {
            "value": dummy_val, 
            "VALUE": dummy_val,
            "Edad": 18, 
            "Nombre": "Test",
            "Monto": 100.50,
            "Fecha": datetime.now()
        }

        evaluator = ExcelFormulaEvaluatorService(context=dummy_context)
        
        try:
            result = evaluator.evaluate(expression)
        except Exception as e:
             raise ValidationError(f"Error de tipos en la fórmula: {str(e)}", field="expression")

        if isinstance(result, str) and result.startswith("#ERROR"):
             raise ValidationError(f"Sintaxis inválida: {result}", field="expression")

    @classmethod
    def _build_expression_from_template(cls, code: str, params: dict) -> str:
        template = STANDARD_RULES.get(code)
        if not template:
            raise ValidationError(f"El código de plantilla '{code}' no existe.", field="template_code")
        
        # Validar parámetros requeridos por el template
        for p in template.params:
            # 1. Validar existencia de la clave
            if p not in params:
                raise ValidationError(f"Falta el parámetro obligatorio '{p}'.", field="template_params")
            
            val = params[p]

            # 2. Validar que no sea vacío
            # Permitimos el 0 (integer/float) y False, por eso no usamos "if not val"
            if val is None or (isinstance(val, str) and str(val).strip() == ""):
                raise ValidationError(f"El valor del parámetro '{p}' no puede estar vacío.", field="template_params")
        
        try:
            # Convertimos params a string para el format, o dejamos que python lo maneje
            return template.expression_fmt.format(**params)
        except Exception as e:
            raise ValidationError(f"Error al generar expresión con los parámetros dados: {str(e)}", field="template_params")

    @classmethod
    def create_within_session(cls, session, obj_data, created_by=None, field_type_code: str = None):
        # Helpers
        def get(k): return obj_data.get(k) if isinstance(obj_data, dict) else getattr(obj_data, k, None)
        def set_val(k, v): 
            if isinstance(obj_data, dict): obj_data[k] = v
            else: setattr(obj_data, k, v)

        expr = get("expression")
        tmpl_code = get("template_code")
        tmpl_params = get("template_params") or {}


        # 1. LÓGICA DE PLANTILLA
        if tmpl_code:
            template = STANDARD_RULES.get(tmpl_code)
            if not template:
                 raise ValidationError(f"El template '{tmpl_code}' no existe.", field="template_code")

            # Autocompletar datos visuales si faltan
            if not get("name"): set_val("name", template.name)
            
            if not get("error_message"):
                base_msg = getattr(template, "error_message", None) or f"Error de validación ({template.name})"
                try:
                    formatted_msg = base_msg.format(**tmpl_params)
                    set_val("error_message", formatted_msg)
                except Exception:
                    set_val("error_message", base_msg)

            # Generar Expresión
            if not expr:
                # Este método ya lanza ValidationError con el field correcto si falla
                generated_expr = cls._build_expression_from_template(tmpl_code, tmpl_params)
                set_val("expression", generated_expr)
                expr = generated_expr

        # 2. VALIDAR SINTAXIS
        # También lanza ValidationError sobre 'expression' si falla
        cls._validate_expression_syntax(expr, field_type_code=field_type_code)


        # 3. CREAR
        return cls.repository.create(session, obj_data, created_by)

    @classmethod
    def create(cls, obj_data, created_by=None):
        """
        Método público para crear reglas sueltas (Endpoint).
        """
        def do_create(uow):
            if hasattr(obj_data, "model_dump"):
                data = obj_data.model_dump()
            else:
                data = obj_data.copy()

            # --- INFERENCIA DE CONTEXTO ---
            field_id = data.get("field_id")
            if not field_id:
                raise ValidationError("El ID del campo es obligatorio.", field="field_id")

            # Buscamos el campo padre
            lead_field = cls.lead_field_repository.get_by_id(uow.session, field_id)
            if not lead_field:
                raise ValidationError(f"El campo {field_id} no existe.", field="field_id")
            
            # 2. Inyectamos la organización en el diccionario local 'data'
            data['organization_id'] = lead_field.organization_id
            
            # Obtenemos el tipo de dato para validar mejor la sintaxis
            ft_code = lead_field.field_type_code
            
            # 3. Llamamos a la lógica interna pasando 'data' (que ya tiene el ID)
            return cls.create_within_session(uow.session, data, created_by, field_type_code=ft_code)

        return cls._execute(
            action="Creando Regla",
            func=do_create,
            success_msg=SUCCESS_CREATE
        )

    @classmethod
    def update(cls, obj_id: int, obj_data):
        def do_update(uow):
            current_obj = cls.repository.get_by_id(uow.session, obj_id)
            if not current_obj: cls._not_found(obj_id)

            get = lambda k: getattr(obj_data, k, None) or (isinstance(obj_data, dict) and obj_data.get(k))
            
            def set_val(k, v):
                if isinstance(obj_data, dict): obj_data[k] = v
                else: setattr(obj_data, k, v)

            new_expr = get("expression")
            new_tmpl_code = get("template_code")
            new_tmpl_params = get("template_params")

            # --- Actualización Template ---
            if new_tmpl_code or new_tmpl_params:
                final_code = new_tmpl_code if new_tmpl_code is not None else current_obj.template_code
                final_params = new_tmpl_params if new_tmpl_params is not None else current_obj.template_params or {}

                if final_code:
                    generated_expr = cls._build_expression_from_template(final_code, final_params)
                    set_val("expression", generated_expr)
            
            # --- Edición Manual ---
            elif new_expr is not None:
                set_val("template_code", None)
                set_val("template_params", None)

            # 2. Validar sintaxis final
            # Ojo: get("expression") ahora trae el valor actualizado por el bloque anterior
            final_expr = get("expression")
            
            if final_expr:
                cls._validate_expression_syntax(final_expr)

            return cls.repository.update(uow.session, obj_id, obj_data)

        return cls._execute(
            action="Actualizando Regla",
            obj_id=obj_id,
            func=do_update,
            success_msg=SUCCESS_UPDATE
        )