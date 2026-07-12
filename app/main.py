from contextlib import asynccontextmanager
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from fastapi.exceptions import RequestValidationError
from app.core.middlewares import setup_cors
from app.core.security import get_client_ip
from app.core.wait_for_db import wait_for_db
from app.db.base_sql import Base
from app.db.session import engine
from app.db.init_data import run_seeds
from app.routers import router as api_router
from app.core.exceptions.exceptions import ValidationError
from app.core.exceptions.handlers import pydantic_exception_handler, custom_validation_exception_handler

# Instanciamos el limitador basado en la IP del cliente
# Hallazgo #11 (2026-07-11): key_func usa get_client_ip (X-Forwarded-For/
# X-Real-IP con fallback a request.client.host) en vez de get_remote_address
# de slowapi — necesario si hay un proxy delante, ver app/core/security.py.
limiter = Limiter(key_func=get_client_ip)

# --- CICLO DE VIDA (LIFESPAN) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Esperar DB (Bloqueante pero seguro)
    print("⏳ Esperando base de datos...")
    wait_for_db()

    # 2. Crear Tablas
    print("🔄 Creando tablas en la base de datos...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas listas.")

    # 3. Correr Seeders
    print("🌱 Ejecutando seeds...")
    try:
        run_seeds()
        print("✅ Seeds completados.")
    except Exception as e:
        print(f"⚠️ Error en seeds al inicio: {e}")
    
    # 4. Iniciar App
    print("🚀 Aplicación lista para recibir peticiones.")
    yield
    
    # 5. Apagar
    print("🛑 Apagando aplicación...")

# --- DEFINICIÓN APP ---
app = FastAPI(
    title="CRM Backend",
    lifespan=lifespan # <--- Todo lo anterior ocurre aquí, UNA sola vez.
)

# --- INYECCIÓN DE SLOWAPI (RATE LIMITER) ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- HANDLERS Y MIDDLEWARES ---
app.add_exception_handler(RequestValidationError, pydantic_exception_handler)
app.add_exception_handler(ValidationError, custom_validation_exception_handler)

setup_cors(app)

app.include_router(api_router)