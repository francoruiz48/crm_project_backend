from typing import List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class FieldTemplate:
    code: str
    name: str
    field_type_code: str
    rules: List[Dict[str, Any]] = field(default_factory=list)

# Definición de los campos estándar
STANDARD_FIELD_TEMPLATES = {
    # =========================================================================
    # 1. ACCESO Y SEGURIDAD
    # =========================================================================
    "EMAIL": FieldTemplate(
        code="EMAIL",
        name="Correo Electrónico",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "EMAIL_FORMAT", 
                "template_params": {},         
            },
            {
                "template_code": "MAX_LENGTH",
                "template_params": {"limit": 100}
            }
        ]
    ),
    "PASSWORD_STRONG": FieldTemplate(
        code="PASSWORD_STRONG",
        name="Contraseña Segura",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "MIN_LENGTH",
                "template_params": {"limit": 8},
                "error_message": "La contraseña debe tener al menos 8 caracteres."
            },
            {
                # Requiere al menos un número y una mayúscula
                "template_code": "REGEX_MATCH",
                # Regex para Excel: (?=.*[A-Z])(?=.*\d)
                "template_params": {"pattern": "^(?=.*[A-Z])(?=.*\\d).+$"},
                "error_message": "La contraseña debe contener al menos una mayúscula y un número."
            },
            {
                # Validar Carácter Especial
                "template_code": "REGEX_MATCH",
                "template_params": {"pattern": "[^a-zA-Z0-9]"}, 
                "error_message": "Debe contener al menos un carácter especial (ej: ! @ # $ %)."
            }
        ]
    ),

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
    "FULL_NAME": FieldTemplate(
        code="FULL_NAME",
        name="Nombre Completo",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "MIN_LENGTH",
                "template_params": {"limit": 3}
            },
            {
                "template_code": "MAX_LENGTH",
                "template_params": {"limit": 80}
            },
            {
                "template_code": "REGEX_MATCH",
                "template_params": {"pattern": "^[a-zA-ZáéíóúÁÉÍÓÚñÑ\\s]+$"},
                "error_message": "El nombre solo puede contener letras y espacios."
            }
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
        rules=[
            {
                "template_code": "ONLY_DIGITS",
                "template_params": {},
                "error_message": "Ingresa el CUIT sin guiones."
            },
            {
                "template_code": "EXACT_LENGTH",
                "template_params": {"limit": 11},
                "error_message": "El CUIT debe tener exactamente 11 dígitos."
            }
        ]
    ),
    
    # =========================================================================
    # 3. DATOS DE CONTACTO
    # =========================================================================
    "PHONE_ARG": FieldTemplate(
        code="PHONE_ARG",
        name="Teléfono (Móvil Arg)",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "REGEX_MATCH",
                "template_params": {"pattern": "^(?:(?:00)?549?)?0?(?:11|[2368]\\d)(?:(?=\\d{0,2}15)\\d{2})??\\d{8}$"},
                "name": "Formato Celular",
                "error_message": "Formato inválido. Ej: 1112345678"
            }
        ]
    ),
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
    "ADDRESS": FieldTemplate(
        code="ADDRESS",
        name="Dirección / Domicilio",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "MIN_LENGTH",
                "template_params": {"limit": 5}
            },
            {
                "template_code": "MAX_LENGTH",
                "template_params": {"limit": 100}
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
    "SALARY_EXPECTATION": FieldTemplate(
        code="SALARY_EXPECTATION",
        name="Remuneración Pretendida",
        field_type_code="NUMBER",
        rules=[
            {
                "template_code": "MIN_VALUE",
                "template_params": {"limit": 0},
                "error_message": "El valor no puede ser negativo."
            },
            {
                "template_code": "NOT_ZERO",
                "template_params": {}
            }
        ]
    ),
    "CREDIT_CARD_SIMPLE": FieldTemplate(
        code="CREDIT_CARD_SIMPLE",
        name="Tarjeta de Crédito (Simple)",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "ONLY_DIGITS",
                "template_params": {},
                "error_message": "Ingrese solo los números de la tarjeta."
            },
            {
                # Validación de longitud manual
                "expression": "AND(LEN(value) >= 13, LEN(value) <= 19)",
                "name": "Longitud Tarjeta",
                "error_message": "La tarjeta debe tener entre 13 y 19 dígitos."
            }
        ]
    ),

    # =========================================================================
    # 6. WEB Y REDES SOCIALES
    # =========================================================================
    "WEBSITE_URL": FieldTemplate(
        code="WEBSITE_URL",
        name="Sitio Web",
        field_type_code="STRING",
        rules=[
            {
                "template_code": "IS_URL",
                "template_params": {},
                "error_message": "Ingrese una URL válida (http://...)."
            }
        ]
    ),
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