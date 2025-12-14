from typing import Dict, Any

class RuleTemplate:
    def __init__(self, code: str, name: str, description: str, expression_fmt: str, params: list, error_message: str):
        self.code = code
        self.name = name
        self.description = description
        self.expression_fmt = expression_fmt
        self.params = params
        self.error_message = error_message

STANDARD_RULES = {
    # =========================================================================
    # 1. NUMÉRICOS (Matemáticas y Rangos)
    # =========================================================================
    "MIN_VALUE": RuleTemplate(
        code="MIN_VALUE",
        name="Valor Mínimo",
        description="El número debe ser mayor o igual al límite.",
        expression_fmt="value >= {limit}",
        params=["limit"],
        error_message="El número debe ser mayor o igual a {limit}."
    ),
    "MAX_VALUE": RuleTemplate(
        code="MAX_VALUE",
        name="Valor Máximo",
        description="El número debe ser menor o igual al límite.",
        expression_fmt="value <= {limit}",
        params=["limit"],
        error_message="El número debe ser menor o igual a {limit}."
    ),
    "RANGE": RuleTemplate(
        code="RANGE",
        name="Rango Numérico",
        description="El valor debe estar entre un mínimo y un máximo (inclusivo).",
        expression_fmt="value >= {min} and value <= {max}",
        params=["min", "max"],
        error_message="El número debe estar entre {min} y {max}."
    ),
    "EXACT_VALUE": RuleTemplate(
        code="EXACT_VALUE",
        name="Valor Exacto",
        description="El valor debe ser exactamente igual al parámetro.",
        expression_fmt="value == {target}",
        params=["target"],
        error_message="El valor debe ser exactamente {target}."
    ),
    "NOT_ZERO": RuleTemplate(
        code="NOT_ZERO",
        name="No puede ser Cero",
        description="Valida que el número no sea 0.",
        expression_fmt="value != 0",
        params=[],
        error_message="El valor no puede ser cero."
    ),
    "MULTIPLE_OF": RuleTemplate(
        code="MULTIPLE_OF",
        name="Múltiplo De",
        description="El número debe ser múltiplo de X (ej: cajas de 6 unidades).",
        expression_fmt="value % {step} == 0",
        params=["step"],
        error_message="El valor debe ser múltiplo de {step}."
    ),
    "IS_EVEN": RuleTemplate(
        code="IS_EVEN",
        name="Es Par",
        description="El número debe ser par.",
        expression_fmt="value % 2 == 0",
        params=[],
        error_message="El número debe ser par."
    ),

    # =========================================================================
    # 2. TEXTO (Longitud, Contenido y Patrones)
    # =========================================================================
    "MAX_LENGTH": RuleTemplate(
        code="MAX_LENGTH",
        name="Longitud Máxima",
        description="Cantidad máxima de caracteres permitidos.",
        expression_fmt="len(str(value)) <= {limit}",
        params=["limit"],
        error_message="El texto no debe exceder {limit} caracteres."
    ),
    "MIN_LENGTH": RuleTemplate(
        code="MIN_LENGTH",
        name="Longitud Mínima",
        description="Cantidad mínima de caracteres permitidos.",
        expression_fmt="len(str(value)) >= {limit}",
        params=["limit"],
        error_message="El texto debe tener al menos {limit} caracteres."
    ),
    "EXACT_LENGTH": RuleTemplate(
        code="EXACT_LENGTH",
        name="Longitud Exacta",
        description="El texto debe tener una cantidad exacta de caracteres.",
        expression_fmt="len(str(value)) == {limit}",
        params=["limit"],
        error_message="El texto debe tener exactamente {limit} caracteres."
    ),
    "STARTS_WITH": RuleTemplate(
        code="STARTS_WITH",
        name="Empieza con...",
        description="El texto debe comenzar con un prefijo específico.",
        expression_fmt="str(value).startswith('{prefix}')",
        params=["prefix"],
        error_message="El valor debe comenzar con '{prefix}'."
    ),
    "ENDS_WITH": RuleTemplate(
        code="ENDS_WITH",
        name="Termina con...",
        description="El texto debe terminar con un sufijo específico.",
        expression_fmt="str(value).endswith('{suffix}')",
        params=["suffix"],
        error_message="El valor debe terminar con '{suffix}'."
    ),
    "CONTAINS_TEXT": RuleTemplate(
        code="CONTAINS_TEXT",
        name="Contiene Texto",
        description="El texto debe contener una palabra o frase específica.",
        expression_fmt="'{text}' in str(value)",
        params=["text"],
        error_message="El valor debe contener el texto '{text}'."
    ),
    "NOT_CONTAINS_TEXT": RuleTemplate(
        code="NOT_CONTAINS_TEXT",
        name="No Contiene Texto",
        description="El texto NO debe contener una palabra prohibida.",
        expression_fmt="'{text}' not in str(value)",
        params=["text"],
        error_message="El valor no puede contener el texto '{text}'."
    ),
    "IS_UPPERCASE": RuleTemplate(
        code="IS_UPPERCASE",
        name="Todo Mayúsculas",
        description="El texto debe estar completamente en mayúsculas.",
        expression_fmt="str(value).isupper()",
        params=[],
        error_message="El texto debe estar en mayúsculas."
    ),
    "IS_LOWERCASE": RuleTemplate(
        code="IS_LOWERCASE",
        name="Todo Minúsculas",
        description="El texto debe estar completamente en minúsculas.",
        expression_fmt="str(value).islower()",
        params=[],
        error_message="El texto debe estar en minúsculas."
    ),
    "NO_SPACES": RuleTemplate(
        code="NO_SPACES",
        name="Sin Espacios",
        description="El texto no puede contener espacios en blanco.",
        expression_fmt="' ' not in str(value)",
        params=[],
        error_message="El valor no puede contener espacios."
    ),

    # =========================================================================
    # 3. FORMATOS ESPECÍFICOS (Regex y Tipos)
    # =========================================================================
    "EMAIL_FORMAT": RuleTemplate(
        code="EMAIL_FORMAT",
        name="Es Email Válido",
        description="Valida formato simple de correo.",
        expression_fmt="'@' in str(value) and '.' in str(value) and len(str(value)) > 5", 
        params=[],
        error_message="El formato del correo electrónico no es válido."
    ),
    "ONLY_DIGITS": RuleTemplate(
        code="ONLY_DIGITS",
        name="Solo Dígitos",
        description="El texto debe contener solo números (útil para teléfonos o IDs).",
        expression_fmt="str(value).isdigit()",
        params=[],
        error_message="El campo solo debe contener números."
    ),
    "ALPHANUMERIC": RuleTemplate(
        code="ALPHANUMERIC",
        name="Alfanumérico",
        description="Solo letras y números, sin símbolos especiales.",
        expression_fmt="str(value).isalnum()",
        params=[],
        error_message="El campo solo puede contener letras y números."
    ),
    "IS_URL": RuleTemplate(
        code="IS_URL",
        name="Es URL",
        description="Validación básica de URL (http/https).",
        expression_fmt="str(value).startswith('http://') or str(value).startswith('https://')",
        params=[],
        error_message="Debe ser una URL válida que comience con http:// o https://."
    ),
    # NOTA: Para REGEX_MATCH necesitas pasar la función 'regex_match' o 're' a SimpleEval
    "REGEX_MATCH": RuleTemplate(
        code="REGEX_MATCH",
        name="Patrón Personalizado (Regex)",
        description="Valida contra una expresión regular personalizada.",
        # Asumiendo que inyectas una función helper: regex_match(pattern, string)
        expression_fmt="regex_match('{pattern}', str(value))", 
        params=["pattern"],
        error_message="El valor no cumple con el formato requerido."
    ),

    # =========================================================================
    # 4. LISTAS Y OPCIONES
    # =========================================================================
    "IN_LIST": RuleTemplate(
        code="IN_LIST",
        name="Debe ser uno de...",
        description="El valor debe estar dentro de una lista separada por comas.",
        # Convertimos el string de params "A,B,C" a lista y chequeamos
        expression_fmt="str(value) in '{options}'.split(',')",
        params=["options"],
        error_message="El valor debe ser uno de los siguientes: {options}."
    ),
    "NOT_IN_LIST": RuleTemplate(
        code="NOT_IN_LIST",
        name="No puede ser uno de... (Lista Negra)",
        description="El valor no puede estar en la lista prohibida.",
        expression_fmt="str(value) not in '{options}'.split(',')",
        params=["options"],
        error_message="El valor no está permitido."
    ),

    # =========================================================================
    # 5. FECHAS (Avanzado)
    # =========================================================================
    "DATE_FUTURE": RuleTemplate(
        code="DATE_FUTURE",
        name="Fecha Futura",
        description="La fecha debe ser estrictamente mayor a hoy.",
        expression_fmt="value > today",
        params=[],
        error_message="La fecha debe ser posterior a hoy."
    ),
    "DATE_PAST": RuleTemplate(
        code="DATE_PAST",
        name="Fecha Pasada",
        description="La fecha debe ser estrictamente menor a hoy.",
        expression_fmt="value < today",
        params=[],
        error_message="La fecha debe ser anterior a hoy."
    ),
    "DATE_PAST_OR_TODAY": RuleTemplate(
        code="DATE_PAST_OR_TODAY",
        name="Pasado o Presente",
        description="No permite fechas futuras.",
        expression_fmt="value <= today",
        params=[],
        error_message="La fecha no puede ser futura."
    ),
    "MIN_AGE": RuleTemplate(
        code="MIN_AGE",
        name="Edad Mínima (Años)",
        description="Calcula si la fecha de nacimiento cumple una edad mínima.",
        # Lógica aproximada segura: (Año actual - Año Nac)
        # Nota: Para precisión exacta de día/mes se requiere lógica más compleja o función helper
        expression_fmt="(today.year - value.year) - (1 if (today.month, today.day) < (value.month, value.day) else 0) >= {age}",
        params=["age"],
        error_message="La persona debe tener al menos {age} años."
    ),
    "IS_WEEKDAY": RuleTemplate(
        code="IS_WEEKDAY",
        name="Es Día de Semana",
        description="La fecha debe caer de Lunes a Viernes.",
        # .weekday(): 0=Lunes, 4=Viernes, 5=Sabado, 6=Domingo
        expression_fmt="value.weekday() < 5",
        params=[],
        error_message="La fecha debe ser un día de semana (Lun-Vie)."
    ),
     "IS_WEEKEND": RuleTemplate(
        code="IS_WEEKEND",
        name="Es Fin de Semana",
        description="La fecha debe caer Sábado o Domingo.",
        expression_fmt="value.weekday() >= 5",
        params=[],
        error_message="La fecha debe ser Sábado o Domingo."
    ),

    # =========================================================================
    # 6. RELACIONALES (Comparación entre campos)
    # =========================================================================
    "GREATER_THAN_FIELD": RuleTemplate(
        code="GREATER_THAN_FIELD",
        name="Mayor que otro campo",
        description="Este valor > Otro campo.",
        expression_fmt="value > fields.get({other_field_id})",
        params=["other_field_id"],
        error_message="El valor debe ser mayor que el campo relacionado."
    ),
    "LESS_THAN_FIELD": RuleTemplate(
        code="LESS_THAN_FIELD",
        name="Menor que otro campo",
        description="Este valor < Otro campo.",
        expression_fmt="value < fields.get({other_field_id})",
        params=["other_field_id"],
        error_message="El valor debe ser menor que el campo relacionado."
    ),
    "EQUALS_FIELD": RuleTemplate(
        code="EQUALS_FIELD",
        name="Igual a otro campo",
        description="Debe ser idéntico a otro campo (ej: Confirmar Email).",
        expression_fmt="value == fields.get({other_field_id})",
        params=["other_field_id"],
        error_message="Los campos no coinciden."
    ),
    "NOT_EQUALS_FIELD": RuleTemplate(
        code="NOT_EQUALS_FIELD",
        name="Distinto a otro campo",
        description="No puede ser igual a otro campo.",
        expression_fmt="value != fields.get({other_field_id})",
        params=["other_field_id"],
        error_message="El valor no puede ser igual al campo relacionado."
    ),
    
    # =========================================================================
    # 7. LÓGICOS CONDICIONALES
    # =========================================================================
    "REQUIRED_IF": RuleTemplate(
        code="REQUIRED_IF",
        name="Obligatorio Si...",
        description="Este campo es obligatorio si otro campo tiene un valor específico.",
        # Si (OtroCampo == ValorGatillo) ENTONCES (EsteCampo no debe ser vacio)
        expression_fmt="(value is not None and str(value).strip() != '') if str(fields.get({other_field_id})) == '{trigger_value}' else True",
        params=["other_field_id", "trigger_value"],
        error_message="Este campo es obligatorio debido a la selección anterior."
    ),
    "REQUIRED_IF_CHECKED": RuleTemplate(
        code="REQUIRED_IF_CHECKED",
        name="Obligatorio si Boolean es True",
        description="Obligatorio si un checkbox/switch está activo.",
        expression_fmt="(value is not None) if str(fields.get({other_field_id})).lower() == 'true' else True",
        params=["other_field_id"],
        error_message="Campo requerido."
    )
}