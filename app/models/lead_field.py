
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.models.validation_rule import ValidationRule

class LeadField(BaseModelDB):
    __tablename__ = "lead_field"

    name = Column(String, nullable=False)

    required = Column(Boolean, default=False)
    default_value = Column(String, nullable=True)
    is_primary = Column(Boolean, default=False)
    field_template_code = Column(String, nullable=True)
    field_type_code = Column(String, ForeignKey("lead_field_type.code"), nullable=False)
    field_type = relationship("LeadFieldType", back_populates="fields", foreign_keys=[field_type_code])

    field_values = relationship("LeadFieldValue", back_populates="field", cascade="all, delete-orphan")

    validation_rules = relationship("ValidationRule", back_populates="field", foreign_keys=lambda: [ValidationRule.field_id], cascade="all, delete-orphan")
