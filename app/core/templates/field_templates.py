from typing import List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class FieldTemplate:
    code: str
    name: str
    field_type_code: str
    rules: List[Dict[str, Any]] = field(default_factory=list)
    input_mask: str = None

# Definición de los campos estándar
STANDARD_FIELD_TEMPLATES = {

    # =========================================================================
    # 2. IDENTIDAD Y PERSONALES (Argentina / Latam)
    # =========================================================================
    "FIRST_NAME": FieldTemplate(
        code="FIRST_NAME",
        name="Nombre",
        field_type_code="STRING",
        rules=[
            { "template_code": "MIN_LENGTH", "template_params": {"limit": 2} },
            { "template_code": "MAX_LENGTH", "template_params": {"limit": 50} },
            {
                "template_code": "REGEX_MATCH",
                # Permite letras, acentos, espacios, guiones y apóstrofes
                "template_params": {"pattern": "^[a-zA-ZáéíóúÁÉÍÓÚñÑ\\s\\-\\']+$"},
                "error_message": "El nombre contiene caracteres inválidos."
            }
        ]
    ),
    "LAST_NAME": FieldTemplate(
        code="LAST_NAME",
        name="Apellido",
        field_type_code="STRING",
        rules=[
            { "template_code": "MIN_LENGTH", "template_params": {"limit": 2} },
            { "template_code": "MAX_LENGTH", "template_params": {"limit": 50} },
            {
                "template_code": "REGEX_MATCH",
                "template_params": {"pattern": "^[a-zA-ZáéíóúÁÉÍÓÚñÑ\\s\\-\\']+$"},
                "error_message": "El apellido contiene caracteres inválidos."
            }
        ]
    ),
    "AGE": FieldTemplate(
        code="AGE",
        name="Edad",
        field_type_code="INT",
        rules=[
            { "template_code": "MIN_VALUE", "template_params": {"limit": 0} },
            { "template_code": "MAX_VALUE", "template_params": {"limit": 120} }
        ]
    ),
    # 3. DOCUMENTACIÓN (Nacional e Internacional)
    "ID_GLOBAL": FieldTemplate(
        code="ID_GLOBAL",
        name="Documento de Identidad (ID)",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "ALPHANUMERIC", 
                "template_params": {},
                "error_message": "El ID solo puede contener letras y números."
            },
            {
                "template_code": "NO_SPACES",
                "template_params": {},
                "error_message": "El ID no debe contener espacios."
            },
            {
                "expression": "AND(LEN(value) >= 5, LEN(value) <= 20)",
                "name": "Longitud ID",
                "error_message": "El documento debe tener entre 5 y 20 caracteres."
            }
        ]
    ),
    "DNI_ARG": FieldTemplate(
        code="DNI_ARG",
        name="DNI (Argentina)",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "ONLY_DIGITS",
                "template_params": {},
                "error_message": "El DNI solo debe contener números."
            },
            {
                "template_code": "MIN_LENGTH",
                "template_params": {"limit": 7}
            },
            {
                "template_code": "MAX_LENGTH",
                "template_params": {"limit": 8}
            }
        ]
    ),
    "CUIT_CUIL": FieldTemplate(
        code="CUIT_CUIL",
        name="CUIT / CUIL",
        field_type_code="STRING",
        input_mask="##-########-#", 
        rules=[
        ]
    ),
    
    # =========================================================================
    # 3. DATOS DE CONTACTO
    # =========================================================================
    "POSTAL_CODE": FieldTemplate(
        code="POSTAL_CODE",
        name="Código Postal",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "ALPHANUMERIC",
                "template_params": {},
                "error_message": "El CP solo puede contener letras y números."
            },
            {
                "template_code": "MAX_LENGTH",
                "template_params": {"limit": 8}
            }
        ]
    ),

    # =========================================================================
    # 4. FECHAS Y EDADES
    # =========================================================================
    "BIRTH_DATE": FieldTemplate(
        code="BIRTH_DATE",
        name="Fecha de Nacimiento",
        field_type_code="DATE",
        rules=[
            {
                "template_code": "DATE_PAST",
                "template_params": {},
                "error_message": "La fecha debe ser en el pasado."
            }
        ]
    ),
    "BIRTH_DATE_ADULT": FieldTemplate(
        code="BIRTH_DATE_ADULT",
        name="Fecha de Nacimiento (+18)",
        field_type_code="DATE",
        rules=[
            {
                "template_code": "DATE_PAST",
                "template_params": {},
                "error_message": "La fecha debe ser en el pasado."
            },
            {
                "template_code": "MIN_AGE",
                "template_params": {"age": 18},
                "error_message": "Debes ser mayor de 18 años."
            }
        ]
    ),
    "APPOINTMENT_DATE": FieldTemplate(
        code="APPOINTMENT_DATE",
        name="Fecha de Cita / Turno",
        field_type_code="DATE_TIME",
        rules=[
            {
                "template_code": "DATE_FUTURE",
                "template_params": {},
                "error_message": "El turno debe ser para una fecha futura."
            },
            {
                "template_code": "IS_WEEKDAY",
                "template_params": {},
                "error_message": "Solo atendemos de Lunes a Viernes."
            }
        ]
    ),

    # =========================================================================
    # 5. FINANCIERO Y NEGOCIOS
    # =========================================================================
    "CBU_ALIAS": FieldTemplate(
        code="CBU_ALIAS",
        name="CBU o Alias Bancario",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "MIN_LENGTH",
                "template_params": {"limit": 6}, 
                "error_message": "Muy corto para ser un Alias o CBU."
            },
            {
                "template_code": "MAX_LENGTH",
                "template_params": {"limit": 22},
                "error_message": "No debe exceder los 22 caracteres."
            }
        ]
    ),
    "CREDIT_CARD_SIMPLE": FieldTemplate(
        code="CREDIT_CARD_SIMPLE",
        name="Tarjeta de Crédito (Simple)",
        field_type_code="STRING",
        input_mask="####-####-####-####",
        rules=[
        ]
    ),

    # =========================================================================
    # 6. WEB Y REDES SOCIALES
    # =========================================================================
    "INSTAGRAM_USER": FieldTemplate(
        code="INSTAGRAM_USER",
        name="Usuario Instagram",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "STARTS_WITH",
                "template_params": {"prefix": "@"},
                "error_message": "El usuario debe comenzar con '@'."
            },
            {
                "template_code": "NO_SPACES",
                "template_params": {},
                "error_message": "El usuario no puede contener espacios."
            }
        ]
    ),
    "IP_ADDRESS_V4": FieldTemplate(
        code="IP_ADDRESS_V4",
        name="Dirección IP (v4)",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "REGEX_MATCH",
                "template_params": {
                    "pattern": "^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
                },
                "error_message": "Formato de IP inválido (ej: 192.168.1.1)"
            }
        ]
    )
}