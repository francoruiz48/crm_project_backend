
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, String,Integer
from sqlalchemy.orm import relationship


class Nomenclator(BaseModelDB):
    __tablename__ = "nomenclator"
    name = Column(String, nullable=False)

    parent_nomenclator_id = Column(Integer, ForeignKey("nomenclator.id"), nullable=True)
    parent_nomenclator = relationship("Nomenclator", remote_side=lambda: [Nomenclator.id], backref="sub_nomenclators")

    items = relationship("NomenclatorItem", back_populates="nomenclator", cascade="all, delete-orphan")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=True)
    organization = relationship("Organization", foreign_keys=[organization_id])