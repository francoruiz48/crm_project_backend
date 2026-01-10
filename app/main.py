from app.core.middlewares import setup_cors
from app.core.wait_for_db import wait_for_db
from app.db.base_sql import Base
from app.db.session import engine
from app.db.init_data import run_seeds
from fastapi import FastAPI
from app.routers import router as api_router
from contextlib import asynccontextmanager

wait_for_db()

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Esto se ejecuta al iniciar la app
    print("🚀 Ejecutando tareas de inicio...")
    try:
        run_seeds()
    except Exception as e:
        print(f"⚠️ Error en seeds al inicio: {e}")
    
    yield
    
    # Esto se ejecuta al apagar la app
    print("🛑 Apagando aplicación...")

app = FastAPI(
    title="CRM Backend",
    lifespan=lifespan
)

setup_cors(app)

app.include_router(api_router)
