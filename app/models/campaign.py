
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, String,Integer
from sqlalchemy.orm import relationship


class Campaign(BaseModelDB):
    __tablename__ = "campaign"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    nomenclators = relationship("Nomenclator", back_populates="campaign", cascade="all, delete-orphan")
