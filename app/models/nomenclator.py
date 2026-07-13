
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, String, Integer, Table
from sqlalchemy.orm import relationship

# Tabla de asociación muchos-a-muchos: un catálogo puede declarar varios
# catálogos "padre" válidos (ej. Ciudades puede ser hija de País Y de Región).
# Reemplaza la vieja columna única parent_nomenclator_id (diseño de la feature
# de nomencladores dependientes, ver docs/nomencladores.md).
nomenclator_parent_association = Table(
    "nomenclator_parent",
    BaseModelDB.metadata,
    Column("nomenclator_id", Integer, ForeignKey("nomenclator.id", ondelete="CASCADE"), primary_key=True),
    Column("parent_nomenclator_id", Integer, ForeignKey("nomenclator.id", ondelete="CASCADE"), primary_key=True),
)


class Nomenclator(BaseModelDB):
    __tablename__ = "nomenclator"
    name = Column(String, nullable=False)

    # parent_nomenclators: los catálogos declarados como "padre válido" de este.
    # child_nomenclators: los catálogos que declaran a este como padre válido.
    parent_nomenclators = relationship(
        "Nomenclator",
        secondary=nomenclator_parent_association,
        primaryjoin=lambda: Nomenclator.id == nomenclator_parent_association.c.nomenclator_id,
        secondaryjoin=lambda: Nomenclator.id == nomenclator_parent_association.c.parent_nomenclator_id,
        backref="child_nomenclators",
    )

    items = relationship("NomenclatorItem", back_populates="nomenclator", cascade="all, delete-orphan")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])