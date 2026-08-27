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
        superadmin = db_session.query(User).filter_by(email="francoruiz.admin@crm.com").first()
        if not superadmin:
            # Fallback: primer usuario de la DB
            superadmin = db_session.query(User).first()
        return superadmin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_get_current_user] = override_get_current_user

    # El schema ya lo crea una única vez por corrida el fixture `db_engine`
    # (scope="session", ver db_fixtures.py). El lifespan de app.main también
    # llama a Base.metadata.create_all + run_seeds en cada startup — y como
    # este fixture es scope="function", eso se repetía en CADA test (~570
    # veces por corrida) contra una base que ya tiene todo creado. run_seeds
    # ya estaba parcheado por este motivo; create_all no, y de vez en cuando
    # esa redundancia corría una carrera real contra el catálogo interno de
    # Postgres (pg_type) y tiraba un IntegrityError espurio en un test
    # cualquiera sin relación con lo que ese test verificaba.
    with patch("app.main.run_seeds"), patch("app.main.Base.metadata.create_all"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()
