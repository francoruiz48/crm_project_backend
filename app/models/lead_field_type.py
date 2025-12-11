
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

class LeadFieldType(BaseModelDB):
    __tablename__ = "lead_field_type"
    code = Column(String, unique=True, nullable=False) 
    description = Column(String, nullable=False)

    fields = relationship("LeadField", back_populates="field_type")
    
