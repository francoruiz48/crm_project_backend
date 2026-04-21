import pytest
from unittest.mock import patch
from app.models.security_models import User, UserOrganization, Role
from app.models.team_member import TeamMember
from app.models.team import Team
from tests.helpers.api_helpers import ApiClient


def _make_user(db_session, name: str, email: str, is_superuser: bool = False) -> User:
    user = User(name=name, email=email, is_superuser=is_superuser)
    db_session.add(user)
    db_session.flush()
    return user


def _link_user_to_org(db_session, user: User, org_id: int, is_owner: bool = False, role_code: str = "admin") -> UserOrganization:
    role = db_session.query(Role).filter_by(code=role_code, organization_id=None).first()
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


class as_user:
    """
    Context manager que usa dependency_overrides para simular un usuario específico en FastAPI.
    """
    def __init__(self, api, user: User):
        self._api = api
        self._user = user

    def __enter__(self):
        from app.core.security import get_current_user_roles, UserContext
        def fake_get_current_user_roles():
            return UserContext(user=self._user, roles=[], is_superuser=self._user.is_superuser, is_owner=False)
        
        self._api.client.app.dependency_overrides[get_current_user_roles] = fake_get_current_user_roles
        return self

    def __exit__(self, *args):
        from app.core.security import get_current_user_roles
        self._api.client.app.dependency_overrides.pop(get_current_user_roles, None)


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


class MultiUserApiClient(ApiClient):
    def __init__(self, client, org_id: int, db_session):
        super().__init__(client, org_id)
        self._db = db_session

    def switch_user(self, user: User):
        from app.core.security import get_current_user_roles, UserContext
        def fake_get_current_user_roles():
            return UserContext(user=user, roles=[], is_superuser=user.is_superuser, is_owner=False)
        self.client.app.dependency_overrides[get_current_user_roles] = fake_get_current_user_roles
        return self

    def restore_user(self):
        from app.core.security import get_current_user_roles
        self.client.app.dependency_overrides.pop(get_current_user_roles, None)

    def as_user(self, user: User) -> "as_user":
        return as_user(self, user)


@pytest.fixture
def api_multi(client, initial_structure, db_session):
    org_id     = initial_structure["org_id"]
    api_client = MultiUserApiClient(client, org_id, db_session)
    yield api_client
    api_client.restore_user()