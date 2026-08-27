import pytest
from datetime import datetime, timedelta

# =============================================================================
# HELPER DE FECHAS DINÁMICAS
# =============================================================================
def get_dynamic_value(val_str):
    """
    Si el valor es un string mágico (ej: '__PAST__'), lo convierte a una fecha real
    relativa al día de hoy. Si es un valor normal, lo devuelve tal cual.
    """
    if not isinstance(val_str, str):
        return val_str
    
    now = datetime.now()
    if val_str == "__PAST__":
        return (now - timedelta(days=5)).strftime("%Y-%m-%d")
    if val_str == "__FUTURE__":
        return (now + timedelta(days=5)).strftime("%Y-%m-%d")
    if val_str == "__ADULT__":
        return (now - timedelta(days=365*25)).strftime("%Y-%m-%d") # 25 años
    if val_str == "__MINOR__":
        return (now - timedelta(days=365*10)).strftime("%Y-%m-%d") # 10 años
    if val_str == "__NEXT_MONDAY__":
        days_ahead = 0 - now.weekday()
        if days_ahead <= 0: # Apunta a la próxima semana
            days_ahead += 7
        return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d 10:00:00")
    if val_str == "__NEXT_SUNDAY__":
        days_ahead = 6 - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d 10:00:00")
    
    return val_str

# =============================================================================
# SUITE PARAMETRIZADA DE TEMPLATES
# =============================================================================

@pytest.mark.parametrize("template_code, valid_val, invalid_val", [
    # 2. IDENTIDAD Y PERSONALES
    ("FIRST_NAME", "Juan Pablo", "J1"), # J1 tiene números, falla REGEX
    ("LAST_NAME", "Gómez-O'Connor", "G0m3z"), 
    ("AGE", 30, 150), # 150 supera el MAX_VALUE de 120

    # 3. DOCUMENTACIÓN
    ("ID_GLOBAL", "AB12345", "AB 12"), # Tiene un espacio, falla NO_SPACES
    ("DNI_ARG", "12345678", "123456"), # Muy corto, falla MIN_LENGTH (7)
    ("CUIT_CUIL", "20-12345637-8", "20-1234-9"), # Tiene guiones,
    
    # 3. DATOS DE CONTACTO
    ("POSTAL_CODE", "C1425AB", "C 1425"), # Tiene espacio, falla ALPHANUMERIC

    # 4. FECHAS Y EDADES
    ("BIRTH_DATE_ADULT", "__ADULT__", "__MINOR__"), # MINOR falla la regla de MIN_AGE
    ("APPOINTMENT_DATE", "__NEXT_MONDAY__", "__NEXT_SUNDAY__"), # Sunday falla IS_WEEKDAY

    # 5. FINANCIERO Y NEGOCIOS
    ("CBU_ALIAS", "micbu.alias.ok", "corto"), # 'corto' tiene 5 letras, falla MIN_LENGTH (6)
    ("CREDIT_CARD_SIMPLE", "1234-5678-9012-3456", "123456789012"), # 12 dígitos, falla expr >=13

    # 6. WEB Y REDES SOCIALES
    ("INSTAGRAM_USER", "@mi_usuario", "mi_usuario"), # No tiene @, falla STARTS_WITH
    ("IP_ADDRESS_V4", "192.168.1.1", "256.256.256.256") # 256 excede el byte, falla REGEX
])
def test_field_template_validation(api, initial_structure, template_code, valid_val, invalid_val):
    """
    Prueba que al crear un campo usando un 'template_code', las reglas predefinidas
    se inyectan correctamente y bloquean los datos inválidos.
    """
    camp_id = initial_structure["campaign_id"]
    api.org_id = initial_structure["org_id"] # <-- Evitamos State Leakage
    
    # Parseamos las fechas dinámicas si existen
    parsed_valid = get_dynamic_value(valid_val)
    parsed_invalid = get_dynamic_value(invalid_val)

    # 1. Crear el campo a partir del template
    res_field = api.client.post("/lead_fields/", json={
        "name": f"Campo {template_code}",
        "field_template_code": template_code,
        "campaign_id": camp_id,
        "order": 1
    }, headers=api.headers)
    
    assert res_field.status_code == 200, f"Error creando campo {template_code}: {res_field.text}"
    f_id = res_field.json()["id"]

    # 2. Happy Path (Probar Valor Válido -> Debe dar 200 OK)
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_id, "value": parsed_valid}], 
        expected_status=200
    )

    # 3. Unhappy Path (Probar Valor Inválido -> Debe dar 400 Bad Request)
    res_fail = api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_id, "value": parsed_invalid}], 
        expected_status=False
    )
    
    assert res_fail.status_code == 400, f"El template {template_code} falló al bloquear el valor inválido: '{parsed_invalid}'"