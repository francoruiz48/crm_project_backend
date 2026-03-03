import pytest
import json
from app.models.lead_field import LeadField
from app.models.lead import Lead
from app.models.campaign import Campaign

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def relationship_setup(api, db_session, initial_structure):
    """
    Setup: 
    - 1 Campaña Origen
    - 1 Campaña Destino
    - 2 Leads en Destino
    - 1 Campo 'LEAD' en Origen apuntando a Destino
    """
    org_id = initial_structure["org_id"]
    ws_id = initial_structure["workspace_id"]
    camp_source_id = initial_structure["campaign_id"]
    
    # Campaña Destino
    camp_target = Campaign(name="Campaña Destino (Pool)", workspace_id=ws_id, organization_id=org_id)
    db_session.add(camp_target)
    db_session.commit()

    # Campo simple en target para crear leads
    f_target_name = LeadField(name="Nombre Target", field_type_code="STRING", campaign_id=camp_target.id, order=1, lead_field_section_id=1, organization_id=org_id, active=True)
    db_session.add(f_target_name)
    db_session.commit()

    # Leads Target
    res_l1 = api.create_lead(
        campaign_id=camp_target.id, 
        values=[{"field_id": f_target_name.id, "value": "Lead Objetivo A"}],
        expected_status=200
    )
    lead_target_1_id = res_l1["id"]

    res_l2 = api.create_lead(
        campaign_id=camp_target.id, 
        values=[{"field_id": f_target_name.id, "value": "Lead Objetivo B"}],
        expected_status=200
    )
    lead_target_2_id = res_l2["id"]

    # Campo Relacional en Source
    res_field = api.client.post("/lead_fields/", json={
        "name": "Leads Amigos",
        "field_type_code": "LEAD",
        "campaign_id": camp_source_id,
        "related_campaign_id": camp_target.id,
        "order": 10,
        "lead_field_section_id": 1
    }, headers=api.headers)
    assert res_field.status_code == 200
    field_rel_id = res_field.json()["id"]

    return {
        "camp_source_id": camp_source_id,
        "camp_target_id": camp_target.id,
        "field_rel_id": field_rel_id,
        "target_ids": [lead_target_1_id, lead_target_2_id]
    }

# =============================================================================
# TESTS CRUD DE RELACIONES
# =============================================================================

def test_create_lead_with_relationships(api, relationship_setup):
    setup = relationship_setup
    
    data = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{
            "field_id": setup["field_rel_id"], 
            "value": setup["target_ids"] 
        }],
        expected_status=200
    )
    
    field_val = next(v for v in data["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(field_val["related_leads"]) == 2
    
    related_ids = [r["id"] for r in field_val["related_leads"]]
    assert set(related_ids) == set(setup["target_ids"])

def test_update_lead_relationships(api, relationship_setup):
    setup = relationship_setup
    target_1, target_2 = setup["target_ids"]

    # 1. Crear Lead
    res_create = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{"field_id": setup["field_rel_id"], "value": [target_1]}]
    )
    lead_id = res_create["id"]

    # 2. Update: Cambiar a Target 2
    res_upd = api.update_lead(
        lead_id=lead_id,
        campaign_id=setup["camp_source_id"], 
        values=[{"field_id": setup["field_rel_id"], "value": [target_2]}]
    )
    
    fv = next(v for v in res_upd["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(fv["related_leads"]) == 1
    assert fv["related_leads"][0]["id"] == target_2

    # 3. Update: Limpiar
    res_clear = api.update_lead(
        lead_id=lead_id,
        campaign_id=setup["camp_source_id"],
        values=[{"field_id": setup["field_rel_id"], "value": []}]
    )
    
    fv_clear = next(v for v in res_clear["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(fv_clear["related_leads"]) == 0

def test_delete_integrity_target_lead(api, relationship_setup):
    """Si borro un target, la relación desaparece del source."""
    setup = relationship_setup
    target_id = setup["target_ids"][0]

    # Crear Padre
    res_padre_create = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{"field_id": setup["field_rel_id"], "value": [target_id]}]
    )
    padre_id = res_padre_create["id"]

    # Borrar Target
    api.delete_lead(lead_id=target_id, expected_status=200)

    # Verificar Padre
    res_padre = api.get_lead(lead_id=padre_id, expected_status=200)
    
    fv = next(v for v in res_padre["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(fv["related_leads"]) == 0

def test_delete_integrity_source_lead_value(api, relationship_setup):
    """Si borro el source, el target sigue vivo."""
    setup = relationship_setup
    target_id = setup["target_ids"][0]

    res_padre = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{"field_id": setup["field_rel_id"], "value": [target_id]}]
    )
    padre_id = res_padre["id"]

    api.delete_lead(lead_id=padre_id, expected_status=200)

    api.get_lead(lead_id=target_id, expected_status=200)

# =============================================================================
# TESTS DE EDICIÓN DE CAMPO (Enviando objeto completo)
# =============================================================================

def test_update_field_fail_change_type(api, relationship_setup):
    f_id = relationship_setup["field_rel_id"]
    
    # 1. GET actual
    current_data = api.client.get(f"/lead_fields/{f_id}", headers=api.headers).json()
    
    # 2. Modificar tipo (prohibido)
    current_data["field_type_code"] = "STRING"
    
    # 3. PUT completo
    res = api.client.put(f"/lead_fields/{f_id}", json=current_data, headers=api.headers)
    
    assert res.status_code == 400, f"Se esperaba 400: {res.text}"
    assert "no se puede cambiar el tipo" in res.text.lower()

def test_update_field_fail_remove_related_campaign(api, relationship_setup):
    f_id = relationship_setup["field_rel_id"]

    # 1. GET actual
    current_data = api.client.get(f"/lead_fields/{f_id}", headers=api.headers).json()
    
    # 2. Nullify related_campaign (Prohibido para LEAD)
    current_data["related_campaign_id"] = None

    # 3. PUT completo
    res = api.client.put(f"/lead_fields/{f_id}", json=current_data, headers=api.headers)
    
    # NOTA: Si este test da 200, es porque falta validación en LeadFieldService.update
    assert res.status_code == 400, f"Se esperaba 400 al quitar related_campaign_id. {res.text}"

def test_update_field_change_related_campaign_constraints(api, relationship_setup):
    setup = relationship_setup
    f_id = setup["field_rel_id"]
    
    # Crear datos para bloquear
    api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{"field_id": f_id, "value": setup["target_ids"]}]
    )

    # 1. GET actual
    current_data = api.client.get(f"/lead_fields/{f_id}", headers=api.headers).json()
    
    # 2. Cambiar destino (prohibido si hay datos)
    current_data["related_campaign_id"] = setup["camp_source_id"]

    res_fail = api.client.put(f"/lead_fields/{f_id}", json=current_data, headers=api.headers)
    
    assert res_fail.status_code == 400, f"Se esperaba 400 por integridad. {res_fail.text}"
    assert "existen leads" in res_fail.text.lower()

def test_update_field_change_related_campaign_success(api, db_session, initial_structure):
    camp_source_id = initial_structure["campaign_id"]
    ws_id = initial_structure["workspace_id"]
    org_id = initial_structure["org_id"]
    
    # Crear campo virgen
    res_f = api.client.post("/lead_fields/", json={
        "name": "Amigos V2", "field_type_code": "LEAD", 
        "campaign_id": camp_source_id, "related_campaign_id": camp_source_id,
        "order": 1, "lead_field_section_id": 1
    }, headers=api.headers)
    f_id = res_f.json()["id"]

    # Nueva campaña
    camp_new = Campaign(name="Otra", workspace_id=ws_id, organization_id=org_id)
    db_session.add(camp_new)
    db_session.commit()

    # 1. GET
    current_data = api.client.get(f"/lead_fields/{f_id}", headers=api.headers).json()
    
    # 2. Modificar
    current_data["related_campaign_id"] = camp_new.id

    # 3. PUT
    res_ok = api.client.put(f"/lead_fields/{f_id}", json=current_data, headers=api.headers)
    
    assert res_ok.status_code == 200, f"Fallo al actualizar: {res_ok.text}"
    
    # [CORRECCIÓN]: Verificar dentro del objeto 'related_campaign'
    resp_json = res_ok.json()
    assert resp_json["related_campaign"]["id"] == camp_new.id

def test_create_lead_fail_cross_campaign_id(api, db_session, relationship_setup, initial_structure):
    """
    Intento de vincular un Lead de una campaña incorrecta.
    El campo espera leads de 'Camp_Target', pero enviamos uno de 'Camp_Extra'.
    """
    setup = relationship_setup

    # 1. Crear una Tercera Campaña "Extra" y un Lead ahí
    ws_id = initial_structure["workspace_id"]
    org_id = initial_structure["org_id"]
    camp_extra = Campaign(name="Campaña Extra", workspace_id=ws_id, organization_id=org_id)
    db_session.add(camp_extra)
    db_session.commit()
    
    f_dummy = LeadField(name="Dummy", field_type_code="STRING", campaign_id=camp_extra.id, order=1, lead_field_section_id=1, organization_id=org_id, active=True)
    db_session.add(f_dummy)
    db_session.commit()

    res_l3 = api.create_lead(
        campaign_id=camp_extra.id,
        values=[{"field_id": f_dummy.id, "value": "Lead Intruso"}]
    )
    lead_intruso_id = res_l3["id"]

    # 2. Intentar relacionar el Lead Intruso (Campaña Extra) en el campo que espera Campaña Target
    res_fail = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{
            "field_id": setup["field_rel_id"], 
            "value": [lead_intruso_id] # <--- ID Válido, pero campaña incorrecta
        }],
        expected_status=False
    )

    assert res_fail.status_code == 400
    assert "campaña" in res_fail.text.lower() 

def test_create_lead_fail_non_existent_id(api, relationship_setup):
    """
    Intento de vincular un ID que no existe en la BD.
    """
    setup = relationship_setup
    fake_id = 999999

    res_fail = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{
            "field_id": setup["field_rel_id"], 
            "value": [fake_id] 
        }],
        expected_status=False
    )

    assert res_fail.status_code == 400
    assert "inválidos" in res_fail.text.lower() or "no existe" in res_fail.text.lower()

def test_update_lead_fail_self_reference(api, relationship_setup):
    """
    Un lead no puede ser padre de sí mismo.
    """
    setup = relationship_setup
    
    # 1. Crear el Lead primero (sin relaciones)
    res_create = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[] 
    )
    lead_self_id = res_create["id"]

    # Creamos un campo autoreferencial rápido en la Source Campaign
    res_field = api.client.post("/lead_fields/", json={
        "name": "Auto Referencia", "field_type_code": "LEAD",
        "campaign_id": setup["camp_source_id"], 
        "related_campaign_id": setup["camp_source_id"], # Apunta a sí misma
        "order": 99, "lead_field_section_id": 1
    }, headers=api.headers)
    f_auto_id = res_field.json()["id"]

    # Intentamos el loop
    res_fail = api.update_lead(
        lead_id=lead_self_id,
        campaign_id=setup["camp_source_id"],
        values=[{"field_id": f_auto_id, "value": [lead_self_id]}],
        expected_status=False
    )

    assert res_fail.status_code == 400
    assert "relacionarse" in res_fail.text.lower()

def test_create_lead_handle_duplicate_ids(api, relationship_setup):
    """
    Si envío [ID_A, ID_A], el sistema debe ser robusto (deduplicar o fallar controlado).
    Lo ideal es que lo guarde una sola vez.
    """
    setup = relationship_setup
    target_id = setup["target_ids"][0]

    data = api.create_lead(
        campaign_id=setup["camp_source_id"],
        values=[{
            "field_id": setup["field_rel_id"], 
            "value": [target_id, target_id] # Duplicado
        }],
        expected_status=200
    )
    
    field_val = next(v for v in data["field_values"] if v["field_id"] == setup["field_rel_id"])
    
    # Verificar que solo se guardó 1
    assert len(field_val["related_leads"]) == 1
    assert field_val["related_leads"][0]["id"] == target_id