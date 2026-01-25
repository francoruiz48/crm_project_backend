
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Float, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

class ValidationRule(BaseModelDB):
    __tablename__ = "validation_rule"
    name = Column(String, nullable=True)
    expression = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    template_code = Column(String, nullable=True)
    template_params = Column(JSON, nullable=True)

    #relationships
    field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=False)
    field = relationship("LeadField", back_populates="validation_rules", foreign_keys=[field_id])

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])