
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Float, Integer, String, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

class ValidationRule(BaseModelDB):
    __tablename__ = "validation_rule"
    name = Column(String, nullable=False)
    expression = Column(String, nullable=False)
    error_message = Column(String, nullable=False) 

    #relationships
    field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=True)
    related_field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=True)

    field = relationship("LeadField", back_populates="validation_rules", foreign_keys=[field_id])
    related_field = relationship("LeadField", back_populates="validation_rules_related", foreign_keys=[related_field_id])
