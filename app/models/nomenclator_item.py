
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, String,Integer
from sqlalchemy.orm import relationship


class NomenclatorItem(BaseModelDB):
    __tablename__ = "nomenclator_item"
    code = Column(String, nullable=False, unique=True)
    value = Column(Integer, nullable=False)
    nomenclator_id = Column(Integer, nullable=False)
    nomenclator = relationship("Nomenclator", back_populates="items", foreign_keys=[nomenclator_id])

    parent_item_id = Column(Integer, nullable=True)
    parent_item = relationship("NomenclatorItem", remote_side=["NomenclatorItem.id"], backref="sub_items")

    