from app.models.base_model import BaseModelDB
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

class Workspace(BaseModelDB):
    __tablename__ = "workspace"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    campaigns = relationship("Campaign", back_populates="workspace", passive_deletes="all")
