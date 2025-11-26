
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship


class Lead(BaseModelDB):
    __tablename__ = "lead"
    field_values = relationship("LeadFieldValue", back_populates="lead", cascade="all, delete-orphan")
