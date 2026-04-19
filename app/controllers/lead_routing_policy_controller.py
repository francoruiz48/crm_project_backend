"""
Controller para LeadRoutingPolicy v3.
Endpoints: GET all, GET one, POST, PUT, DELETE, POST /validate
"""
from typing import Optional, Union
from fastapi import APIRouter, Body, Depends, Query

from app.core.constans import DEFAULT_PAGE_SIZE
from app.core.security import get_current_user_roles
from app.schemas.pagination_schema import PaginatedResponse
from app.schemas.lead_routing_policy_schema import (
    LeadRoutingPolicyCreate,
    LeadRoutingPolicyDetailedResponse,
    LeadRoutingPolicyResponse,
    LeadRoutingPolicyUpdate,
    LeadRoutingPolicyValidateRequest,
    LeadRoutingPolicyValidateResponse,
)
from app.services.lead_routing_policy_service import LeadRoutingPolicyService

router = APIRouter(prefix="/lead_routing_policies", tags=["Routing Policies"])

ResponseModelItem = Union[LeadRoutingPolicyDetailedResponse, LeadRoutingPolicyResponse]
ResponseModelPaginated = PaginatedResponse[ResponseModelItem]


@router.get("/", response_model=ResponseModelPaginated)
def get_all(
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(DEFAULT_PAGE_SIZE),
    only_active: bool          = True,
    detailed:    bool          = Query(False),
    campaign_id: Optional[int] = Query(None),
    user_context               = Depends(get_current_user_roles),
):
    kwargs = {}
    if campaign_id is not None:
        kwargs["campaign_id"] = campaign_id

    total, items = LeadRoutingPolicyService.get_all(
        user_context=user_context,
        page=page,
        page_size=page_size,
        only_active=only_active,
        detailed=detailed,
        **kwargs,
    )
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.get("/{obj_id}", response_model=ResponseModelItem)
def get_one(
    obj_id:      int,
    detailed:    bool = Query(True),
    user_context      = Depends(get_current_user_roles),
):
    obj = LeadRoutingPolicyService.get_by_id(obj_id, detailed=detailed, user_context=user_context)
    if not obj:
        from fastapi import HTTPException
        raise HTTPException(404, "Política de enrutamiento no encontrada.")
    return obj


@router.post("/", response_model=LeadRoutingPolicyDetailedResponse)
def create(
    obj_in:      LeadRoutingPolicyCreate = Body(...),
    user_context                          = Depends(get_current_user_roles),
):
    return LeadRoutingPolicyService.create(obj_in, user_context=user_context)


@router.put("/{obj_id}", response_model=LeadRoutingPolicyDetailedResponse)
def update(
    obj_id:      int,
    obj_in:      LeadRoutingPolicyUpdate = Body(...),
    user_context                          = Depends(get_current_user_roles),
):
    return LeadRoutingPolicyService.update(obj_id, obj_in, user_context=user_context)


@router.delete("/{obj_id}")
def delete(obj_id: int, user_context=Depends(get_current_user_roles)):
    return LeadRoutingPolicyService.delete(obj_id, user_context=user_context)


@router.post("/validate", response_model=LeadRoutingPolicyValidateResponse)
def validate(
    obj_in:      LeadRoutingPolicyValidateRequest = Body(...),
    user_context                                   = Depends(get_current_user_roles),
):
    """Valida condiciones sin persistirlas. Útil mientras se construye la política."""
    return LeadRoutingPolicyService.validate(obj_in, user_context=user_context)