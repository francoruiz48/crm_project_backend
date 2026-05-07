from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from app.models.base_model import BaseModelDB

class FieldAutomation(BaseModelDB):
    __tablename__ = "field_automation"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(150), nullable=False)
    description = Column(String(500), nullable=True)
    
    # ARRAY de strings para saber cuándo escuchar. Ej: ["ON_CREATE", "ON_UPDATE"]
    trigger_events = Column(ARRAY(String), nullable=False)
    
    # El árbol recursivo de condiciones
    conditions = Column(JSONB, nullable=False)
    
    # La lista de acciones a ejecutar
    actions = Column(JSONB, nullable=False)
    
    # Orden de ejecución (por si hay conflictos entre dos reglas)
    priority = Column(Integer, default=1, nullable=False)
    
    active = Column(Boolean, default=True, nullable=False)