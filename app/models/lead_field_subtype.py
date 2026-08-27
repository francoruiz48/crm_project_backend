
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

class LeadFieldSubtype(BaseModelDB):
    __tablename__ = "lead_field_subtype"
    code = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=False)

    lead_field_type_code = Column(String, ForeignKey("lead_field_type.code"), nullable=False)
    lead_field_type = relationship("LeadFieldType", back_populates="subtypes", foreign_keys=[lead_field_type_code])
