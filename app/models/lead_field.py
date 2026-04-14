
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

    #relations
    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False)
    nomenclator_id = Column(Integer, ForeignKey("nomenclator.id"), nullable=True)
    related_campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=True)
    field_template_code = Column(String, nullable=True)
    field_template_name = Column(String, nullable=True)
    field_type_code = Column(String, ForeignKey("lead_field_type.code"), nullable=False)
    lead_field_section_id = Column(Integer, ForeignKey("lead_field_section.id"), nullable=False)
    field_subtype_code = Column(String, ForeignKey("lead_field_subtype.code"), nullable=True)
    
    field_type = relationship("LeadFieldType", back_populates="fields", foreign_keys=[field_type_code])
    field_subtype = relationship("LeadFieldSubtype", foreign_keys=[field_subtype_code])
    field_values = relationship("LeadFieldValue", back_populates="field", passive_deletes="all")
    validation_rules = relationship("ValidationRule", back_populates="field", foreign_keys=lambda: [ValidationRule.field_id], cascade="all, delete-orphan")
    campaign = relationship("Campaign", foreign_keys=[campaign_id])
    nomenclator = relationship("Nomenclator", foreign_keys=[nomenclator_id])
    lead_field_section = relationship("LeadFieldSection", foreign_keys=[lead_field_section_id])
    related_campaign = relationship("Campaign", foreign_keys=[related_campaign_id])

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])