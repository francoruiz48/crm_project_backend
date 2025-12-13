
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Float, Integer, String, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime

class ValidationRule(BaseModelDB):
    __tablename__ = "validation_rule"
    static_value = Column(String, nullable=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    min_length = Column(Integer, nullable=True)
    max_length = Column(Integer, nullable=True)
    regex_pattern = Column(String, nullable=True)
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)

    rule_type_code = Column(String, ForeignKey("validation_rule_type.code"), nullable=False)
    field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=False)
    related_field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=True)

    rule_type  = relationship("ValidationRuleType", foreign_keys=[rule_type_code])
    field = relationship("LeadField", back_populates="validation_rules", foreign_keys=[field_id])
    related_field = relationship("LeadField", back_populates="validation_rules_related", foreign_keys=[related_field_id])
