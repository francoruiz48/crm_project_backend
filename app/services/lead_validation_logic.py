from datetime import date, datetime
from typing import Any, Dict
from app.models.lead_field import LeadField
from app.core.constans import DATE_FORMAT
# IMPORTAMOS EL NUEVO MOTOR
from app.services.excel_formula_evaluator_service import ExcelFormulaEvaluatorService

class LeadValidationLogic:

    @classmethod
    def validate_rules(
        cls, 
        current_field: LeadField, 
        raw_value: Any, 
        all_values: Dict[int, Any], 
        all_fields_defs: Dict[int, LeadField]
    ):
        """
        Ejecuta reglas usando ExcelFormulaEvaluatorService.
        """
        if not current_field.validation_rules:
            return

        # 1. Preparar Contexto Global (Todos los campos por su Nombre)
        # Esto permite reglas cruzadas tipo: "Si Ciudad = 'Madrid', Precio > 100"
        context = {}
        
        # Pre-casteo de todos los valores del lead
        for f_id, f_val in all_values.items():
            f_def = all_fields_defs.get(f_id)
            if f_def:
                # Usamos el nombre del campo como variable (ej: "Edad")
                clean_val = cls._cast_value_for_rules(f_val, f_def.field_type.code)
                context[f_def.name] = clean_val

        # 2. Inyectar el valor del campo actual
        # Permitimos usar "value" o el nombre del campo en la fórmula
        current_val_casted = cls._cast_value_for_rules(raw_value, current_field.field_type.code)
        
        context["value"] = current_val_casted
        context["VALUE"] = current_val_casted # Por si lo escriben en mayúsculas
        # También nos aseguramos de que el propio nombre del campo tenga el valor actual
        context[current_field.name] = current_val_casted

        # 3. Instanciar Evaluador
        evaluator = ExcelFormulaEvaluatorService(context=context)

        # 4. Ejecutar Reglas
        for rule in current_field.validation_rules:
            if hasattr(rule, 'active') and not rule.active:
                continue
            
            # Si el valor es nulo, generalmente saltamos la validación extra, 
            # salvo que la regla sea explícita. (Asumimos 'Required' ya validó nulos).
            if current_val_casted is None:
                continue

            # Evaluamos
            result = evaluator.evaluate(rule.expression)

            # Verificamos errores de sintaxis del motor (devuelve strings con #ERROR)
            if isinstance(result, str) and result.startswith("#ERROR"):
                # Opción: Loguear el error técnico y fallar, o ignorar.
                # Aquí fallamos para avisar que la regla está rota.
                raise ValueError(f"Error técnico en la regla '{rule.name}': {result}")

            # La regla debe devolver TRUE para pasar. Si devuelve False o 0, falla.
            # Nota: En Excel, IF devuelve valores, pero validaciones suelen ser booleanas.
            if not result:
                raise ValueError(rule.error_message or f"El valor '{raw_value}' no cumple la regla: {rule.name}")

    @staticmethod
    def _cast_value_for_rules(value, type_code):
        """
        Convierte valores para que el motor de Excel pueda operar matemáticamente.
        """
        if value is None or value == "":
            return None
        try:
            if type_code == "INT":
                return int(value)
            elif type_code == "NUMBER":
                return float(value)
            elif type_code == "BOOL":
                # Manejo string 'true'/'false'
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "si")
                return bool(value)
            elif type_code == "DATE":
                if isinstance(value, datetime): return value.date() # Si ya es datetime, bajamos a date
                if isinstance(value, date): return value # Si ya es date, ok

                return datetime.strptime(str(value)[:10], DATE_FORMAT).date()
            elif type_code == "DATE_TIME":
                 # El motor soporta datetimes
                 if isinstance(value, str):
                     # Asumiendo ISO o similar
                     if len(value) <= 10: # Si viene solo fecha '2023-01-01'
                         return datetime.strptime(value, DATE_FORMAT)
                     return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                 return value
        except:
            return value 
        return value