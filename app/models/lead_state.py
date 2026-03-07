
from sqlalchemy.orm import relationship

from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean

class LeadState(BaseModelDB):
    __tablename__ = "lead_state"
    
    lead_flow_id = Column(Integer, ForeignKey("lead_flow.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    
    name = Column(String, nullable=False) 
    color = Column(String, nullable=True)
    
    # Categoría para resolver el problema visual y lógico
    # Opciones: "OPEN" (Activo), "WON" (Éxito), "LOST" (Fracaso)
    category = Column(String, nullable=False, default="OPEN") 
    
    is_initial = Column(Boolean, default=False)
    
    # Solo aplica para los category="OPEN" para ordenar las columnas
    order = Column(Integer, nullable=True)

    lead_flow = relationship("LeadFlow", back_populates="states")