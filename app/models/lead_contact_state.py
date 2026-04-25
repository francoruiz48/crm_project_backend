from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class LeadContactState(BaseModelDB):
    __tablename__ = "lead_contact_state"

    name = Column(String(100), nullable=False)
    color = Column(String, nullable=True)
    is_initial = Column(Boolean, default=False)
    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)
    leads = relationship("Lead", back_populates="contact_state")