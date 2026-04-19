from __future__ import annotations
from typing import Optional

from fastapi import HTTPException, status

from app.core.security import UserContext
from app.db.repository.base_repository import BaseRepository
from app.db.unit_of_work import UnitOfWork
from app.models.lead_routing_policy import LeadRoutingCondition, LeadRoutingPolicy
from app.models.team import Team
from app.models.team_member import TeamMember
from app.schemas.lead_routing_policy_schema import (
    LeadRoutingConditionCreate,
    LeadRoutingPolicyCreate,
    LeadRoutingPolicyDetailedResponse,
    LeadRoutingPolicyResponse,
    LeadRoutingPolicyUpdate,
    LeadRoutingPolicyValidateRequest,
    LeadRoutingPolicyValidateResponse,
)
from app.services.base_service import BaseService
from app.services.routing_rule_evaluator_service import RoutingRuleEvaluatorService


class LeadRoutingPolicyRepository(BaseRepository):
    model             = LeadRoutingPolicy
    schema_out        = LeadRoutingPolicyResponse
    schema_out_detail = LeadRoutingPolicyDetailedResponse


def _assert_manager(session, user_context: Optional[UserContext], team_id: int):
    if not user_context or not user_context.user:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Se requiere autenticación.")
    if user_context.is_superuser or user_context.is_owner:
        return
    membership = session.query(TeamMember).filter_by(
        team_id=team_id, user_id=user_context.user.id, role="MANAGER"
    ).first()
    if not membership:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Solo un MANAGER del equipo puede gestionar sus políticas de enrutamiento."
        )


def _validate_team_org(session, team_id: int, organization_id: int):
    team = session.query(Team).filter_by(id=team_id).first()
    if not team:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=[{"field": "target_team_id", "message": f"El equipo ID={team_id} no existe."}]
        )
    if team.organization_id != organization_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=[{"field": "target_team_id", "message": "El equipo no pertenece a esta organización."}]
        )


def _validate_priority(session, org_id: int, campaign_id: Optional[int], priority: int, exclude_id: Optional[int] = None):
    q = session.query(LeadRoutingPolicy).filter_by(
        organization_id=org_id, campaign_id=campaign_id, priority=priority
    )
    if exclude_id:
        q = q.filter(LeadRoutingPolicy.id != exclude_id)
    if q.first():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=[{"field": "priority", "message": f"Ya existe una política con prioridad {priority} en este scope."}]
        )


def _build_conditions(session, conditions_in: list[LeadRoutingConditionCreate], policy_id: int, organization_id: int):
    for cond in conditions_in:
        db_cond = LeadRoutingCondition(
            policy_id     = policy_id,
            position      = cond.position,
            lead_field_id = cond.lead_field_id,
            native_field  = cond.native_field,
            operator      = cond.operator,
            value_str     = cond.value_str,
            value_list    = cond.value_list,
            operator_min  = cond.operator_min,
            value_min     = cond.value_min,
            operator_max  = cond.operator_max,
            value_max     = cond.value_max,
        )
        session.add(db_cond)
    session.flush()


def _delete_conditions(session, policy: LeadRoutingPolicy):
    for cond in policy.conditions:
        session.delete(cond)
    session.flush()


class LeadRoutingPolicyService(BaseService):
    repository = LeadRoutingPolicyRepository

    @classmethod
    def create(cls, obj_in: LeadRoutingPolicyCreate, user_context: Optional[UserContext] = None):
        def do_create(uow):
            from app.core.context import TENANT_ORG_ID
            org_id = TENANT_ORG_ID.get()
            if not org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Falta el header X-Organization-Id.")

            _validate_team_org(uow.session, obj_in.target_team_id, org_id)
            _assert_manager(uow.session, user_context, obj_in.target_team_id)
            _validate_priority(uow.session, org_id, obj_in.campaign_id, obj_in.priority)

            errors = RoutingRuleEvaluatorService.validate_conditions(
                session         = uow.session,
                conditions_data = [c.model_dump() for c in obj_in.conditions],
                organization_id = org_id,
                campaign_id     = obj_in.campaign_id,
                target_team_id  = obj_in.target_team_id,
            )
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "conditions", "message": e} for e in errors])

            policy = LeadRoutingPolicy(
                organization_id  = org_id,
                campaign_id      = obj_in.campaign_id,
                name             = obj_in.name,
                description      = obj_in.description,
                priority         = obj_in.priority,
                logical_operator = obj_in.logical_operator,
                target_team_id   = obj_in.target_team_id,
            )
            uow.session.add(policy)
            uow.session.flush()

            _build_conditions(uow.session, obj_in.conditions, policy.id, org_id)

            cls._log_audit(uow.session, policy, action="CREATE",
                           changes=obj_in.model_dump(exclude={"conditions"}),
                           user_id=user_context.user.id if user_context else None)

            return LeadRoutingPolicyDetailedResponse.model_validate(policy)

        return cls._execute(action="Crear Política de Enrutamiento", func=do_create)

    @classmethod
    def update(cls, obj_id: int, obj_in: LeadRoutingPolicyUpdate, user_context: Optional[UserContext] = None):
        def do_update(uow):
            from app.core.context import TENANT_ORG_ID
            org_id = TENANT_ORG_ID.get()

            policy = uow.session.query(LeadRoutingPolicy).filter_by(id=obj_id, organization_id=org_id).first()
            if not policy:
                cls._not_found(obj_id)

            team_id = obj_in.target_team_id or policy.target_team_id
            _assert_manager(uow.session, user_context, team_id)

            if obj_in.target_team_id and obj_in.target_team_id != policy.target_team_id:
                _validate_team_org(uow.session, obj_in.target_team_id, org_id)

            if obj_in.priority and obj_in.priority != policy.priority:
                _validate_priority(uow.session, org_id, policy.campaign_id, obj_in.priority, exclude_id=obj_id)

            for field in ("name", "description", "priority", "logical_operator", "target_team_id"):
                val = getattr(obj_in, field, None)
                if val is not None:
                    setattr(policy, field, val)

            if obj_in.conditions is not None:
                errors = RoutingRuleEvaluatorService.validate_conditions(
                    session         = uow.session,
                    conditions_data = [c.model_dump() for c in obj_in.conditions],
                    organization_id = org_id,
                    campaign_id     = policy.campaign_id,
                    target_team_id  = policy.target_team_id,
                )
                if errors:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "conditions", "message": e} for e in errors])
                _delete_conditions(uow.session, policy)
                _build_conditions(uow.session, obj_in.conditions, policy.id, org_id)

            uow.session.flush()

            cls._log_audit(uow.session, policy, action="UPDATE",
                           changes=obj_in.model_dump(exclude_unset=True, exclude={"conditions"}),
                           user_id=user_context.user.id if user_context else None)

            return LeadRoutingPolicyDetailedResponse.model_validate(policy)

        return cls._execute(action="Actualizar Política", obj_id=obj_id, func=do_update)

    @classmethod
    def validate(cls, obj_in: LeadRoutingPolicyValidateRequest, user_context: Optional[UserContext] = None) -> LeadRoutingPolicyValidateResponse:
        from app.core.context import TENANT_ORG_ID
        with UnitOfWork() as uow:
            # FIX DE PRECEDENCIA: Garantiza que org_id sea seguro incluso si el middleware de test client está en otro thread
            org_id = TENANT_ORG_ID.get()
            if not org_id and hasattr(obj_in, "organization_id"):
                org_id = obj_in.organization_id

            errors = RoutingRuleEvaluatorService.validate_conditions(
                session         = uow.session,
                conditions_data = [c.model_dump() for c in obj_in.conditions],
                organization_id = org_id,
                campaign_id     = obj_in.campaign_id,
                target_team_id  = obj_in.target_team_id,
            )
        return LeadRoutingPolicyValidateResponse(valid=len(errors) == 0, errors=errors)