from sqlalchemy import Column, String, Integer, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB, Base


# Tabla intermedia para guardar la lista de items seleccionados
lead_field_value_nomenclator_assoc = Table(
    'lead_field_value_nomenclator',
    Base.metadata,
    Column('lead_field_value_id', Integer, ForeignKey('lead_field_value.id'), primary_key=True),
    Column('nomenclator_item_id', Integer, ForeignKey('nomenclator_item.id'), primary_key=True)
)

lead_field_value_leads_assoc = Table(
    'lead_field_value_leads',
    Base.metadata,
    Column('lead_field_value_id', Integer, ForeignKey('lead_field_value.id', ondelete="CASCADE"), primary_key=True),
    Column('related_lead_id', Integer, ForeignKey('lead.id', ondelete="CASCADE"), primary_key=True)
)

class LeadFieldValue(BaseModelDB):
    __tablename__ = "lead_field_value"
    lead_id = Column(Integer, ForeignKey("lead.id"), nullable=False)
    field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=False)
    value = Column(String, nullable=True)  # Todo se guarda como texto y se interpreta según field_type

    lead = relationship("Lead", back_populates="field_values")
    field = relationship("LeadField", back_populates="field_values")

    nomenclator_items = relationship(
        "NomenclatorItem",
        secondary=lead_field_value_nomenclator_assoc,
        lazy="selectin" # Cargamos la lista automáticamente
    )

    related_leads = relationship(
        "Lead", 
        secondary=lead_field_value_leads_assoc,
        lazy="joined"
    )

