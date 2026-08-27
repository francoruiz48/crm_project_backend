"""
test_routing_access.py
======================
Tests de seguridad de acceso a workspaces, campaigns y leads.

Verifica los filtros de seguridad en WorkspaceRepository, CampaignRepository
y LeadRepository usando usuarios reales (no superadmin) via `as_user`.

Escenarios:
  - Top-Down:  equipo con acceso a workspace → ve las campaigns hijas
  - Bottom-Up: equipo con acceso a campaign → ve el workspace padre
  - Strict Agent vs Manager: visibilidad de leads en equipo no colaborativo
  - Superadmin bypass: el superadmin ignora todos los filtros
"""
import pytest
from app.models.campaign import Campaign
from app.models.workspace import Workspace
from tests.fixtures.user_fixtures import _make_user, _link_user_to_org, as_user
from tests.helpers.api_helpers import ApiClient


def _ids(resp) -> list:
    data = resp.json()
    if isinstance(data, list):
        return [item["id"] for item in data]
    if isinstance(data, dict):
        return [item["id"] for item in data.get("items", data.get("data", []))]
    return []


# ---------------------------------------------------------------------------
# Top-Down: equipo con acceso a workspace ve las campaigns dentro
# ---------------------------------------------------------------------------

def test_security_macro_top_down_and_containment_wall(api, db_session, initial_structure):
    """
    Un miembro con acceso de equipo a un workspace VE las campaigns privadas
    dentro de ese workspace. NO ve las campaigns de workspaces no concedidos.
    """
    org_id  = initial_structure["org_id"]
    flow_id = initial_structure["lead_flow_id"]

    # Crear un miembro regular (no owner, no superuser)
    member = _make_user(db_session, "Member TDC", f"member_tdc_{org_id}@test.com")
    _link_user_to_org(db_session, member, org_id)
    db_session.commit()

    # Superadmin crea dos workspaces y dos campaigns privadas
    ws_permitido = api.create_workspace("WS Permitido TDC", is_public=False)
    ws_prohibido = api.create_workspace("WS Prohibido TDC", is_public=False)
    camp_visible  = api.create_campaign(ws_permitido["id"], "Camp Visible",  lead_flow_id=flow_id, is_public=False)
    camp_oculta   = api.create_campaign(ws_prohibido["id"], "Camp Oculta",   lead_flow_id=flow_id, is_public=False)

    # Crear equipo, agregar member, dar acceso al workspace permitido
    team = api.create_team("Equipo TDC")
    # member.id sería el id interno de la fila ORM cruda (_make_user construye el User directo
    # en la DB, no vía API) -- POST /team_members/ espera el public_uuid (Fase 3).
    api.add_team_member(team["id"], member.public_uuid, role="AGENT")
    api.grant_workspace_access(team["id"], ws_permitido["id"])

    # Verificar desde el punto de vista del member
    member_api = ApiClient(api.client, org_id)
    with as_user(member_api, member):
        res_camps = api.client.get("/campaigns/", headers=member_api.headers)

    camp_ids = _ids(res_camps)
    assert camp_visible["id"] in camp_ids,  "Top-Down falló: el member no ve la campaign del workspace concedido."
    assert camp_oculta["id"] not in camp_ids, "Aislamiento roto: el member ve una campaign de un workspace no concedido."

    # Muro de contención: no puede acceder por ID directo a la campaign oculta
    with as_user(member_api, member):
        res_wall = api.client.get(f"/campaigns/{camp_oculta['id']}", headers=member_api.headers)
    assert res_wall.status_code == 404, "Muro roto: el member accedió directamente a una campaign prohibida."


# ---------------------------------------------------------------------------
# Bottom-Up: equipo con acceso a campaign ve el workspace padre
# ---------------------------------------------------------------------------

def test_security_macro_bottom_up(api, db_session, initial_structure):
    """
    Un miembro con acceso directo a una campaign VE también el workspace padre,
    aunque no tenga acceso explícito a ese workspace.
    """
    org_id  = initial_structure["org_id"]
    flow_id = initial_structure["lead_flow_id"]

    member = _make_user(db_session, "Member BU", f"member_bu_{org_id}@test.com")
    _link_user_to_org(db_session, member, org_id)
    db_session.commit()

    # Superadmin crea workspace privado y campaign privada dentro
    ws_padre   = api.create_workspace("WS Padre BU", is_public=False)
    camp_hija  = api.create_campaign(ws_padre["id"], "Camp Hija BU", lead_flow_id=flow_id, is_public=False)

    # Dar acceso al equipo directo a la campaign (no al workspace)
    team = api.create_team("Equipo BU")
    api.add_team_member(team["id"], member.public_uuid, role="AGENT")
    api.grant_campaign_access(team["id"], camp_hija["id"])

    member_api = ApiClient(api.client, org_id)
    with as_user(member_api, member):
        res_ws = api.client.get("/workspaces/", headers=member_api.headers)

    ws_ids = _ids(res_ws)
    assert ws_padre["id"] in ws_ids, "Bottom-Up falló: el member no ve el workspace padre de su campaign."


# ---------------------------------------------------------------------------
# Strict Agent vs Manager: visibilidad de leads en equipo no colaborativo
# ---------------------------------------------------------------------------

def test_security_micro_manager_vs_strict_agent(api, db_session, initial_structure):
    """
    En un equipo con is_visibility_shared=False:
      - AGENT solo ve sus leads asignados + leads sin asignar del equipo.
      - MANAGER ve todos los leads del equipo.
    """
    org_id  = initial_structure["org_id"]
    flow_id = initial_structure["lead_flow_id"]

    agent    = _make_user(db_session, "Agent Strict",   f"agent_strict_{org_id}@test.com")
    companero = _make_user(db_session, "Companero",     f"companero_{org_id}@test.com")
    _link_user_to_org(db_session, agent,     org_id, role_code="agent")
    _link_user_to_org(db_session, companero, org_id, role_code="agent")
    db_session.commit()

    # Crear workspace, campaign, equipo ESTRICTO (no colaborativo)
    ws   = api.create_workspace("WS Strict", is_public=False)
    camp = api.create_campaign(ws["id"], "Camp Strict", lead_flow_id=flow_id, is_public=False)

    team_strict = api.create_team("Equipo Estricto", is_visibility_shared=False)
    api.grant_workspace_access(team_strict["id"], ws["id"])

    agent_member    = api.add_team_member(team_strict["id"], agent.public_uuid,     role="AGENT")
    comp_member     = api.add_team_member(team_strict["id"], companero.public_uuid, role="AGENT")

    # Crear campo y leads
    f_base = api.create_lead_field(camp["id"], "Dato Strict", "STRING")

    lead_del_agent    = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead del Agent"}])
    lead_huerfano     = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead sin dueño"}])
    lead_del_companero = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead del Companero"}])

    # Asignar leads
    api.bulk_assign([lead_del_agent["id"]],     target_team_id=team_strict["id"], target_user_id=agent.public_uuid)
    api.bulk_assign([lead_huerfano["id"]],      target_team_id=team_strict["id"])
    api.bulk_assign([lead_del_companero["id"]], target_team_id=team_strict["id"], target_user_id=companero.public_uuid)

    agent_api = ApiClient(api.client, org_id)

    # --- Vista como AGENT ---
    with as_user(agent_api, agent):
        res_agent = api.client.get(f"/leads/?campaign_id={camp['id']}", headers=agent_api.headers)

    leads_agent = _ids(res_agent)
    assert lead_del_agent["id"] in leads_agent,    "Agent no ve su propio lead."
    assert lead_huerfano["id"] in leads_agent,     "Agent no ve el lead huérfano del equipo."
    assert lead_del_companero["id"] not in leads_agent, "Agent estricto ve el lead de su compañero."

    # Ascender agent a MANAGER
    api.client.put(f"/team_members/{agent_member['id']}", json={"role": "MANAGER"}, headers=api.headers)

    # --- Vista como MANAGER ---
    with as_user(agent_api, agent):
        res_mgr = api.client.get(f"/leads/?campaign_id={camp['id']}", headers=agent_api.headers)

    leads_mgr = _ids(res_mgr)
    assert lead_del_companero["id"] in leads_mgr, "Manager no ve los leads de sus subordinados."


# ---------------------------------------------------------------------------
# Superadmin bypass: ve TODO sin pertenecer a ningún equipo
# ---------------------------------------------------------------------------

def test_security_super_admin_bypass(api, db_session, initial_structure):
    """
    El superadmin ignora todos los filtros de seguridad y ve absolutamente
    todo, aunque los recursos sean privados y no pertenezca a ningún equipo.
    """
    org_id  = initial_structure["org_id"]
    flow_id = initial_structure["lead_flow_id"]

    # Un usuario regular crea recursos privados (como si fuera el dueño)
    otro = _make_user(db_session, "Otro Duenio", f"otro_{org_id}@test.com")
    _link_user_to_org(db_session, otro, org_id)
    db_session.commit()

    otro_api = ApiClient(api.client, org_id)

    with as_user(otro_api, otro):
        ws_secreto = api.client.post("/workspaces/",
                                     json={"name": "WS Area 51", "is_public": False},
                                     headers=otro_api.headers)
        assert ws_secreto.status_code == 200
        ws_id = ws_secreto.json()["id"]

        camp_secreta = api.client.post("/campaigns/", json={
            "name":         "Camp Top Secret",
            "workspace_id": ws_id,
            "lead_flow_id": flow_id,
            "is_public":    False,
        }, headers=otro_api.headers)
        assert camp_secreta.status_code == 200
        camp_id = camp_secreta.json()["id"]

    # El superadmin (api fixture) ve todo sin estar en ningún equipo
    res_list = api.client.get("/campaigns/", headers=api.headers)
    camp_ids = _ids(res_list)
    assert camp_id in camp_ids, "El superadmin no ve la campaign privada de otro usuario."

    res_direct = api.client.get(f"/campaigns/{camp_id}", headers=api.headers)
    assert res_direct.status_code == 200, "El superadmin fue bloqueado al acceder por ID."


# ---------------------------------------------------------------------------
# Equipo compartido: agente ve leads de sus compañeros
# ---------------------------------------------------------------------------

def test_security_micro_shared_team_agent_sees_all_leads(api, db_session, initial_structure):
    """
    En un equipo con is_visibility_shared=True (comportamiento por defecto),
    un AGENT ve TODOS los leads del equipo, incluyendo los asignados a sus compañeros.
    Es el caso espejo del test estricto (is_visibility_shared=False).
    """
    org_id  = initial_structure["org_id"]
    flow_id = initial_structure["lead_flow_id"]

    agent    = _make_user(db_session, "Agent Shared",    f"agent_shared_{org_id}@test.com")
    companero = _make_user(db_session, "Companero Shared", f"comp_shared_{org_id}@test.com")
    _link_user_to_org(db_session, agent,     org_id)
    _link_user_to_org(db_session, companero, org_id)
    db_session.commit()

    ws   = api.create_workspace("WS Shared", is_public=False)
    camp = api.create_campaign(ws["id"], "Camp Shared", lead_flow_id=flow_id, is_public=False)

    # Equipo compartido (is_visibility_shared=True → todos ven todos los leads)
    team_shared = api.create_team("Equipo Compartido", is_visibility_shared=True)
    api.grant_workspace_access(team_shared["id"], ws["id"])
    api.add_team_member(team_shared["id"], agent.public_uuid,     role="AGENT")
    api.add_team_member(team_shared["id"], companero.public_uuid, role="AGENT")

    f_base             = api.create_lead_field(camp["id"], "Dato Shared", "STRING")
    lead_del_companero = api.create_lead(camp["id"], [{"field_id": f_base["id"], "value": "Lead Compañero"}])
    api.bulk_assign([lead_del_companero["id"]], target_team_id=team_shared["id"], target_user_id=companero.public_uuid)

    agent_api = ApiClient(api.client, org_id)
    with as_user(agent_api, agent):
        res = api.client.get(f"/leads/?campaign_id={camp['id']}", headers=agent_api.headers)

    assert lead_del_companero["id"] in _ids(res), \
        "En equipo compartido, el AGENT debería ver los leads asignados a sus compañeros."
