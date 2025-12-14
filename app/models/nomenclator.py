
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, String,Integer
from sqlalchemy.orm import relationship


class Nomenclator(BaseModelDB):
    __tablename__ = "nomenclator"
    name = Column(String, nullable=False)
    
    #relations
    campaign_id = Column(Integer, nullable=True)
    campaign = relationship("Campaign", back_populates="nomenclators", foreign_keys=[campaign_id])
    parent_nomenclator_id = Column(Integer, nullable=True)
    parent_nomenclator = relationship("Nomenclator", remote_side=["Nomenclator.id"], backref="sub_nomenclators")
    items = relationship("NomenclatorItem", back_populates="nomenclator")