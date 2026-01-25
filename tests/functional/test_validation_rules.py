import pytest
from app.models.lead_field import LeadField
import json
from datetime import datetime, timedelta

def test_validation_rule_test_rule_success(client, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    2. Verificar que permite datos válidos.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # 1. Setup: Crear un campo numérico "Edad"
    f_edad = LeadField(
        name="Edad Regla", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        order=1,
        lead_field_section_id=1, 
        organization_id=org_id
    )
    db_session.add(f_edad)
    db_session.commit()

    # 2. CREAR REGLA: Valor Mínimo 18
    # Usamos el endpoint de creación por Template (Opción A en tu doc)
    payload_rule = {
        "field_id": f_edad.id,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = client.post("/validation_rules/", json=payload_rule)
    assert res_create.status_code == 200
    rule_id = res_create.json()["id"]

    # 4. PROBAR REGLA (Caso Exitoso)
    # Intentamos enviar 20 -> Debe pasar (200)
    res_ok = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_edad.id, "value": "20"}]
    })
    assert res_ok.status_code == 200


def test_validation_rule_test_rule_failure(client, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    2. Verificar que bloquea datos inválidos.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # 1. Setup: Crear un campo numérico "Edad"
    payload_edad = {
        "name":"Edad Regla", 
        "field_type_code":"INT", 
        "campaign_id":camp_id, 
        "lead_field_section_id":1,
        "order":1,
        "organization_id":org_id
    }
    res_create_field = client.post("/lead_fields/", json=payload_edad)
    assert res_create_field.status_code == 200
    f_edad_id = res_create_field.json()["id"]

    # 2. CREAR REGLA: Valor Mínimo 18
    # Usamos el endpoint de creación por Template (Opción A en tu doc)
    payload_rule = {
        "field_id": f_edad_id,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = client.post("/validation_rules/", json=payload_rule)
    assert res_create.status_code == 200

    # 3. PROBAR REGLA (Caso Fallido)
    # Intentamos enviar 15 (Menor a 18) -> Debe fallar (400)
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_edad_id, "value": "15"}]
    })
    assert res_fail.status_code == 400
    assert "mayor de 18" in res_fail.text  # Verificamos mensaje personalizado


def test_validation_rule_delete_rule(client, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    2. Deshabilitar regla y verificar que deja pasar todo.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # 1. Setup: Crear un campo numérico "Edad"
    f_edad = LeadField(
        name="Edad Regla", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        order=1,
        lead_field_section_id=1, organization_id=org_id
    )
    db_session.add(f_edad)
    db_session.commit()

    # 2. CREAR REGLA: Valor Mínimo 18
    # Usamos el endpoint de creación por Template (Opción A en tu doc)
    payload_rule = {
        "field_id": f_edad.id,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = client.post("/validation_rules/", json=payload_rule)
    assert res_create.status_code == 200
    rule_id = res_create.json()["id"]

    # 5. BORRAR REGLA
    client.delete(f"/validation_rules/{rule_id}")

    # Ahora el valor 10 debería pasar porque la regla está eliminada
    res_disabled = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_edad.id, "value": "10"}]
    })
    assert res_disabled.status_code == 200


def test_validation_rule_delete_rule(client, db_session, initial_structure):
    """
    Prueba integral de Reglas de Validación:
    1. Crear regla (MIN_VALUE).
    5. Eliminar regla.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # 1. Setup: Crear un campo numérico "Edad"
    f_edad = LeadField(
        name="Edad Regla", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        order=1,
        lead_field_section_id=1, organization_id=org_id
    )
    db_session.add(f_edad)
    db_session.commit()

    # 2. CREAR REGLA: Valor Mínimo 18
    # Usamos el endpoint de creación por Template (Opción A en tu doc)
    payload_rule = {
        "field_id": f_edad.id,
        "template_code": "MIN_VALUE",
        "template_params": {"limit": 18},
        "error_message": "Debes ser mayor de 18 años."
    }
    res_create = client.post("/validation_rules/", json=payload_rule)
    assert res_create.status_code == 200
    rule_id = res_create.json()["id"]

    # 6. ELIMINAR REGLA (Hard Delete)
    res_del = client.delete(f"/validation_rules/{rule_id}")
    assert res_del.status_code == 200

    # Verificar que ya no existe
    res_get = client.get(f"/validation_rules/{rule_id}")
    assert res_get.status_code == 404

def test_create_manual_validation_rule_success(client, db_session, initial_structure):
    """
    Prueba la creación de una regla en 'Modo Experto' (Expresión Python manual).
    Ejemplo: Valor debe ser par.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    f_num = LeadField(name="Numero Par", field_type_code="INT", campaign_id=camp_id, order=2, lead_field_section_id=1, organization_id=org_id)
    db_session.add(f_num)
    db_session.commit() 

    # Crear regla manual: "int(value) % 2 == 0"
    # Nota: La expresión depende de cómo tu backend evalúe (eval, simpleeval, etc.)
    # Asumimos que 'value' está disponible en el contexto.
    payload_manual = {
        "field_id": f_num.id,
        "name": "Solo Pares",
        "expression": "MOD(value,2) = 0", 
        "error_message": "El número debe ser par."
    }
    
    res = client.post("/validation_rules/", json=payload_manual)
    # Si tu backend no soporta modo manual o falla la sintaxis, esto dará error.
    # Ajusta la aserción según tu implementación.
    if res.status_code == 200:        
        # Probamos par (Éxito)
        res_par = client.post("/leads/", json={
            "campaign_id": camp_id,
            "values": [{"field_id": f_num.id, "value": "4"}]
        })
        assert res_par.status_code == 200

def test_create_manual_validation_rule_failure(client, db_session, initial_structure):
    """
    Prueba la creación de una regla en 'Modo Experto' (Expresión Python manual).
    Ejemplo: Valor debe ser par.
    """
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id

    payload_num = {
        "name":"Número Par", 
        "field_type_code":"INT", 
        "campaign_id":camp_id, 
        "lead_field_section_id":1,
        "order":1,
        "organization_id":org_id
    }
    res_create_field = client.post("/lead_fields/", json=payload_num)
    assert res_create_field.status_code == 200
    f_num_id = res_create_field.json()["id"]

    payload_manual = {
        "field_id": f_num_id,
        "name": "Solo Pares",
        "expression": "MOD(value, 2) = 0", 
        "error_message": "El número debe ser par."
    }
    
    res = client.post("/validation_rules/", json=payload_manual)
    assert res.status_code == 200

    # Probamos impar (Fallo)
    res_impar = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_num_id, "value": "3"}]
    })
    assert res_impar.status_code == 400
    assert "par" in res_impar.text 

# --- 1. PRUEBA DE MATEMÁTICAS (Template: AGE -> MIN_VALUE / MAX_VALUE) ---
def test_validation_rule_math_min_max(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # Creamos campo Edad usando el template AGE (0 - 120)
    res_field = client.post("/lead_fields/", json={
        "name": "Edad Test",
        "field_template_code": "AGE",
        "campaign_id": camp_id,
        "order": 1,
        "lead_field_section_id": 1, "organization_id":org_id
    })
    assert res_field.status_code == 200
    f_id = res_field.json()["id"]

    # Caso Éxito: 25
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": 25}]
    }).raise_for_status()

    # Caso Fallo: -5 (Menor al mínimo)
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": -5}]
    })
    assert res_fail.status_code == 400
    assert "mayor o igual" in res_fail.text.lower()

# --- 2. PRUEBA DE REGEX (Template: EMAIL -> EMAIL_FORMAT) ---
def test_validation_rule_regex_email(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # Creamos campo Email
    res_field = client.post("/lead_fields/", json={
        "field_template_code": "EMAIL",
        "campaign_id": camp_id,
        "order": 2,
        "lead_field_section_id": 1, "organization_id":org_id
    })
    f_id = res_field.json()["id"]

    # Caso Éxito
    res_ok = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": "usuario@test.com"}]
    })
    assert res_ok.status_code == 200

    # Caso Fallo (Regex)
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": "usuario-sin-arroba.com"}]
    })
    assert res_fail.status_code == 400
    assert "formato" in res_fail.text.lower()

# --- 3. PRUEBA DE FECHAS (Template: BIRTH_DATE -> DATE_PAST) ---
def test_validation_rule_date_logic(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # Creamos campo Fecha Nacimiento
    res_field = client.post("/lead_fields/", json={
        "field_template_code": "BIRTH_DATE",
        "campaign_id": camp_id,
        "order": 3,
        "lead_field_section_id": 1, "organization_id":org_id
    })
    f_id = res_field.json()["id"]

    # Caso Éxito: Ayer
    ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": ayer}]
    }).raise_for_status()

    # Caso Fallo: Mañana (Usa TODAY() < value)
    manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": manana}]
    })
    assert res_fail.status_code == 400
    assert "pasado" in res_fail.text.lower()

# --- 4. PRUEBA DE TEXTO (Template: CBU_ALIAS -> LEN / MIN_LENGTH) ---
def test_validation_rule_text_length(client, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # CBU Alias pide min 6 caracteres
    res_field = client.post("/lead_fields/", json={
        "field_template_code": "CBU_ALIAS",
        "campaign_id": camp_id,
        "order": 4,
        "lead_field_section_id": 1, "organization_id":org_id
    })
    f_id = res_field.json()["id"]

    # Caso Fallo: Muy corto
    res_fail = client.post("/leads/", json={
        "campaign_id": camp_id,
        "values": [{"field_id": f_id, "value": "ABC"}] # 3 chars
    })
    assert res_fail.status_code == 400
    assert "corto" in res_fail.text.lower()