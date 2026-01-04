from app.core.middlewares import setup_cors
from app.core.wait_for_db import wait_for_db
from app.db.base_sql import Base
from app.db.session import engine
from app.db.init_data import run_seeds
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import router as api_router

wait_for_db()

Base.metadata.create_all(bind=engine)
run_seeds()

app = FastAPI(title="CRM Flexible")

setup_cors(app)

app.include_router(api_router)
