import pytest
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.base_sql import Base
from app.db import session as db_session_module
from app.db.init_data import run_seeds

# Importamos explícitamente para asegurar que esté cargado y poder parchearlo
import app.db.unit_of_work 

# Configuración de URLs
ADMIN_DB_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/postgres"
TEST_DB_NAME = "crm_test_db"
TEST_DB_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{TEST_DB_NAME}"

@pytest.fixture(scope="session")
def db_engine():
    # 1. Crear DB Limpia
    admin_engine = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        # Terminamos conexiones activas para evitar bloqueos
        conn.execute(text(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TEST_DB_NAME}'
            AND pid <> pg_backend_pid();
        """))
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    
    test_engine = create_engine(TEST_DB_URL)
    
    # 2. Crear Schema
    Base.metadata.create_all(bind=test_engine)
    
    # 3. Correr Seeders
    SessionForSeeds = sessionmaker(bind=test_engine)
    session_seeds = SessionForSeeds()
    print("🌱 [TEST] Ejecutando seeders en DB de prueba...")
    try:
        run_seeds(db=session_seeds)
        session_seeds.commit()
    except Exception as e:
        print(f"🔥 [TEST] Falló el seeding: {e}")
        raise e
    finally:
        session_seeds.close()

    yield test_engine
    test_engine.dispose()

@pytest.fixture(scope="function")
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    
    # join_transaction_mode="create_savepoint": sin esto, un session.commit() hecho por
    # código de producción (UnitOfWork.__exit__ en una request exitosa) termina la
    # transacción REAL de la conexión (no un savepoint anidado dentro de `transaction` de
    # arriba). Si más tarde, en la misma sesión de test, una request que se espera que
    # falle dispara session.rollback() (UnitOfWork.__exit__ en el path de excepción), ese
    # rollback deshace TODO lo commiteado desde el arranque del test, no solo esa request
    # fallida -- bug real encontrado 2026-08-01 (ver backend/AGENTS.md), reproducido con un
    # script standalone: sin este flag, una fila commiteada desaparece tras un rollback
    # posterior en la misma sesión; con el flag, sobrevive y el aislamiento entre tests
    # (rollback de `transaction` al final de este fixture) sigue funcionando igual.
    SessionTest = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    session = SessionTest()

    # --- 🛡️ PROTECCIÓN CONTRA CIERRE PREMATURO ---
    # Guardamos el método close original
    real_close = session.close
    
    # Reemplazamos .close() por una función vacía para que el UnitOfWork no la cierre
    session.close = lambda: None
    # ---------------------------------------------
    
    # --- MONKEYPATCHING NUCLEAR ---
    # 1. Guardamos el original (Source of Truth) para restaurar después
    real_session_factory = db_session_module.SessionLocal
    
    # 2. Guardamos explícitamente el original de UnitOfWork (si existe)
    real_uow_session = getattr(app.db.unit_of_work, "SessionLocal", None)

    mock_session_factory = lambda: session
    
    # 3. Parcheamos TODOS los módulos cargados que usen la sesión original
    patched_modules = []
    for mod_name, module in list(sys.modules.items()):
        if hasattr(module, "SessionLocal") and module.SessionLocal is real_session_factory:
            setattr(module, "SessionLocal", mock_session_factory)
            patched_modules.append(mod_name)
            
    # 4. Parcheamos explícitamente UnitOfWork (Redundancia de seguridad)
    if hasattr(app.db.unit_of_work, "SessionLocal"):
        app.db.unit_of_work.SessionLocal = mock_session_factory

    yield session
    
    # --- LIMPIEZA ---
    # 1. Restaurar en todos los módulos parcheados dinámicamente
    for mod_name in patched_modules:
        module = sys.modules[mod_name]
        setattr(module, "SessionLocal", real_session_factory)

    # 2. Restaurar explícitamente UnitOfWork y el módulo base
    db_session_module.SessionLocal = real_session_factory
    if real_uow_session:
        app.db.unit_of_work.SessionLocal = real_uow_session

    # 3. Restauramos el .close() real
    session.close = real_close
    
    # 4. Rollback y cierre ordenado (El orden es clave para evitar warnings)
    transaction.rollback() 
    session.close()
    connection.close()