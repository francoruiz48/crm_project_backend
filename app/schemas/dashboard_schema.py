from datetime import datetime
from typing import Optional
from pydantic import BaseModel


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
    id: int
    action: str
    entity_type: str
    entity_id: int
    user_name: Optional[str] = None
    created_at: datetime

class OrgUser(BaseModel):
    id: int
    name: str
    last_name: Optional[str] = None
    email: str
    is_owner: bool

class OrgDashboardResponse(BaseModel):
    total_leads: int
    leads_by_flow_state: list[LeadsByState]
    leads_by_contact_state: list[LeadsByContactState]
    recent_activity: list[RecentActivity]
    org_users: list[OrgUser]


# ── Admin / Panel Global Dashboard ────────────────────────────────────────

class OrgStats(BaseModel):
    org_id: int
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
