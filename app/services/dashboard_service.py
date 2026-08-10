from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.lead import Lead
from app.models.lead_state import LeadState
from app.models.lead_contact_state import LeadContactState
from app.models.security_models import User, UserOrganization
from app.models.organization import Organization
from app.models.audit.system_audit_log import SystemAuditLog
from app.schemas.dashboard_schema import (
    OrgDashboardResponse, LeadsByState, LeadsByContactState,
    RecentActivity, OrgUser,
    AdminDashboardResponse, OrgStats,
)
from app.core.constans import ADMIN_ORG_ID


class DashboardService:

    @classmethod
    def get_org_dashboard(cls, organization_id: int, db: Session) -> OrgDashboardResponse:
        # Total leads
        total_leads = db.query(func.count(Lead.id)).filter(
            Lead.organization_id == organization_id,
            Lead.active == True,
        ).scalar() or 0

        # Leads by flow state
        # Leads by contact state
        contact_counts = (
            db.query(LeadContactState.id, LeadContactState.name, LeadContactState.color, func.count(Lead.id))
            .join(Lead, Lead.contact_state_id == LeadContactState.id)
            .filter(Lead.organization_id == organization_id, Lead.active == True)
            .group_by(LeadContactState.id, LeadContactState.name, LeadContactState.color)
            .all()
        )
        leads_by_contact_state = [
            LeadsByContactState(state_id=r[0], state_name=r[1], color=r[2], total=r[3])
            for r in contact_counts
        ]

        # Recent activity (last 20 audit logs for this org)
        recent_logs = (
            db.query(SystemAuditLog, User)
            .outerjoin(User, SystemAuditLog.created_by == User.id)
            .filter(SystemAuditLog.organization_id == organization_id)
            .order_by(SystemAuditLog.created_at.desc())
            .limit(20)
            .all()
        )
        recent_activity = [
            RecentActivity(
                id=log.public_uuid,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_uuid,
                user_name=f"{u.name} {u.last_name or ''}".strip() if u else None,
                created_at=log.created_at,
            )
            for log, u in recent_logs
        ]

        # Org users
        memberships = (
            db.query(UserOrganization, User)
            .join(User, UserOrganization.user_id == User.id)
            .filter(
                UserOrganization.organization_id == organization_id,
                UserOrganization.active == True,
            )
            .all()
        )
        org_users = [
            OrgUser(
                id=u.public_uuid, name=u.name, last_name=u.last_name,
                email=u.email, is_owner=m.is_owner,
            )
            for m, u in memberships
        ]

        state_rows = (
            db.query(
                LeadState.id, LeadState.name, LeadState.color,
                func.count(Lead.id).label("total")
            )
            .join(Lead, Lead.current_state_id == LeadState.id)
            .filter(Lead.organization_id == organization_id, Lead.active == True)
            .group_by(LeadState.id, LeadState.name, LeadState.color)
            .all()
        )
        leads_by_flow_state = [
            LeadsByState(state_id=r[0], state_name=r[1], color=r[2], total=r[3])
            for r in state_rows
        ]

        return OrgDashboardResponse(
            total_leads=total_leads,
            leads_by_flow_state=leads_by_flow_state,
            leads_by_contact_state=leads_by_contact_state,
            recent_activity=recent_activity,
            org_users=org_users,
        )

    @classmethod
    def get_admin_dashboard(cls, db: Session) -> AdminDashboardResponse:
        # All active orgs except Panel Global (id=ADMIN_ORG_ID)
        orgs = db.query(Organization).filter(
            Organization.active == True,
            Organization.id != ADMIN_ORG_ID,
        ).all()

        total_active_orgs = len(orgs)

        org_stats = []
        total_users_global = 0
        total_leads_global = 0

        for org in orgs:
            user_count = db.query(func.count(UserOrganization.id)).filter(
                UserOrganization.organization_id == org.id,
                UserOrganization.active == True,
            ).scalar() or 0

            lead_count = db.query(func.count(Lead.id)).filter(
                Lead.organization_id == org.id,
                Lead.active == True,
            ).scalar() or 0

            last_log = (
                db.query(SystemAuditLog.created_at)
                .filter(SystemAuditLog.organization_id == org.id)
                .order_by(SystemAuditLog.created_at.desc())
                .first()
            )

            total_users_global += user_count
            total_leads_global += lead_count

            # Owner
            owner_row = (
                db.query(User)
                .join(UserOrganization, UserOrganization.user_id == User.id)
                .filter(
                    UserOrganization.organization_id == org.id,
                    UserOrganization.is_owner == True,
                    UserOrganization.active == True,
                )
                .first()
            )
            owner_name = f"{owner_row.name} {owner_row.last_name or ''}".strip() if owner_row else None

            org_stats.append(OrgStats(
                org_id=org.public_uuid,
                org_name=org.name,
                total_users=user_count,
                total_leads=lead_count,
                last_activity=last_log[0] if last_log else None,
                owner_name=owner_name,
            ))

        return AdminDashboardResponse(
            total_active_orgs=total_active_orgs,
            total_users=total_users_global,
            total_leads=total_leads_global,
            orgs=org_stats,
        )
