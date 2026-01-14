import pytest
import json
from app.models.lead_field import LeadField
from app.models.lead import Lead
from app.models.campaign import Campaign

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def relationship_setup(client, db_session, initial_structure):
    """
    Setup: 
    - 1 Campaña Origen
    - 1 Campaña Destino
    - 2 Leads en Destino
    - 1 Campo 'LEAD' en Origen apuntando a Destino
    """
    ws_id = initial_structure["workspace"].id
    camp_source = initial_structure["campaign"]
    
    # Campaña Destino
    camp_target = Campaign(name="Campaña Destino (Pool)", workspace_id=ws_id)
    db_session.add(camp_target)
    db_session.commit()

    # Campo simple en target para crear leads
    f_target_name = LeadField(name="Nombre Target", field_type_code="STRING", campaign_id=camp_target.id, order=1, lead_field_section_id=1)
    db_session.add(f_target_name)
    db_session.commit()

    # Leads Target
    res_l1 = client.post("/leads/", json={
        "campaign_id": camp_target.id,
        "values": [{"field_id": f_target_name.id, "value": "Lead Objetivo A"}]
    })
    lead_target_1_id = res_l1.json()["id"]

    res_l2 = client.post("/leads/", json={
        "campaign_id": camp_target.id,
        "values": [{"field_id": f_target_name.id, "value": "Lead Objetivo B"}]
    })
    lead_target_2_id = res_l2.json()["id"]

    # Campo Relacional en Source
    res_field = client.post("/lead_fields/", json={
        "name": "Leads Amigos",
        "field_type_code": "LEAD",
        "campaign_id": camp_source.id,
        "related_campaign_id": camp_target.id,
        "order": 10,
        "lead_field_section_id": 1
    })
    assert res_field.status_code == 200
    field_rel_id = res_field.json()["id"]

    return {
        "camp_source_id": camp_source.id,
        "camp_target_id": camp_target.id,
        "field_rel_id": field_rel_id,
        "target_ids": [lead_target_1_id, lead_target_2_id]
    }

# =============================================================================
# TESTS CRUD DE RELACIONES
# =============================================================================

def test_create_lead_with_relationships(client, relationship_setup):
    setup = relationship_setup
    
    payload = {
        "campaign_id": setup["camp_source_id"],
        "values": [
            {
                "field_id": setup["field_rel_id"], 
                "value": setup["target_ids"] 
            }
        ]
    }

    res = client.post("/leads/", json=payload)
    assert res.status_code == 200, f"Error al crear: {res.text}"
    
    data = res.json()
    field_val = next(v for v in data["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(field_val["related_leads"]) == 2
    
    related_ids = [r["id"] for r in field_val["related_leads"]]
    assert set(related_ids) == set(setup["target_ids"])

def test_update_lead_relationships(client, relationship_setup):
    setup = relationship_setup
    target_1, target_2 = setup["target_ids"]

    # 1. Crear Lead
    res_create = client.post("/leads/", json={
        "campaign_id": setup["camp_source_id"],
        "values": [{"field_id": setup["field_rel_id"], "value": [target_1]}]
    })
    lead_id = res_create.json()["id"]

    # 2. Update: Cambiar a Target 2
    # [CORRECCIÓN]: Se envía 'campaign_id' (el original) porque el schema lo exige.
    res_upd = client.put(f"/leads/{lead_id}", json={
        "campaign_id": setup["camp_source_id"], 
        "values": [{"field_id": setup["field_rel_id"], "value": [target_2]}]
    })
    assert res_upd.status_code == 200, f"Error al actualizar: {res_upd.text}"
    
    fv = next(v for v in res_upd.json()["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(fv["related_leads"]) == 1
    assert fv["related_leads"][0]["id"] == target_2

    # 3. Update: Limpiar
    res_clear = client.put(f"/leads/{lead_id}", json={
        "campaign_id": setup["camp_source_id"],
        "values": [{"field_id": setup["field_rel_id"], "value": []}]
    })
    assert res_clear.status_code == 200, f"Error al limpiar: {res_clear.text}"
    
    fv_clear = next(v for v in res_clear.json()["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(fv_clear["related_leads"]) == 0

def test_delete_integrity_target_lead(client, relationship_setup):
    """Si borro un target, la relación desaparece del source."""
    setup = relationship_setup
    target_id = setup["target_ids"][0]

    # Crear Padre
    res = client.post("/leads/", json={
        "campaign_id": setup["camp_source_id"],
        "values": [{"field_id": setup["field_rel_id"], "value": [target_id]}]
    })
    padre_id = res.json()["id"]

    # Borrar Target
    client.delete(f"/leads/{target_id}").raise_for_status()

    # Verificar Padre
    res_padre = client.get(f"/leads/{padre_id}")
    assert res_padre.status_code == 200
    
    fv = next(v for v in res_padre.json()["field_values"] if v["field_id"] == setup["field_rel_id"])
    assert len(fv["related_leads"]) == 0

def test_delete_integrity_source_lead_value(client, relationship_setup):
    """Si borro el source, el target sigue vivo."""
    setup = relationship_setup
    target_id = setup["target_ids"][0]

    res = client.post("/leads/", json={
        "campaign_id": setup["camp_source_id"],
        "values": [{"field_id": setup["field_rel_id"], "value": [target_id]}]
    })
    padre_id = res.json()["id"]

    client.delete(f"/leads/{padre_id}").raise_for_status()

    res_hijo = client.get(f"/leads/{target_id}")
    assert res_hijo.status_code == 200

# =============================================================================
# TESTS DE EDICIÓN DE CAMPO (Enviando objeto completo)
# =============================================================================

def test_update_field_fail_change_type(client, relationship_setup):
    f_id = relationship_setup["field_rel_id"]
    
    # 1. GET actual
    current_data = client.get(f"/lead_fields/{f_id}").json()
    
    # 2. Modificar tipo (prohibido)
    current_data["field_type_code"] = "STRING"
    
    # 3. PUT completo
    res = client.put(f"/lead_fields/{f_id}", json=current_data)
    
    assert res.status_code == 400, f"Se esperaba 400: {res.text}"
    assert "no se puede cambiar el tipo" in res.text.lower()

def test_update_field_fail_remove_related_campaign(client, relationship_setup):
    f_id = relationship_setup["field_rel_id"]

    # 1. GET actual
    current_data = client.get(f"/lead_fields/{f_id}").json()
    
    # 2. Nullify related_campaign (Prohibido para LEAD)
    current_data["related_campaign_id"] = None

    # 3. PUT completo
    res = client.put(f"/lead_fields/{f_id}", json=current_data)
    
    # NOTA: Si este test da 200, es porque falta validación en LeadFieldService.update
    assert res.status_code == 400, f"Se esperaba 400 al quitar related_campaign_id. {res.text}"

def test_update_field_change_related_campaign_constraints(client, relationship_setup):
    setup = relationship_setup
    f_id = setup["field_rel_id"]
    
    # Crear datos para bloquear
    client.post("/leads/", json={
        "campaign_id": setup["camp_source_id"],
        "values": [{"field_id": f_id, "value": setup["target_ids"]}]
    })

    # 1. GET actual
    current_data = client.get(f"/lead_fields/{f_id}").json()
    
    # 2. Cambiar destino (prohibido si hay datos)
    current_data["related_campaign_id"] = setup["camp_source_id"]

    res_fail = client.put(f"/lead_fields/{f_id}", json=current_data)
    
    assert res_fail.status_code == 400, f"Se esperaba 400 por integridad. {res_fail.text}"
    assert "existen leads" in res_fail.text.lower()

def test_update_field_change_related_campaign_success(client, db_session, initial_structure):
    camp_source = initial_structure["campaign"]
    
    # Crear campo virgen
    res_f = client.post("/lead_fields/", json={
        "name": "Amigos V2", "field_type_code": "LEAD", 
        "campaign_id": camp_source.id, "related_campaign_id": camp_source.id,
        "order": 1, "lead_field_section_id": 1
    })
    f_id = res_f.json()["id"]

    # Nueva campaña
    camp_new = Campaign(name="Otra", workspace_id=initial_structure["workspace"].id)
    db_session.add(camp_new)
    db_session.commit()

    # 1. GET
    current_data = client.get(f"/lead_fields/{f_id}").json()
    
    # 2. Modificar
    current_data["related_campaign_id"] = camp_new.id

    # 3. PUT
    res_ok = client.put(f"/lead_fields/{f_id}", json=current_data)
    
    assert res_ok.status_code == 200, f"Fallo al actualizar: {res_ok.text}"
    
    # [CORRECCIÓN]: Verificar dentro del objeto 'related_campaign'
    # La respuesta detallada devuelve un objeto, no el ID plano en la raíz
    resp_json = res_ok.json()
    assert resp_json["related_campaign"]["id"] == camp_new.id