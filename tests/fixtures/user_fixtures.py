import pytest
from unittest.mock import patch
from app.models.security_models import User, UserOrganization, Role
from app.models.team_member import TeamMember
from app.models.team import Team
from app.core.constans import ADMIN_ORG_ID
from tests.helpers.api_helpers import ApiClient


def _make_user(db_session, name: str, email: str, is_superuser: bool = False) -> User:
    user = User(name=name, email=email, is_superuser=is_superuser)
    db_session.add(user)
    db_session.flush()
    return user


def _link_user_to_org(db_session, user: User, org_id: int, is_owner: bool = False, role_code: str = "admin") -> UserOrganization:
    role = db_session.query(Role).filter_by(code=role_code, organization_id=ADMIN_ORG_ID).first()
    link = UserOrganization(user_id=user.id, organization_id=org_id, is_owner=is_owner)
    if role:
        link.roles = [role]
    db_session.add(link)
    db_session.flush()
    return link


def _make_team_member(db_session, team_id: int, user_id: int, role: str) -> TeamMember:
    member = TeamMember(team_id=team_id, user_id=user_id, role=role)
    db_session.add(member)
    db_session.flush()
    return member


def _apply_user_overrides(app, user: User, org_id: int = None, is_owner: bool = False):
    """
    Overridea tanto _get_current_user como get_current_user_roles para simular
    un usuario específico. Cubre todos los endpoints: los que usan una u otra dependencia.
    """
    from app.core.security import _get_current_user, get_current_user_roles, UserContext
    from app.core.context import TENANT_ORG_ID
    from fastapi import Header
    from typing import Optional

    captured_user  = user      # captura explícita para el closure
    captured_owner = is_owner  # idem para is_owner

    def fake_get_current_user():
        return captured_user

    def fake_get_current_user_roles(
        x_organization_id: Optional[int] = Header(default=None, alias="X-Organization-Id"),
    ):
        if x_organization_id is not None:
            TENANT_ORG_ID.set(x_organization_id)
        effective_org = x_organization_id or org_id
        # Poblamos los permisos reales del usuario para que PermissionChecker
        # y los servicios (ej: LeadRepository) funcionen correctamente en tests.
        permissions = captured_user.get_permissions(org_id=effective_org) if effective_org else []
        return UserContext(
            user=captured_user,
            is_superuser=captured_user.is_superuser,
            is_owner=captured_owner,
            organization_id=effective_org,
            permissions=permissions,
        )

    app.dependency_overrides[_get_current_user] = fake_get_current_user
    app.dependency_overrides[get_current_user_roles] = fake_get_current_user_roles


def _remove_user_overrides(app):
    from app.core.security import _get_current_user, get_current_user_roles
    app.dependency_overrides.pop(_get_current_user, None)
    app.dependency_overrides.pop(get_current_user_roles, None)


class as_user:
    """
    Context manager que simula un usuario específico en FastAPI.
    Overridea tanto _get_current_user como get_current_user_roles.
    Al salir, RESTAURA los overrides previos (ej: el superadmin del fixture client).

    Si se pasa db_session, consulta UserOrganization para determinar is_owner
    automáticamente. De lo contrario, is_owner=False.
    """
    def __init__(self, api, user: User, db_session=None):
        self._api        = api
        self._user       = user
        self._db         = db_session
        self._prev_overrides = {}

    def __enter__(self):
        from app.core.security import _get_current_user, get_current_user_roles
        app = self._api.client.app

        # Resolver is_owner consultando la DB si se proporcionó sesión
        is_owner = False
        if self._db is not None and self._api.org_id is not None:
            link = self._db.query(UserOrganization).filter_by(
                user_id=self._user.id,
                organization_id=self._api.org_id,
            ).first()
            is_owner = bool(link and link.is_owner)

        # Guardamos los overrides actuales antes de pisarlos
        self._prev_overrides = {
            k: v for k, v in app.dependency_overrides.items()
            if k in (_get_current_user, get_current_user_roles)
        }
        _apply_user_overrides(app, self._user, self._api.org_id, is_owner=is_owner)
        return self

    def __exit__(self, *args):
        from app.core.security import _get_current_user, get_current_user_roles
        app = self._api.client.app
        # Quitamos los overrides que pusimos
        app.dependency_overrides.pop(_get_current_user, None)
        app.dependency_overrides.pop(get_current_user_roles, None)
        # Restauramos los overrides previos
        app.dependency_overrides.update(self._prev_overrides)


class MultiUserApiClient(ApiClient):
    def __init__(self, client, org_id: int, db_session):
        super().__init__(client, org_id)
        self._db = db_session

    def switch_user(self, user: User):
        _apply_user_overrides(self.client.app, user, self.org_id)
        return self

    def restore_user(self):
        _remove_user_overrides(self.client.app)

    def as_user(self, user: User) -> "as_user":
        return as_user(self, user)


@pytest.fixture
def team_users(db_session, initial_structure):
    org_id = initial_structure["org_id"]

    manager  = _make_user(db_session, "Manager Test",  f"manager_{org_id}@test.com")
    agent    = _make_user(db_session, "Agent Test",    f"agent_{org_id}@test.com")
    outsider = _make_user(db_session, "Outsider Test", f"outsider_{org_id}@test.com")

    _link_user_to_org(db_session, manager,  org_id)
    _link_user_to_org(db_session, agent,    org_id)
    _link_user_to_org(db_session, outsider, org_id)

    db_session.commit()

    return {
        "manager":  manager,
        "agent":    agent,
        "outsider": outsider,
        "org_id":   org_id,
    }


@pytest.fixture
def api_multi(client, initial_structure, db_session):
    org_id     = initial_structure["org_id"]
    api_client = MultiUserApiClient(client, org_id, db_session)
    yield api_client
    api_client.restore_user()
