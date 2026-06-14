"""
test_lead_views.py
==================
Tests de visibilidad de vistas de leads (LeadView).

LeadViewRepository.apply_security_filter implementa:
  - PRIVATE  → solo el creador y el owner del org ven la vista
  - TEAM     → solo miembros del equipo asignado + owner ven la vista
  - PUBLIC   → todos los miembros de la org ven la vista
  - is_superuser / is_owner → bypass completo (ven todas las vistas)
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


def _create_view(client, org_id, campaign_id, name, visibility, team_id=None):
    """Helper: crea una LeadView via la API con el contexto de org actual."""
    payload = {
        "name":        name,
        "campaign_id": campaign_id,
        "visibility":  visibility,
    }
    if team_id is not None:
        payload["team_id"] = team_id
    resp = client.post(
        "/lead_views/",
        json=payload,
        headers={"X-Organization-Id": str(org_id)},
    )
    assert resp.status_code == 200, f"Error creando vista: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# PRIVATE
# ---------------------------------------------------------------------------

class TestPrivateLeadView:

    def test_private_view_not_visible_to_other_member(self, api, db_session, initial_structure):
        """Una vista PRIVATE solo la ve su creador."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        other = _make_user(db_session, "Other Member PV", f"other_pv_{org_id}@test.com")
        _link_user_to_org(db_session, other, org_id)
        db_session.commit()

        # El superadmin crea una vista privada
        view = _create_view(api.client, org_id, camp_id, "Vista Privada SA", "PRIVATE")

        # El otro miembro no la ve
        other_api = ApiClient(api.client, org_id)
        with as_user(other_api, other):
            resp = api.client.get(
                f"/lead_views/?campaign_id={camp_id}",
                headers=other_api.headers,
            )

        assert view["id"] not in _ids(resp), "Un miembro no debería ver la vista PRIVATE de otro."

    def test_private_view_visible_to_creator(self, api, db_session, initial_structure):
        """El creador de una vista PRIVATE siempre la ve."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        creator = _make_user(db_session, "Creator PV", f"creator_pv_{org_id}@test.com")
        _link_user_to_org(db_session, creator, org_id)
        db_session.commit()

        creator_api = ApiClient(api.client, org_id)

        with as_user(creator_api, creator):
            view = _create_view(api.client, org_id, camp_id, "Vista Privada Creator", "PRIVATE")
            resp = api.client.get(
                f"/lead_views/?campaign_id={camp_id}",
                headers=creator_api.headers,
            )

        assert view["id"] in _ids(resp), "El creador no ve su propia vista PRIVATE."

    def test_private_view_visible_to_owner(self, api, db_session, initial_structure):
        """El owner de la org ve todas las vistas, incluyendo las PRIVATE de otros."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        creator = _make_user(db_session, "Creator for Owner", f"creator_owner_{org_id}@test.com")
        owner   = _make_user(db_session, "Owner PV",          f"owner_pv_{org_id}@test.com")
        _link_user_to_org(db_session, creator, org_id, is_owner=False)
        _link_user_to_org(db_session, owner,   org_id, is_owner=True)
        db_session.commit()

        creator_api = ApiClient(api.client, org_id)
        owner_api   = ApiClient(api.client, org_id)

        with as_user(creator_api, creator):
            view = _create_view(api.client, org_id, camp_id, "Vista Privada para Owner", "PRIVATE")

        with as_user(owner_api, owner, db_session):
            resp = api.client.get(
                f"/lead_views/?campaign_id={camp_id}",
                headers=owner_api.headers,
            )

        assert view["id"] in _ids(resp), "El owner no ve la vista PRIVATE de otro miembro."


# ---------------------------------------------------------------------------
# TEAM
# ---------------------------------------------------------------------------

class TestTeamLeadView:

    def test_team_view_visible_to_team_member(self, api, db_session, initial_structure):
        """Un miembro del equipo asignado VE la vista TEAM."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        member = _make_user(db_session, "Member TV", f"member_tv_{org_id}@test.com")
        _link_user_to_org(db_session, member, org_id)
        db_session.commit()

        # Crear equipo y agregar member
        team = api.create_team("Equipo Vista Team")
        api.add_team_member(team["id"], member.id, role="AGENT")

        # Superadmin crea vista de tipo TEAM asignada a ese equipo
        view = _create_view(api.client, org_id, camp_id, "Vista Team", "TEAM", team_id=team["id"])

        member_api = ApiClient(api.client, org_id)
        with as_user(member_api, member):
            resp = api.client.get(
                f"/lead_views/?campaign_id={camp_id}",
                headers=member_api.headers,
            )

        assert view["id"] in _ids(resp), "El miembro del equipo no ve la vista TEAM."

    def test_team_view_not_visible_to_outsider(self, api, db_session, initial_structure):
        """Un miembro que NO pertenece al equipo NO ve la vista TEAM."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        outsider = _make_user(db_session, "Outsider TV", f"outsider_tv_{org_id}@test.com")
        _link_user_to_org(db_session, outsider, org_id)
        db_session.commit()

        team = api.create_team("Equipo Vista Team Excl")
        # El outsider NO es agregado al equipo

        view = _create_view(api.client, org_id, camp_id, "Vista Team Excl", "TEAM", team_id=team["id"])

        outsider_api = ApiClient(api.client, org_id)
        with as_user(outsider_api, outsider):
            resp = api.client.get(
                f"/lead_views/?campaign_id={camp_id}",
                headers=outsider_api.headers,
            )

        assert view["id"] not in _ids(resp), "Un outsider no debería ver la vista TEAM."

    def test_team_view_visible_to_owner(self, api, db_session, initial_structure):
        """El owner ve todas las vistas TEAM aunque no pertenezca al equipo."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        owner = _make_user(db_session, "Owner TV", f"owner_tv_{org_id}@test.com")
        _link_user_to_org(db_session, owner, org_id, is_owner=True)
        db_session.commit()

        team = api.create_team("Equipo Vista Team Owner")
        # El owner no es miembro del equipo

        view = _create_view(api.client, org_id, camp_id, "Vista Team Owner", "TEAM", team_id=team["id"])

        owner_api = ApiClient(api.client, org_id)
        with as_user(owner_api, owner, db_session):
            resp = api.client.get(
                f"/lead_views/?campaign_id={camp_id}",
                headers=owner_api.headers,
            )

        assert view["id"] in _ids(resp), "El owner no ve la vista TEAM."


# ---------------------------------------------------------------------------
# PUBLIC
# ---------------------------------------------------------------------------

class TestPublicLeadView:

    def test_public_view_visible_to_all_members(self, api, db_session, initial_structure):
        """Cualquier miembro de la org ve una vista PUBLIC."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        member_a = _make_user(db_session, "Member A PUB", f"member_a_pub_{org_id}@test.com")
        member_b = _make_user(db_session, "Member B PUB", f"member_b_pub_{org_id}@test.com")
        _link_user_to_org(db_session, member_a, org_id)
        _link_user_to_org(db_session, member_b, org_id)
        db_session.commit()

        # Superadmin crea la vista pública
        view = _create_view(api.client, org_id, camp_id, "Vista Publica", "PUBLIC")

        api_a = ApiClient(api.client, org_id)
        api_b = ApiClient(api.client, org_id)

        with as_user(api_a, member_a):
            resp_a = api.client.get(f"/lead_views/?campaign_id={camp_id}", headers=api_a.headers)

        with as_user(api_b, member_b):
            resp_b = api.client.get(f"/lead_views/?campaign_id={camp_id}", headers=api_b.headers)

        assert view["id"] in _ids(resp_a), "Member A no ve la vista PUBLIC."
        assert view["id"] in _ids(resp_b), "Member B no ve la vista PUBLIC."

    def test_public_view_visible_to_member_without_team(self, api, db_session, initial_structure):
        """Una vista PUBLIC la ve incluso un miembro que no pertenece a ningún equipo."""
        org_id  = initial_structure["org_id"]
        camp_id = initial_structure["campaign_id"]

        loner = _make_user(db_session, "Loner PUB", f"loner_pub_{org_id}@test.com")
        _link_user_to_org(db_session, loner, org_id)
        db_session.commit()

        view = _create_view(api.client, org_id, camp_id, "Vista Publica Loner", "PUBLIC")

        loner_api = ApiClient(api.client, org_id)
        with as_user(loner_api, loner):
            resp = api.client.get(f"/lead_views/?campaign_id={camp_id}", headers=loner_api.headers)

        assert view["id"] in _ids(resp), "El miembro sin equipo no ve la vista PUBLIC."
