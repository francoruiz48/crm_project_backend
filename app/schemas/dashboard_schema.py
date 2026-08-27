from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Org Dashboard ─────────────────────────────────────────────────────────

class LeadsByState(BaseModel):
    state_id: int
    state_name: str
    color: Optional[str] = None
    total: int

class LeadsByContactState(BaseModel):
    state_id: int
    state_name: str
    color: Optional[str] = None
    total: int

class RecentActivity(BaseModel):
    # Se construye a mano en dashboard_service.py (no via model_validate desde el
    # ORM), así que ahí se pasa id=log.public_uuid directamente. El alias queda
    # igual para soportar también una futura construcción desde el objeto ORM.
    # entity_id ahora es el uuid real de la entidad auditada (log.entity_uuid),
    # no el id interno -- mismo fix que system_audit_log_schema.py, ver
    # backend/AGENTS.md §18-ter.
    id: str = Field(validation_alias="public_uuid")
    action: str
    entity_type: str
    entity_id: str
    user_name: Optional[str] = None
    created_at: datetime

    model_config = {"populate_by_name": True}

class OrgUser(BaseModel):
    # Idem RecentActivity: dashboard_service.py pasa id=u.public_uuid a mano.
    id: str = Field(validation_alias="public_uuid")
    name: str
    last_name: Optional[str] = None
    email: str
    is_owner: bool

    model_config = {"populate_by_name": True}

class OrgDashboardResponse(BaseModel):
    total_leads: int
    leads_by_flow_state: list[LeadsByState]
    leads_by_contact_state: list[LeadsByContactState]
    recent_activity: list[RecentActivity]
    org_users: list[OrgUser]


# ── Admin / Panel Global Dashboard ────────────────────────────────────────

class OrgStats(BaseModel):
    # org_id acá es el id de la propia organización de esta fila (no una FK a otra
    # entidad), así que aplica el mismo criterio: se pasa org.public_uuid desde
    # dashboard_service.py en vez del id interno.
    org_id: str
    org_name: str
    total_users: int
    total_leads: int
    last_activity: Optional[datetime] = None
    owner_name: Optional[str] = None

class AdminDashboardResponse(BaseModel):
    total_active_orgs: int
    total_users: int
    total_leads: int
    orgs: list[OrgStats]
