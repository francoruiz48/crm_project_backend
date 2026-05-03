import pytest

# =============================================================================
# FIXTURE PARA EL ENTORNO DE ETIQUETAS
# =============================================================================

@pytest.fixture
def tags_setup(api):
    """
    Prepara un escenario limpio para probar etiquetas.
    Crea una organización, una campaña, un lead, una etiqueta válida y una etiqueta 'hacker' (de otra org).
    """
    # 1. Crear Organización propia para el test
    res_org = api.client.post("/organizations/", json={"name": "Org Tags Test"}, headers=api.headers).json()
    org_id = res_org["id"]
    
    old_org_id = api.org_id
    api.org_id = org_id

    # 2. Traer el flujo inyectado automáticamente y crear Campaña + Lead
    flows = api.client.get("/lead_flows/", headers=api.headers).json()["items"]
    flow_id = flows[0]["id"]
    
    ws = api.client.post("/workspaces/", json={"name": "WS Tags", "organization_id": org_id}, headers=api.headers).json()
    camp = api.client.post("/campaigns/", json={"name": "Campaña Tags", "workspace_id": ws["id"], "lead_flow_id": flow_id}, headers=api.headers).json()
    
    api.client.post("/lead_fields/", json={
        "campaign_id": camp["id"], 
        "name": "Nombre Dummy", 
        "field_type_code": "STRING"
    }, headers=api.headers)

    lead = api.client.post("/leads/", json={"campaign_id": camp["id"], "values": []}, headers=api.headers).json()

    # 3. Crear una etiqueta inicial válida
    tag = api.client.post("/tags/", json={"name": "VIP", "color": "#FFD700"}, headers=api.headers).json()

    # 4. Crear una organización y etiqueta "Hacker" para probar aislamiento
    api.org_id = old_org_id # Volvemos al contexto root temporalmente
    res_hacker = api.client.post("/organizations/", json={"name": "Org Hacker"}, headers=api.headers).json()
    api.org_id = res_hacker["id"]
    
    tag_hacker = api.client.post("/tags/", json={"name": "Etiqueta Maliciosa", "color": "#000000"}, headers=api.headers).json()

    # Volvemos a la org del test
    api.org_id = org_id

    yield {
        "org_id": org_id,
        "lead_id": lead["id"],
        "tag_vip_id": tag["id"],
        "hacker_tag_id": tag_hacker["id"]
    }

    # Limpieza final
    api.org_id = old_org_id


# =============================================================================
# TESTS DEL CRUD DE ETIQUETAS (TAGS)
# =============================================================================

def test_tag_create_success(api, tags_setup):
    """Debe permitir crear una etiqueta nueva con color."""
    res = api.client.post("/tags/", json={
        "name": "Urgente", "color": "#FF0000"
    }, headers=api.headers)
    
    assert res.status_code in (200, 201)
    assert res.json()["name"] == "Urgente"
    assert res.json()["color"] == "#FF0000"

def test_tag_create_duplicate_fails(api, tags_setup):
    """No debe permitir crear una etiqueta si el nombre ya existe en la organización."""
    # Intentamos crear otra que se llame "VIP" (ya creada en el fixture)
    res = api.client.post("/tags/", json={
        "name": "vip", "color": "#000000" 
    }, headers=api.headers)
    
    assert res.status_code == 400
    assert "Ya existe una etiqueta" in res.text

def test_tag_update_success(api, tags_setup):
    """Debe permitir actualizar el nombre y color de una etiqueta existente."""
    tag_id = tags_setup["tag_vip_id"]
    
    res = api.client.put(f"/tags/{tag_id}", json={
        "name": "Súper VIP", "color": "#FFFFFF"
    }, headers=api.headers)
    
    assert res.status_code == 200
    assert res.json()["name"] == "Súper VIP"

def test_tag_update_duplicate_fails(api, tags_setup):
    """Impide renombrar una etiqueta con un nombre que ya está en uso por otra."""
    # Creamos una etiqueta temporal
    tag_temp = api.client.post("/tags/", json={"name": "Normal"}, headers=api.headers).json()
    
    # Intentamos renombrarla a "VIP" (colisión)
    res = api.client.put(f"/tags/{tag_temp['id']}", json={
        "name": "VIP"
    }, headers=api.headers)
    
    assert res.status_code == 400
    assert "Ya existe una etiqueta" in res.text


# =============================================================================
# TESTS DE ASOCIACIÓN CON LEADS
# =============================================================================

def test_lead_assign_tags_success(api, tags_setup):
    """Debe asociar correctamente una etiqueta a un lead y devolverla en la respuesta."""
    lead_id = tags_setup["lead_id"]
    tag_id = tags_setup["tag_vip_id"]

    res = api.client.put(f"/leads/{lead_id}", json={
        "tag_ids": [tag_id]
    }, headers=api.headers)
    
    assert res.status_code == 200
    
    # Validamos que la etiqueta viaje en el LeadDetailedResponse
    tags_in_lead = res.json().get("tags", [])
    assert len(tags_in_lead) == 1
    assert tags_in_lead[0]["id"] == tag_id
    assert tags_in_lead[0]["name"] == "VIP"

def test_lead_clear_tags_success(api, tags_setup):
    """Debe permitir borrar todas las etiquetas de un lead enviando un array vacío."""
    lead_id = tags_setup["lead_id"]
    tag_id = tags_setup["tag_vip_id"]

    # 1. Asignamos primero la etiqueta
    api.client.put(f"/leads/{lead_id}", json={"tag_ids": [tag_id]}, headers=api.headers)
    
    # 2. Enviamos el array vacío para limpiar
    res = api.client.put(f"/leads/{lead_id}", json={
        "tag_ids": []
    }, headers=api.headers)
    
    assert res.status_code == 200
    assert len(res.json().get("tags", [])) == 0

def test_lead_assign_tags_hacker_fails(api, tags_setup):
    """Seguridad: Impide asignar a un lead una etiqueta que pertenece a otra organización."""
    lead_id = tags_setup["lead_id"]
    hacker_tag_id = tags_setup["hacker_tag_id"]

    res = api.client.put(f"/leads/{lead_id}", json={
        "tag_ids": [hacker_tag_id]
    }, headers=api.headers)
    
    assert res.status_code == 400
    assert "no pertenecen a tu organización" in res.text

def test_lead_assign_tags_invalid_id_fails(api, tags_setup):
    """Impide fallos de base de datos enviando IDs de etiquetas que no existen."""
    lead_id = tags_setup["lead_id"]

    res = api.client.put(f"/leads/{lead_id}", json={
        "tag_ids": [999999] # ID falso
    }, headers=api.headers)
    
    assert res.status_code == 400
    assert "no existen o no pertenecen" in res.text