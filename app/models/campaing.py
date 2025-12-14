
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, String,Integer
from sqlalchemy.orm import relationship


class Campaign(BaseModelDB):
    __tablename__ = "campaign"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    parent_campaign_id = Column(Integer, nullable=True)

    parent_campaign = relationship("Campaign", remote_side=["Campaign.id"], backref="sub_campaigns")
    nomenclators = relationship("Nomenclator", back_populates="campaign", cascade="all, delete-orphan")
