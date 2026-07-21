
from app.models.base_model import BaseModelDB
from sqlalchemy import JSON, Column, Integer, String, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.models.validation_rule import ValidationRule

class LeadField(BaseModelDB):
    __tablename__ = "lead_field"

    name = Column(String, nullable=False)
    required = Column(Boolean, default=False)
    default_value = Column(String, nullable=True)
    is_primary = Column(Boolean, default=False)
    input_mask = Column(String, nullable=True)
    order = Column(Integer, nullable=False)
    is_visible = Column(Boolean, default=True)
    calculation_expression = Column(String, nullable=True)
    configuration = Column(JSON, nullable=True)
    title_order = Column(Integer, nullable=True)
    #Igual que title_order pero para el subtítulo (línea secundaria debajo del título, ej. Cargo
    #+ Empresa). Mismo mecanismo: varios campos pueden tener subtitle_order, se concatenan en ese
    #orden. Ver LeadFieldService._maybe_auto_assign_title_order (auto-detección) y
    #getLeadSubtitleArray en el frontend (leadUtils.ts).
    subtitle_order = Column(Integer, nullable=True)

    #relations
    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False)
    nomenclator_id = Column(Integer, ForeignKey("nomenclator.id"), nullable=True)
    related_campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=True)
    field_template_code = Column(String, nullable=True)
    field_template_name = Column(String, nullable=True)
    field_type_code = Column(String, ForeignKey("lead_field_type.code"), nullable=False)
    lead_field_section_id = Column(Integer, ForeignKey("lead_field_section.id"), nullable=False)
    field_subtype_code = Column(String, ForeignKey("lead_field_subtype.code"), nullable=True)
    # Feature de nomencladores dependientes (ver docs/nomencladores.md): este
    # campo (de tipo SELECTOR/CHECKBOX) solo ofrece ítems cuyo padre sea el
    # ítem elegido en depends_on_field, otro campo nomenclador de la MISMA
    # campaña. Autoreferencia simple (un solo padre por campo) — permite
    # cadenas (A depende de B que depende de C).
    depends_on_field_id = Column(Integer, ForeignKey("lead_field.id"), nullable=True)

    field_type = relationship("LeadFieldType", back_populates="fields", foreign_keys=[field_type_code])
    field_subtype = relationship("LeadFieldSubtype", foreign_keys=[field_subtype_code])
    field_values = relationship("LeadFieldValue", back_populates="field", passive_deletes="all")
    validation_rules = relationship("ValidationRule", back_populates="field", foreign_keys=lambda: [ValidationRule.field_id], cascade="all, delete-orphan")
    web_form_fields = relationship("WebFormField", foreign_keys="WebFormField.lead_field_id", viewonly=True, overlaps="lead_field")
    campaign = relationship("Campaign", foreign_keys=[campaign_id])
    nomenclator = relationship("Nomenclator", foreign_keys=[nomenclator_id])
    lead_field_section = relationship("LeadFieldSection", foreign_keys=[lead_field_section_id])
    related_campaign = relationship("Campaign", foreign_keys=[related_campaign_id])
    depends_on_field = relationship("LeadField", remote_side=lambda: [LeadField.id], backref="dependent_fields")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])