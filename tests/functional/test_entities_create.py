import pytest
import random

def test_create_and_update_full_hierarchy_flow(api):
    """
    Prueba la creación y actualización parcial (put) en cadena: 
    Org -> Workspace -> LeadFlow -> LeadState -> Transition -> Campaign -> Field -> Lead.
    Garantiza que ningún endpoint explote con 400/500 en escenarios básicos.
    """
    rnd = random.randint(1000, 9999)

    # 1. Organization
    res_org = api.create_organization(name=f"Org Test {rnd}")
    org_id = res_org["id"]
    
    # TRUCO MÁGICO: Actualizamos el ID del tenant en el helper. 
    api.org_id = org_id

    # put Org
    put_org = api.client.put(f"/organizations/{org_id}", json={"name": f"Org Update {rnd}"}, headers=api.headers)
    assert put_org.status_code == 200

    # 2. Workspace
    res_ws = api.create_workspace(name=f"WS Test {rnd}")
    ws_id = res_ws["id"]

    # put Workspace
    put_ws = api.client.put(f"/workspaces/{ws_id}", json={"name": f"WS Update {rnd}"}, headers=api.headers)
    assert put_ws.status_code == 200

    # 3. LeadFlow
    res_flow = api.client.post("/lead_flows/", json={"name": f"Flujo Test {rnd}"}, headers=api.headers)
    assert res_flow.status_code == 200, f"Fallo creando LeadFlow: {res_flow.text}"
    flow_id = res_flow.json()["id"]

    # put LeadFlow
    put_flow = api.client.put(f"/lead_flows/{flow_id}", json={"name": f"Flujo Update {rnd}"}, headers=api.headers)
    assert put_flow.status_code == 200

    # 4. LeadStates (Necesitamos al menos 2 para armar una transición y recibir leads)
    res_state_1 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Ingresado", "category": "OPEN", "is_initial": True
    }, headers=api.headers)
    assert res_state_1.status_code == 200
    state_1_id = res_state_1.json()["id"]

    res_state_2 = api.client.post("/lead_states/", json={
        "lead_flow_id": flow_id, "name": "Contactado", "category": "OPEN", "is_initial": False
    }, headers=api.headers)
    state_2_id = res_state_2.json()["id"]

    # put LeadState
    put_state = api.client.put(f"/lead_states/{state_1_id}", json={"name": "Nuevo Ingresado"}, headers=api.headers)
    assert put_state.status_code == 200

    # 5. LeadStateTransition
    res_trans = api.client.post("/lead_state_transitions/", json={
        "lead_flow_id": flow_id, "from_state_id": state_1_id, "to_state_id": state_2_id
    }, headers=api.headers)
    assert res_trans.status_code == 200

    # 6. Campaign
    res_camp = api.create_campaign(
        workspace_id=ws_id, 
        name=f"Camp {rnd}",
        lead_flow_id=flow_id
    )
    camp_id = res_camp["id"]

    # put Campaign
    put_camp = api.client.put(f"/campaigns/{camp_id}", json={"name": f"Camp Update {rnd}"}, headers=api.headers)
    assert put_camp.status_code == 200

    # 7. Lead Field
    res_field = api.create_lead_field(
        campaign_id=camp_id, 
        name="Campo Test", 
        field_type_code="STRING", 
        section_id=1, 
        expected_status=200
    )
    field_id = res_field["id"]

    # put Lead Field
    put_field = api.client.put(f"/lead_fields/{field_id}", json={"name": "Campo Test Editado"}, headers=api.headers)
    assert put_field.status_code == 200

    # 8. Lead
    # Si todo lo anterior funcionó, el Lead debería crearse sin problemas y nacer en el estado inicial
    res_lead = api.client.post("/leads/", json={
        "campaign_id": camp_id, 
        "values": [{"field_id": field_id, "value": "Dato de prueba"}]
    }, headers=api.headers)
    assert res_lead.status_code == 200
    lead_id = res_lead.json()["id"]

    # put Lead (Actualizamos solo el valor sin tocar su estado)
    put_lead = api.client.put(f"/leads/{lead_id}", json={
        "values": [{"field_id": field_id, "value": "Dato actualizado"}]
    }, headers=api.headers)
    assert put_lead.status_code == 200


def test_create_and_update_independent_entities(api, initial_structure):
    """
    Prueba entidades que no dependen estrictamente de la jerarquía principal
    (Nomencladores, Items de Nomencladores, Reglas de Validación).
    """
    camp_id = initial_structure["campaign_id"]
    rnd = random.randint(100, 999)
    
    # 1. Nomenclator
    res_nom = api.client.post("/nomenclators/", json={"name": f"Nom Test {rnd}"}, headers=api.headers)
    assert res_nom.status_code in [200, 201], f"Fallo Nomenclator: {res_nom.text}"
    nom_id = res_nom.json()["id"]

    # put Nomenclator
    put_nom = api.client.put(f"/nomenclators/{nom_id}", json={"name": f"Nom Editado {rnd}"}, headers=api.headers)
    assert put_nom.status_code == 200

    # 2. Nomenclator Item (Aprovechamos para probar la creación de las opciones del select)
    res_nom_item = api.client.post("/nomenclator_items/", json={
        "code": "OPT1", "value": "1", "nomenclator_id": nom_id, "parent_item_id": None
    }, headers=api.headers)
    assert res_nom_item.status_code == 200
    item_id = res_nom_item.json()["id"]

    # put Nomenclator Item
    put_item = api.client.put(f"/nomenclator_items/{item_id}", json={"value": "Opción 1 Editada"}, headers=api.headers)
    assert put_item.status_code == 200

    # 3. Validation Rule
    f_res = api.create_lead_field(
        campaign_id=camp_id, 
        name=f"FieldParaRegla_{rnd}", 
        field_type_code="INT"
    )
    field_id = f_res["id"]

    res_rule = api.create_rule(
        field_id=field_id,
        name="Regla Test",
        expression="value > 10",
        error_msg="Error Original",
        expected_status=200
    )
    rule_id = res_rule["id"]

    # PUT Validation Rule
    put_rule = api.client.put(f"/validation_rules/{rule_id}", json={"error_msg": "Error Actualizado"}, headers=api.headers)
    assert put_rule.status_code == 200