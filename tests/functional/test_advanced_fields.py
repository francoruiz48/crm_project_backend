import pytest
from app.models.lead_field import LeadField

# Helper para no repetir código de creación
def create_field_and_assert_validation(client, camp_id, org_id, field_props, valid_val, invalid_val, error_fragment):
    """
    1. Crea un campo con el tipo/subtipo dado.
    2. Intenta crear un lead con valor VÁLIDO (Debe dar 200).
    3. Intenta crear un lead con valor INVÁLIDO (Debe dar 400).
    4. Verifica que el mensaje de error contenga el fragmento esperado.
    """
    # Setup del payload del campo
    payload = {
        "campaign_id": camp_id,
        "organization_id": org_id,
        "lead_field_section_id": 1,
        "is_visible": True,
        **field_props # Name, type_code, subtype_code
    }
    
    # 1. Crear Campo
    res_field = client.post("/lead_fields/", json=payload)
    assert res_field.status_code == 200, f"Error creando campo: {res_field.text}"
    f_id = res_field.json()["id"]

    # 2. Caso Éxito
    res_ok = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": valid_val}]
    })
    assert res_ok.status_code == 200, f"Falló con valor válido '{valid_val}': {res_ok.text}"

    # 3. Caso Fallo
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": invalid_val}]
    })
    assert res_fail.status_code == 400, f"Debió fallar con '{invalid_val}' pero pasó."
    
    # 4. Validar Mensaje
    # Normalizamos a minúsculas para facilitar el match
    assert error_fragment.lower() in res_fail.text.lower(), f"Mensaje esperado '{error_fragment}' no encontrado en '{res_fail.text}'"


# =============================================================================
# 1. TEST TIPO MONEY (Sin validación de positivo, solo numérico)
# =============================================================================
def test_field_money_logic(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={"name": "Precio Venta", "field_type_code": "MONEY"},
        valid_val="-1500.50",
        invalid_val="Mil pesos", 
        error_fragment="número" 
    )

# =============================================================================
# 2. TEST TIPO EMAIL
# =============================================================================
def test_field_email_logic(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={"name": "Email Corporativo", "field_type_code": "EMAIL"},
        valid_val="usuario@empresa.com",
        invalid_val="usuario.empresa.com", # Falta @
        error_fragment="formato" # Viene de DEFAULT_TYPE_RULES["EMAIL"]
    )

# =============================================================================
# 3. TEST TIPO URL (Base)
# =============================================================================
def test_field_url_logic(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "LinkedIn", 
            "field_type_code": "URL", 
            "field_subtype_code": "SOCIAL_MEDIA"
        },
        valid_val="https://linkedin.com/in/usuario",
        invalid_val="linkedin/usuario", # Falta protocolo
        error_fragment="válida" # Viene de DEFAULT_TYPE_RULES["URL"]
    )

# =============================================================================
# 4. TEST TIPO PHONE (Base + Subtipo Mobile)
# =============================================================================
def test_field_phone_logic(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    # Prueba la Regex base (Solo números, espacios, +)
    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "Celular", 
            "field_type_code": "PHONE", 
            "field_subtype_code": "MOBILE"
        },
        valid_val="+54 9 11 1234-5678",
        invalid_val="12345abc", # Letras no permitidas
        error_fragment="inválidos" 
    )

# =============================================================================
# 5. TEST TIPO RATING (Variantes de Subtipos)
# =============================================================================

def test_field_rating_stars(client, initial_structure):
    """Subtipo STAR_RATING debe limitar a 5"""
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "Calidad Estrellas", 
            "field_type_code": "RATING", 
            "field_subtype_code": "STAR_RATING"
        },
        valid_val="5",
        invalid_val="6", # Se pasa del límite de subtipo
        error_fragment="menor"
    )

def test_field_rating_nps(client, initial_structure):
    """Subtipo NPS debe limitar a 10"""
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "NPS Encuesta", 
            "field_type_code": "RATING", 
            "field_subtype_code": "NPS"
        },
        valid_val="9",
        invalid_val="11", 
        error_fragment="menor" # Mensaje genérico o específico de NPS
    )

def test_field_rating_score(client, initial_structure):
    """Subtipo SCORE debe limitar a 100"""
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "Scoring Crediticio", 
            "field_type_code": "RATING", 
            "field_subtype_code": "SCORE"
        },
        valid_val="98",
        invalid_val="101", 
        error_fragment="menor"
    )

# =============================================================================
# 6. TEST TIPO ADDRESS (Subtipo Coordenadas)
# =============================================================================
def test_field_address_coordinates(client, initial_structure):
    """Prueba la Regex compleja de Latitud/Longitud"""
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "Ubicación GPS", 
            "field_type_code": "ADDRESS", 
            "field_subtype_code": "COORDINATES"
        },
        valid_val="-34.6037, -58.3816", # Obelisco BA
        invalid_val="Calle Falsa 123", 
        error_fragment="coordenadas"
    )

# =============================================================================
# 7. TEST TIPO PASSWORD (Validación compuesta: Largo + Regex Complejidad)
# =============================================================================
def test_field_password_logic(client, initial_structure):
    """
    Verifica que el campo PASSWORD exija:
    1. Mínimo 8 caracteres.
    2. Al menos 1 Mayúscula y 1 Número.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    # Caso 1: Fallo por Complejidad (Tiene largo, pero no tiene mayúscula/número)
    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "Clave Acceso", 
            "field_type_code": "PASSWORD"
        },
        valid_val="Segura123", # Cumple todo (Largo 9, Mayúscula, Número)
        invalid_val="insegura123456", # Falla Regex (No tiene mayúsculas)
        error_fragment="mayúscula" # Mensaje esperado: "...contener al menos una mayúscula..."
    )

def test_field_password_length(client, initial_structure):
    """
    Verifica específicamente el fallo por longitud en PASSWORD.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    create_field_and_assert_validation(
        client, camp_id, org_id,
        field_props={
            "name": "Clave Corta", 
            "field_type_code": "PASSWORD"
        },
        valid_val="Correcta1", 
        invalid_val="Ab1", # Falla Longitud (Solo 3 chars)
        error_fragment="8 caracteres" # Mensaje esperado: "...tener al menos 8 caracteres."
    )