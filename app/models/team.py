from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class Team(BaseModelDB):
    __tablename__ = "team"

    name = Column(String, nullable=False)
    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)
    
    # Si es True, todos los miembros ven los leads de todos en el equipo.
    # Si es False, el agente solo ve los suyos (asignados a él) y los "sin asignar".
    is_visibility_shared = Column(Boolean, default=True, nullable=False)
    

    # Relaciones
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    workspace_access = relationship("TeamWorkspaceAccess", back_populates="team", cascade="all, delete-orphan")
    campaign_access = relationship("TeamCampaignAccess", back_populates="team", cascade="all, delete-orphan")