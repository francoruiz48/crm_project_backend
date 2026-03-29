
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, String,Integer
from sqlalchemy.orm import relationship


class NomenclatorItem(BaseModelDB):
    __tablename__ = "nomenclator_item"
    value = Column(String, nullable=False)
    
    nomenclator_id = Column(Integer, ForeignKey("nomenclator.id"), nullable=False)
    nomenclator = relationship("Nomenclator", back_populates="items", foreign_keys=[nomenclator_id])

    parent_item_id = Column(Integer, ForeignKey("nomenclator_item.id"), nullable=True)
    parent_item = relationship("NomenclatorItem", remote_side=lambda: [NomenclatorItem.id], backref="sub_items")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=True)
    organization = relationship("Organization", foreign_keys=[organization_id])

    