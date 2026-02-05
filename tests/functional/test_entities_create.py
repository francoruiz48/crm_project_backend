import pytest
import random

def test_create_full_hierarchy_flow(client):
    """
    Prueba la creación en cadena: Org -> Workspace -> Campaign -> Field
    Esto valida la integridad referencial y que los POST funcionen.
    """
    rnd = random.randint(1000, 9999)

    # 1. Organization
    org_payload = {"name": f"Org Test {rnd}", "description": "Auto test"}
    res_org = client.post("/organizations/", json=org_payload)
    assert res_org.status_code in [200, 201], f"Fallo Org: {res_org.text}"
    org_id = res_org.json()["id"]

    # 2. Workspace
    ws_payload = {"name": f"WS Test {rnd}", "organization_id": org_id}
    res_ws = client.post("/workspaces/", json=ws_payload)
    assert res_ws.status_code in [200, 201], f"Fallo WS: {res_ws.text}"
    ws_id = res_ws.json()["id"]

    # 3. Campaign
    camp_payload = {"name": f"Camp {rnd}", "workspace_id": ws_id, "active": True}
    res_camp = client.post("/campaigns/", json=camp_payload)
    assert res_camp.status_code in [200, 201], f"Fallo Campaign: {res_camp.text}"
    camp_id = res_camp.json()["id"]

    # 4. Lead Field
    field_payload = {
        "name": "Campo Test", 
        "field_type_code": "STRING", 
        "campaign_id": camp_id, 
        "lead_field_section_id": 1, # Asumiendo ID 1 existe
        "is_visible": True
    }
    res_field = client.post("/lead_fields/", json=field_payload)
    assert res_field.status_code in [200, 201], f"Fallo Field: {res_field.text}"

def test_create_independent_entities(client, initial_structure):
    """
    Prueba entidades que no dependen estrictamente de la jerarquía principal
    o que usan datos del fixture.
    """
    org_id = initial_structure["organization"].id
    
    # 1. Nomenclator
    nom_payload = {"name": "Nomenclador Test", "organization_id": org_id}
    res_nom = client.post("/nomenclators/", json=nom_payload)
    assert res_nom.status_code in [200, 201], f"Fallo Nomenclator: {res_nom.text}"

    # 2. Validation Rule (Manual)
    # Necesitamos un field_id valido
    camp_id = initial_structure["campaign"].id
    # Creamos un campo rápido para asignarle la regla
    f_res = client.post("/lead_fields/", json={
        "name": "FieldParaRegla", "field_type_code": "INT", 
        "campaign_id": camp_id, "lead_field_section_id": 1
    })
    field_id = f_res.json()["id"]

    rule_payload = {
        "name": "Regla Test",
        "field_id": field_id,
        "organization_id": org_id,
        "expression": "value > 10",
        "error_message": "Error",
        "active": True
    }
    res_rule = client.post("/validation_rules/", json=rule_payload)
    assert res_rule.status_code in [200, 201], f"Fallo Validation Rule: {res_rule.text}"