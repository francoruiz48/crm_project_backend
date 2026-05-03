import pytest

# =============================================================================
# FIXTURE LOCAL (Aislado para estos tests)
# =============================================================================

@pytest.fixture
def api_with_states(api):
    """
    Crea una organización nueva a través del endpoint (Service) para garantizar 
    que se ejecute la lógica de inyección de estados de contacto por defecto.
    Luego cambia el contexto del cliente API para usar esa nueva organización.
    """
    res_org = api.client.post(
        "/organizations/", 
        json={"name": "Org Con Estados Inyectados"}, 
        headers=api.headers
    )
    new_org_id = res_org.json()["id"]

    # Guardamos la org anterior
    old_org_id = api.org_id
    
    # Seteamos la nueva org para que todos los requests del test apunten a ella
    api.org_id = new_org_id

    yield api

    # Restauramos el contexto al finalizar el test
    api.org_id = old_org_id


# =============================================================================
# TESTS DE INYECCIÓN DE PLANTILLAS
# =============================================================================

def test_organization_creation_injects_states_and_initial(api):
    """
    Test manual puro: Verifica que al crear una organización, nazca con 
    los 5 estados y que exactamente uno sea el inicial.
    (Usa el 'api' original para probar el endpoint de organizaciones)
    """
    res_org = api.client.post("/organizations/", json={"name": "Org Tests"}, headers=api.headers)
    new_org_id = res_org.json()["id"]

    old_org_id = api.org_id
    api.org_id = new_org_id

    res_states = api.client.get("/lead_contact_states/", headers=api.headers)
    states = res_states.json().get("items", [])

    api.org_id = old_org_id

    assert len(states) == 6, "Fallo al inyectar los 5 estados por defecto."
    
    initial_states = [s for s in states if s.get("is_initial") is True]
    assert len(initial_states) == 1, "Debe haber exactamente un estado inicial."
    assert initial_states[0]["name"] == "No Contactado", "El estado inicial debe ser 'No Contactado'."


# =============================================================================
# TESTS DE UNICIDAD DE NOMBRE (Usan el nuevo fixture)
# =============================================================================

def test_lead_contact_state_create_success(api_with_states):
    """Debe permitir crear un estado de contacto con un nombre nuevo."""
    res = api_with_states.client.post("/lead_contact_states/", json={
        "name": "Estado Único", "color": "#111111"
    }, headers=api_with_states.headers)
    
    assert res.status_code in (200, 201)
    assert res.json()["name"] == "Estado Único"

def test_lead_contact_state_create_duplicate_fails(api_with_states):
    """No debe permitir crear un estado si el nombre ya existe (case insensitive)."""
    # 'No Contactado' ya existe por el seed de la organización inyectada
    res = api_with_states.client.post("/lead_contact_states/", json={
        "name": "NO CONTACTADO", "color": "#222222"
    }, headers=api_with_states.headers)
    
    assert res.status_code == 400
    assert "Ya existe un estado de contacto" in res.text

def test_lead_contact_state_update_duplicate_fails(api_with_states):
    """No debe permitir renombrar un estado a un nombre que ya está en uso."""
    states = api_with_states.client.get("/lead_contact_states/", headers=api_with_states.headers).json()["items"]
    
    # Tomamos uno existente que NO sea 'No Contactado'
    state_to_edit = next(s for s in states if s["name"] == "En Conversación")

    # Intentamos renombrarlo para que colisione
    res = api_with_states.client.put(f"/lead_contact_states/{state_to_edit['id']}", json={
        "name": "no contactado"
    }, headers=api_with_states.headers)
    
    assert res.status_code == 400
    assert "Ya existe un estado de contacto" in res.text


# =============================================================================
# TESTS DE ESTADO INICIAL ÚNICO (Usan el nuevo fixture)
# =============================================================================

def test_lead_contact_state_create_second_initial_fails(api_with_states):
    """El sistema bloquea la creación de un nuevo estado marcado como inicial."""
    res = api_with_states.client.post("/lead_contact_states/", json={
        "name": "Intento de Inicio", "is_initial": True
    }, headers=api_with_states.headers)
    
    assert res.status_code == 400
    assert "Ya existe un estado inicial" in res.text

def test_lead_contact_state_prevent_uncheck_initial(api_with_states):
    """Impide que el único estado inicial pierda su marca, evitando que el sistema quede sin estado de entrada."""
    states = api_with_states.client.get("/lead_contact_states/", headers=api_with_states.headers).json()["items"]
    initial_state = next(s for s in states if s.get("is_initial") is True)

    res = api_with_states.client.put(f"/lead_contact_states/{initial_state['id']}", json={
        "is_initial": False
    }, headers=api_with_states.headers)
    
    assert res.status_code == 400
    assert "No puede quitar el estado inicial" in res.text