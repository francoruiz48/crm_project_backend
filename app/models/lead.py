
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship


class Lead(BaseModelDB):
    __tablename__ = "lead"

    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False)
    campaign = relationship("Campaign", back_populates="leads")
    field_values = relationship("LeadFieldValue", back_populates="lead", cascade="all, delete-orphan")
    comments = relationship("LeadComment", back_populates="lead", cascade="all, delete-orphan")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])

    current_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=True)
    current_state = relationship("LeadState", foreign_keys=[current_state_id])

    state_history = relationship(
        "LeadStateHistory", 
        back_populates="lead", 
        cascade="all, delete-orphan"
    )
