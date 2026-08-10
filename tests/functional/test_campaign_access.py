"""
test_campaign_access.py
=======================
Tests de control de acceso a workspaces y campaigns privadas.

CampaignRepository / WorkspaceRepository aplican este filtro a usuarios
que NO son superadmin ni owner:

  Un miembro VE una campaign si:
    1. is_public = True
    2. La creó él mismo (created_by = user.id)
    3. Su equipo tiene acceso DIRECTO a esa campaign
    4. Su equipo tiene acceso al WORKSPACE padre (herencia top-down)

  Un miembro VE un workspace si:
    1. is_public = True
    2. Lo creó él mismo
    3. Su equipo tiene acceso DIRECTO a ese workspace
    4. Su equipo tiene acceso a alguna CAMPAIGN dentro (herencia bottom-up)

  Owner: bypass completo — ve todo en su org sin importar is_public.
"""
import pytest
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
# Baseline: campaigns y workspaces públicos son visibles para todos
# ---------------------------------------------------------------------------

class TestPublicVisibility:

    def test_public_campaign_visible_to_any_member(self, api, db_session, initial_structure):
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member Pub Camp", f"m_pub_camp_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws    = api.create_workspace("WS Pub Camp", is_public=True)
        camp  = api.create_campaign(ws["id"], "Camp Publica", lead_flow_id=flow_id, is_public=True)

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/campaigns/", headers=member_api.headers)

        assert camp["id"] in _ids(resp)

    def test_public_workspace_visible_to_any_member(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]

        member = _make_user(db_session, "Member Pub WS", f"m_pub_ws_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws = api.create_workspace("WS Publico", is_public=True)

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/workspaces/", headers=member_api.headers)

        assert ws["id"] in _ids(resp)


# ---------------------------------------------------------------------------
# Privado sin acceso: miembro no ve nada
# ---------------------------------------------------------------------------

class TestPrivateNoAccess:

    def test_member_cannot_see_private_campaign_without_team_access(self, api, db_session, initial_structure):
        """Un miembro sin equipo no ve campaigns privadas creadas por otros."""
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member NoAccess", f"m_noacc_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws   = api.create_workspace("WS Privado NoAcc", is_public=False)
        camp = api.create_campaign(ws["id"], "Camp Privada NoAcc", lead_flow_id=flow_id, is_public=False)

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/campaigns/", headers=member_api.headers)

        assert camp["id"] not in _ids(resp), "El miembro sin acceso ve una campaign privada."

    def test_member_cannot_see_private_workspace_without_team_access(self, api, db_session, initial_structure):
        org_id = initial_structure["org_id"]

        member = _make_user(db_session, "Member NoAccess WS", f"m_noacc_ws_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws = api.create_workspace("WS Privado NoAcc WS", is_public=False)

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/workspaces/", headers=member_api.headers)

        assert ws["id"] not in _ids(resp), "El miembro sin acceso ve un workspace privado."

    def test_member_gets_404_on_direct_access_to_private_campaign(self, api, db_session, initial_structure):
        """El muro de contención: acceso directo por ID también devuelve 404."""
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member Wall", f"m_wall_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws   = api.create_workspace("WS Muro", is_public=False)
        camp = api.create_campaign(ws["id"], "Camp Muro", lead_flow_id=flow_id, is_public=False)

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get(f"/campaigns/{camp['id']}", headers=member_api.headers)

        assert resp.status_code == 404, "Muro roto: el miembro accedió directamente a una campaign privada."


# ---------------------------------------------------------------------------
# Top-Down: acceso al workspace → ve las campaigns hijas
# ---------------------------------------------------------------------------

class TestTopDownAccess:

    def test_team_workspace_access_grants_visibility_of_child_campaigns(self, api, db_session, initial_structure):
        """
        Un equipo con acceso a un workspace privado HEREDA visibilidad
        de todas las campaigns privadas dentro de ese workspace.
        """
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member TopDown", f"m_td_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws    = api.create_workspace("WS TopDown", is_public=False)
        camp1 = api.create_campaign(ws["id"], "Camp TD 1", lead_flow_id=flow_id, is_public=False)
        camp2 = api.create_campaign(ws["id"], "Camp TD 2", lead_flow_id=flow_id, is_public=False)

        team = api.create_team("Equipo TopDown")
        # member.id sería el id interno de la fila ORM cruda (_make_user construye el User
        # directo en la DB, no vía API) -- POST /team_members/ espera el public_uuid (Fase 3).
        api.add_team_member(team["id"], member.public_uuid, role="AGENT")
        api.grant_workspace_access(team["id"], ws["id"])

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/campaigns/", headers=member_api.headers)

        camp_ids = _ids(resp)
        assert camp1["id"] in camp_ids, "Top-Down: camp1 no visible."
        assert camp2["id"] in camp_ids, "Top-Down: camp2 no visible."

    def test_team_workspace_access_does_not_grant_other_workspace_campaigns(self, api, db_session, initial_structure):
        """El acceso al WS-A no concede visibilidad de campaigns en WS-B."""
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member Aislado TD", f"m_ais_td_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws_a = api.create_workspace("WS Concedido",   is_public=False)
        ws_b = api.create_workspace("WS No Concedido", is_public=False)
        camp_a = api.create_campaign(ws_a["id"], "Camp Concedida",    lead_flow_id=flow_id, is_public=False)
        camp_b = api.create_campaign(ws_b["id"], "Camp No Concedida", lead_flow_id=flow_id, is_public=False)

        team = api.create_team("Equipo Solo WS-A")
        # member.id sería el id interno de la fila ORM cruda (_make_user construye el User
        # directo en la DB, no vía API) -- POST /team_members/ espera el public_uuid (Fase 3).
        api.add_team_member(team["id"], member.public_uuid, role="AGENT")
        api.grant_workspace_access(team["id"], ws_a["id"])

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/campaigns/", headers=member_api.headers)

        camp_ids = _ids(resp)
        assert camp_a["id"] in camp_ids,     "Camp del workspace concedido no es visible."
        assert camp_b["id"] not in camp_ids, "Camp de otro workspace no debería ser visible."


# ---------------------------------------------------------------------------
# Bottom-Up: acceso a campaign → ve el workspace padre
# ---------------------------------------------------------------------------

class TestBottomUpAccess:

    def test_team_campaign_access_grants_visibility_of_parent_workspace(self, api, db_session, initial_structure):
        """
        Un equipo con acceso directo a una campaign privada HEREDA visibilidad
        del workspace padre, aunque sea privado.
        """
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member BottomUp", f"m_bu_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws   = api.create_workspace("WS BottomUp", is_public=False)
        camp = api.create_campaign(ws["id"], "Camp BottomUp", lead_flow_id=flow_id, is_public=False)

        team = api.create_team("Equipo BottomUp")
        # member.id sería el id interno de la fila ORM cruda (_make_user construye el User
        # directo en la DB, no vía API) -- POST /team_members/ espera el public_uuid (Fase 3).
        api.add_team_member(team["id"], member.public_uuid, role="AGENT")
        api.grant_campaign_access(team["id"], camp["id"])

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp_ws = api.client.get("/workspaces/", headers=member_api.headers)

        assert ws["id"] in _ids(resp_ws), "Bottom-Up: el workspace padre no es visible."

    def test_campaign_direct_access_visible_in_campaign_list(self, api, db_session, initial_structure):
        """El acceso directo a una campaign la hace visible en la lista de campaigns."""
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        member = _make_user(db_session, "Member Direct Camp", f"m_dc_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        ws   = api.create_workspace("WS Direct Camp", is_public=False)
        camp = api.create_campaign(ws["id"], "Camp Direct", lead_flow_id=flow_id, is_public=False)

        team = api.create_team("Equipo Direct Camp")
        # member.id sería el id interno de la fila ORM cruda (_make_user construye el User
        # directo en la DB, no vía API) -- POST /team_members/ espera el public_uuid (Fase 3).
        api.add_team_member(team["id"], member.public_uuid, role="AGENT")
        api.grant_campaign_access(team["id"], camp["id"])

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get("/campaigns/", headers=member_api.headers)

        assert camp["id"] in _ids(resp), "La campaign con acceso directo no es visible en la lista."


# ---------------------------------------------------------------------------
# Owner bypass
# ---------------------------------------------------------------------------

class TestOwnerBypass:

    def test_owner_sees_all_private_campaigns(self, api, db_session, initial_structure):
        """El owner de la org ve todas las campaigns sin importar is_public."""
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        creator = _make_user(db_session, "Creator Owner Byp", f"creator_ob_{org_id}@test.com")
        owner   = _make_user(db_session, "Owner Bypass",      f"owner_ob_{org_id}@test.com")
        _link_user_to_org(db_session, creator, org_id, is_owner=False)
        _link_user_to_org(db_session, owner,   org_id, is_owner=True)
        db_session.commit()

        # Un miembro regular crea una campaign privada
        creator_api = ApiClient(api.client, org_id)
        with as_user(creator_api, creator):
            ws_resp = api.client.post(
                "/workspaces/",
                json={"name": "WS del Creator", "is_public": False},
                headers=creator_api.headers,
            )
            assert ws_resp.status_code == 200
            ws_id = ws_resp.json()["id"]

            camp_resp = api.client.post("/campaigns/", json={
                "name":         "Camp Privada del Creator",
                "workspace_id": ws_id,
                "lead_flow_id": flow_id,
                "is_public":    False,
            }, headers=creator_api.headers)
            assert camp_resp.status_code == 200
            camp_id = camp_resp.json()["id"]

        # El owner ve la campaign aunque no sea pública y no pertenezca a ningún equipo
        owner_api = ApiClient(api.client, org_id)
        with as_user(owner_api, owner, db_session):
            resp = api.client.get("/campaigns/", headers=owner_api.headers)

        assert camp_id in _ids(resp), "El owner no ve la campaign privada de otro miembro."

    def test_owner_sees_all_private_workspaces(self, api, db_session, initial_structure):
        """El owner ve todos los workspaces sin importar is_public."""
        org_id = initial_structure["org_id"]

        creator = _make_user(db_session, "Creator WS Owner", f"creator_ws_ob_{org_id}@test.com")
        owner   = _make_user(db_session, "Owner WS Bypass",  f"owner_ws_ob_{org_id}@test.com")
        _link_user_to_org(db_session, creator, org_id, is_owner=False)
        _link_user_to_org(db_session, owner,   org_id, is_owner=True)
        db_session.commit()

        creator_api = ApiClient(api.client, org_id)
        with as_user(creator_api, creator):
            ws_resp = api.client.post(
                "/workspaces/",
                json={"name": "WS Privado del Creator", "is_public": False},
                headers=creator_api.headers,
            )
            assert ws_resp.status_code == 200
            ws_id = ws_resp.json()["id"]

        owner_api = ApiClient(api.client, org_id)
        with as_user(owner_api, owner, db_session):
            resp = api.client.get("/workspaces/", headers=owner_api.headers)

        assert ws_id in _ids(resp), "El owner no ve el workspace privado de otro miembro."

    def test_member_who_created_private_campaign_can_see_it(self, api, db_session, initial_structure):
        """El creador de una campaign privada siempre la ve (created_by = user.id)."""
        org_id  = initial_structure["org_id"]
        flow_id = initial_structure["lead_flow_id"]

        creator = _make_user(db_session, "Self Creator", f"self_creator_{org_id}@test.com")
        _link_user_to_org(db_session, creator, org_id, is_owner=False)
        db_session.commit()

        creator_api = ApiClient(api.client, org_id)
        with as_user(creator_api, creator):
            ws_resp = api.client.post(
                "/workspaces/",
                json={"name": "WS Self", "is_public": False},
                headers=creator_api.headers,
            )
            ws_id = ws_resp.json()["id"]

            camp_resp = api.client.post("/campaigns/", json={
                "name":         "Camp Self",
                "workspace_id": ws_id,
                "lead_flow_id": flow_id,
                "is_public":    False,
            }, headers=creator_api.headers)
            camp_id = camp_resp.json()["id"]

            resp = api.client.get("/campaigns/", headers=creator_api.headers)

        assert camp_id in _ids(resp), "El creador no ve su propia campaign privada."
