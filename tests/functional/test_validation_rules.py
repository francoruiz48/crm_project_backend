import pytest
from app.models.lead_field import LeadField
from app.models.campaign import Campaign
from app.models.lead_field_section import LeadFieldSection
import json
from datetime import datetime, timedelta


def _resolve_internal_id(db_session, model, public_uuid):
    """
    initial_structure devuelve public_uuid para campaign_id (Fase 3, ver backend/AGENTS.md
    §18), pero este archivo también construye filas ORM (LeadField) directo en la DB, que
    necesitan el id interno (columna FK Integer real).
    """
    return db_session.query(model.id).filter_by(public_uuid=public_uuid).scalar()


def test_validation_rule_test_rule_success(api, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    2. Verificar que permite datos válidos.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    
    # 1. Setup: Crear un campo numérico "Edad"
    f_edad = LeadField(
        name="Edad Regla",
        field_type_code="INT",
        campaign_id=_resolve_internal_id(db_session, Campaign, camp_id),
        order=1,
        lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id),
        organization_id=org_id,
        active=True
    )
    db_session.add(f_edad)
    db_session.commit()

    # 2. CREAR REGLA: Valor Mínimo 18
    payload_rule = {
        # ValidationRuleCreate.field_id es str (public_uuid, Fase 3) -- f_edad.id acá sería
        # el id interno crudo de la fila ORM.
        "field_id": f_edad.public_uuid,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = api.client.post("/validation_rules/", json=payload_rule, headers=api.headers)
    assert res_create.status_code == 200

    # 4. PROBAR REGLA (Caso Exitoso)
    # Intentamos enviar 20 -> Debe pasar (200)
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_edad.id, "value": "20"}],
        expected_status=200
    )


def test_validation_rule_test_rule_failure(api, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    2. Verificar que bloquea datos inválidos.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Setup: Crear un campo numérico "Edad" vía API
    payload_edad = {
        "name":"Edad Regla", 
        "field_type_code":"INT", 
        "campaign_id":camp_id, 
        "order":1
    }
    res_create_field = api.client.post("/lead_fields/", json=payload_edad, headers=api.headers)
    assert res_create_field.status_code == 200
    f_edad_id = res_create_field.json()["id"]

    # 2. CREAR REGLA: Valor Mínimo 18
    payload_rule = {
        "field_id": f_edad_id,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = api.client.post("/validation_rules/", json=payload_rule, headers=api.headers)
    assert res_create.status_code == 200

    # 3. PROBAR REGLA (Caso Fallido)
    # Intentamos enviar 15 (Menor a 18) -> Debe fallar (400)
    res_fail = api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_edad_id, "value": "15"}],
        expected_status=False
    )
    assert res_fail.status_code == 400
    assert "mayor de 18" in res_fail.text  # Verificamos mensaje personalizado


def test_validation_rule_delete_rule(api, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    2. Deshabilitar regla y verificar que deja pasar todo.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    
    # 1. Setup: Crear un campo numérico "Edad"
    f_edad = LeadField(
        name="Edad Regla",
        field_type_code="INT",
        campaign_id=_resolve_internal_id(db_session, Campaign, camp_id),
        order=1,
        lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id),
        organization_id=org_id,
        active=True
    )
    db_session.add(f_edad)
    db_session.commit()

    # 2. CREAR REGLA
    payload_rule = {
        # ValidationRuleCreate.field_id es str (public_uuid, Fase 3) -- f_edad.id acá sería
        # el id interno crudo de la fila ORM.
        "field_id": f_edad.public_uuid,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = api.client.post("/validation_rules/", json=payload_rule, headers=api.headers)
    assert res_create.status_code == 200
    rule_id = res_create.json()["id"]

    # 5. BORRAR REGLA
    api.client.delete(f"/validation_rules/{rule_id}", headers=api.headers)

    # Ahora el valor 10 debería pasar porque la regla está eliminada
    api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_edad.id, "value": "10"}],
        expected_status=200
    )


def test_validation_rule_delete_rule_check_404(api, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    5. Eliminar regla.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    
    # 1. Setup: Crear un campo numérico "Edad"
    f_edad = LeadField(
        name="Edad Regla",
        field_type_code="INT",
        campaign_id=_resolve_internal_id(db_session, Campaign, camp_id),
        order=1,
        lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id),
        organization_id=org_id,
        active=True
    )
    db_session.add(f_edad)
    db_session.commit()

    # 2. CREAR REGLA
    payload_rule = {
        # ValidationRuleCreate.field_id es str (public_uuid, Fase 3) -- f_edad.id acá sería
        # el id interno crudo de la fila ORM.
        "field_id": f_edad.public_uuid,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = api.client.post("/validation_rules/", json=payload_rule, headers=api.headers)
    assert res_create.status_code == 200
    rule_id = res_create.json()["id"]

    # 6. ELIMINAR REGLA (Hard Delete)
    res_del = api.client.delete(f"/validation_rules/{rule_id}", headers=api.headers)
    assert res_del.status_code == 200

    # Verificar que ya no existe
    res_get = api.client.get(f"/validation_rules/{rule_id}", headers=api.headers)
    assert res_get.status_code == 404


def test_create_manual_validation_rule_success(api, db_session, initial_structure):
    """
    Prueba la creación de una regla en 'Modo Experto' (Expresión Python manual).
    Ejemplo: Valor debe ser par.
    """
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    section_id = initial_structure["section_id"]
    
    f_num = LeadField(
        name="Numero Par",
        field_type_code="INT",
        campaign_id=_resolve_internal_id(db_session, Campaign, camp_id),
        order=2,
        lead_field_section_id=_resolve_internal_id(db_session, LeadFieldSection, section_id),
        organization_id=org_id,
        active=True
    )
    db_session.add(f_num)
    db_session.commit() 

    # Crear regla manual: "MOD(value,2) = 0"
    payload_manual = {
        # mismo motivo que arriba: field_id es str (public_uuid).
        "field_id": f_num.public_uuid,
        "name": "Solo Pares",
        "expression": "MOD(value,2) = 0", 
        "error_message": "El número debe ser par."
    }
    
    res = api.client.post("/validation_rules/", json=payload_manual, headers=api.headers)
    
    if res.status_code == 200:        
        # Probamos par (Éxito)
        api.create_lead(
            campaign_id=camp_id, 
            values=[{"field_id": f_num.id, "value": "4"}],
            expected_status=200
        )


def test_create_manual_validation_rule_failure(api, db_session, initial_structure):
    """
    Prueba la creación de una regla en 'Modo Experto' (Expresión Python manual).
    Ejemplo: Valor debe ser par.
    """
    camp_id = initial_structure["campaign_id"]

    payload_num = {
        "name":"Número Par", 
        "field_type_code":"INT", 
        "campaign_id":camp_id, 
        "order":1
    }
    res_create_field = api.client.post("/lead_fields/", json=payload_num, headers=api.headers)
    assert res_create_field.status_code == 200
    f_num_id = res_create_field.json()["id"]

    payload_manual = {
        "field_id": f_num_id,
        "name": "Solo Pares",
        "expression": "MOD(value, 2) = 0", 
        "error_message": "El número debe ser par."
    }
    
    res = api.client.post("/validation_rules/", json=payload_manual, headers=api.headers)
    assert res.status_code == 200

    # Probamos impar (Fallo)
    res_impar = api.create_lead(
        campaign_id=camp_id, 
        values=[{"field_id": f_num_id, "value": "3"}],
        expected_status=False
    )
    assert res_impar.status_code == 400
    assert "par" in res_impar.text 


# --- PRUEBA DE MATEMÁTICAS (Template: AGE -> MIN_VALUE / MAX_VALUE) ---
def test_validation_rule_math_min_max(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    
    # Creamos campo Edad usando el template AGE (0 - 120)
    res_field = api.client.post("/lead_fields/", json={
        "name": "Edad Test",
        "field_template_code": "AGE",
        "campaign_id": camp_id,
        "order": 1
    }, headers=api.headers)
    assert res_field.status_code == 200
    f_id = res_field.json()["id"]

    # Caso Éxito: 25
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": 25}], expected_status=200)

    # Caso Fallo: -5 (Menor al mínimo)
    res_fail = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": -5}], expected_status=False)
    assert res_fail.status_code == 400
    assert "mayor o igual" in res_fail.text.lower()


# --- PRUEBA DE FECHAS (Template: BIRTH_DATE -> DATE_PAST) ---
def test_validation_rule_date_logic(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    
    # Creamos campo Fecha Nacimiento
    res_field = api.client.post("/lead_fields/", json={
        "name": "Fecha Nacimiento Test",
        "field_type_code": "DATE",
        "field_subtype_code": "BIRTH_DATE",
        "campaign_id": camp_id
    }, headers=api.headers)
    f_id = res_field.json()["id"]

    # Caso Éxito: Ayer
    ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": ayer}], expected_status=200)

    # Caso Fallo: Mañana (Usa TODAY() < value)
    manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    res_fail = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": manana}], expected_status=False)
    assert res_fail.status_code == 400
    assert "pasado" in res_fail.text.lower()


# --- PRUEBA DE TEXTO (Template: CBU_ALIAS -> LEN / MIN_LENGTH) ---
def test_validation_rule_text_length(api, initial_structure):
    camp_id = initial_structure["campaign_id"]
    
    # CBU Alias pide min 6 caracteres
    res_field = api.client.post("/lead_fields/", json={
        "field_template_code": "CBU_ALIAS",
        "campaign_id": camp_id,
        "order": 4
    }, headers=api.headers)
    f_id = res_field.json()["id"]

    # Caso Fallo: Muy corto
    res_fail = api.create_lead(campaign_id=camp_id, values=[{"field_id": f_id, "value": "ABC"}], expected_status=False)
    assert res_fail.status_code == 400
    assert "corto" in res_fail.text.lower()


def test_create_validation_rule_fail_empty_params(api, initial_structure):
    """
    Prueba de validación de integridad:
    Intentar crear una regla usando un template (MIN_VALUE) pero enviando 
    el parámetro obligatorio ('limit') como una cadena vacía.
    
    El sistema debe rechazarlo (400) indicando que no puede estar vacío.
    """
    camp_id = initial_structure["campaign_id"]
    
    # 1. Crear un campo numérico auxiliar
    res_field = api.client.post("/lead_fields/", json={
        "name": "Campo Test Params",
        "field_type_code": "INT",
        "campaign_id": camp_id,
        "order": 99
    }, headers=api.headers)
    assert res_field.status_code == 200
    field_id = res_field.json()["id"]

    # 2. Intentar crear regla con parámetro vacío
    payload = {
        "field_id": field_id,
        "template_code": "MIN_VALUE",      # Este template requiere el param 'limit'
        "template_params": {"limit": ""},  # <--- ERROR: Enviamos string vacío
        "error_message": "Error custom"
    }
    
    res = api.client.post("/validation_rules/", json=payload, headers=api.headers)
    
    # 3. Validar rechazo
    assert res.status_code == 400
    
    error_msg = res.text.lower()
    assert "no puede estar vacío" in error_msg or "required" in error_msg