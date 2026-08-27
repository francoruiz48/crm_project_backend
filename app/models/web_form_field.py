from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class WebFormField(BaseModelDB):
    __tablename__ = "web_form_field"

    id = Column(Integer, primary_key=True, index=True)
    web_form_id = Column(Integer, ForeignKey("web_form.id", ondelete="CASCADE"), nullable=False)
    lead_field_id = Column(Integer, ForeignKey("lead_field.id", ondelete="CASCADE"), nullable=False)

    # Orden visual dentro del formulario web
    order = Column(Integer, nullable=False, default=1)

    # Sobrescrituras visuales (Opcionales)
    custom_label = Column(String(150), nullable=True) # Ej: "Tu número de WhatsApp" en vez de "Teléfono"
    custom_placeholder = Column(String(150), nullable=True)
    
    # Reglas de negocio para el formulario público
    is_required = Column(Boolean, default=False)
    
    # Si tiene un hidden_value, el campo NO se muestra al usuario, 
    # pero el backend lo inyecta automáticamente al crear el lead.
    hidden_value = Column(String(500), nullable=True)

    # Relaciones ORM
    web_form = relationship("WebForm", back_populates="fields")
    lead_field = relationship("LeadField", overlaps="web_form_fields")