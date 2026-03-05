
from sqlalchemy.orm import relationship

from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint

class LeadStateTransition(BaseModelDB):
    __tablename__ = "lead_state_transition"
    
    lead_flow_id = Column(Integer, ForeignKey("lead_flow.id"), nullable=False)
    
    from_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=False)
    to_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint('lead_flow_id', 'from_state_id', 'to_state_id', name='uix_lead_flow_from_to_state'),
    )

    lead_flow = relationship("LeadFlow", back_populates="transitions")
    from_state = relationship("LeadState", foreign_keys=[from_state_id])
    to_state = relationship("LeadState", foreign_keys=[to_state_id])