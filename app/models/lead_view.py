from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class LeadView(BaseModelDB):
    __tablename__ = "lead_view"

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    
    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False) 
    name = Column(String, nullable=False)
    visibility = Column(String, nullable=False, default="PRIVATE") # 'PRIVATE', 'TEAM', 'PUBLIC'
    team_id = Column(Integer, ForeignKey("team.id"), nullable=True)
    
    # --- CONFIGURACIÓN DEL FRONTEND ---
    view_type = Column(String, nullable=False, default="LIST") # 'LIST', 'KANBAN', 'CALENDAR', etc.
    filters = Column(JSONB, nullable=True, default={})
    ui_config = Column(JSONB, nullable=True, default={}) # Todo lo visual: order de columnas, anchos
    sort_config = Column(JSONB, nullable=True, default={"sort_by": "created_at", "ascending": False})

    # Relaciones
    campaign = relationship("Campaign")
    team = relationship("Team")