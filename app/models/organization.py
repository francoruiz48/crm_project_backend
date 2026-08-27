
from app.models.base_model import BaseModelDB
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class Organization(BaseModelDB):
    __tablename__ = "organization"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    require_lead_state_notes = Column(Boolean, default=False)

    # Identifica a "Panel Global" (la org interna del sistema, ADMIN_ORG_ID) sin
    # depender de que su id interno sea 1. Se setea únicamente en el seed
    # (seed_admin_org, app/db/init_data.py) -- no expuesto en OrganizationCreate/
    # Update, así que ningún usuario puede setearlo vía API. Agregado 2026-07-30:
    # el frontend comparaba activeOrg.id === 1 para identificar esta organización,
    # pero desde Fase 3 Organization.id (expuesto al front) es el public_uuid, no
    # el id interno -- esa comparación dejó de matchear nunca. Ver también
    # SUPERUSER en frontend/src/utils/constants.ts.
    is_system = Column(Boolean, default=False, nullable=False)

    # Contador interno para el número de referencia legible de Lead (ver Lead.lead_number/
    # reference, backend/AGENTS.md §50). Nunca se expone directamente en ningún schema --
    # solo lo usa lead_service.create() para asignar el próximo lead_number de la organización,
    # con un SELECT... FOR UPDATE sobre esta fila para que dos altas simultáneas no puedan
    # terminar con el mismo número.
    lead_counter = Column(Integer, nullable=False, default=0)

    users_access = relationship(
        "UserOrganization", 
        foreign_keys="[UserOrganization.organization_id]", 
        back_populates="organization", 
        cascade="all, delete-orphan"
    )
