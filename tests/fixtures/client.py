import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.db.session import get_db
from app.core.security import _get_current_user


@pytest.fixture(scope="function")
def client(db_session):
    # Override de DB
    def override_get_db():
        yield db_session

    # Override de autenticación: devuelve el superadmin de la DB de test
    # sin validar ningún JWT. Todos los tests existentes siguen funcionando igual.
    def override_get_current_user():
        from app.models.security_models import User
        superadmin = db_session.query(User).filter_by(email="admin@crm.com").first()
        if not superadmin:
            # Fallback: primer usuario de la DB
            superadmin = db_session.query(User).first()
        return superadmin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_get_current_user] = override_get_current_user

    with patch("app.main.run_seeds"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()
