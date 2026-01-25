from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

class Workspace(BaseModelDB):
    __tablename__ = "workspace"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    campaigns = relationship("Campaign", back_populates="workspace", passive_deletes="all")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])
