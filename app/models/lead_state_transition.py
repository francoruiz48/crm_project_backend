
from sqlalchemy.orm import relationship

from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint

class LeadStateTransition(BaseModelDB):
    __tablename__ = "lead_state_transition"
    
    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False)
    
    from_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=True)
    to_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint('campaign_id', 'from_state_id', 'to_state_id', name='uix_campaign_from_to_state'),
    )

    from_state = relationship("LeadState", foreign_keys=[from_state_id])
    to_state = relationship("LeadState", foreign_keys=[to_state_id])