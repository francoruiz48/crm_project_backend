from datetime import datetime
import re
from typing import Any, Dict
from simpleeval import SimpleEval, NameNotDefined
from app.models.lead_field import LeadField

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
        Ejecuta SOLAMENTE las reglas dinámicas (validation_rules) usando SimpleEval.
        Asume que 'raw_value' ya pasó las validaciones básicas de tipo y requerimiento.
        """
        # Si no hay reglas, salimos rápido
        if not current_field.validation_rules:
            return

        # 1. Casteamos el valor actual para que las reglas funcionen (ej: value > 10)
        value = cls._cast_value_for_rules(raw_value, current_field.field_type.code)

        # 2. PREPARACIÓN DE CONTEXTO (Variables disponibles para las reglas)
        typed_fields = {}
        for f_id, f_val in all_values.items():
            f_def = all_fields_defs.get(f_id)
            if f_def:
                typed_fields[f_id] = cls._cast_value_for_rules(f_val, f_def.field_type.code)
            else:
                typed_fields[f_id] = f_val

        def regex_match_helper(pattern, text):
            if text is None: return False
            return bool(re.search(pattern, str(text)))
        
        # Funciones permitidas en las reglas
        allowed_functions = {
            "len": len,
            "sum": sum,
            "abs": abs,
            "str": str,
            "regex_match": regex_match_helper
        }

        # Variables disponibles
        context_names = {
            "value": value,          
            "fields": typed_fields, 
            "today": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            "now": datetime.now(),
        }

        # 3. EJECUCIÓN DE REGLAS
        for rule in current_field.validation_rules:
            try:
                # Si el valor es nulo y la regla no menciona "required", solemos saltarla.
                # Pero como la validación de 'required' ya se hizo en el Service, 
                # aquí evaluamos todo o decidimos saltar si value es None.
                if value is None:
                    continue 

                if hasattr(rule, 'active') and not rule.active:
                    continue

                is_valid = SimpleEval(
                    names=context_names, 
                    functions=allowed_functions
                ).eval(rule.expression)

                if not is_valid:
                    raise ValueError(rule.error_message or "Error de validación personalizada.")

            except NameNotDefined as e:
                raise ValueError(f"Regla inválida: Variable desconocida {e}")
            except Exception as e:
                # Si ya es ValueError lo dejamos pasar, sino lo envolvemos
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"Error técnico en regla '{rule.name}': {str(e)}")

    @staticmethod
    def _cast_value_for_rules(value, type_code):
        """
        Intenta convertir el valor al tipo correcto para que las comparaciones
        matemáticas funcionen en SimpleEval. Si falla, devuelve el original 
        (para no romper, aunque la regla podría fallar después).
        """
        if value is None or value == "":
            return None
        try:
            if type_code == "INT":
                return int(value)
            elif type_code == "NUMBER":
                return float(value)
            elif type_code == "BOOL":
                return str(value).lower() in ("true", "1")
            elif type_code == "DATE":
                return datetime.strptime(str(value), "%Y-%m-%d")
        except:
            return value 
        return value