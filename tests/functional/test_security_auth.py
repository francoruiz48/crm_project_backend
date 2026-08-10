"""
test_security_auth.py
=====================
Tests de autenticación y autorización:
  - Register / Login / Refresh / Logout
  - Invite + Accept-invite
  - Límite de 1 organización por usuario
  - Restricciones de acceso en endpoints de usuarios
  - Hallazgo #12: rate limiting en /auth/login y /auth/register
  - Hallazgo #13: normalización de email (.strip().lower()) en Login/Register/UpdateMe
  - Hallazgo #14: PUT /auth/me valida formato (EmailStr) y unicidad de email
  - Hallazgo #11: get_client_ip (X-Forwarded-For/X-Real-IP) como fuente de IP
    real detrás de un proxy, usada por el rate limiter de /auth/*
"""
import pytest
from app.core.constans import ADMIN_ORG_ID
from app.core.security import hash_password, _get_current_user, get_current_user_roles
from app.models.security_models import User, UserOrganization
from app.models.organization import Organization
from tests.fixtures.user_fixtures import _make_user, _link_user_to_org
from app.controllers.security_controllers.auth_controller import limiter as auth_limiter


# ---------------------------------------------------------------------------
# Fixtures auxiliares
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """El Limiter de /auth/login y /auth/register (hallazgo #12) vive a nivel de
    módulo y sus contadores persisten mientras dure el proceso de test. Casi todos
    los tests de este archivo llaman a /auth/login y/o /auth/register (directo o
    vía `registered_user`) — sin este reset se irían pisando la cuota de '10/minute'
    entre sí y tests sin relación con rate limiting empezarían a fallar con 429."""
    auth_limiter.reset()
    yield


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
        "last_name": "Security",
        "email": "testuser@security.com",
        "password": "Password123",
    })
    assert resp.status_code == 200, f"Register falló: {resp.text}"
    tokens = resp.json()
    return {
        "email": "testuser@security.com",
        "password": "Password123",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


# ---------------------------------------------------------------------------
# GET_CLIENT_IP (hallazgo #11)
# ---------------------------------------------------------------------------

class TestGetClientIp:
    """get_client_ip (app/core/security.py) es la única fuente de verdad para
    resolver la IP real de un visitante detrás de un proxy — la usan el rate
    limiter de /auth/* y de /public/forms/*/submit, y el `remoteip` de CAPTCHA."""

    @staticmethod
    def _make_request(headers: dict, client_host: str = "127.0.0.1"):
        from starlette.requests import Request
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        scope = {"type": "http", "headers": raw_headers, "client": (client_host, 12345)}
        return Request(scope)

    def test_prefers_x_forwarded_for_first_ip(self):
        from app.core.security import get_client_ip
        req = self._make_request({"x-forwarded-for": "203.0.113.1, 10.0.0.1"}, client_host="10.0.0.1")
        assert get_client_ip(req) == "203.0.113.1"

    def test_falls_back_to_x_real_ip_without_forwarded_for(self):
        from app.core.security import get_client_ip
        req = self._make_request({"x-real-ip": "203.0.113.2"}, client_host="10.0.0.1")
        assert get_client_ip(req) == "203.0.113.2"

    def test_falls_back_to_request_client_host_without_proxy_headers(self):
        from app.core.security import get_client_ip
        req = self._make_request({}, client_host="198.51.100.9")
        assert get_client_ip(req) == "198.51.100.9"


# ---------------------------------------------------------------------------
# REGISTER
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, plain_client):
        resp = plain_client.post("/auth/register", json={
            "name": "Franco",
            "last_name": "Ruiz",
            "email": "franco@newuser.com",
            "password": "Securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, plain_client):
        payload = {"name": "Duplicado", "last_name": "Test", "email": "dup@test.com", "password": "Pass123456"}
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

    @pytest.mark.parametrize("weak_password", [
        "abc123",        # muy corta (menos de 10)
        "password12345", # sin mayúscula
        "PASSWORD12345", # sin minúscula
        "Passwordabcde",  # sin número
    ])
    def test_register_rejects_weak_password(self, plain_client, weak_password):
        """La política de contraseñas (10+ caracteres, mayúscula, minúscula y número) aplica en el registro."""
        resp = plain_client.post("/auth/register", json={
            "name": "Debil",
            "last_name": "Password",
            "email": f"debil_{len(weak_password)}@test.com",
            "password": weak_password,
        })
        assert resp.status_code == 422
        fields = [e["field"] for e in resp.json()["detail"]]
        assert "password" in fields

    def test_register_accepts_strong_password(self, plain_client):
        """Contraparte del test anterior: una contraseña que cumple la política sí registra."""
        resp = plain_client.post("/auth/register", json={
            "name": "Fuerte",
            "last_name": "Password",
            "email": "fuerte@test.com",
            "password": "Fuerte1234",
        })
        assert resp.status_code == 200

    def test_register_normalizes_email_to_lowercase(self, plain_client, db_session):
        """Hallazgo #13: el email se guarda normalizado (.strip().lower()),
        sin importar cómo lo mande el cliente."""
        resp = plain_client.post("/auth/register", json={
            "name": "Mayus",
            "last_name": "Culas",
            "email": "  Mayusculas@Test.COM  ",
            "password": "Password123",
        })
        assert resp.status_code == 200, resp.text

        user = db_session.query(User).filter_by(email="mayusculas@test.com").first()
        assert user is not None, "El email debería haberse guardado normalizado a minúsculas."

    def test_register_rejects_duplicate_email_different_case(self, plain_client):
        """Hallazgo #13: dos registros con el mismo email en distinta
        capitalización deben tratarse como el mismo email (400 duplicado)."""
        plain_client.post("/auth/register", json={
            "name": "Original", "last_name": "Test",
            "email": "CaseTest@Empresa.com", "password": "Password123",
        })
        resp = plain_client.post("/auth/register", json={
            "name": "Duplicado", "last_name": "Test",
            "email": "casetest@empresa.com", "password": "Password123",
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, plain_client, db_session):
        # Crear usuario con password hasheada directamente
        user = User(name="Login User", last_name="Test", email="login@test.com",
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
        user = User(name="Wrong Pass", last_name="Test", email="wrongpass@test.com",
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
        user = User(name="Inactive", last_name="Test", email="inactive@test.com",
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
        user = User(name="No Pass", last_name="Test", email="nopass@test.com", hashed_password=None)
        db_session.add(user)
        db_session.commit()

        resp = plain_client.post("/auth/login", json={
            "email": "nopass@test.com",
            "password": "cualquiera",
        })
        assert resp.status_code == 401

    def test_login_with_different_case_succeeds_after_register(self, plain_client):
        """Hallazgo #13: registrarse con una capitalización y loguearse con otra
        debe funcionar, porque ambos extremos normalizan antes de comparar."""
        resp_register = plain_client.post("/auth/register", json={
            "name": "Case", "last_name": "Login",
            "email": "CaseLogin@Test.com", "password": "Password123",
        })
        assert resp_register.status_code == 200, resp_register.text

        resp_login = plain_client.post("/auth/login", json={
            "email": "caselogin@test.com",
            "password": "Password123",
        })
        assert resp_login.status_code == 200, resp_login.text


# ---------------------------------------------------------------------------
# RATE LIMITING (hallazgo #12) — /auth/login y /auth/register, 10/minuto por IP
# ---------------------------------------------------------------------------

class TestAuthRateLimiting:
    def test_login_rate_limited_after_ten_per_minute(self, plain_client):
        """Al 11vo intento de login en la misma ventana, debe cortar con 429
        en vez de seguir evaluando credenciales (fuerza bruta sin freno,
        hallazgo #12)."""
        statuses = []
        for _ in range(11):
            resp = plain_client.post("/auth/login", json={
                "email": "no-existe-rate-limit@test.com",
                "password": "cualquiera",
            })
            statuses.append(resp.status_code)

        assert 429 in statuses, f"Se esperaba al menos un 429 entre los 11 intentos, se obtuvo: {statuses}"
        # Antes de agotar la cuota, el intento debe fallar por credenciales (401),
        # no por otro motivo distinto al rate limit.
        assert all(s in (401, 429) for s in statuses)

    def test_register_rate_limited_after_ten_per_minute(self, plain_client):
        """Al 11vo intento de registro en la misma ventana, debe cortar con 429
        (protección contra spam de creación de cuentas, hallazgo #12)."""
        statuses = []
        for i in range(11):
            resp = plain_client.post("/auth/register", json={
                "name": "Rate",
                "last_name": "Limit",
                "email": f"rate_limit_{i}@test.com",
                "password": "Password123",
            })
            statuses.append(resp.status_code)

        assert 429 in statuses, f"Se esperaba al menos un 429 entre los 11 intentos, se obtuvo: {statuses}"
        # Antes de agotar la cuota, cada registro con email distinto debe dar 200.
        assert all(s in (200, 429) for s in statuses)

    def test_rate_limit_uses_x_forwarded_for_not_shared_across_visitors(self, plain_client):
        """Hallazgo #11: el rate limit debe basarse en X-Forwarded-For (IP real del
        visitante detrás de un proxy), no en request.client.host — que sería la
        misma para todos los visitantes si hay un proxy delante (como el
        TestClient, que siempre pega desde la misma conexión)."""
        headers_visitor_a = {"X-Forwarded-For": "203.0.113.10"}
        headers_visitor_b = {"X-Forwarded-For": "203.0.113.20"}

        # Agotar la cuota del visitante A.
        statuses_a = []
        for _ in range(11):
            resp = plain_client.post(
                "/auth/login",
                json={"email": "no-existe-rate-limit-a@test.com", "password": "cualquiera"},
                headers=headers_visitor_a,
            )
            statuses_a.append(resp.status_code)
        assert 429 in statuses_a, f"Se esperaba al menos un 429 para el visitante A, se obtuvo: {statuses_a}"

        # El visitante B, con IP distinta, no debería estar bloqueado todavía.
        resp_b = plain_client.post(
            "/auth/login",
            json={"email": "no-existe-rate-limit-b@test.com", "password": "cualquiera"},
            headers=headers_visitor_b,
        )
        assert resp_b.status_code == 401, (
            f"Esperaba 401 (IP distinta, cuota propia) pero recibió {resp_b.status_code}: {resp_b.text}"
        )


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
# PUT /auth/me — hallazgos #13 (normalización) y #14 (formato + unicidad de email)
# ---------------------------------------------------------------------------

class TestUpdateMe:
    def test_update_me_rejects_email_taken_by_another_user(self, plain_client, registered_user):
        """Hallazgo #14: antes esto terminaba en un 500 (IntegrityError sin
        capturar, User.email es unique) en vez de un 400 prolijo. registered_user
        es el PRIMER usuario; acá probamos que un SEGUNDO usuario no pueda
        apropiarse de su email vía PUT /auth/me."""
        plain_client.post("/auth/register", json={
            "name": "Segundo", "last_name": "Usuario",
            "email": "segundo@security.com", "password": "Password123",
        })
        resp_login_segundo = plain_client.post("/auth/login", json={
            "email": "segundo@security.com", "password": "Password123",
        })
        segundo_token = resp_login_segundo.json()["access_token"]

        resp = plain_client.put(
            "/auth/me",
            json={"email": registered_user["email"]},
            headers={"Authorization": f"Bearer {segundo_token}"},
        )
        assert resp.status_code == 400, resp.text

    def test_update_me_rejects_invalid_email_format(self, plain_client, registered_user):
        """Hallazgo #14: UserUpdate.email pasó de str suelto a EmailStr."""
        resp = plain_client.put(
            "/auth/me",
            json={"email": "no-es-un-email"},
            headers={"Authorization": f"Bearer {registered_user['access_token']}"},
        )
        assert resp.status_code == 422

    def test_update_me_normalizes_new_email(self, plain_client, registered_user, db_session):
        """Hallazgo #13 aplicado también acá: el nuevo email se guarda en minúsculas."""
        resp = plain_client.put(
            "/auth/me",
            json={"email": "NuevoEmail@Test.COM"},
            headers={"Authorization": f"Bearer {registered_user['access_token']}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == "nuevoemail@test.com"

    def test_update_me_allows_resubmitting_own_email_different_case(self, plain_client, registered_user):
        """No debe dispararse el chequeo de unicidad contra uno mismo cuando el
        'nuevo' email es, normalizado, el mismo que ya tenía."""
        own_email_shouting = registered_user["email"].upper()
        resp = plain_client.put(
            "/auth/me",
            json={"email": own_email_shouting},
            headers={"Authorization": f"Bearer {registered_user['access_token']}"},
        )
        assert resp.status_code == 200, resp.text


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

        owner = User(name="Owner", last_name="Test", email="owner@invite.com",
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
        # organization_id en el body es str (public_uuid, Fase 3) desde 2026-08-01 -- ver
        # AGENTS.md. org.id acá es el id interno de la fila ORM cruda, no sirve para el body.
        resp_invite = plain_client.post(
            "/auth/invite",
            json={"email": "invited@test.com", "organization_id": org.public_uuid},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp_invite.status_code == 200
        invite_token = resp_invite.json()["invite_token"]

        # 4. Usuario nuevo → se registra normalmente, con el invite_token en el body
        #    (el que invita no elige nombre/apellido/contraseña, eso lo define el invitado).
        resp_accept = plain_client.post("/auth/register", json={
            "name": "Invitado",
            "last_name": "Test",
            "email": "invited@test.com",
            "password": "Pass1234ab",
            "invite_token": invite_token,
        })
        assert resp_accept.status_code == 200
        assert "access_token" in resp_accept.json()
        assert resp_accept.json().get("invite_warning") is None

        # 5. Verificar que el usuario fue creado y vinculado a la org
        db_session.expire_all()
        new_user = db_session.query(User).filter_by(email="invited@test.com").first()
        assert new_user is not None
        membership = db_session.query(UserOrganization).filter_by(
            user_id=new_user.id, organization_id=org.id
        ).first()
        assert membership is not None

    def test_accept_invite_existing_user_joins_org(self, plain_client, db_session):
        """Un usuario que YA tiene cuenta usa /auth/accept-invite (autenticado) para unirse a otra org."""
        # 1. Crear org + owner que invita
        org = Organization(name="Org Invite Existente")
        db_session.add(org)
        db_session.flush()

        owner = User(name="Owner", last_name="Test", email="owner2@invite.com",
                     hashed_password=hash_password("ownerpass"))
        db_session.add(owner)
        db_session.flush()

        link = UserOrganization(user_id=owner.id, organization_id=org.id, is_owner=True)
        db_session.add(link)
        db_session.flush()

        from app.models.security_models import Role
        admin_role = db_session.query(Role).filter_by(code="admin", organization_id=ADMIN_ORG_ID).first()
        if admin_role:
            link.roles = [admin_role]

        # 2. Usuario ya existente (registrado antes, sin relación con esta org)
        existing = User(name="Ya Existo", last_name="Test", email="yaexisto@test.com",
                         hashed_password=hash_password("mipass123"))
        db_session.add(existing)
        db_session.commit()

        # 3. Owner invita al email del usuario existente
        resp_login_owner = plain_client.post("/auth/login", json={
            "email": "owner2@invite.com", "password": "ownerpass",
        })
        owner_token = resp_login_owner.json()["access_token"]

        resp_invite = plain_client.post(
            "/auth/invite",
            json={"email": "yaexisto@test.com", "organization_id": org.public_uuid},
            headers={
                "Authorization": f"Bearer {owner_token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp_invite.status_code == 200
        invite_token = resp_invite.json()["invite_token"]

        # 4. El usuario existente se loguea con SU propia contraseña (no la elige quien invita)
        resp_login_existing = plain_client.post("/auth/login", json={
            "email": "yaexisto@test.com", "password": "mipass123",
        })
        assert resp_login_existing.status_code == 200
        existing_token = resp_login_existing.json()["access_token"]

        # 5. Acepta la invitación ya autenticado, sin mandar contraseña
        resp_accept = plain_client.post(
            "/auth/accept-invite",
            json={"invite_token": invite_token},
            headers={"Authorization": f"Bearer {existing_token}"},
        )
        assert resp_accept.status_code == 200
        assert resp_accept.json()["organization_id"] == org.id

        db_session.expire_all()
        membership = db_session.query(UserOrganization).filter_by(
            user_id=existing.id, organization_id=org.id
        ).first()
        assert membership is not None

    def test_accept_invite_rejects_mismatched_email(self, plain_client, db_session):
        """Si el token es para un email distinto al usuario autenticado, se rechaza con 403."""
        org = Organization(name="Org Invite Mismatch")
        db_session.add(org)
        db_session.flush()

        owner = User(name="Owner", last_name="Test", email="owner3@invite.com",
                     hashed_password=hash_password("ownerpass"))
        db_session.add(owner)
        db_session.flush()

        link = UserOrganization(user_id=owner.id, organization_id=org.id, is_owner=True)
        db_session.add(link)
        db_session.flush()

        from app.models.security_models import Role
        admin_role = db_session.query(Role).filter_by(code="admin", organization_id=ADMIN_ORG_ID).first()
        if admin_role:
            link.roles = [admin_role]

        # Otro usuario, ajeno a la invitación
        intruder = User(name="Intruso", last_name="Test", email="intruso@test.com",
                         hashed_password=hash_password("intrusopass"))
        db_session.add(intruder)
        db_session.commit()

        resp_login_owner = plain_client.post("/auth/login", json={
            "email": "owner3@invite.com", "password": "ownerpass",
        })
        owner_token = resp_login_owner.json()["access_token"]

        resp_invite = plain_client.post(
            "/auth/invite",
            json={"email": "destinatario@test.com", "organization_id": org.public_uuid},
            headers={
                "Authorization": f"Bearer {owner_token}",
                "X-Organization-Id": str(org.id),
            },
        )
        assert resp_invite.status_code == 200
        invite_token = resp_invite.json()["invite_token"]

        resp_login_intruder = plain_client.post("/auth/login", json={
            "email": "intruso@test.com", "password": "intrusopass",
        })
        intruder_token = resp_login_intruder.json()["access_token"]

        resp_accept = plain_client.post(
            "/auth/accept-invite",
            json={"invite_token": invite_token},
            headers={"Authorization": f"Bearer {intruder_token}"},
        )
        assert resp_accept.status_code == 403

    def test_register_with_invalid_invite_token_still_creates_account(self, plain_client, db_session):
        """Un invite_token roto/vencido no debe impedir el registro, pero debe avisar por qué no se unió a la org."""
        resp = plain_client.post("/auth/register", json={
            "name": "Cuenta",
            "last_name": "Suelta",
            "email": "cuentasuelta@test.com",
            "password": "Pass1234ab",
            "invite_token": "esto-no-es-un-jwt-valido",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data.get("invite_warning") is not None

    def test_invite_outsider_cannot_invite(self, plain_client, db_session):
        """Un usuario que no pertenece a la org no puede invitar."""
        org = Organization(name="Org Ajena")
        db_session.add(org)
        db_session.flush()

        outsider = User(name="Outsider", last_name="Test", email="outsider@noinvite.com",
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
# CAMBIO DE CONTRASEÑA — misma política que el registro
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_change_password_rejects_weak_new_password(self, client):
        """change-password usa la misma validate_password_strength que /auth/register (fuente única)."""
        resp = client.post("/auth/change-password", json={
            "current_password": "ADQSilR4aAKCO%a^",
            "new_password": "debil123",
        })
        assert resp.status_code == 422
        fields = [e["field"] for e in resp.json()["detail"]]
        assert "new_password" in fields

    def test_change_password_accepts_strong_new_password(self, client):
        resp = client.post("/auth/change-password", json={
            "current_password": "ADQSilR4aAKCO%a^",
            "new_password": "NuevaClave123",
        })
        assert resp.status_code == 200


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
        superadmin = db_session.query(User).filter_by(email="francoruiz.admin@crm.com").first()

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
        superadmin = db_session.query(User).filter_by(email="francoruiz.admin@crm.com").first()
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
            # user.id sería el id interno crudo de la fila ORM (_make_user construye el User
            # directo en la DB) -- PUT /users/{id} espera el public_uuid (Fase 2/3).
            resp = client.put(f"/users/{user.public_uuid}",
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
            resp = client.put(f"/users/{user_b.public_uuid}",
                              json={"name": "Hackeado"},
                              headers={"X-Organization-Id": str(initial_structure["org_id"])})
            assert resp.status_code == 403
        finally:
            _remove_user_overrides(app)

    def test_superadmin_can_update_any_user(self, client, db_session, initial_structure):
        """El superadmin puede actualizar cualquier usuario."""
        target = _make_user(db_session, "Target User", "target@test.com")
        superadmin = db_session.query(User).filter_by(email="francoruiz.admin@crm.com").first()
        db_session.commit()

        from tests.fixtures.user_fixtures import _apply_user_overrides, _remove_user_overrides
        from app.main import app

        _apply_user_overrides(app, superadmin)
        try:
            resp = client.put(f"/users/{target.public_uuid}",
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

        user1 = User(name="Member 1", last_name="Test", email="m1@test.com",
                     hashed_password=hash_password("pass123"))
        user2 = User(name="Member 2", last_name="Test", email="m2@test.com",
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

        outsider = User(name="Outsider", last_name="Test", email="outsider@members.com",
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

        user = User(name="Schema User", last_name="Test", email="schema@test.com",
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
