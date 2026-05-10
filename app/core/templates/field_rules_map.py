# =========================================================================
# REGLAS DE VALIDACIÓN POR DEFECTO
# =========================================================================

# Reglas que se aplican a TODOS los campos de este TIPO BASE
DEFAULT_TYPE_RULES = {
    "NUMBER": [
        {
            "template_code": "IS_NUMBER", 
            "template_params": {}
        }
    ],
    "INT": [
        {
            "template_code": "IS_NUMBER", 
            "template_params": {}
        }
    ]
    # STRING, DATE, BOOL, etc. generalmente no tienen reglas restrictivas 
    # a nivel "Base", se manejan en los subtipos.
}

# Reglas ADICIONALES que se suman si el campo tiene este SUBTIPO específico
DEFAULT_SUBTYPE_RULES = {
    # -------------------------------------
    # SUBTIPOS DE STRING
    # -------------------------------------
    "EMAIL": [
        {
            "template_code": "EMAIL_FORMAT", 
            "template_params": {},        
        },
        {
            "template_code": "MAX_LENGTH",
            "template_params": {"limit": 100}
        }
    ],
    "URL": [
        { "template_code": "IS_URL", "template_params": {} }
    ],
    "WEBSITE": [
        { "template_code": "IS_URL", "template_params": {} }
    ],
    "MAPS_URL": [
        { "template_code": "IS_URL", "template_params": {} }
    ],
    "SOCIAL_MEDIA": [
        { "template_code": "IS_URL", "template_params": {} }
    ],
    "PASSWORD": [
        {
            "template_code": "MIN_LENGTH",
            "template_params": {"limit": 8},
            "error_message": "La contraseña debe tener al menos 8 caracteres."
        },
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": r"^(?=.*[A-Z])(?=.*\d).+$"}, 
            "error_message": "La contraseña debe contener al menos una mayúscula y un número."
        }
    ],
    "COORDINATES": [
        {
            # Valida formato "lat, long" (ej: -32.9, -68.8)
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$"},
            "error_message": "Formato de coordenadas inválido (Lat, Long)."
        }
    ],
    "SIMPLE_ADDRESS": [
        { "template_code": "MAX_LENGTH", "template_params": {"limit": 500} }
    ],
    "HTML": [
        { "template_code": "MAX_LENGTH", "template_params": {"limit": 5000} }
    ],
    "MARKDOWN": [
        { "template_code": "MAX_LENGTH", "template_params": {"limit": 5000} }
    ],
    
    # --- Subfamilias de Teléfonos (Heredan el Regex de caracteres válidos) ---
    "MOBILE": [
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": "^[0-9+\\- ]+$"},
            "error_message": "El teléfono contiene caracteres inválidos."
        },
        { "template_code": "MIN_LENGTH", "template_params": {"limit": 8} }
    ],
    "PHONE": [
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": "^[0-9+\\- ]+$"},
            "error_message": "El teléfono contiene caracteres inválidos."
        }
    ],
    "LANDLINE": [
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": "^[0-9+\\- ]+$"},
            "error_message": "El teléfono contiene caracteres inválidos."
        }
    ],
    "WHATSAPP": [
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": "^[0-9+\\- ]+$"},
            "error_message": "El teléfono contiene caracteres inválidos."
        }
    ],

    # -------------------------------------
    # SUBTIPOS DE NUMBER
    # -------------------------------------
    "PERCENTAGE": [
        { "template_code": "MIN_VALUE", "template_params": {"limit": 0} },
        { "template_code": "MAX_VALUE", "template_params": {"limit": 100} }
    ],
    "STAR_RATING": [
        { "template_code": "MIN_VALUE", "template_params": {"limit": 0} },
        { "template_code": "MAX_VALUE", "template_params": {"limit": 5} }
    ],
    "NPS": [
        { "template_code": "MIN_VALUE", "template_params": {"limit": 0} },
        { "template_code": "MAX_VALUE", "template_params": {"limit": 10} }
    ],
    "SCORE": [
        { "template_code": "MIN_VALUE", "template_params": {"limit": 0} },
        { "template_code": "MAX_VALUE", "template_params": {"limit": 100} }
    ],

    # -------------------------------------
    # SUBTIPOS DE FECHAS (DATE / DATE_TIME)
    # -------------------------------------
    "BIRTH_DATE": [
        {"template_code": "DATE_PAST", "template_params": {}, "error_message": "La fecha de nacimiento debe ser en el pasado."}
    ],
    "DATE_EVENT": [
        {"template_code": "DATE_FUTURE", "template_params": {}, "error_message": "La fecha del evento debe ser a futuro."}
    ],
    "TIME_ONLY": [
        {
            # Valida formato de hora HH:MM o HH:MM:SS
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$"},
            "error_message": "El formato de hora debe ser HH:MM o HH:MM:SS."
        }
    ]
}

# =========================================================================
# MÁSCARAS DE ENTRADA (INPUT MASKS)
# =========================================================================

# 1. Catálogo de máscaras para que el Frontend muestre en un Dropdown
STANDARD_INPUT_MASKS = {
    "DNI_ARG": {"name": "DNI (Argentina)", "mask": "##.###.###"},
    "CUIT_CUIL": {"name": "CUIT / CUIL", "mask": "##-########-#"},
    "PHONE_AR": {"name": "Teléfono Fijo (AR)", "mask": "####-####"},
    "MOBILE_AR": {"name": "Celular (AR)", "mask": "+54 9 ### #######"},
    "CREDIT_CARD": {"name": "Tarjeta de Crédito", "mask": "####-####-####-####"},
    "DATE_DMY": {"name": "Fecha (DD/MM/YYYY)", "mask": "##/##/####"},
    "TIME_HM": {"name": "Hora (HH:MM)", "mask": "##:##"},
    "POSTAL_CODE_AR": {"name": "Código Postal (AR)", "mask": "A####AAA"} 
}

# 2. Máscaras por defecto si se elige un TIPO genérico
DEFAULT_TYPE_MASKS = {
    # DATE y DATE_TIME suelen ser manejados por DatePickers en el front.
}

# 3. Máscaras por defecto que sobrescriben al tipo si se elige un SUBTIPO
DEFAULT_SUBTYPE_MASKS = {

}