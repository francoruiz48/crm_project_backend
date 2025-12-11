
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.models.validation_rule import ValidationRule

class LeadField(BaseModelDB):
    __tablename__ = "lead_field"

    name = Column(String, nullable=False)

    field_type_code = Column(
        String,
        ForeignKey("lead_field_type.code"),
        nullable=False
    )

    required = Column(Boolean, default=False)
    default_value = Column(String, nullable=True)
    is_primary = Column(Boolean, default=False)

    field_type = relationship(
        "LeadFieldType",
        back_populates="fields",
        foreign_keys=[field_type_code]
    )

    # LISTA DE VALORES
    field_values = relationship(
        "LeadFieldValue",
        back_populates="field",
        cascade="all, delete-orphan"
    )

    # LISTA DE VALIDACIONES donde este campo es PRINCIPAL
    validation_rules = relationship(
        "ValidationRule",
        back_populates="field",
        foreign_keys=lambda: [ValidationRule.field_id],
        cascade="all, delete-orphan"
    )

    # LISTA DE VALIDACIONES donde este campo es campo RELACIONADO
    validation_rules_related = relationship(
        "ValidationRule",
        back_populates="related_field",
        foreign_keys=lambda: [ValidationRule.related_field_id],
        cascade="all, delete-orphan"
    )
