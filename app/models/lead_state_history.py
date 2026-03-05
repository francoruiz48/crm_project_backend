from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, ForeignKey, Text

class LeadStateHistory(BaseModelDB):
    __tablename__ = "lead_state_history"
    
    lead_id = Column(Integer, ForeignKey("lead.id"), nullable=False)
    
    # from_state_id puede ser nulo si es el primer estado al crearse
    from_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=True)
    to_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=False)
    
    notes = Column(Text, nullable=True) # Motivo del cambio

    from_state = relationship("LeadState", foreign_keys=[from_state_id])
    to_state = relationship("LeadState", foreign_keys=[to_state_id])