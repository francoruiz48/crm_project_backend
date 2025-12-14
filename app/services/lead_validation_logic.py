# app/services/lead_validation_logic.py
from datetime import datetime
from typing import Any, Dict
from simpleeval import SimpleEval, NameNotDefined
from app.models.lead_field import LeadField

class LeadValidationLogic:
    """
    Motor de reglas dinámico basado en expresiones.
    """

    @classmethod
    def validate_field(cls, field: LeadField, raw_value: Any, all_values: Dict[int, Any]):
        # 1. Validación Hardcoded: Required
        # Convertimos a string para verificar si está vacío visualmente
        str_val = str(raw_value) if raw_value is not None else ""
        
        if field.required and not str_val.strip():
            raise ValueError(f"El campo '{field.name}' es obligatorio.")

        # Si está vacío y no es requerido, normalmente salimos.
        # PERO, si tienes reglas condicionales (ej: required_if), 
        # necesitamos evaluar la expresión de todos modos.
        # Estrategia: Si el valor es nulo, lo pasamos como None al contexto.
        
        # 2. Casteo de tipos para el motor (Python nativo)
        value = cls._cast_value(raw_value, field.field_type.code)

        for rule in field.validation_rules:
            # Preparamos las variables que la fórmula puede usar
            context = {
                "value": value,
                "today": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                "now": datetime.now(),
                "len": len,  # Permitir usar len() en la fórmula
                "related": None
            }

            # Inyectar valor relacionado si existe
            if rule.related_field_id:
                raw_related = all_values.get(rule.related_field_id)
                context["related"] = cls._cast_auto(raw_related)

            try:
                # Escribe lógica para ignorar validaciones numéricas/fecha si el valor es None
                # O bien, maneja eso dentro de la expresión en BD (ej: "value is None or value > 10")
                if value is None and "required" not in rule.expression.lower():
                    continue

                # EVALUACIÓN SEGURA
                is_valid = SimpleEval(names=context).eval(rule.expression)

                # Si la expresión devuelve False, lanzamos el error personalizado
                if not is_valid:
                    raise ValueError(rule.error_message)

            except NameNotDefined as e:
                # Esto pasa si la fórmula usa una variable que no definimos
                raise ValueError(f"Error técnico en regla de validación: variable desconocida {e}")
            except Exception as e:
                # Si la fórmula falla (ej: comparar int con string)
                # Opcional: Loggear el error real y mostrar uno genérico
                raise ValueError(f"Error al validar regla: {rule.error_message} (Detalle: {str(e)})")

    @staticmethod
    def _cast_value(value, type_code):
        """Convierte inputs (generalmente strings) a tipos Python reales."""
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
                # Asumiendo ISO format YYYY-MM-DD
                return datetime.strptime(str(value), "%Y-%m-%d")
        except ValueError:
            # Si falla el casteo, devolvemos el valor crudo o lanzamos error.
            # Mejor lanzar error de formato aquí si es estricto.
            raise ValueError(f"El valor '{value}' no corresponde al tipo {type_code}")
            
        return str(value)

    @staticmethod
    def _cast_auto(value):
        """Intenta adivinar el tipo para el campo 'related' sin saber su metadata."""
        if value is None or value == "":
            return None
        # Intenta número
        try: 
            if "." in str(value): return float(value)
            return int(value)
        except: pass
        # Intenta fecha
        try:
            return datetime.strptime(str(value), "%Y-%m-%d")
        except: pass
        return str(value)