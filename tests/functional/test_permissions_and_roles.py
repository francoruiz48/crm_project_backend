"""
test_permissions_and_roles.py
=============================
Tests del sistema de permisos y roles implementado:

  1. Clonado de roles al crear una organización
  2. Permiso user:invite — quién puede invitar y con qué rol
  3. Permiso user:view_all — GET /users/ y GET /users/{id}
  4. promote_to_superuser requiere superadmin
  5. Visibilidad de leads según campaña pública / privada / lead:view_all
"""
import pytest
from app.core.constans import ADMIN_ORG_ID
from app.core.context import TENANT_ORG_ID
from app.core.security import hash_password, _get_current_user, get_current_user_roles
from app.models.campaign import Campaign
from app.models.lead import Lead
from app.models.lead_flow import LeadFlow
from app.models.lead_state import LeadState
from app.models.organization import Organization
from app.models.security_models import Permission, Role, User, UserOrganization
from app.models.workspace import Workspace
from tests.fixtures.user_fixtures import (
    _apply_user_overrides,
    _link_user_to_org,
    _make_user,
    _remove_user_overrides,
)


# ---------------------------------------------------------------------------
# Helpers locales
# ---------------------------------------------------------------------------

def _make_org_with_roles(db_session, name: str):
    """
    Crea una organización y clona los roles plantilla para ella,
    simulando lo que hace OrganizationService.create().
    """
    org = Organization(name=name, description="Test org con roles")
    db_session.add(org)
    db_session.flush()

    templates = db_session.query(Role).filter_by(organization_id=ADMIN_ORG_ID).all()
    cloned = {}
    for template in templates:
        new_role = Role(
            name=template.name,
            code=template.code,
            organization_id=org.id,
        )
        new_role.permissions = list(template.permissions)
        db_session.add(new_role)
        db_session.flush()
        cloned[template.code] = new_role

    db_session.commit()
    return org, cloned


def _make_campaign(db_session, org_id, name="Camp", is_public=True):
    lf = LeadFlow(name=f"Flow {name}", organization_id=org_id)
    db_session.add(lf)
    db_session.flush()

    ws = Workspace(name=f"WS {name}", organization_id=org_id)
    db_session.add(ws)
    db_session.flush()

    camp = Campaign(
        name=name,
        workspace_id=ws.id,
        lead_flow_id=lf.id,
        organization_id=org_id,
        is_public=is_public,
    )
    db_session.add(camp)
    db_session.flush()
    return camp


def _make_lead(db_session, campaign_id, org_id, created_by=None):
    # LeadResponse requiere current_state_id y current_state (non-optional),
    # así que creamos un estado inicial mínimo para que la serialización no falle.
    campaign = db_session.query(Campaign).filter_by(id=campaign_id).first()
    state = LeadState(
        name="Estado Inicial",
        lead_flow_id=campaign.lead_flow_id,
        organization_id=org_id,
    )
    db_session.add(state)
    db_session.flush()

    lead = Lead(
        campaign_id=campaign_id,
        organization_id=org_id,
        created_by=created_by,
        current_state_id=state.id,
    )
    db_session.add(lead)
    db_session.flush()
    return lead


def _login(plain_client, email, password):
    resp = plain_client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login falló: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Fixture: plain_client sin overrides de auth
# ---------------------------------------------------------------------------

@pytest.fixture
def plain_client(db_session):
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    from app.main import app
    from app.db.session import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.run_seeds"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


# ===========================================================================
# 1. CLONADO DE ROLES AL CREAR UNA ORGANIZACIÓN
# ===========================================================================

class TestRoleCloning:
    def test_cloned_roles_exist_for_org(self, db_session):
        """Al crear una org con roles clonados, existen admin/agent/viewer para esa org."""
        org, cloned = _make_org_with_roles(db_session, "Org Cloning Test")

        assert "admin" in cloned
        assert "agent" in cloned
        assert "viewer" in cloned

        # Todos son de la org, no globales
        for code, role in cloned.items():
            assert role.organization_id == org.id

    def test_admin_role_has_invite_permission(self, db_session):
        """El rol admin clonado tiene user:invite."""
        org, cloned = _make_org_with_roles(db_session, "Org Admin Perms")
        admin_codenames = [p.codename for p in cloned["admin"].permissions]
        assert "user:invite" in admin_codenames
        assert "user:view_all" in admin_codenames
        assert "lead:view_all" in admin_codenames

    def test_agent_role_lacks_restricted_permissions(self, db_session):
        """El rol agent NO tiene user:invite, user:view_all ni lead:view_all."""
        org, cloned = _make_org_with_roles(db_session, "Org Agent Perms")
        agent_codenames = [p.codename for p in cloned["agent"].permissions]
        assert "user:invite" not in agent_codenames
        assert "user:view_all" not in agent_codenames
        assert "lead:view_all" not in agent_codenames

    def test_viewer_role_is_read_only(self, db_session):
        """El rol viewer no tiene permisos de create/update/delete en leads."""
        org, cloned = _make_org_with_roles(db_session, "Org Viewer Perms")
        viewer_codenames = [p.codename for p in cloned["viewer"].permissions]
        assert "lead:create" not in viewer_codenames
        assert "lead:update" not in viewer_codenames
        assert "lead:delete" not in viewer_codenames
        assert "lead:view" in viewer_codenames

    def test_org_creation_via_api_clones_roles(self, client, db_session):
        """Crear una org vía API produce los roles clonados para esa org."""
        from app.main import app

        creator = _make_user(db_session, "Creator", "creator_roles@test.com")
        db_session.commit()

        _apply_user_overrides(app, creator)
        try:
            resp = client.post(
                "/organizations/",
                json={"name": "Org Via API"},
                headers={"X-Organization-Id": "1"},
            )
            assert resp.status_code == 200
            org_id = resp.json()["id"]
        finally:
            _remove_user_overrides(app)

        db_session.expire_all()
        admin_role = db_session.query(Role).filter_by(code="admin", organization_id=org_id).first()
        agent_role = db_session.query(Role).filter_by(code="agent", organization_id=org_id).first()
        viewer_role = db_session.query(Role).filter_by(code="viewer", organization_id=org_id).first()

        assert admin_role is not None, "El rol admin no fue clonado para la nueva org"
        assert agent_role is not None, "El rol agent no fue clonado para la nueva org"
        assert viewer_role is not None, "El rol viewer no fue clonado para la nueva org"

    def test_org_creator_gets_admin_role(self, client, db_session):
        """El creador de una org queda con el rol admin de esa org."""
        from app.main import app

        creator = _make_user(db_session, "Creator Admin", "creator_admin@test.com")
        db_session.commit()

        _apply_user_overrides(app, creator)
        try:
            resp = client.post(
                "/organizations/",
                json={"name": "Org Creator Admin"},
                headers={"X-Organization-Id": "1"},
            )
            assert resp.status_code == 200
            org_id = resp.json()["id"]
        finally:
            _remove_user_overrides(app)

        db_session.expire_all()
        membership = db_session.query(UserOrganization).filter_by(
            user_id=creator.id, organization_id=org_id
        ).first()
        assert membership is not None
        assert membership.is_owner is True

        role_codes = [r.code for r in membership.roles]
        assert "admin" in role_codes


# ===========================================================================
# 2. PERMISO user:invite
# ===========================================================================

class TestUserInvitePermission:
    def test_admin_can_invite(self, plain_client, db_session):
        """Un admin (con user:invite) puede invitar a alguien a su org."""
        org, cloned = _make_org_with_roles(db_session, "Org Invite Admin")

        admin_user = User(
            name="Admin Inviter",
            email="admin_inviter@test.com",
            hashed_password=hash_password("pass123"),
        )
        db_session.add(admin_user)
        db_session.flush()

        link = UserOrganization(user_id=admin_user.id, organization_id=org.id, is_owner=True)
        link.roles = [cloned["admin"]]
        db_session.add(link)
        db_session.commit()

        token = _login(plain_client, "admin_inviter@test.com", "pass123")

        resp = plain_client.post(
            "/auth/invite",
            json={"email": "nuevo@test.com", "organization_id": org.id, "role_code": "agent"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp.status_code == 200
        assert "invite_token" in resp.json()

    def test_agent_cannot_invite(self, plain_client, db_session):
        """Un agent (sin user:invite) recibe 403 al intentar invitar."""
        org, cloned = _make_org_with_roles(db_session, "Org Invite Agent")

        agent_user = User(
            name="Agent No Invite",
            email="agent_noinvite@test.com",
            hashed_password=hash_password("pass123"),
        )
        db_session.add(agent_user)
        db_session.flush()

        link = UserOrganization(user_id=agent_user.id, organization_id=org.id)
        link.roles = [cloned["agent"]]
        db_session.add(link)
        db_session.commit()

        token = _login(plain_client, "agent_noinvite@test.com", "pass123")

        resp = plain_client.post(
            "/auth/invite",
            json={"email": "nuevo@test.com", "organization_id": org.id},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp.status_code == 403

    def test_invite_with_invalid_role_returns_400(self, plain_client, db_session):
        """Invitar con un role_code que no existe en la org devuelve 400."""
        org, cloned = _make_org_with_roles(db_session, "Org Invite Bad Role")

        admin_user = User(
            name="Admin Bad Role",
            email="admin_badrole@test.com",
            hashed_password=hash_password("pass123"),
        )
        db_session.add(admin_user)
        db_session.flush()

        link = UserOrganization(user_id=admin_user.id, organization_id=org.id, is_owner=True)
        link.roles = [cloned["admin"]]
        db_session.add(link)
        db_session.commit()

        token = _login(plain_client, "admin_badrole@test.com", "pass123")

        resp = plain_client.post(
            "/auth/invite",
            json={"email": "nuevo@test.com", "organization_id": org.id, "role_code": "rol_inexistente"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp.status_code == 400

    def test_accept_invite_assigns_org_role(self, plain_client, db_session):
        """accept_invite asigna el rol de la org especificado en el token (no el global)."""
        org, cloned = _make_org_with_roles(db_session, "Org Accept Role")

        admin_user = User(
            name="Admin Accept",
            email="admin_accept@test.com",
            hashed_password=hash_password("pass123"),
        )
        db_session.add(admin_user)
        db_session.flush()

        link = UserOrganization(user_id=admin_user.id, organization_id=org.id, is_owner=True)
        link.roles = [cloned["admin"]]
        db_session.add(link)
        db_session.commit()

        token = _login(plain_client, "admin_accept@test.com", "pass123")

        # Invitar con role_code="agent"
        resp_invite = plain_client.post(
            "/auth/invite",
            json={"email": "invitee_role@test.com", "organization_id": org.id, "role_code": "agent"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp_invite.status_code == 200
        invite_token = resp_invite.json()["invite_token"]

        # Aceptar la invitación
        resp_accept = plain_client.post(
            f"/auth/accept-invite?invite_token={invite_token}&name=Invitee&password=pass1234"
        )
        assert resp_accept.status_code == 200

        # Verificar que el rol asignado es el agent de la org (no el global)
        db_session.expire_all()
        new_user = db_session.query(User).filter_by(email="invitee_role@test.com").first()
        assert new_user is not None

        membership = db_session.query(UserOrganization).filter_by(
            user_id=new_user.id, organization_id=org.id
        ).first()
        assert membership is not None

        role_codes = [r.code for r in membership.roles]
        org_ids = [r.organization_id for r in membership.roles]
        assert "agent" in role_codes
        # El rol debe ser de la org, no global
        assert org.id in org_ids

    def test_accept_invite_default_role_is_agent(self, plain_client, db_session):
        """Si no se especifica role_code en la invitación, se asigna agent por defecto."""
        org, cloned = _make_org_with_roles(db_session, "Org Default Role")

        admin_user = User(
            name="Admin Default",
            email="admin_default@test.com",
            hashed_password=hash_password("pass123"),
        )
        db_session.add(admin_user)
        db_session.flush()

        link = UserOrganization(user_id=admin_user.id, organization_id=org.id, is_owner=True)
        link.roles = [cloned["admin"]]
        db_session.add(link)
        db_session.commit()

        token = _login(plain_client, "admin_default@test.com", "pass123")

        # Invitar sin especificar role_code (usa default="agent")
        resp_invite = plain_client.post(
            "/auth/invite",
            json={"email": "default_invitee@test.com", "organization_id": org.id},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp_invite.status_code == 200
        invite_token = resp_invite.json()["invite_token"]

        resp_accept = plain_client.post(
            f"/auth/accept-invite?invite_token={invite_token}&name=Default&password=pass1234"
        )
        assert resp_accept.status_code == 200

        db_session.expire_all()
        new_user = db_session.query(User).filter_by(email="default_invitee@test.com").first()
        membership = db_session.query(UserOrganization).filter_by(
            user_id=new_user.id, organization_id=org.id
        ).first()
        role_codes = [r.code for r in membership.roles]
        assert "agent" in role_codes


# ===========================================================================
# 3. PERMISO user:view_all
# ===========================================================================

class TestUserViewAllPermission:
    def test_admin_can_list_users(self, client, db_session, initial_structure):
        """Un admin con user:view_all puede acceder a GET /users/."""
        from app.main import app

        org_id = initial_structure["org_id"]
        admin_user = _make_user(db_session, "Admin View", "admin_view@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.get("/users/", headers={"X-Organization-Id": str(org_id)})
            assert resp.status_code == 200
        finally:
            _remove_user_overrides(app)

    def test_agent_cannot_list_users(self, client, db_session, initial_structure):
        """Un agent sin user:view_all recibe 403 en GET /users/."""
        from app.main import app

        org_id = initial_structure["org_id"]
        agent_user = _make_user(db_session, "Agent No View", "agent_noview@test.com")
        _link_user_to_org(db_session, agent_user, org_id, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, agent_user, org_id)
        try:
            resp = client.get("/users/", headers={"X-Organization-Id": str(org_id)})
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_viewer_cannot_list_users(self, client, db_session, initial_structure):
        """Un viewer tampoco tiene user:view_all."""
        from app.main import app

        org_id = initial_structure["org_id"]
        viewer_user = _make_user(db_session, "Viewer No List", "viewer_nolist@test.com")
        _link_user_to_org(db_session, viewer_user, org_id, role_code="viewer")
        db_session.commit()

        _apply_user_overrides(app, viewer_user, org_id)
        try:
            resp = client.get("/users/", headers={"X-Organization-Id": str(org_id)})
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_superadmin_requires_org_header(self, client, db_session, initial_structure):
        """El superadmin también requiere X-Organization-Id (aislamiento de contexto)."""
        from app.main import app

        org_id = initial_structure["org_id"]
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
        _apply_user_overrides(app, superadmin, org_id)
        try:
            # Sin header → 400
            resp_no_header = client.get("/users/")
            assert resp_no_header.status_code == 400

            # Con header → 200
            resp_with_header = client.get("/users/", headers={"X-Organization-Id": str(org_id)})
            assert resp_with_header.status_code == 200
        finally:
            _remove_user_overrides(app)

    def test_admin_can_get_one_user(self, client, db_session, initial_structure):
        """Un admin puede ver un usuario específico con GET /users/{id}."""
        from app.main import app

        org_id = initial_structure["org_id"]
        admin_user = _make_user(db_session, "Admin Get One", "admin_getone@test.com")
        target = _make_user(db_session, "Target", "target_getone@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.get(
                f"/users/{target.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
        finally:
            _remove_user_overrides(app)

    def test_agent_cannot_get_one_user(self, client, db_session, initial_structure):
        """Un agent no puede ver un usuario específico."""
        from app.main import app

        org_id = initial_structure["org_id"]
        agent_user = _make_user(db_session, "Agent No Get", "agent_noget@test.com")
        target = _make_user(db_session, "Target2", "target2_getone@test.com")
        _link_user_to_org(db_session, agent_user, org_id, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, agent_user, org_id)
        try:
            resp = client.get(
                f"/users/{target.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)


# ===========================================================================
# 4. promote_to_superuser REQUIERE SUPERADMIN
# ===========================================================================

class TestPromoteSuperuser:
    def test_non_superadmin_cannot_promote(self, client, db_session, initial_structure):
        """Un admin de org NO puede llamar a promote_to_superuser."""
        from app.main import app

        org_id = initial_structure["org_id"]
        admin_user = _make_user(db_session, "Admin No Promote", "admin_nopromote@test.com")
        target = _make_user(db_session, "Promote Target", "promote_target@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.patch(
                f"/users/promote_to_superuser/{target.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_superadmin_can_promote(self, client, db_session, initial_structure):
        """El superadmin puede promover a otro usuario a superadmin."""
        from app.main import app

        target = _make_user(db_session, "To Be Super", "tobsuper@test.com")
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
        db_session.commit()

        _apply_user_overrides(app, superadmin)
        try:
            resp = client.patch(
                f"/users/promote_to_superuser/{target.id}",
                headers={"X-Organization-Id": str(initial_structure["org_id"])},
            )
            assert resp.status_code == 200
        finally:
            _remove_user_overrides(app)

        db_session.expire_all()
        assert db_session.get(User, target.id).is_superuser is True

    def test_agent_cannot_promote(self, client, db_session, initial_structure):
        """Un agent tampoco puede promover."""
        from app.main import app

        org_id = initial_structure["org_id"]
        agent_user = _make_user(db_session, "Agent Promote", "agent_promote@test.com")
        target = _make_user(db_session, "Promote Target2", "promote_target2@test.com")
        _link_user_to_org(db_session, agent_user, org_id, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, agent_user, org_id)
        try:
            resp = client.patch(
                f"/users/promote_to_superuser/{target.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)


# ===========================================================================
# 5. VISIBILIDAD DE LEADS
# ===========================================================================

class TestLeadVisibility:
    def test_admin_with_view_all_sees_all_leads(self, client, db_session, initial_structure):
        """Un admin (lead:view_all) ve todos los leads sin importar la campaña."""
        from app.main import app

        org_id = initial_structure["org_id"]

        private_camp = _make_campaign(db_session, org_id, "Camp Privada", is_public=False)
        lead_priv = _make_lead(db_session, private_camp.id, org_id)
        db_session.commit()

        admin_user = _make_user(db_session, "Admin Leads", "admin_leads@test.com")
        _link_user_to_org(db_session, admin_user, org_id, role_code="admin")
        db_session.commit()

        _apply_user_overrides(app, admin_user, org_id)
        try:
            resp = client.get(
                f"/leads?campaign_id={private_camp.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [item["id"] for item in data.get("items", data)]
            assert lead_priv.id in ids
        finally:
            _remove_user_overrides(app)

    def test_agent_sees_public_campaign_leads(self, client, db_session, initial_structure):
        """Un agent (sin lead:view_all) ve los leads de campañas públicas."""
        from app.main import app

        org_id = initial_structure["org_id"]

        public_camp = _make_campaign(db_session, org_id, "Camp Publica Agent", is_public=True)
        lead_pub = _make_lead(db_session, public_camp.id, org_id)
        db_session.commit()

        agent_user = _make_user(db_session, "Agent Public", "agent_public@test.com")
        _link_user_to_org(db_session, agent_user, org_id, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, agent_user, org_id)
        try:
            resp = client.get(
                f"/leads?campaign_id={public_camp.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [item["id"] for item in data.get("items", data)]
            assert lead_pub.id in ids
        finally:
            _remove_user_overrides(app)

    def test_agent_cannot_see_private_campaign_leads(self, client, db_session, initial_structure):
        """Un agent sin team membership no ve leads de campañas privadas."""
        from app.main import app

        org_id = initial_structure["org_id"]

        private_camp = _make_campaign(db_session, org_id, "Camp Privada Agent", is_public=False)
        other_user = _make_user(db_session, "Other Owner", "other_owner@test.com")
        lead_priv = _make_lead(db_session, private_camp.id, org_id, created_by=other_user.id)
        db_session.commit()

        agent_user = _make_user(db_session, "Agent Private", "agent_private@test.com")
        _link_user_to_org(db_session, agent_user, org_id, role_code="agent")
        db_session.commit()

        _apply_user_overrides(app, agent_user, org_id)
        try:
            resp = client.get(
                f"/leads?campaign_id={private_camp.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [item["id"] for item in data.get("items", data)]
            # El lead no debería aparecer (campaña privada, no es del agent)
            assert lead_priv.id not in ids
        finally:
            _remove_user_overrides(app)

    def test_agent_sees_own_leads_in_private_campaign(self, client, db_session, initial_structure):
        """Un agent sí ve los leads que él mismo creó, aunque la campaña sea privada."""
        from app.main import app

        org_id = initial_structure["org_id"]

        agent_user = _make_user(db_session, "Agent Own Lead", "agent_ownlead@test.com")
        _link_user_to_org(db_session, agent_user, org_id, role_code="agent")
        db_session.commit()

        private_camp = _make_campaign(db_session, org_id, "Camp Priv Own", is_public=False)
        my_lead = _make_lead(db_session, private_camp.id, org_id, created_by=agent_user.id)
        db_session.commit()

        _apply_user_overrides(app, agent_user, org_id)
        try:
            resp = client.get(
                f"/leads?campaign_id={private_camp.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [item["id"] for item in data.get("items", data)]
            assert my_lead.id in ids
        finally:
            _remove_user_overrides(app)

    def test_superadmin_sees_all_leads(self, client, db_session, initial_structure):
        """El superadmin ve todos los leads sin restricción."""
        from app.main import app

        org_id = initial_structure["org_id"]
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()

        private_camp = _make_campaign(db_session, org_id, "Camp Priv Super", is_public=False)
        lead_priv = _make_lead(db_session, private_camp.id, org_id)
        db_session.commit()

        _apply_user_overrides(app, superadmin, org_id)
        try:
            resp = client.get(
                f"/leads?campaign_id={private_camp.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [item["id"] for item in data.get("items", data)]
            assert lead_priv.id in ids
        finally:
            _remove_user_overrides(app)

    def test_owner_sees_all_leads(self, client, db_session, initial_structure):
        """El owner de la org ve todos los leads (is_owner=True bypasea el filtro)."""
        from app.main import app

        org_id = initial_structure["org_id"]
        owner_user = _make_user(db_session, "Owner Leads", "owner_leads@test.com")
        _link_user_to_org(db_session, owner_user, org_id, is_owner=True, role_code="admin")
        db_session.commit()

        private_camp = _make_campaign(db_session, org_id, "Camp Priv Owner", is_public=False)
        other = _make_user(db_session, "Other", "other_leads@test.com")
        lead_priv = _make_lead(db_session, private_camp.id, org_id, created_by=other.id)
        db_session.commit()

        _apply_user_overrides(app, owner_user, org_id, is_owner=True)
        try:
            resp = client.get(
                f"/leads?campaign_id={private_camp.id}",
                headers={"X-Organization-Id": str(org_id)},
            )
            assert resp.status_code == 200
            data = resp.json()
            ids = [item["id"] for item in data.get("items", data)]
            assert lead_priv.id in ids
        finally:
            _remove_user_overrides(app)
