from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

# Tabla de asociación para la relación Muchos a Muchos
lead_tag_association = Table(
    "lead_tag",
    BaseModelDB.metadata,
    Column("lead_id", Integer, ForeignKey("lead.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)

class Tag(BaseModelDB):
    __tablename__ = "tag"

    name = Column(String, nullable=False)
    color = Column(String, nullable=False, default="#3B82F6")
    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)

    # Relación con Leads
    leads = relationship("Lead", secondary=lead_tag_association, back_populates="tags")