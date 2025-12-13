import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
# Asumo que estos imports existen en tu proyecto
from app.models.lead_field import LeadField
from app.models.validation_rule import ValidationRule

class LeadValidationLogic:
    """
    Servicio de lógica pura para validar valores contra reglas configuradas.
    """

    @classmethod
    def validate_field(cls, field: LeadField, value: Any, all_values: Dict[int, Any]):
        """
        Valida un campo específico contra sus reglas configuradas.
        """
        
        # 1. Validación Básica: Required (definido en LeadField)
        # Nota: Convertimos a string para asegurar que 0 no sea considerado vacío si fuera el caso
        str_val = str(value) if value is not None else ""
        
        if field.required and not str_val.strip():
            raise ValueError(f"El campo '{field.name}' es obligatorio.")

        # Si el valor es vacío, revisamos si hay reglas condicionales que lo fuercen
        if not str_val.strip():
            # Buscamos si tiene REQUIRED_IF...
            req_if_rules = [r for r in field.validation_rules if r.rule_type_code == "REQUIRED_IF_FIELD_EQUALS"]
            
            # Si NO hay reglas condicionales, y está vacío, no validamos nada más (longitud, regex, etc.)
            if not req_if_rules:
                return 

        # 2. Iterar sobre las reglas
        for rule in field.validation_rules:
            handler = cls._get_handler(rule.rule_type_code)
            if handler:
                try:
                    # Pasamos el valor como string para uniformidad
                    handler(rule, str_val, all_values)
                except ValueError as e:
                    raise ValueError(f"Error en campo '{field.name}': {str(e)}")

    @classmethod
    def _get_handler(cls, code: str):
        mapping = {
            "MAX_LENGTH": cls._validate_max_length,
            "MIN_LENGTH": cls._validate_min_length,
            "MIN_NUMBER": cls._validate_min_number,
            "MAX_NUMBER": cls._validate_max_number, # <--- CORREGIDO (antes apuntaba a min_number)
            "MIN_INT": cls._validate_min_int,
            "MAX_INT": cls._validate_max_int,
            "STRING_REGEX": cls._validate_regex,
            "DATE_LESS_THAN_FIELD": cls._validate_date_less_than_field,
            "DATE_GREATER_THAN_FIELD": cls._validate_date_greater_than_field,
            "DATE_LESS_THAN_TODAY": cls._validate_date_less_than_today,
            "DATE_GREATER_THAN_TODAY": cls._validate_date_greater_than_today,
            "REQUIRED_IF_FIELD_EQUALS": cls._validate_required_if,
        }
        return mapping.get(code)

    # ==========================================
    # LÓGICA DE REGLAS ESPECÍFICAS
    # ==========================================

    @staticmethod
    def _validate_max_length(rule: ValidationRule, value: str, context: dict):
        if value and len(value) > int(rule.value):
            raise ValueError(f"Excede la longitud máxima de {rule.value} caracteres.")

    @staticmethod
    def _validate_min_length(rule: ValidationRule, value: str, context: dict):
        if value and len(value) < int(rule.value):
            raise ValueError(f"Debe tener al menos {rule.value} caracteres.")

    @staticmethod
    def _validate_min_number(rule: ValidationRule, value: str, context: dict):
        if not value: return # <--- IMPORTANTE: Ignorar si es vacío
        try:
            val_float = float(value)
            limit = float(rule.value)
            if val_float < limit:
                raise ValueError(f"El valor debe ser mayor o igual a {limit}.")
        except (TypeError, ValueError):
            raise ValueError("No es un número válido.")

    @staticmethod
    def _validate_max_number(rule: ValidationRule, value: str, context: dict):
        if not value: return # <--- IMPORTANTE
        try:
            val_float = float(value)
            limit = float(rule.value)
            if val_float > limit:
                raise ValueError(f"El valor debe ser menor o igual a {limit}.")
        except (TypeError, ValueError):
             raise ValueError("No es un número válido.")
        
    @staticmethod
    def _validate_min_int(rule: ValidationRule, value: str, context: dict):
        if not value: return # <--- IMPORTANTE
        try:
            val = int(value)
            limit = int(rule.value)
            if val < limit:
                raise ValueError(f"El valor debe ser mayor o igual a {limit}.")
        except (TypeError, ValueError):
            raise ValueError("No es un entero válido.")

    @staticmethod
    def _validate_max_int(rule: ValidationRule, value: str, context: dict):
        if not value: return # <--- IMPORTANTE
        try:
            val = int(value)
            limit = int(rule.value)
            if val > limit:
                raise ValueError(f"El valor debe ser menor o igual a {limit}.")
        except (TypeError, ValueError):
             raise ValueError("No es un entero válido.")

    @staticmethod
    def _validate_regex(rule: ValidationRule, value: str, context: dict):
        if value and not re.match(rule.value, value):
            raise ValueError("El formato no es válido.")

    # --- FECHAS ---
    
    @staticmethod
    def _validate_date_less_than_field(rule: ValidationRule, value: str, context: dict):
        if not rule.related_field_id: return 
        related_val = context.get(rule.related_field_id)
        if not value or not related_val: return

        # 1. Intentamos PARSEAR (Si falla aquí, es error de formato)
        try:
            date_curr = datetime.strptime(value, "%Y-%m-%d")
            date_rel = datetime.strptime(str(related_val), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Formato de fecha inválido (se espera YYYY-MM-DD).")

        # 2. Validamos LÓGICA (Si falla aquí, es error de negocio)
        if date_curr >= date_rel:
            raise ValueError(f"La fecha debe ser anterior a la del campo relacionado.")

    @staticmethod
    def _validate_date_less_than_today(rule: ValidationRule, value: str, context: dict):
        if not value: return

        # 1. Parseo
        try:
            date_curr = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Formato de fecha inválido (se espera YYYY-MM-DD).")
            
        # 2. Lógica
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if date_curr >= today:
            raise ValueError(f"La fecha debe ser menor a la fecha actual.")

    @staticmethod
    def _validate_date_greater_than_today(rule: ValidationRule, value: str, context: dict):
        if not value: return

        # 1. Parseo
        try:
            date_curr = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Formato de fecha inválido (se espera YYYY-MM-DD).")

        # 2. Lógica
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if date_curr <= today:
            raise ValueError(f"La fecha debe ser mayor a la fecha actual.")

    @staticmethod
    def _validate_date_greater_than_field(rule: ValidationRule, value: str, context: dict):
        if not rule.related_field_id: return
        related_val = context.get(rule.related_field_id)
        if not value or not related_val: return

        # 1. Parseo
        try:
            date_curr = datetime.strptime(value, "%Y-%m-%d")
            date_rel = datetime.strptime(str(related_val), "%Y-%m-%d")
        except ValueError:
             raise ValueError("Formato de fecha inválido (se espera YYYY-MM-DD).")

        # 2. Lógica
        if date_curr <= date_rel:
            raise ValueError(f"La fecha debe ser posterior a la del campo relacionado.")

    @staticmethod
    def _validate_required_if(rule: ValidationRule, value: str, context: dict):
        if not rule.related_field_id: return

        # Obtenemos el valor del campo relacionado (safe get)
        related_val = str(context.get(rule.related_field_id, ""))
        trigger_value = str(rule.value)

        # Si se cumple la condición en el OTRO campo
        if related_val == trigger_value:
            # Nuestro campo NO puede estar vacío
            if not value or not value.strip():
                raise ValueError(f"Este campo es obligatorio cuando el campo relacionado es '{trigger_value}'.")