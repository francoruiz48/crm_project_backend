from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

class LeadFlow(BaseModelDB):
    __tablename__ = "lead_flow"
    
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    
    # Relaciones
    states = relationship("LeadState", back_populates="lead_flow", cascade="all, delete-orphan")
    transitions = relationship("LeadStateTransition", back_populates="lead_flow", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="lead_flow")