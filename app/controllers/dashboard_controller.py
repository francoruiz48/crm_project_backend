from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.security import get_current_user_roles, UserContext, require_superuser
from app.db.session import get_db
from app.schemas.dashboard_schema import OrgDashboardResponse, AdminDashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/org", response_model=OrgDashboardResponse)
def org_dashboard(
    user_context: UserContext = Depends(get_current_user_roles),
    db: Session = Depends(get_db),
):
    """Dashboard de la organizacion activa: leads, estados, actividad, usuarios."""
    return DashboardService.get_org_dashboard(
        organization_id=user_context.organization_id,
        db=db,
    )


@router.get("/admin", response_model=AdminDashboardResponse)
def admin_dashboard(
    _: bool = Depends(require_superuser),
    db: Session = Depends(get_db),
):
    """Dashboard global del Panel Global: metricas de todas las orgs."""
    return DashboardService.get_admin_dashboard(db=db)
