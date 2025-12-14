from typing import Dict, Any

class RuleTemplate:
    def __init__(self, code: str, name: str, description: str, expression_fmt: str, params: list, error_message: str):
        self.code = code
        self.name = name
        self.description = description
        self.expression_fmt = expression_fmt
        self.params = params
        self.error_message = error_message

# Catálogo "Hardcoded" de reglas básicas
STANDARD_RULES = {
    # --- NUMÉRICOS ---
    "MIN_VALUE": RuleTemplate(
        code="MIN_VALUE",
        name="Valor Mínimo",
        description="El número debe ser mayor o igual al límite.",
        expression_fmt="value >= {limit}",
        params=["limit"],
        error_message= f"El número debe ser mayor o igual a {{limit}}."
    ),
    "MAX_VALUE": RuleTemplate(
        code="MAX_VALUE",
        name="Valor Máximo",
        description="El número debe ser menor o igual al límite.",
        expression_fmt="value <= {limit}",
        params=["limit"],
        error_message= f"El número debe ser menor o igual a {{limit}}."
    ),
    "RANGE": RuleTemplate(
        code="RANGE",
        name="Rango de Valores",
        description="El valor debe estar entre un mínimo y un máximo.",
        expression_fmt="value >= {min} and value <= {max}",
        params=["min", "max"],
        error_message= f"El número debe estar entre {{min}} y {{max}}."
    ),
    
    # --- TEXTO ---
    "MAX_LENGTH": RuleTemplate(
        code="MAX_LENGTH",
        name="Longitud Máxima",
        description="Cantidad máxima de caracteres permitidos.",
        expression_fmt="len(value) <= {limit}",
        params=["limit"],
        error_message= f"La longitud del texto no debe exceder {{limit}} caracteres."
    ),
    "MIN_LENGTH": RuleTemplate(
        code="MIN_LENGTH",
        name="Longitud Mínima",
        description="Cantidad mínima de caracteres permitidos.",
        expression_fmt="len(value) >= {limit}",
        params=["limit"],
        error_message= f"La longitud del texto debe ser al menos {{limit}} caracteres."
    ),
    "EMAIL_FORMAT": RuleTemplate(
        code="EMAIL_FORMAT",
        name="Es Email Válido",
        description="Valida formato simple de correo.",
        expression_fmt="'@' in str(value) and '.' in str(value)", 
        params=[],
        error_message="El formato del correo electrónico no es válido."
    ),

    # --- FECHAS ---
    "DATE_FUTURE": RuleTemplate(
        code="DATE_FUTURE",
        name="Solo Fechas Futuras",
        description="La fecha debe ser posterior al día de hoy.",
        expression_fmt="value > today",
        params=[],
        error_message="La fecha debe ser posterior a hoy."
    ),
    "DATE_PAST_OR_TODAY": RuleTemplate(
        code="DATE_PAST_OR_TODAY",
        name="Pasado o Presente",
        description="No permite fechas futuras (ideal para nacimiento).",
        expression_fmt="value <= today",
        params=[],
        error_message="La fecha no puede ser futura."
    ),
    
    # --- RELACIONALES (Lógica cruzada) ---
    "GREATER_THAN_FIELD": RuleTemplate(
        code="GREATER_THAN_FIELD",
        name="Mayor que otro campo",
        description="Este valor debe ser mayor que el campo seleccionado.",
        # OJO: fields[{other_id}] busca el valor del otro campo
        expression_fmt="value > fields[{other_field_id}]",
        params=["other_field_id"],
        error_message="El valor debe ser mayor que el del campo relacionado."
    ),
    
    # --- LÓGICOS ---
    "REQUIRED_IF": RuleTemplate(
        code="REQUIRED_IF",
        name="Obligatorio Si...",
        description="Es obligatorio si otro campo tiene un valor específico.",
        # Traducción: (Si la condición se cumple) ENTONCES (value no puede ser vacío) SINO (True/Pasa)
        expression_fmt="(value is not None and str(value).strip() != '') if str(fields[{other_field_id}]) == '{trigger_value}' else True",
        params=["other_field_id", "trigger_value"],
        error_message="Este campo es obligatorio debido a la condición establecida."
    )
}