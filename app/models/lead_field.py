
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

class LeadField(BaseModelDB):
    __tablename__ = "lead_field"
    name = Column(String, nullable=False)
    field_type_id = Column(Integer, ForeignKey("lead_field_type.id"), nullable=False)
    required = Column(Boolean, default=False)
    default_value = Column(String, nullable=True)

    field_type  = relationship("LeadFieldType", back_populates="fields")
    field_values = relationship("LeadFieldValue", back_populates="field", cascade="all, delete-orphan")