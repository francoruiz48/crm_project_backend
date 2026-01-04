
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, String,Integer
from sqlalchemy.orm import relationship


class LeadFieldSection(BaseModelDB):
    __tablename__ = "lead_field_section"
    name = Column(String, nullable=False)