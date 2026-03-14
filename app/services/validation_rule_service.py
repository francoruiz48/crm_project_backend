from fastapi import HTTPException, status
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
    def _check_expression_syntax(cls, expression: str, errors: list, field_type_code: str = None):
        """
        Valida la sintaxis de la expresión usando el evaluador. 
        Agrega errores a la lista si falla.
        """
        if not expression:
            errors.append({"field": "expression", "message": "La expresión no puede estar vacía."})
            return

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
            
            # Verificar si el evaluador retornó un error de Excel
            if isinstance(result, str) and result.startswith("#ERROR"):
                 errors.append({"field": "expression", "message": f"Sintaxis inválida: {result}"})

        except Exception as e:
             errors.append({"field": "expression", "message": f"Error de tipos en la fórmula: {str(e)}"})

    @classmethod
    def _build_expression_from_template(cls, code: str, params: dict, errors: list) -> str:
        """
        Construye la expresión a partir de un template.
        Valida parámetros requeridos y vacíos. Agrega errores a la lista.
        Retorna None si hay errores.
        """
        template = STANDARD_RULES.get(code)
        if not template:
            errors.append({"field": "template_code", "message": f"El código de plantilla '{code}' no existe."})
            return None
        
        local_error = False
        
        # Validar parámetros requeridos por el template
        for p in template.params:
            # 1. Existencia
            if p not in params:
                errors.append({"field": "template_params", "message": f"Falta el parámetro obligatorio '{p}'."})
                local_error = True
                continue
            
            val = params[p]

            # 2. Contenido (Permitimos 0, rechazamos vacío o None)
            if val is None or (isinstance(val, str) and str(val).strip() == ""):
                errors.append({"field": "template_params", "message": f"El valor del parámetro '{p}' no puede estar vacío."})
                local_error = True
        
        if local_error:
            return None

        try:
            return template.expression_fmt.format(**params)
        except Exception as e:
            errors.append({"field": "template_params", "message": f"Error al generar expresión: {str(e)}"})
            return None

    @classmethod
    def create_within_session(cls, session, obj_data, created_by=None, field_type_code: str = None, errors: list = None):
        """
        Método interno para crear reglas dentro de una transacción mayor.
        Soporta la inyección de una lista 'errors' para acumulación.
        """
        # Si no nos pasan lista externa, usamos una local (modo estricto)
        local_errors_mode = False
        if errors is None:
            errors = []
            local_errors_mode = True

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
            
            if template:
                # Autocompletar datos visuales si faltan
                if not get("name"): set_val("name", template.name)
                
                if not get("error_message"):
                    base_msg = getattr(template, "error_message", None) or f"Error de validación ({template.name})"
                    try:
                        formatted_msg = base_msg.format(**tmpl_params)
                        set_val("error_message", formatted_msg)
                    except Exception:
                        set_val("error_message", base_msg)

            # Generar Expresión (Valida template y params)
            if not expr:
                generated_expr = cls._build_expression_from_template(tmpl_code, tmpl_params, errors)
                if generated_expr:
                    set_val("expression", generated_expr)
                    expr = generated_expr

        # 2. VALIDAR SINTAXIS (Solo si tenemos expresión)
        if expr:
            cls._check_expression_syntax(expr, errors, field_type_code=field_type_code)
        elif not tmpl_code:
             # Si no hay template ni expression, es un error
             errors.append({"field": "expression", "message": "Debe proveer una expresión manual o un código de plantilla."})

        # 3. MANEJO DE ERRORES
        if errors:
            # Si estamos en modo local (llamada interna sin lista), fallamos aquí para proteger integridad
            if local_errors_mode:
                 # Revertimos a excepción simple para no romper contratos antiguos que no esperan listas
                 raise ValidationError(errors[0]['message'], field=errors[0]['field'])
            
            # Si hay lista externa, retornamos None y dejamos que el llamador maneje la lista
            return None

        # 4. CREAR
        new_rule = cls.repository.create(session, obj_data, created_by)
        session.flush()

        # 5. LOG DE AUDITORÍA (Aquí obj_data ya es el dict procesado con exclude_unset=True)
        cls._log_audit(session, new_rule, action="CREATE", changes=obj_data, user_id=created_by)

        return new_rule

    @classmethod
    def create(cls, obj_data, created_by=None):
        """
        Método público (Endpoint).
        """
        def do_create(uow):
            errors = []
            
            if hasattr(obj_data, "model_dump"):
                data = obj_data.model_dump()
            else:
                data = obj_data.copy()

            # --- VALIDACIÓN DE CONTEXTO ---
            field_id = data.get("field_id")
            if not field_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "field_id", "message": "El ID del campo es obligatorio."}])

            # Buscamos el campo padre para contexto y tipo
            lead_field = cls.lead_field_repository.get_by_id(uow.session, field_id)
            if not lead_field:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "field_id", "message": f"El campo {field_id} no existe."}])
            
            # Llamamos a la lógica interna pasando nuestra lista 'errors'
            new_rule = cls.create_within_session(
                uow.session, 
                data, 
                created_by, 
                field_type_code=lead_field.field_type_code, 
                errors=errors
            )

            # Si la lista se llenó, lanzamos el error acumulado
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)
            
            return new_rule

        return cls._execute(
            action="Creando Regla",
            func=do_create,
            success_msg=SUCCESS_CREATE
        )

    @classmethod
    def update(cls, obj_id: int, obj_data, updated_by=None):
        def do_update(uow):
            errors = []
            current_obj = cls.repository.get_by_id(uow.session, obj_id)
            if not current_obj: cls._not_found(obj_id)

            # Convertimos a diccionario usando exclude_unset para saber qué envió realmente el usuario
            if hasattr(obj_data, "model_dump"):
                data = obj_data.model_dump(exclude_unset=True)
            else:
                data = obj_data.copy()

            new_expr = data.get("expression")
            new_tmpl_params = data.get("template_params")

            # ===============================================================
            # 2. Control de Flujo (Manual vs Template)
            # ===============================================================
            if current_obj.template_code:
                # CASO A: Es una regla basada en plantilla
                
                # Bloqueamos el intento de meter una expresión a mano
                if "expression" in data and new_tmpl_params is None:
                     errors.append({
                         "field": "expression",
                         "message": "Esta regla utiliza una plantilla. Modifique los parámetros ('template_params') en lugar de la expresión directa."
                     })
                
                # Si envían nuevos parámetros, regeneramos la expresión
                if new_tmpl_params is not None:
                    generated_expr = cls._build_expression_from_template(current_obj.template_code, new_tmpl_params, errors)
                    if generated_expr:
                        data["expression"] = generated_expr
            else:
                # CASO B: Es una regla manual (sin plantilla)
                
                # Bloqueamos el intento de enviarle parámetros de plantilla
                if "template_params" in data:
                    errors.append({
                        "field": "template_params",
                        "message": "Esta regla es manual y no acepta parámetros de plantilla."
                    })

            # ===============================================================
            # 3. Validar sintaxis final
            # ===============================================================
            final_expr = data.get("expression")
            
            if final_expr:
                # Obtenemos tipo del campo padre para validación precisa
                lead_field = cls.lead_field_repository.get_by_id(uow.session, current_obj.field_id)
                ft_code = lead_field.field_type_code if lead_field else None
                
                cls._check_expression_syntax(final_expr, errors, field_type_code=ft_code)

            # --- Check final ---
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=errors)

            # ARMAMOS EL DIFF PARA LA AUDITORÍA
            changes = {}
            for key, new_val in data.items():
                if hasattr(current_obj, key):
                    old_val = getattr(current_obj, key)
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}

            updated_rule = cls.repository.update(uow.session, obj_id, data, updated_by=updated_by)
            uow.session.flush()

            if changes:
                cls._log_audit(uow.session, updated_rule, action="UPDATE", changes=changes, user_id=updated_by)

            return updated_rule
        
        return cls._execute(
            action="Actualizando Regla",
            obj_id=obj_id,
            func=do_update,
            success_msg=SUCCESS_UPDATE
        )