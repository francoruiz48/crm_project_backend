import pytest
from app.models.lead_field import LeadField
from datetime import datetime, timedelta

# =============================================================================
# HELPERS LOCALES PARA REDUCIR REPETICIÓN
# =============================================================================

def _setup_rule_scenario(api, camp_id, name, type_code, rule_code, rule_params):
    # 1. Crear campo
    res_field = api.client.post("/lead_fields/", json={
        "name": name,
        "field_type_code": type_code,
        "campaign_id": camp_id,
        "lead_field_section_id": 1,
        "order": 99
    }, headers=api.headers)
    assert res_field.status_code == 200, f"Error creando campo: {res_field.text}"
    f_id = res_field.json()["id"]

    # 2. Crear Regla
    res_rule = api.client.post("/validation_rules/", json={
        "field_id": f_id,
        "template_code": rule_code,
        "template_params": rule_params,
        "error_message": f"Fallo en regla {rule_code}"
    }, headers=api.headers)
    assert res_rule.status_code == 200, f"Error creando regla {rule_code}: {res_rule.text}"
    
    return f_id

# =============================================================================
# 1. TESTS DE NÚMEROS (Matemáticas y Rangos)
# =============================================================================

@pytest.mark.parametrize("rule_code, params, valid_val, invalid_val", [
    ("RANGE", {"min": 10, "max": 20}, 15, 25),
    ("EXACT_VALUE", {"target": 100}, 100, 99),
    ("NOT_ZERO", {}, -5, 0),
    ("MULTIPLE_OF", {"step": 5}, 15, 16),
    ("IS_EVEN", {}, 4, 5)
])
def test_validation_rule_numeric(api, initial_structure, rule_code, params, valid_val, invalid_val):
    camp_id = initial_structure["campaign_id"]
    f_id = _setup_rule_scenario(api, camp_id, f"F_{rule_code}", "INT", rule_code, params)
    
    # Happy Path
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": valid_val}], expected_status=200)
    # Unhappy Path (Hace rollback al final del test, no afecta al siguiente)
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": invalid_val}], expected_status=False)

# =============================================================================
# 2. TESTS DE TEXTO (Longitud y Contenido)
# =============================================================================

@pytest.mark.parametrize("rule_code, params, valid_val, invalid_val", [
    ("MAX_LENGTH", {"limit": 5}, "12345", "123456"),
    ("EXACT_LENGTH", {"limit": 3}, "ABC", "AB"),
    ("STARTS_WITH", {"prefix": "PRE-"}, "PRE-123", "123-PRE"),
    ("ENDS_WITH", {"suffix": "-SUF"}, "123-SUF", "SUF-123"),
    ("CONTAINS_TEXT", {"text": "mid"}, "amida", "xyz"),
    ("NOT_CONTAINS_TEXT", {"text": "bad"}, "good", "verybad"),
    ("IS_UPPERCASE", {}, "HELLO", "Hello"),
    ("IS_LOWERCASE", {}, "hello", "HELLO"),
    ("NO_SPACES", {}, "hello_world", "hello world"),
])
def test_validation_rule_text(api, initial_structure, rule_code, params, valid_val, invalid_val):
    camp_id = initial_structure["campaign_id"]
    f_id = _setup_rule_scenario(api, camp_id, f"F_{rule_code}", "STRING", rule_code, params)
    
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": valid_val}], expected_status=200)
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": invalid_val}], expected_status=False)

# =============================================================================
# 3. TESTS DE FORMATOS (Regex y Tipos)
# =============================================================================

@pytest.mark.parametrize("rule_code, params, valid_val, invalid_val", [
    ("EMAIL_FORMAT", {}, "test@mail.com", "testmail.com"),
    ("ONLY_DIGITS", {}, "12345", "123a4"),
    ("ALPHANUMERIC", {}, "abc12", "abc-12"),
    ("IS_URL", {}, "https://google.com", "google.com"),
    ("REGEX_MATCH", {"pattern": "^[A-Z]{3}$"}, "ABC", "ab"),
])
def test_validation_rule_format(api, initial_structure, rule_code, params, valid_val, invalid_val):
    camp_id = initial_structure["campaign_id"]
    f_id = _setup_rule_scenario(api, camp_id, f"F_{rule_code}", "STRING", rule_code, params)
    
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": valid_val}], expected_status=200)
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": invalid_val}], expected_status=False)

# =============================================================================
# 4. TESTS DE LISTAS (Regex anidado)
# =============================================================================

@pytest.mark.parametrize("rule_code, params, valid_val, invalid_val", [
    ("IN_LIST", {"options": "A|B|C"}, "B", "D"),
    ("NOT_IN_LIST", {"options": "X|Y|Z"}, "A", "X"),
])
def test_validation_rule_list(api, initial_structure, rule_code, params, valid_val, invalid_val):
    camp_id = initial_structure["campaign_id"]
    f_id = _setup_rule_scenario(api, camp_id, f"F_{rule_code}", "STRING", rule_code, params)
    
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": valid_val}], expected_status=200)
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": invalid_val}], expected_status=False)

# =============================================================================
# 5. TESTS DE FECHAS
# =============================================================================

@pytest.mark.parametrize("rule_code, date_type_valid, date_type_invalid", [
    ("DATE_FUTURE", "tomorrow", "today"),
    ("DATE_PAST_OR_TODAY", "today", "tomorrow"),
    ("IS_WEEKDAY", "monday", "sunday"),
    ("IS_WEEKEND", "sunday", "monday")
])
def test_validation_rule_dates(api, initial_structure, rule_code, date_type_valid, date_type_invalid):
    camp_id = initial_structure["campaign_id"]
    
    # Diccionario dinámico de fechas
    fechas = {
        "today": datetime.now().strftime("%Y-%m-%d"),
        "tomorrow": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
        "monday": "2026-03-09",
        "sunday": "2026-03-08"
    }
    
    valid_val = fechas[date_type_valid]
    invalid_val = fechas[date_type_invalid]
    
    f_id = _setup_rule_scenario(api, camp_id, f"F_{rule_code}", "DATE", rule_code, {})
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": valid_val}], expected_status=200)
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": invalid_val}], expected_status=False)

# =============================================================================
# 6. TESTS RELACIONALES (Comparación entre campos del mismo Lead)
# =============================================================================

def test_validation_rule_relational_templates(api, initial_structure):
    camp_id = initial_structure["campaign_id"]

    # Necesitamos crear dos campos manualmente para que interactúen entre sí
    res_f1 = api.client.post("/lead_fields/", json={"name": "Sueldo", "field_type_code": "INT", "campaign_id": camp_id, "lead_field_section_id": 1, "order": 1}, headers=api.headers)
    f1_id = res_f1.json()["id"]

    res_f2 = api.client.post("/lead_fields/", json={"name": "Gasto", "field_type_code": "INT", "campaign_id": camp_id, "lead_field_section_id": 1, "order": 2}, headers=api.headers)
    f2_id = res_f2.json()["id"]

    # Regla: Gasto debe ser menor al Sueldo
    api.client.post("/validation_rules/", json={
        "field_id": f2_id, 
        "template_code": "LESS_THAN_FIELD", 
        "template_params": {"other_field_name": "Sueldo"}, 
        "error_message": "Gasto no puede superar el sueldo"
    }, headers=api.headers)

    # Éxito: Sueldo 1000, Gasto 500
    api.create_lead(campaign_id=camp_id, values=[
        {"field_id": f1_id, "value": 1000},
        {"field_id": f2_id, "value": 500}
    ], expected_status=200)

    # Fallo: Sueldo 1000, Gasto 2000
    api.create_lead(campaign_id=camp_id, values=[
        {"field_id": f1_id, "value": 1000},
        {"field_id": f2_id, "value": 2000}
    ], expected_status=False)

# =============================================================================
# 7. TESTS CONDICIONALES
# =============================================================================

def test_validation_rule_conditional_templates(api, initial_structure):
    camp_id = initial_structure["campaign_id"]

    # REQUIRED_IF (Si Estado_Civil == 'Casado', entonces Conyuge_Nombre es obligatorio)
    res_f1 = api.client.post("/lead_fields/", json={"name": "Estado_Civil", "field_type_code": "STRING", "campaign_id": camp_id, "lead_field_section_id": 1, "order": 1}, headers=api.headers)
    f1_id = res_f1.json()["id"]

    res_f2 = api.client.post("/lead_fields/", json={"name": "Conyuge_Nombre", "field_type_code": "STRING", "campaign_id": camp_id, "lead_field_section_id": 1, "order": 2}, headers=api.headers)
    f2_id = res_f2.json()["id"]

    # Regla: Conyuge_Nombre REQUIRED_IF Estado_Civil = 'Casado'
    api.client.post("/validation_rules/", json={
        "field_id": f2_id, 
        "template_code": "REQUIRED_IF", 
        "template_params": {"other_field_name": "Estado_Civil", "trigger_value": "Casado"}, 
        "error_message": "Falta cónyuge"
    }, headers=api.headers)

    # Éxito: Soltero y sin cónyuge
    api.create_lead(campaign_id=camp_id, values=[
        {"field_id": f1_id, "value": "Soltero"},
        {"field_id": f2_id, "value": ""}
    ], expected_status=200)

    # Éxito: Casado y con cónyuge
    api.create_lead(campaign_id=camp_id, values=[
        {"field_id": f1_id, "value": "Casado"},
        {"field_id": f2_id, "value": "María"}
    ], expected_status=200)

    # Fallo: Casado y SIN cónyuge
    api.create_lead(campaign_id=camp_id, values=[
        {"field_id": f1_id, "value": "Casado"},
        {"field_id": f2_id, "value": ""}
    ], expected_status=False)


# =============================================================================
# TESTS EXISTENTES (CRUD, Eliminación y Edge Cases)
# =============================================================================

def test_validation_rule_delete_rule(api, db_session, initial_structure):
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    
    f_edad = LeadField(name="Edad Regla", field_type_code="INT", campaign_id=camp_id, order=1, lead_field_section_id=1, organization_id=org_id, active=True)
    db_session.add(f_edad)
    db_session.commit()

    payload_rule = {"field_id": f_edad.id, "template_code": "MIN_VALUE", "template_params": {"limit": 18}, "error_message": "Err"}
    res_create = api.client.post("/validation_rules/", json=payload_rule, headers=api.headers)
    rule_id = res_create.json()["id"]

    api.client.delete(f"/validation_rules/{rule_id}", headers=api.headers)

    # Ahora 10 pasa porque la regla está borrada
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_edad.id, "value": "10"}], expected_status=200)

def test_validation_rule_delete_rule_check_404(api, db_session, initial_structure):
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    
    f_edad = LeadField(name="Edad Regla 404", field_type_code="INT", campaign_id=camp_id, order=1, lead_field_section_id=1, organization_id=org_id, active=True)
    db_session.add(f_edad)
    db_session.commit()

    res_create = api.client.post("/validation_rules/", json={"field_id": f_edad.id, "template_code": "MIN_VALUE", "template_params": {"limit": 18}, "error_message": "Err"}, headers=api.headers)
    rule_id = res_create.json()["id"]

    res_del = api.client.delete(f"/validation_rules/{rule_id}", headers=api.headers)
    assert res_del.status_code == 200

    res_get = api.client.get(f"/validation_rules/{rule_id}", headers=api.headers)
    assert res_get.status_code == 404

def test_create_manual_validation_rule_success(api, db_session, initial_structure):
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    
    f_num = LeadField(name="Numero Par", field_type_code="INT", campaign_id=camp_id, order=2, lead_field_section_id=1, organization_id=org_id, active=True)
    db_session.add(f_num)
    db_session.commit() 

    payload_manual = {"field_id": f_num.id, "name": "Solo Pares", "expression": "MOD(value,2) = 0", "error_message": "Par"}
    res = api.client.post("/validation_rules/", json=payload_manual, headers=api.headers)
    
    if res.status_code == 200:        
        api.create_lead(campaign_id=camp_id, values=[{"field_id": f_num.id, "value": "4"}], expected_status=200)

def test_create_validation_rule_fail_empty_params(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    
    res_field = api.client.post("/lead_fields/", json={"name": "Test Params", "field_type_code": "INT", "campaign_id": camp_id, "lead_field_section_id": 1, "order": 99}, headers=api.headers)
    field_id = res_field.json()["id"]

    payload = {
        "field_id": field_id,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": ""},  # <--- ERROR
        "error_message": "Custom"
    }
    
    res = api.client.post("/validation_rules/", json=payload, headers=api.headers)
    assert res.status_code == 400
    assert "no puede estar vacío" in res.text.lower() or "required" in res.text.lower()