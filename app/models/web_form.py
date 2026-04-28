import uuid
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID # Si usas PostgreSQL, esto es ideal. Si usas MySQL/SQLite, puedes usar String(36)
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class WebForm(BaseModelDB):
    __tablename__ = "web_form"

    # ID interno para relaciones (Rápido y eficiente)
    id = Column(Integer, primary_key=True, index=True)
    
    # UUID público para el iframe (Seguro e inyectable)
    public_uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, index=True, nullable=False)

    # Relaciones base
    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False)

    # Textos
    name = Column(String(150), nullable=False) # Nombre interno (Ej: "Landing Ventas 2026")
    title = Column(String(255), nullable=True) # Título público (Ej: "Déjanos tus datos")
    description = Column(Text, nullable=True) # Subtítulo público

    # Configuración Visual y Comportamiento
    theme_config = Column(JSON, nullable=True) # { "primary_color": "#FF0000", "font": "Arial" }
    success_message = Column(Text, nullable=True)
    redirect_url = Column(String(500), nullable=True)
    
    # Seguridad
    allowed_domains = Column(JSON, nullable=True) # ["https://miweb.com", "https://landing.com"]
    require_captcha = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    # Relaciones ORM
    campaign = relationship("Campaign")
    organization = relationship("Organization")
    fields = relationship("WebFormField", back_populates="web_form", cascade="all, delete-orphan", order_by="WebFormField.order")