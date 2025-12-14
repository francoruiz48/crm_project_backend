from datetime import datetime
import re
from typing import Any, Dict, List
from simpleeval import SimpleEval, NameNotDefined
from app.models.lead_field import LeadField

class LeadValidationLogic:


    @classmethod
    def validate_field(
        cls, 
        current_field: LeadField, 
        raw_value: Any, 
        all_values: Dict[int, Any], 
        all_fields_defs: Dict[int, LeadField]
    ):
        # ... (código previo de validación 'required' y casting igual que antes) ...
        
        # 1. Casteamos el valor actual
        value = cls._cast_value(raw_value, current_field.field_type.code)

        # 2. PREPARACIÓN DE CONTEXTO
        typed_fields = {}
        for f_id, f_val in all_values.items():
            f_def = all_fields_defs.get(f_id)
            if f_def:
                typed_fields[f_id] = cls._cast_value(f_val, f_def.field_type.code)
            else:
                typed_fields[f_id] = f_val

        def regex_match_helper(pattern, text):
            if text is None: return False
            return bool(re.search(pattern, str(text)))
        
        # Definimos las FUNCIONES permitidas
        allowed_functions = {
            "len": len,
            "sum": sum,
            "abs": abs,
            "str": str,
            "regex_match": regex_match_helper
        }

        for rule in current_field.validation_rules:
            # Definimos las VARIABLES (Datos)
            context_names = {
                "value": value,          
                "fields": typed_fields, 
                "today": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                "now": datetime.now(),
            }

            try:
                if value is None and "required" not in rule.expression.lower():
                    continue

                # EVALUACIÓN: Pasamos 'names' y 'functions' por separado
                is_valid = SimpleEval(
                    names=context_names, 
                    functions=allowed_functions
                ).eval(rule.expression)

                if not is_valid:
                    raise ValueError(rule.error_message)

            except NameNotDefined as e:
                # ... (resto de tus excepts igual) ...
                raise ValueError(f"Variable desconocida en regla: {e}")
            except Exception as e:
                 raise ValueError(f"Error en regla '{rule.name}': {str(e)}")

    @staticmethod
    def _cast_value(value, type_code):
        """Convierte inputs a tipos Python reales."""
        if value is None or value == "":
            return None
        try:
            if type_code == "INT":
                return int(value)
            elif type_code == "NUMBER":
                return float(value)
            elif type_code == "BOOL":
                return str(value).lower() == "true"
            elif type_code == "DATE":
                # Asegúrate que el formato coincida con tu frontend
                return datetime.strptime(str(value), "%Y-%m-%d")
        except:
            return str(value) # Fallback
        return str(value)