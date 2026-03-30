from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class LeadRoutingRule(BaseModelDB):
    __tablename__ = "lead_routing_rule"

    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)
    
    # Si es NULL, es una regla global de la Organización (Solo válido para nomencladores)
    campaign_id = Column(Integer, ForeignKey("campaign.id", ondelete="CASCADE"), nullable=True)
    
    # 'NOMENCLATOR' o 'CUSTOM_FIELD'
    condition_type = Column(String, nullable=False) 
    
    # El ID del Nomenclador (ej: 2 para Provincias) o el ID del LeadField (ej: 85 para Sueldo)
    condition_target_id = Column(Integer, nullable=False)
    
    # El valor a comparar: El ID del item del nomenclador (ej: "45" para Mendoza) o el texto exacto
    condition_value = Column(String, nullable=False)
    
    # A qué equipo se le asigna si hace match
    target_team_id = Column(Integer, ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    
    # Prioridad de ejecución (1 se ejecuta antes que 2)
    order = Column(Integer, nullable=False)

    # Relaciones
    target_team = relationship("Team")
    campaign = relationship("Campaign")