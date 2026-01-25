
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class Organization(BaseModelDB):
    __tablename__ = "organization"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
