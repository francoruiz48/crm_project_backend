
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer
from sqlalchemy.orm import relationship


class Lead(BaseModelDB):
    __tablename__ = "lead"

    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False)
    campaign = relationship("Campaign", back_populates="leads")
    field_values = relationship("LeadFieldValue", back_populates="lead", cascade="all, delete-orphan")
    comments = relationship("LeadComment", back_populates="lead", cascade="all, delete-orphan")
