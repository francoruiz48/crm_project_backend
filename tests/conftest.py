import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.db.base_sql import Base
from app.db import session as db_session_module  # Importamos el módulo de sesión

# Motor SQLite en memoria para tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Reemplazamos SessionLocal temporalmente
db_session_module.SessionLocal = TestingSessionLocal

# Crear tablas en la DB de test
Base.metadata.create_all(bind=engine)

# Fixture para sesión de base de datos
@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

# Fixture para cliente de test (FastAPI)
@pytest.fixture(scope="function")
def client(db_session):
    with TestClient(app) as c:
        yield c

# Fixture para datos iniciales
@pytest.fixture(scope="function")
def initial_fields(db_session):
    from app.models.lead_field_type import LeadFieldType
    from app.models.lead_field import LeadField

    # Crear tipos de campo
    string_type = LeadFieldType(code="STRING", description="Texto")
    db_session.add(string_type)
    db_session.commit()
    db_session.refresh(string_type)

    # Crear campos
    nombre_field = LeadField(name="Nombre", field_type_id=string_type.id, required=True)
    apellido_field = LeadField(name="Apellido", field_type_id=string_type.id, required=False)
    db_session.add_all([nombre_field, apellido_field])
    db_session.commit()

    return {"nombre": nombre_field, "apellido": apellido_field}
