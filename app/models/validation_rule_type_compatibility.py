
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

class ValidationRuleTypeCompatibility(BaseModelDB):
    __tablename__ = "validation_rule_type_compatibility"
    validation_rule_type_code = Column(String, ForeignKey("validation_rule_type.code"), nullable=False)
    lead_field_type_code = Column(String, ForeignKey("lead_field_type.code"), nullable=False)
    is_compatible = Column(Boolean, default=True)

    validation_rule_type  = relationship("ValidationRuleType", back_populates="validation_rule_compatibilities", foreign_keys=[validation_rule_type_code])
    lead_field_type = relationship("LeadFieldType", foreign_keys=[lead_field_type_code])


    