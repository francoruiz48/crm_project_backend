from app.core.wait_for_db import wait_for_db
from app.db.base_sql import Base
from app.db.session import engine
from app.db.init_data import run_seeds
from fastapi import FastAPI
import app.models
from app.controllers.lead_controller import router as lead_router
from app.controllers.lead_field_controller import router as lead_field_router
from app.controllers.lead_field_type_controller import router as lead_field_type_router

wait_for_db()

Base.metadata.create_all(bind=engine)
run_seeds()

app = FastAPI(title="CRM Flexible")
app.include_router(lead_router)
app.include_router(lead_field_router)
app.include_router(lead_field_type_router)
