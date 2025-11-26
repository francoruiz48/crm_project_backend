from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class LeadFieldValue(BaseModelDB):
    __tablename__ = "lead_field_value"
    lead_id = Column(Integer, ForeignKey("lead.id"), nullable=False)
    field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=False)
    value = Column(String, nullable=True)  # Todo se guarda como texto y se interpreta según field_type

    lead = relationship("Lead", back_populates="field_values")
    field = relationship("LeadField", back_populates="field_values")
