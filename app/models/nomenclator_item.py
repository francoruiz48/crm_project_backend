
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, String, Integer, Table
from sqlalchemy.orm import relationship

# Tabla de asociación muchos-a-muchos: un ítem puede tener varios ítems "padre"
# a la vez (uno por cada dimensión de jerarquía que declare su catálogo, ej.
# una ciudad puede tener como padre tanto su país como su región). Reemplaza
# la vieja columna única parent_item_id (ver docs/nomencladores.md).
nomenclator_item_parent_association = Table(
    "nomenclator_item_parent",
    BaseModelDB.metadata,
    Column("item_id", Integer, ForeignKey("nomenclator_item.id", ondelete="CASCADE"), primary_key=True),
    Column("parent_item_id", Integer, ForeignKey("nomenclator_item.id", ondelete="CASCADE"), primary_key=True),
)


class NomenclatorItem(BaseModelDB):
    __tablename__ = "nomenclator_item"
    value = Column(String, nullable=False)

    nomenclator_id = Column(Integer, ForeignKey("nomenclator.id"), nullable=False)
    nomenclator = relationship("Nomenclator", back_populates="items", foreign_keys=[nomenclator_id])

    # parent_items: los ítems padre de este ítem (uno por cada catálogo padre
    # aplicable). child_items: los ítems que declaran a este como padre.
    parent_items = relationship(
        "NomenclatorItem",
        secondary=nomenclator_item_parent_association,
        primaryjoin=lambda: NomenclatorItem.id == nomenclator_item_parent_association.c.item_id,
        secondaryjoin=lambda: NomenclatorItem.id == nomenclator_item_parent_association.c.parent_item_id,
        backref="child_items",
    )

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])
