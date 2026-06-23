"""
test_security_auth.py
=====================
Tests de autenticación y autorización:
  - Register / Login / Refresh / Logout
  - Invite + Accept-invite
  - Límite de 1 organización por usuario
  - Restricciones de acceso en endpoints de usuarios
"""
import pytest
from app.core.constans import ADMIN_ORG_ID
from app.core.security import hash_password, _get_current_user, get_current_user_roles
from app.models.security_models import User, UserOrganization
from app.models.organization import Organization
from tests.fixtures.user_fixtures import _make_user, _link_user_to_org


# ---------------------------------------------------------------------------
# Fixtures auxiliares
# ---------------------------------------------------------------------------

@pytest.fixture
def plain_client(db_session):
    """
    Cliente SIN overrides de autenticación.
    Necesario para testear los endpoints de /auth/* que deben funcionar sin token.
    """
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    from app.main import app
    from app.db.session import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # NO overrideamos _get_current_user — queremos que falle si no hay token

    with patch("app.main.run_seeds"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture
def registered_user(plain_client):
    """Registra un usuario de prueba y devuelve sus credenciales + tokens."""
    resp = plain_client.post("/auth/register", json={
        "name": "Test User",
        "email": "testuser@security.com",
        "password": "password123",
    })
    assert resp.status_code == 200, f"Register falló: {resp.text}"
    tokens = resp.json()
    return {
        "email": "testuser@security.com",
        "password": "password123",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


# ---------------------------------------------------------------------------
# REGISTER
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, plain_client):
        resp = plain_client.post("/auth/register", json={
            "name": "Franco Ruiz",
            "email": "franco@newuser.com",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, plain_client):
        payload = {"name": "Duplicado", "email": "dup@test.com", "password": "pass123"}
        plain_client.post("/auth/register", json=payload)
        resp = plain_client.post("/auth/register", json=payload)
        assert resp.status_code == 400
        assert "email" in resp.json()["detail"].lower() or "cuenta" in resp.json()["detail"].lower()

    def test_register_invalid_email(self, plain_client):
        resp = plain_client.post("/auth/register", json={
            "name": "Bad Email",
            "email": "not-an-email",
            "password": "pass123",
        })
        # pydantic_exception_handler devuelve 422 para errores de schema
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, plain_client, db_session):
        # Crear usuario con password hasheada directamente
        user = User(name="Login User", email="login@test.com",
                    hashed_password=hash_password("mypass123"))
        db_session.add(user)
        db_session.commit()

        resp = plain_client.post("/auth/login", json={
            "email": "login@test.com",
            "password": "mypass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_wrong_password(self, plain_client, db_session):
        user = User(name="Wrong Pass", email="wrongpass@test.com",
                    hashed_password=hash_password("correct"))
        db_session.add(user)
        db_session.commit()

        resp = plain_client.post("/auth/login", json={
            "email": "wrongpass@test.com",
            "password": "incorrecto",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_email(self, plain_client):
        resp = plain_client.post("/auth/login", json={
            "email": "noexiste@test.com",
            "password": "cualquiera",
        })
        assert resp.status_code == 401

    def test_login_inactive_user(self, plain_client, db_session):
        user = User(name="Inactive", email="inactive@test.com",
                    hashed_password=hash_password("pass123"), active=False)
        db_session.add(user)
        db_session.commit()

        resp = plain_client.post("/auth/login", json={
            "email": "inactive@test.com",
            "password": "pass123",
        })
        assert resp.status_code in [401, 403]

    def test_login_user_without_password(self, plain_client, db_session):
        """Usuario creado sin password (ej: por seed antiguo) no puede logearse."""
        user = User(name="No Pass", email="nopass@test.com", hashed_password=None)
        db_session.add(user)
        db_session.commit()

        resp = plain_client.post("/auth/login", json={
            "email": "nopass@test.com",
            "password": "cualquiera",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# REFRESH
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_refresh_success(self, plain_client, registered_user):
        resp = plain_client.post("/auth/refresh", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # El nuevo refresh token debe ser distinto al anterior (rotación)
        assert data["refresh_token"] != registered_user["refresh_token"]

    def test_refresh_invalid_token(self, plain_client):
        resp = plain_client.post("/auth/refresh", json={
            "refresh_token": "token-inventado-invalido",
        })
        assert resp.status_code == 401

    def test_refresh_revoked_token(self, plain_client, registered_user):
        """Después de hacer refresh, el token viejo queda revocado."""
        rt = registered_user["refresh_token"]
        # Primer refresh — OK
        plain_client.post("/auth/refresh", json={"refresh_token": rt})
        # Segundo refresh con el mismo token — debe fallar
        resp = plain_client.post("/auth/refresh", json={"refresh_token": rt})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# LOGOUT
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_success(self, plain_client, registered_user):
        resp = plain_client.post("/auth/logout", json={
            "refresh_token": registered_user["refresh_token"],
        })
        assert resp.status_code == 200

    def test_logout_then_refresh_fails(self, plain_client, registered_user):
        """Después de logout, el refresh token no puede usarse."""
        rt = registered_user["refresh_token"]
        plain_client.post("/auth/logout", json={"refresh_token": rt})
        resp = plain_client.post("/auth/refresh", json={"refresh_token": rt})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# INVITE + ACCEPT INVITE
# ---------------------------------------------------------------------------

class TestInvite:
    def test_invite_requires_auth(self, plain_client):
        """Sin token no se puede invitar."""
        resp = plain_client.post("/auth/invite", json={
            "email": "alguien@test.com",
            "organization_id": 1,
        })
        assert resp.status_code == 401

    def test_invite_and_accept_new_user(self, plain_client, db_session):
        """Flujo completo: invitar a email nuevo → aceptar → usuario creado en org."""
        # 1. Crear org + owner
        org = Organization(name="Org Invite Test")
        db_session.add(org)
        db_session.flush()

        owner = User(name="Owner", email="owner@invite.com",
                     hashed_password=hash_password("ownerpass"))
        db_session.add(owner)
        db_session.flush()

        link = UserOrganization(user_id=owner.id, organization_id=org.id, is_owner=True)
        db_session.add(link)
        db_session.flush()

        # Asignar rol admin global al owner para que tenga user:invite
        from app.models.security_models import Role
        admin_role = db_session.query(Role).filter_by(code="admin", organization_id=ADMIN_ORG_ID).first()
        if admin_role:
            link.roles = [admin_role]
        db_session.commit()

        # 2. Login como owner para obtener token
        resp_login = plain_client.post("/auth/login", json={
            "email": "owner@invite.com", "password": "ownerpass",
        })
        assert resp_login.status_code == 200
        access_token = resp_login.json()["access_token"]

        # 3. Invitar a un email nuevo (X-Organization-Id requerido por PermissionChecker)
        resp_invite = plain_client.post(
            "/auth/invite",
            json={"email": "invited@test.com", "organization_id": org.id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp_invite.status_code == 200
        invite_token = resp_invite.json()["invite_token"]

        # 4. Aceptar invitación
        resp_accept = plain_client.post(
            f"/auth/accept-invite?invite_token={invite_token}&name=Invitado&password=pass1234"
        )
        assert resp_accept.status_code == 200
        assert "access_token" in resp_accept.json()

        # 5. Verificar que el usuario fue creado y vinculado a la org
        db_session.expire_all()
        new_user = db_session.query(User).filter_by(email="invited@test.com").first()
        assert new_user is not None
        membership = db_session.query(UserOrganization).filter_by(
            user_id=new_user.id, organization_id=org.id
        ).first()
        assert membership is not None

    def test_invite_outsider_cannot_invite(self, plain_client, db_session):
        """Un usuario que no pertenece a la org no puede invitar."""
        org = Organization(name="Org Ajena")
        db_session.add(org)
        db_session.flush()

        outsider = User(name="Outsider", email="outsider@noinvite.com",
                        hashed_password=hash_password("pass123"))
        db_session.add(outsider)
        db_session.commit()

        resp_login = plain_client.post("/auth/login", json={
            "email": "outsider@noinvite.com", "password": "pass123",
        })
        access_token = resp_login.json()["access_token"]

        # Con X-Organization-Id, PermissionChecker verifica user:invite.
        # El outsider no tiene roles → 403.
        resp = plain_client.post(
            "/auth/invite",
            json={"email": "alguien@test.com", "organization_id": org.id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# LÍMITE DE 1 ORGANIZACIÓN POR USUARIO
# ---------------------------------------------------------------------------

class TestOrgLimit:
    def test_user_can_create_one_org(self, client, db_session, initial_structure):
        """Un usuario común puede crear solo 1 organización."""
        user = _make_user(db_session, "Org Creator", "orgcreator@test.com")
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, user)
        try:
            resp1 = client.post("/organizations/", json={"name": "Mi Primera Org"},
                                headers={"X-Organization-Id": "1"})
            assert resp1.status_code == 200

            resp2 = client.post("/organizations/", json={"name": "Mi Segunda Org"},
                                headers={"X-Organization-Id": "1"})
            assert resp2.status_code == 400
            assert "propietario" in resp2.json()["detail"].lower()
        finally:
            _remove_user_overrides(app)

    def test_superadmin_can_create_multiple_orgs(self, client, db_session):
        """El superadmin puede crear múltiples organizaciones."""
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, superadmin)
        try:
            for i in range(3):
                resp = client.post("/organizations/", json={"name": f"Org Admin {i}"},
                                   headers={"X-Organization-Id": "1"})
                assert resp.status_code == 200
        finally:
            _remove_user_overrides(app)


# ---------------------------------------------------------------------------
# RESTRICCIONES EN /users
# ---------------------------------------------------------------------------

class TestUserEndpoints:
    def test_get_all_users_forbidden_for_regular_user(self, client, db_session, initial_structure):
        """GET /users requiere user:view_all — un agente no lo tiene."""
        regular = _make_user(db_session, "Regular", "regular@test.com")
        _link_user_to_org(db_session, regular, initial_structure["org_id"], role_code="agent")
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, regular, initial_structure["org_id"])
        try:
            resp = client.get("/users/", headers={"X-Organization-Id": str(initial_structure["org_id"])})
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_get_all_users_allowed_for_superadmin(self, client, db_session, initial_structure):
        """GET /users funciona para superadmin (con X-Organization-Id requerido)."""
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
        org_id = initial_structure["org_id"]

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, superadmin, org_id)
        try:
            resp = client.get("/users/", headers={"X-Organization-Id": str(org_id)})
            assert resp.status_code == 200
        finally:
            _remove_user_overrides(app)

    def test_get_one_user_forbidden_for_regular_user(self, client, db_session, initial_structure):
        """GET /users/{id} requiere user:view_all — un agente no lo tiene."""
        regular = _make_user(db_session, "RegularGet", "regularget@test.com")
        _link_user_to_org(db_session, regular, initial_structure["org_id"], role_code="agent")
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, regular, initial_structure["org_id"])
        try:
            resp = client.get(f"/users/{regular.id}",
                              headers={"X-Organization-Id": str(initial_structure["org_id"])})
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_update_own_user(self, client, db_session, initial_structure):
        """Un usuario puede actualizar su propia cuenta."""
        user = _make_user(db_session, "SelfUpdate", "selfupdate@test.com")
        _link_user_to_org(db_session, user, initial_structure["org_id"])
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, user, initial_structure["org_id"])
        try:
            resp = client.put(f"/users/{user.id}",
                              json={"name": "Nuevo Nombre"},
                              headers={"X-Organization-Id": str(initial_structure["org_id"])})
            assert resp.status_code == 200
            assert resp.json()["name"] == "Nuevo Nombre"
        finally:
            _remove_user_overrides(app)

    def test_update_other_user_forbidden(self, client, db_session, initial_structure):
        """Un usuario NO puede actualizar la cuenta de otro."""
        user_a = _make_user(db_session, "User A", "usera@test.com")
        user_b = _make_user(db_session, "User B", "userb@test.com")
        _link_user_to_org(db_session, user_a, initial_structure["org_id"])
        _link_user_to_org(db_session, user_b, initial_structure["org_id"])
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        # User A intenta editar a User B
        _apply_user_overrides(app, user_a, initial_structure["org_id"])
        try:
            resp = client.put(f"/users/{user_b.id}",
                              json={"name": "Hackeado"},
                              headers={"X-Organization-Id": str(initial_structure["org_id"])})
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_superadmin_can_update_any_user(self, client, db_session, initial_structure):
        """El superadmin puede actualizar cualquier usuario."""
        target = _make_user(db_session, "Target User", "target@test.com")
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, superadmin)
        try:
            resp = client.put(f"/users/{target.id}",
                              json={"name": "Actualizado por Admin"},
                              headers={"X-Organization-Id": str(initial_structure["org_id"])})
            assert resp.status_code == 200
        finally:
            _remove_user_overrides(app)


# ---------------------------------------------------------------------------
# GET /users/in-org/members
# ---------------------------------------------------------------------------

class TestUsersInOrg:
    def test_member_can_see_org_users(self, plain_client, db_session):
        """Un miembro de la org puede ver los usuarios de su organización."""
        org = Organization(name="Org Members Test")
        db_session.add(org)
        db_session.flush()

        user1 = User(name="Member 1", email="m1@test.com",
                     hashed_password=hash_password("pass123"))
        user2 = User(name="Member 2", email="m2@test.com",
                     hashed_password=hash_password("pass123"))
        db_session.add_all([user1, user2])
        db_session.flush()

        db_session.add(UserOrganization(user_id=user1.id, organization_id=org.id))
        db_session.add(UserOrganization(user_id=user2.id, organization_id=org.id))
        db_session.commit()

        # Login como user1
        resp_login = plain_client.post("/auth/login", json={"email": "m1@test.com", "password": "pass123"})
        token = resp_login.json()["access_token"]

        resp = plain_client.get(
            "/users/in-org/members",
            headers={"Authorization": f"Bearer {token}", "X-Organization-Id": str(org.id)},
        )
        assert resp.status_code == 200
        members = resp.json()
        emails = [m["email"] for m in members]
        assert "m1@test.com" in emails
        assert "m2@test.com" in emails

    def test_non_member_cannot_see_org_users(self, plain_client, db_session):
        """Un usuario que no pertenece a la org no puede ver sus miembros."""
        org = Organization(name="Org Private")
        db_session.add(org)
        db_session.flush()

        outsider = User(name="Outsider", email="outsider@members.com",
                        hashed_password=hash_password("pass123"))
        db_session.add(outsider)
        db_session.commit()

        resp_login = plain_client.post("/auth/login", json={
            "email": "outsider@members.com", "password": "pass123",
        })
        token = resp_login.json()["access_token"]

        resp = plain_client.get(
            "/users/in-org/members",
            headers={"Authorization": f"Bearer {token}", "X-Organization-Id": str(org.id)},
        )
        assert resp.status_code == 403

    def test_response_schema_is_limited(self, plain_client, db_session):
        """La respuesta de in-org NO incluye campos sensibles como is_superuser."""
        org = Organization(name="Org Schema Test")
        db_session.add(org)
        db_session.flush()

        user = User(name="Schema User", email="schema@test.com",
                    hashed_password=hash_password("pass123"), is_superuser=True)
        db_session.add(user)
        db_session.flush()
        db_session.add(UserOrganization(user_id=user.id, organization_id=org.id))
        db_session.commit()

        resp_login = plain_client.post("/auth/login", json={
            "email": "schema@test.com", "password": "pass123",
        })
        token = resp_login.json()["access_token"]

        resp = plain_client.get(
            "/users/in-org/members",
            headers={"Authorization": f"Bearer {token}", "X-Organization-Id": str(org.id)},
        )
        assert resp.status_code == 200
        member = resp.json()[0]
        # Campos permitidos
        assert "id" in member
        assert "name" in member
        assert "email" in member
        assert "active" in member
        # Campos sensibles NO deben estar
        assert "is_superuser" not in member
        assert "hashed_password" not in member
        assert "organizations_access" not in member
