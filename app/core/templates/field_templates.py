from typing import List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class FieldTemplate:
    name: str            
    type_code: str        
    rules: List[Dict[str, Any]] = field(default_factory=list)

# Definición de los campos estándar
STANDARD_FIELD_TEMPLATES = {
    "EMAIL": FieldTemplate(
        name="Correo Electrónico",
        type_code="STRING",
        rules=[
            {
                "template_code": "EMAIL_FORMAT", 
                "template_params": {},         
            }
        ]
    ),
    "ADULT_AGE": FieldTemplate(
        name="Edad (Adulto)",
        type_code="INT",
        rules=[
            {
                "template_code": "NUMERIC_RANGE",
                "template_params": {"min": 18, "max": 100},
                "error_message": "El contacto debe ser mayor de edad." # Override opcional
            }
        ]
    ),
    "PHONE_ARG": FieldTemplate(
        name="Teléfono (Argentina)",
        type_code="STRING",
        rules=[
            {
                "template_code": "REGEX_MATCH",
                "template_params": {"pattern": "^(?:(?:00)?549?)?0?(?:11|[2368]\d)(?:(?=\d{0,2}15)\d{2})??\d{8}$"},
                "name": "Formato Celular Arg"
            },
            {
                "template_code": "TEXT_LENGTH",
                "template_params": {"min": 10, "max": 15}
            }
        ]
    ),
    "PASSWORD": FieldTemplate(
        name="Contraseña Segura",
        type_code="STRING", # O 'PASSWORD' si tienes un tipo especial para ocultarlo en UI
        rules=[
            {
                "template_code": "TEXT_LENGTH",
                "template_params": {"min": 8, "max": 50},
                "error_message": "La contraseña debe tener al menos 8 caracteres."
            }
            # Aquí podrías agregar otra regla de regex para mayúsculas/números
        ]
    )
}