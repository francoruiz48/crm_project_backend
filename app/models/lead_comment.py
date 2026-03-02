
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

class LeadComment(BaseModelDB):
    __tablename__ = "lead_comment"
    content = Column(String, nullable=False)

    lead_id = Column(Integer, ForeignKey("lead.id"), nullable=False)

    lead = relationship("Lead", foreign_keys=[lead_id], back_populates="comments")
