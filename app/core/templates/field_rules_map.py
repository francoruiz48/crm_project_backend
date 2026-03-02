# Reglas que se aplican a TODOS los campos de este TIPO (Base)
DEFAULT_TYPE_RULES = {
    "MONEY": [
        {
            "template_code": "IS_NUMBER", 
            "template_params": {}
        }
    ],
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
        {
            "template_code": "IS_URL",
            "template_params": {}
        }
    ],
    "RATING": [
        {"template_code": "MIN_VALUE", "template_params": {"limit": 0}},
        {
            "template_code": "IS_NUMBER",
            "template_params": {},
        }
    ],
    "PHONE": [
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": "^[0-9+\\- ]+$"},
            "error_message": "El teléfono contiene caracteres inválidos."
        }
    ],
    "PASSWORD": [
        {
            "template_code": "MIN_LENGTH",
            "template_params": {"limit": 8},
            "error_message": "La contraseña debe tener al menos 8 caracteres."
        },
        {
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": r"^(?=.*[A-Z])(?=.*\d).+$"}, # Nota la r"" para raw string
            "error_message": "La contraseña debe contener al menos una mayúscula y un número."
        }
    ]
}

# Reglas ADICIONALES que se suman si el campo tiene este SUBTIPO específico
DEFAULT_SUBTYPE_RULES = {
    # --- RATING Subtypes ---
    "STAR_RATING": [
        {
            "template_code": "MAX_VALUE",
            "template_params": {"limit": 5}
        }
    ],
    "NPS": [
        {
            "template_code": "MAX_VALUE",
            "template_params": {"limit": 10}
        }
    ],
    "SCORE": [
        {
            "template_code": "MAX_VALUE",
            "template_params": {"limit": 100}
        }
    ],

    # --- ADDRESS Subtypes ---
    "COORDINATES": [
        {
            # Valida formato "lat, long" (ej: -32.9, -68.8)
            "template_code": "REGEX_MATCH",
            "template_params": {"pattern": r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$"},
            "error_message": "Formato de coordenadas inválido (Lat, Long)."
        }
    ],

    # --- RICH TEXT Subtypes ---
    "HTML": [
        { "template_code": "MAX_LENGTH", "template_params": {"limit": 5000} }
    ],
    
    # --- PHONE Subtypes ---
    "MOBILE": [
        { "template_code": "MIN_LENGTH", "template_params": {"limit": 8} }
    ]
}