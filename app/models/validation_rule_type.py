
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

class ValidationRuleType(BaseModelDB):
    __tablename__ = "validation_rule_type"
    code = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    validation_rule_compatibilities = relationship("ValidationRuleTypeCompatibility", back_populates="validation_rule_type", cascade="all, delete-orphan")
