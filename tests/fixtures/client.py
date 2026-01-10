import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db, SessionLocal 
from unittest.mock import patch

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    # Aquí la magia: sobrescribimos la función EXACTA que usan tus rutas
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.main.run_seeds"):
        with TestClient(app) as c:
            yield c
    
    # Limpieza: quitamos el override para no afectar otros tests si los hubiera
    app.dependency_overrides.clear()