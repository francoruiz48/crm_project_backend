
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

class ValidationRuleType(BaseModelDB):
    __tablename__ = "validation_rule_type"
    code = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    lead_field_type_code = Column(String, ForeignKey("lead_field_type.code"), nullable=False)

    lead_field_type = relationship("LeadFieldType", foreign_keys=[lead_field_type_code])
