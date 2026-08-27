from __future__ import annotations
from typing import Optional

from fastapi import HTTPException, status

from app.core.security import UserContext
from app.db.repository.base_repository import BaseRepository
from app.db.repository.team_repository import TeamRepository
from app.db.repository.campaign_repository import CampaignRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.security_repositories.user_repository import UserRepository
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
from app.core.constans import DeleteStrategy
from app.services.routing_rule_evaluator_service import RoutingRuleEvaluatorService
from app.core.constans import SystemAuditLogAction


class LeadRoutingPolicyRepository(BaseRepository):
    model             = LeadRoutingPolicy
    schema_out        = LeadRoutingPolicyResponse
    schema_out_detail = LeadRoutingPolicyDetailedResponse
    delete_strategy   = DeleteStrategy.HARD_DELETE_WITH_TOGGLE


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


# Campos nativos tipo "ID de otra entidad" (a diferencia de current_state_id, que se
# ingresa a mano como el id interno -- ver RoutingConditionRow.tsx -- y de created_at/
# updated_at, que son fechas). El front (RoutingConditionRow.tsx) los muestra como un
# selector de la entidad real y guarda su public_uuid en value_str.
_NATIVE_ID_REPOSITORIES = {
    "assigned_to_user_id": UserRepository,
    "team_id": TeamRepository,
    "campaign_id": CampaignRepository,
}


def _resolve_native_condition_values(session, conditions_in: list[LeadRoutingConditionCreate]) -> list[LeadRoutingConditionCreate]:
    """cond.value_str llega como public_uuid para condiciones sobre los campos nativos de
    _NATIVE_ID_REPOSITORIES (el usuario elige la entidad real desde un selector). El
    evaluador de reglas (routing_rule_evaluator_service.py::_evaluate_condition) compara
    ese valor contra el id interno crudo del Lead (lead.team_id, lead.assigned_to_user_id,
    lead.campaign_id -- FKs embebidas, nunca migradas a uuid), como string. Sin resolver
    acá, un uuid nunca es igual a un int y la condición no matchea NUNCA -- bug real
    encontrado en el audit de Fase 4 (ver backend/AGENTS.md §18-ter): cualquier política
    de enrutamiento que filtrara por equipo/usuario/campaña quedaba silenciosamente
    inoperante. Se resuelve una sola vez acá (al guardar), no en cada evaluación, mismo
    criterio que _resolve_condition_field_ids.

    Si value_str YA es numérico (id interno), se deja tal cual -- mismo criterio que
    resolve_fk_filter_value (base_repository.py): permite pasar el id interno directo
    además del uuid real que manda el front. Sin este chequeo se rompía
    test_routing_policy_native_field_assigned_to_user (test_teams_and_routing.py),
    que arma la condición a mano con el id interno del usuario de prueba (creado
    directo en la sesión de test, no via API) -- antes "funcionaba" de casualidad
    porque el evaluador también compara contra el id interno crudo del Lead."""
    for cond in conditions_in:
        repo = _NATIVE_ID_REPOSITORIES.get(cond.native_field)
        if repo is None or not cond.value_str:
            continue
        if cond.value_str.lstrip("-").isdigit():
            continue
        resolved = repo.get_internal_id_by_public_uuid(session, cond.value_str)
        if resolved is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "conditions", "message": f"El valor de la condición ('{cond.native_field}') no existe."}]
            )
        cond.value_str = str(resolved)
    return conditions_in


def _resolve_selector_condition_values(session, conditions_in: list[LeadRoutingConditionCreate]) -> list[LeadRoutingConditionCreate]:
    """cond.value_str/value_list llegan como public_uuid de NomenclatorItem para condiciones
    sobre campos DINÁMICOS tipo SELECTOR/CHECKBOX (el front, RoutingConditionRow.tsx, arma
    un <Select> con los NomenclatorItem reales -- item.id es el public_uuid desde Fase 3,
    es lo único que expone la API). El evaluador (routing_rule_evaluator_service.py::
    _evaluate_condition) compara ese valor contra el id interno crudo que LeadFieldValue.value
    guarda para SELECTOR (lead_service.py ya resuelve public_uuid -> id interno al guardar
    un lead). Sin resolver acá, un uuid nunca es igual a un int y la condición no matchea
    NUNCA -- mismo bug de Fase 4 que _resolve_native_condition_values, pero para campos
    dinámicos en vez de nativos; quedó afuera de ese barrido. Bug real encontrado 2026-08-01
    corriendo scripts/seed_data_v1.py (ver backend/AGENTS.md): ni la API ni el front podían
    crear una política con condición sobre un campo SELECTOR -- _validate_condition_data la
    rechazaba con 400 "Los valores para campos SELECTOR deben ser IDs enteros".

    Requiere que _resolve_condition_field_ids ya haya corrido (usa cond.lead_field_id como
    id interno para ubicar el LeadField y su nomenclator_id)."""
    from app.models.lead_field import LeadField
    from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository

    field_ids = {c.lead_field_id for c in conditions_in if c.lead_field_id and not c.native_field}
    if not field_ids:
        return conditions_in

    fields = session.query(LeadField).filter(LeadField.id.in_(field_ids)).all()
    selector_field_ids = {
        f.id for f in fields
        if f.field_type_code in ("SELECTOR", "CHECKBOX") and f.nomenclator_id
    }
    if not selector_field_ids:
        return conditions_in

    def _resolve_one(raw):
        if raw is None:
            return raw
        s = str(raw)
        if s.lstrip("-").isdigit():
            return s  # ya es el id interno (compat, mismo criterio que _resolve_native_condition_values)
        resolved = NomenclatorItemRepository.get_internal_id_by_public_uuid(session, s)
        if resolved is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=[{"field": "conditions", "message": f"El valor de la condición ('{raw}') no existe en el nomenclador del campo."}]
            )
        return str(resolved)

    for cond in conditions_in:
        if cond.lead_field_id not in selector_field_ids:
            continue
        if cond.value_str:
            cond.value_str = _resolve_one(cond.value_str)
        if cond.value_list:
            cond.value_list = [_resolve_one(v) for v in cond.value_list]

    return conditions_in


def _delete_conditions(session, policy: LeadRoutingPolicy):
    for cond in policy.conditions:
        session.delete(cond)
    session.flush()


def _resolve_condition_field_ids(session, conditions_in: list[LeadRoutingConditionCreate]) -> list[LeadRoutingConditionCreate]:
    """cond.lead_field_id llega como public_uuid de LeadField (Fase 3, ver
    backend/AGENTS.md §18). Se resuelve acá a id interno, mutando la lista in-place
    (mismos objetos se reusan después en _build_conditions y en validate_conditions
    vía model_dump())."""
    field_uuids = {c.lead_field_id for c in conditions_in if c.lead_field_id}
    if not field_uuids:
        return conditions_in
    uuid_to_id = LeadFieldRepository.get_internal_ids_by_public_uuids(session, list(field_uuids))
    for c in conditions_in:
        if c.lead_field_id:
            resolved = uuid_to_id.get(c.lead_field_id)
            if resolved is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=[{"field": "conditions", "message": f"El campo {c.lead_field_id} no existe."}]
                )
            c.lead_field_id = resolved
    return conditions_in


class LeadRoutingPolicyService(BaseService):
    repository = LeadRoutingPolicyRepository

    @classmethod
    def create(cls, obj_in: LeadRoutingPolicyCreate, user_context: Optional[UserContext] = None):
        def do_create(uow):
            from app.core.context import TENANT_ORG_ID
            # FIX DE PRECEDENCIA: TENANT_ORG_ID puede no estar seteado si la dependencia
            # sync corrió en otro thread (mismo problema ya parcheado en validate()).
            # user_context.organization_id es más confiable: se resuelve como atributo
            # normal en get_current_user_roles, sin depender del contextvar.
            org_id = TENANT_ORG_ID.get() or (user_context.organization_id if user_context else None)
            if not org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Falta el header X-Organization-Id.")

            # obj_in.target_team_id/campaign_id llegan como public_uuid (Fase 3, ver
            # backend/AGENTS.md §18); se resuelven acá antes de cualquier query cruda.
            target_team_internal_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.target_team_id)
            if target_team_internal_id is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "target_team_id", "message": "El equipo destino no existe."}])

            campaign_internal_id = None
            if obj_in.campaign_id:
                campaign_internal_id = CampaignRepository.get_internal_id_by_public_uuid(uow.session, obj_in.campaign_id)
                if campaign_internal_id is None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "campaign_id", "message": "La campaña no existe."}])

            _validate_team_org(uow.session, target_team_internal_id, org_id)
            _assert_manager(uow.session, user_context, target_team_internal_id)
            _validate_priority(uow.session, org_id, campaign_internal_id, obj_in.priority)

            # Resuelve lead_field_id de cada condición (public_uuid -> id interno) antes de
            # validar/persistir.
            _resolve_condition_field_ids(uow.session, obj_in.conditions)
            # Resuelve value_str de condiciones nativas tipo entidad (assigned_to_user_id/
            # team_id/campaign_id) de public_uuid a id interno -- ver comentario en la
            # función, bug de Fase 4 catalogado en backend/AGENTS.md §18-ter.
            _resolve_native_condition_values(uow.session, obj_in.conditions)
            # Idem para value_str/value_list de condiciones sobre campos dinámicos SELECTOR/
            # CHECKBOX (public_uuid de NomenclatorItem -> id interno) -- ver AGENTS.md.
            _resolve_selector_condition_values(uow.session, obj_in.conditions)

            errors = RoutingRuleEvaluatorService.validate_conditions(
                session         = uow.session,
                conditions_data = [c.model_dump() for c in obj_in.conditions],
                organization_id = org_id,
                campaign_id     = campaign_internal_id,
                target_team_id  = target_team_internal_id,
            )
            if errors:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "conditions", "message": e} for e in errors])

            policy = LeadRoutingPolicy(
                organization_id  = org_id,
                campaign_id      = campaign_internal_id,
                name             = obj_in.name,
                description      = obj_in.description,
                priority         = obj_in.priority,
                logical_operator = obj_in.logical_operator,
                target_team_id   = target_team_internal_id,
            )
            uow.session.add(policy)
            uow.session.flush()

            _build_conditions(uow.session, obj_in.conditions, policy.id, org_id)

            cls._log_audit(uow.session, policy, action=SystemAuditLogAction.CREATED,
                           changes=obj_in.model_dump(exclude={"conditions"}),
                           user_id=user_context.user.id if user_context else None)

            return LeadRoutingPolicyDetailedResponse.model_validate(policy)

        return cls._execute(action="Crear Política de Enrutamiento", func=do_create)

    @classmethod
    def update(cls, obj_id: str, obj_in: LeadRoutingPolicyUpdate, user_context: Optional[UserContext] = None):
        def do_update(uow):
            from app.core.context import TENANT_ORG_ID
            # FIX DE PRECEDENCIA: mismo caso que en create() (ver comentario ahí).
            org_id = TENANT_ORG_ID.get() or (user_context.organization_id if user_context else None)
            if not org_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Falta el header X-Organization-Id.")

            # obj_id llega como public_uuid (lo único que conoce el front) — lo resolvemos
            # al id interno antes de cualquier query directa (ver BaseService._resolve_id).
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            policy = uow.session.query(LeadRoutingPolicy).filter_by(id=internal_id, organization_id=org_id).first()
            if not policy:
                cls._not_found(obj_id)

            # obj_in.target_team_id llega como public_uuid (Fase 3, ver backend/AGENTS.md
            # §18); se resuelve acá antes de compararlo/asignarlo (policy.target_team_id,
            # atributo ORM, sigue siendo el id interno).
            resolved_team_id = None
            if obj_in.target_team_id is not None:
                resolved_team_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.target_team_id)
                if resolved_team_id is None:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=[{"field": "target_team_id", "message": "El equipo destino no existe."}])

            team_id = resolved_team_id if resolved_team_id is not None else policy.target_team_id
            _assert_manager(uow.session, user_context, team_id)

            if resolved_team_id is not None and resolved_team_id != policy.target_team_id:
                _validate_team_org(uow.session, resolved_team_id, org_id)

            if obj_in.priority and obj_in.priority != policy.priority:
                _validate_priority(uow.session, org_id, policy.campaign_id, obj_in.priority, exclude_id=internal_id)

            for field in ("name", "description", "priority", "logical_operator"):
                val = getattr(obj_in, field, None)
                if val is not None:
                    setattr(policy, field, val)

            if resolved_team_id is not None:
                policy.target_team_id = resolved_team_id

            if obj_in.conditions is not None:
                # Resuelve lead_field_id de cada condición (public_uuid -> id interno).
                _resolve_condition_field_ids(uow.session, obj_in.conditions)
                # Idem para value_str de condiciones nativas tipo entidad, ver comentario
                # en la función (bug de Fase 4, backend/AGENTS.md §18-ter).
                _resolve_native_condition_values(uow.session, obj_in.conditions)
                _resolve_selector_condition_values(uow.session, obj_in.conditions)
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

            cls._log_audit(uow.session, policy, action=SystemAuditLogAction.UPDATED,
                           changes=obj_in.model_dump(exclude_unset=True, exclude={"conditions"}),
                           user_id=user_context.user.id if user_context else None)

            return LeadRoutingPolicyDetailedResponse.model_validate(policy)

        return cls._execute(action="Actualizar Política", obj_id=obj_id, func=do_update)

    @classmethod
    def _get_policy_or_404(cls, session, obj_id: int, user_context: Optional[UserContext] = None) -> LeadRoutingPolicy:
        policy = cls.repository.get_by_id(session, obj_id, user_context, detailed=False)
        if not policy:
            cls._not_found(obj_id)
        return policy

    @classmethod
    def delete(cls, obj_id: str, user_context: Optional[UserContext] = None, force: bool = False):
        # Hallazgo #16: a diferencia de create/update, el genérico de BaseService
        # solo valida organización (vía get_by_id) — no rol MANAGER del equipo.
        # obj_id llega como public_uuid; lo resolvemos acá para el chequeo de manager,
        # pero le pasamos a super() el uuid original (BaseService lo vuelve a resolver).
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            policy = cls._get_policy_or_404(uow.session, internal_id, user_context)
            _assert_manager(uow.session, user_context, policy.target_team_id)
        return super().delete(obj_id, user_context=user_context, force=force)

    @classmethod
    def set_active(cls, obj_id: str, user_context: Optional[UserContext] = None):
        # Hallazgo #16: mismo chequeo que delete/deactivate.
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            policy = cls._get_policy_or_404(uow.session, internal_id, user_context)
            _assert_manager(uow.session, user_context, policy.target_team_id)
        return super().set_active(obj_id, user_context=user_context)

    @classmethod
    def deactivate(cls, obj_id: str, user_context: Optional[UserContext] = None):
        # Hallazgo #16: mismo chequeo que delete/set_active.
        with UnitOfWork() as uow:
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)
            policy = cls._get_policy_or_404(uow.session, internal_id, user_context)
            _assert_manager(uow.session, user_context, policy.target_team_id)
        return super().deactivate(obj_id, user_context=user_context)

    @classmethod
    def validate(cls, obj_in: LeadRoutingPolicyValidateRequest, user_context: Optional[UserContext] = None) -> LeadRoutingPolicyValidateResponse:
        from app.core.context import TENANT_ORG_ID
        with UnitOfWork() as uow:
            # FIX DE PRECEDENCIA: Garantiza que org_id sea seguro incluso si el middleware de test client está en otro thread
            org_id = TENANT_ORG_ID.get()
            if not org_id and hasattr(obj_in, "organization_id"):
                org_id = obj_in.organization_id

            # obj_in.target_team_id/campaign_id llegan como public_uuid (Fase 3, ver
            # backend/AGENTS.md §18); se resuelven acá. Al ser un endpoint de validación
            # (no lanza HTTPException por reglas de negocio), un uuid que no resuelve se
            # reporta como error de validación en vez de un 400.
            target_team_internal_id = TeamRepository.get_internal_id_by_public_uuid(uow.session, obj_in.target_team_id)
            if target_team_internal_id is None:
                return LeadRoutingPolicyValidateResponse(valid=False, errors=["El equipo destino no existe."])

            campaign_internal_id = None
            if obj_in.campaign_id:
                campaign_internal_id = CampaignRepository.get_internal_id_by_public_uuid(uow.session, obj_in.campaign_id)
                if campaign_internal_id is None:
                    return LeadRoutingPolicyValidateResponse(valid=False, errors=["La campaña no existe."])

            try:
                _resolve_condition_field_ids(uow.session, obj_in.conditions)
                _resolve_native_condition_values(uow.session, obj_in.conditions)
                _resolve_selector_condition_values(uow.session, obj_in.conditions)
            except HTTPException as e:
                detail = e.detail if isinstance(e.detail, list) else [{"message": str(e.detail)}]
                return LeadRoutingPolicyValidateResponse(valid=False, errors=[d.get("message", str(d)) for d in detail])

            errors = RoutingRuleEvaluatorService.validate_conditions(
                session         = uow.session,
                conditions_data = [c.model_dump() for c in obj_in.conditions],
                organization_id = org_id,
                campaign_id     = campaign_internal_id,
                target_team_id  = target_team_internal_id,
            )
        return LeadRoutingPolicyValidateResponse(valid=len(errors) == 0, errors=errors)