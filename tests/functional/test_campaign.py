"""
test_campaign.py
================
Tests funcionales para creación y edición de campañas.

Cubre:
  - Creación básica (B2B / B2C / sin audiencia)
  - Validaciones de workspace y lead_flow
  - Unicidad de nombre (activas e inactivas)
  - Control de acceso en update (creador / no-creador / superuser)
  - Validaciones de negocio en update (nombre duplicado, cambio de flow)
  - Filtros dinámicos permitidos y no permitidos
"""
import pytest
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.organization import Organization
from tests.fixtures.user_fixtures import _make_user, _link_user_to_org, as_user


# ======================================================================
# FIXTURES LOCALES
# ======================================================================

@pytest.fixture
def two_users(db_session, initial_structure):
    """Dos usuarios regulares (no superadmin) vinculados a la organización de prueba."""
    org_id = initial_structure["org_id"]
    creator  = _make_user(db_session, "Camp Creator",  f"camp_creator_{org_id}@test.com")
    outsider = _make_user(db_session, "Camp Outsider", f"camp_outsider_{org_id}@test.com")
    _link_user_to_org(db_session, creator,  org_id)
    _link_user_to_org(db_session, outsider, org_id)
    db_session.commit()
    return {"creator": creator, "outsider": outsider, "org_id": org_id}


@pytest.fixture
def second_org_flow(db_session):
    """Organización y lead_flow ajenos para tests de cross-org."""
    other_org = Organization(name="Org Ajena Campaign Tests")
    db_session.add(other_org)
    db_session.flush()
    other_flow = LeadFlow(name="Flow Ajeno", organization_id=other_org.id)
    db_session.add(other_flow)
    db_session.commit()
    return {"org_id": other_org.id, "flow_id": other_flow.id}


# ======================================================================
# CREAR CAMPAÑA — BÁSICOS
# ======================================================================

def test_campaign_create_success(api, initial_structure):
    """Crear una campaña sin target_audience retorna 200 y no genera campos por defecto."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    camp = api.create_campaign(workspace_id=ws_id, name="Campaña Nueva", lead_flow_id=lf_id, expected_status=200)

    assert camp["id"] is not None
    assert camp["name"] == "Campaña Nueva"
    assert camp["workspace_id"] == ws_id
    assert camp["lead_flow_id"] == lf_id

    res_fields = api.client.get(f"/lead_fields/?campaign_id={camp['id']}", headers=api.headers)
    assert res_fields.json().get("items", []) == []


def test_campaign_create_b2b_injects_five_fields_in_order(api, initial_structure):
    """
    B2B debe inyectar exactamente 5 campos con órdenes consecutivos 1-5 sin gaps.
    Regresión: antes existía un gap (1,2,4,5,6). El orden 3 (Teléfono) estaba ausente.
    """
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    res = api.client.post("/campaigns/", json={
        "name": "Campaña B2B",
        "workspace_id": ws_id,
        "lead_flow_id": lf_id,
        "target_audience": "B2B",
        "is_public": True,
    }, headers=api.headers)
    assert res.status_code == 200, res.text
    camp_id = res.json()["id"]

    fields_res = api.client.get(f"/lead_fields/?campaign_id={camp_id}", headers=api.headers)
    fields = fields_res.json().get("items", [])

    assert len(fields) == 5, f"Esperaba 5 campos B2B, obtuvo {len(fields)}"
    orders = sorted(f["order"] for f in fields)
    assert orders == [1, 2, 3, 4, 5], f"Gap en órdenes B2B: {orders}"

    by_order = {f["order"]: f["name"] for f in fields}
    assert by_order[3] == "Teléfono", "El campo en posición 3 debería ser 'Teléfono'"
    assert by_order[4] == "Email"
    assert by_order[5] == "Sitio Web"


def test_campaign_create_b2c_injects_four_fields(api, initial_structure):
    """B2C debe inyectar exactamente 4 campos con órdenes 1-4."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    res = api.client.post("/campaigns/", json={
        "name": "Campaña B2C",
        "workspace_id": ws_id,
        "lead_flow_id": lf_id,
        "target_audience": "B2C",
        "is_public": True,
    }, headers=api.headers)
    assert res.status_code == 200, res.text
    camp_id = res.json()["id"]

    fields_res = api.client.get(f"/lead_fields/?campaign_id={camp_id}", headers=api.headers)
    fields = fields_res.json().get("items", [])

    assert len(fields) == 4, f"Esperaba 4 campos B2C, obtuvo {len(fields)}"
    orders = sorted(f["order"] for f in fields)
    assert orders == [1, 2, 3, 4]
    by_order = {f["order"]: f["name"] for f in fields}
    assert by_order[1] == "Nombre Completo"
    assert by_order[4] == "Fecha de Nacimiento"


def test_campaign_create_unknown_target_audience_creates_no_fields(api, initial_structure):
    """
    Un target_audience desconocido o vacío no crea campos y no lanza error.
    Es comportamiento intencional: el usuario elige los campos manualmente.
    """
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    res = api.client.post("/campaigns/", json={
        "name": "Campaña Sin Audiencia",
        "workspace_id": ws_id,
        "lead_flow_id": lf_id,
        "target_audience": "DESCONOCIDO",
        "is_public": True,
    }, headers=api.headers)
    assert res.status_code == 200, res.text
    camp_id = res.json()["id"]

    fields_res = api.client.get(f"/lead_fields/?campaign_id={camp_id}", headers=api.headers)
    assert fields_res.json().get("items", []) == []


# ======================================================================
# CREAR CAMPAÑA — WORKSPACE Y LEAD FLOW
# ======================================================================

def test_campaign_create_invalid_workspace_returns_400(api, initial_structure):
    """Workspace inexistente debe retornar 400 con mensaje claro, no un 500."""
    lf_id = initial_structure["lead_flow_id"]

    res = api.client.post("/campaigns/", json={
        "name": "Camp WS Inválido",
        "workspace_id": 999999,
        "lead_flow_id": lf_id,
        "is_public": True,
    }, headers=api.headers)

    assert res.status_code == 400
    assert "workspace" in res.text.lower()


def test_campaign_create_invalid_workspace_without_lead_flow_no_crash(api):
    """
    Regresión crítica: workspace inválido + sin lead_flow_id no debe crashear.
    Antes del fix se accedía a workspace.organization_id cuando workspace era None,
    lanzando AttributeError en lugar del 400 esperado.
    """
    res = api.client.post("/campaigns/", json={
        "name": "Camp Crash Test",
        "workspace_id": 999999,
        "is_public": True,
    }, headers=api.headers)

    assert res.status_code == 400, (
        f"Esperaba 400 pero recibió {res.status_code}. "
        "Posible regresión: crash con AttributeError al acceder a workspace=None."
    )
    assert "workspace" in res.text.lower()


def test_campaign_create_without_lead_flow_uses_org_default(api, initial_structure):
    """Sin lead_flow_id el sistema debe asignar el flujo predeterminado de la organización."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    res = api.client.post("/campaigns/", json={
        "name": "Camp Flow Default",
        "workspace_id": ws_id,
        "is_public": True,
    }, headers=api.headers)
    assert res.status_code == 200, res.text
    assert res.json()["lead_flow_id"] == lf_id


def test_campaign_create_lead_flow_from_another_org_fails(api, initial_structure, second_org_flow):
    """Lead_flow de otra organización debe ser rechazado con 400."""
    ws_id = initial_structure["workspace_id"]

    res = api.client.post("/campaigns/", json={
        "name": "Camp Flow Ajeno",
        "workspace_id": ws_id,
        "lead_flow_id": second_org_flow["flow_id"],
        "is_public": True,
    }, headers=api.headers)

    assert res.status_code == 400
    body = res.text.lower()
    assert "lead_flow" in body or "organización" in body or "flujo" in body


# ======================================================================
# CREAR CAMPAÑA — UNICIDAD DE NOMBRE
# ======================================================================

def test_campaign_create_duplicate_name_same_workspace_fails(api, initial_structure):
    """Dos campañas con el mismo nombre en el mismo workspace deben fallar en el segundo intento."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    api.create_campaign(workspace_id=ws_id, name="Nombre Duplicado", lead_flow_id=lf_id, expected_status=200)
    res = api.create_campaign(workspace_id=ws_id, name="Nombre Duplicado", lead_flow_id=lf_id, expected_status=False)

    assert res.status_code == 400
    body = res.text.lower()
    assert "nombre" in body or "campaña" in body or "existe" in body


def test_campaign_create_same_name_different_workspace_ok(api, initial_structure):
    """El mismo nombre debe ser aceptado en workspaces distintos."""
    lf_id = initial_structure["lead_flow_id"]
    ws1 = api.create_workspace(name="WS Unicidad A")
    ws2 = api.create_workspace(name="WS Unicidad B")

    api.create_campaign(workspace_id=ws1["id"], name="Nombre Compartido WS", lead_flow_id=lf_id, expected_status=200)
    api.create_campaign(workspace_id=ws2["id"], name="Nombre Compartido WS", lead_flow_id=lf_id, expected_status=200)



# ======================================================================
# EDITAR CAMPAÑA — CONTROL DE ACCESO
# ======================================================================

def test_campaign_update_by_creator_succeeds(api, initial_structure, two_users):
    """El usuario que creó la campaña puede editarla."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    creator = two_users["creator"]

    with as_user(api, creator):
        camp = api.create_campaign(workspace_id=ws_id, name="Camp del Creador", lead_flow_id=lf_id, expected_status=200)
        res = api.client.put(f"/campaigns/{camp['id']}", json={"name": "Camp Editada por Creador"}, headers=api.headers)

    assert res.status_code == 200
    assert res.json()["name"] == "Camp Editada por Creador"


def test_campaign_update_by_non_creator_fails_with_403(api, initial_structure, two_users):
    """Un usuario que no creó la campaña debe recibir 403 al intentar editarla."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    creator  = two_users["creator"]
    outsider = two_users["outsider"]

    with as_user(api, creator):
        camp = api.create_campaign(workspace_id=ws_id, name="Camp Protegida", lead_flow_id=lf_id, expected_status=200)

    with as_user(api, outsider):
        res = api.client.put(f"/campaigns/{camp['id']}", json={"name": "Intento de Hijack"}, headers=api.headers)

    assert res.status_code == 403, f"Esperaba 403 pero recibió {res.status_code}: {res.text}"


def test_campaign_update_by_superuser_succeeds_regardless_of_creator(api, db_session, initial_structure):
    """Un superuser puede editar cualquier campaña aunque no la haya creado."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    org_id = initial_structure["org_id"]

    regular = _make_user(db_session, "Regular No Super", f"regular_nosuper_{org_id}@test.com")
    _link_user_to_org(db_session, regular, org_id)
    db_session.commit()

    # Crear campaña como usuario regular
    with as_user(api, regular):
        camp = api.create_campaign(workspace_id=ws_id, name="Camp de Regular", lead_flow_id=lf_id, expected_status=200)

    # Editar como superuser (el fixture 'api' usa superuser por defecto)
    res = api.client.put(f"/campaigns/{camp['id']}", json={"name": "Editada por Superuser"}, headers=api.headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Editada por Superuser"


# ======================================================================
# EDITAR CAMPAÑA — VALIDACIONES DE NEGOCIO
# ======================================================================

def test_campaign_update_duplicate_name_fails(api, initial_structure):
    """Cambiar el nombre a uno ya existente en el mismo workspace debe fallar con 400."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    api.create_campaign(workspace_id=ws_id, name="Nombre Ya Tomado", lead_flow_id=lf_id, expected_status=200)
    camp2 = api.create_campaign(workspace_id=ws_id, name="Nombre Libre", lead_flow_id=lf_id, expected_status=200)

    res = api.client.put(f"/campaigns/{camp2['id']}", json={"name": "Nombre Ya Tomado"}, headers=api.headers)

    assert res.status_code == 400
    body = res.text.lower()
    assert "nombre" in body or "campaña" in body or "existe" in body


def test_campaign_update_same_name_does_not_fail(api, initial_structure):
    """Editar una campaña enviando el mismo nombre actual no debe fallar."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    camp = api.create_campaign(workspace_id=ws_id, name="Nombre Sin Cambio", lead_flow_id=lf_id, expected_status=200)

    res = api.client.put(
        f"/campaigns/{camp['id']}",
        json={"name": "Nombre Sin Cambio", "description": "Solo cambio la descripción"},
        headers=api.headers
    )
    assert res.status_code == 200
    assert res.json()["description"] == "Solo cambio la descripción"



def test_campaign_update_lead_flow_with_leads_fails(api, db_session, initial_structure):
    """No se puede cambiar el lead_flow_id si la campaña ya tiene leads asignados."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    org_id = initial_structure["org_id"]

    camp = api.create_campaign(workspace_id=ws_id, name="Camp Con Leads", lead_flow_id=lf_id, expected_status=200)

    # Insertar un lead directamente en BD (mínimo requerido: campaign_id + organization_id)
    lead = Lead(campaign_id=camp["id"], organization_id=org_id)
    db_session.add(lead)
    db_session.flush()

    new_flow = LeadFlow(name="Flujo Alternativo Para Bloqueo", organization_id=org_id)
    db_session.add(new_flow)
    db_session.commit()

    res = api.client.put(f"/campaigns/{camp['id']}", json={"lead_flow_id": new_flow.id}, headers=api.headers)

    assert res.status_code == 400
    body = res.text.lower()
    assert "lead_flow_id" in body or "prospectos" in body or "leads" in body


def test_campaign_update_lead_flow_without_leads_ok(api, db_session, initial_structure):
    """Se puede cambiar el lead_flow_id si la campaña no tiene leads."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    org_id = initial_structure["org_id"]

    camp = api.create_campaign(workspace_id=ws_id, name="Camp Sin Leads Para Flow", lead_flow_id=lf_id, expected_status=200)

    new_flow = LeadFlow(name="Nuevo Flujo Permitido", organization_id=org_id)
    db_session.add(new_flow)
    db_session.flush()
    state = LeadState(
        lead_flow_id=new_flow.id, organization_id=org_id,
        name="Inicio Nuevo", category="OPEN", is_initial=True, order=1
    )
    db_session.add(state)
    db_session.commit()

    res = api.client.put(f"/campaigns/{camp['id']}", json={"lead_flow_id": new_flow.id}, headers=api.headers)

    assert res.status_code == 200
    assert res.json()["lead_flow_id"] == new_flow.id


def test_campaign_update_lead_flow_from_another_org_fails(api, initial_structure, second_org_flow):
    """Cambiar el lead_flow por uno de otra organización debe ser rechazado."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]

    camp = api.create_campaign(workspace_id=ws_id, name="Camp Flow Ajeno Update", lead_flow_id=lf_id, expected_status=200)

    res = api.client.put(f"/campaigns/{camp['id']}", json={"lead_flow_id": second_org_flow["flow_id"]}, headers=api.headers)

    assert res.status_code == 400
    body = res.text.lower()
    assert "lead_flow" in body or "organización" in body or "válido" in body


def test_campaign_update_nonexistent_returns_404(api, initial_structure):
    """Editar una campaña inexistente debe retornar 404."""
    res = api.client.put("/campaigns/999999", json={"name": "No Existe"}, headers=api.headers)
    assert res.status_code == 404


# ======================================================================
# FILTROS DINÁMICOS
# ======================================================================

def test_campaign_filter_by_workspace_id(api, initial_structure):
    """Filtrar por workspace_id devuelve solo las campañas de ese workspace."""
    lf_id = initial_structure["lead_flow_id"]
    ws1 = api.create_workspace("WS Filtro Camp A")
    ws2 = api.create_workspace("WS Filtro Camp B")
    api.create_campaign(workspace_id=ws1["id"], name="Camp WS1", lead_flow_id=lf_id)
    api.create_campaign(workspace_id=ws2["id"], name="Camp WS2", lead_flow_id=lf_id)

    res = api.client.get(f"/campaigns/?workspace_id={ws1['id']}", headers=api.headers)
    assert res.status_code == 200
    items = res.json().get("items", [])
    assert all(c["workspace_id"] == ws1["id"] for c in items)
    assert any(c["name"] == "Camp WS1" for c in items)
    assert not any(c["name"] == "Camp WS2" for c in items)


def test_campaign_filter_by_is_public(api, initial_structure):
    """Filtrar por is_public=false devuelve solo campañas privadas."""
    ws_id = initial_structure["workspace_id"]
    lf_id = initial_structure["lead_flow_id"]
    api.create_campaign(workspace_id=ws_id, name="Camp Pública Filtro",  lead_flow_id=lf_id, is_public=True)
    api.create_campaign(workspace_id=ws_id, name="Camp Privada Filtro", lead_flow_id=lf_id, is_public=False)

    res = api.client.get("/campaigns/?is_public=false", headers=api.headers)
    assert res.status_code == 200
    items = res.json().get("items", [])
    assert all(not c["is_public"] for c in items)
    assert any(c["name"] == "Camp Privada Filtro" for c in items)


def test_campaign_filter_disallowed_field_is_ignored_no_error(api, initial_structure):
    """
    Un filtro por campo no permitido (organization_id) debe ser ignorado
    silenciosamente sin causar error, devolviendo resultados normales.
    """
    res = api.client.get("/campaigns/?organization_id=99999", headers=api.headers)
    # No debe fallar con 400/500 — el campo se ignora
    assert res.status_code == 200
    # Debe seguir devolviendo las campañas visibles para el usuario (no filtra por organización ajena)
    items = res.json().get("items", [])
    assert isinstance(items, list)
