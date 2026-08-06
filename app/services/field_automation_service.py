from typing import Optional
from fastapi import HTTPException, status
from app.services.base_service import BaseService
from app.core.error_messages import SUCCESS_CREATE, SUCCESS_UPDATE
from app.db.repository.field_automation_repository import FieldAutomationRepository
from app.db.repository.lead_field_repository import LeadFieldRepository
from app.db.repository.nomenclator_item_repository import NomenclatorItemRepository
from app.db.repository.lead_contact_state_repository import LeadContactStateRepository
from app.db.repository.lead_state_repository import LeadStateRepository
from app.db.repository.team_repository import TeamRepository
from app.db.repository.security_repositories.user_repository import UserRepository
from app.core.security import UserContext
from app.core.constans import SystemAuditLogAction
from app.core.native_lead_fields import NATIVE_LEAD_FIELDS
from app.models.campaign import Campaign
from app.schemas.field_automation_schema import ActionTypeEnum

# Repositorio real de cada campo nativo tipo NATIVE_ID (Etapa/Estado/Equipo/Asignado a/Creador/
# Modificación), usado para resolver condition.value/action.value de public_uuid a id interno --
# ver _resolve_native_id_value. Mismo criterio que _NATIVE_ID_REPOSITORIES en
# lead_routing_policy_service.py, pero cubriendo también Etapa/Estado (contact_state_id/
# current_state_id), que ese archivo no necesita porque las políticas de enrutamiento no
# condicionan/accionan sobre esos dos.
_NATIVE_ID_REPOSITORIES_BY_ATTR = {
    "contact_state_id": LeadContactStateRepository,
    "current_state_id": LeadStateRepository,
    "team_id": TeamRepository,
    "assigned_to_user_id": UserRepository,
    "created_by": UserRepository,
    "updated_by": UserRepository,
}


def _resolve_one_field_id(session, raw_value, field_name: str):
    """Resuelve un field_id de condición/acción (uuid o id interno como string) al id interno
    real. Mismo criterio que _resolve_native_condition_values (lead_routing_policy_service.py):
    si ya es numérico, se deja tal cual (caller interno ya resuelto); si no, se resuelve por
    public_uuid de LeadField."""
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value
    raw_str = str(raw_value)
    if raw_str.lstrip("-").isdigit():
        return int(raw_str)
    resolved = LeadFieldRepository.get_internal_id_by_public_uuid(session, raw_str)
    if resolved is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=[{"field": field_name, "message": f"El campo referenciado ('{raw_str}') no existe."}]
        )
    return resolved


def _get_selector_field_ids(session, field_ids: set) -> set:
    """Devuelve el subconjunto de field_ids (ids internos, ya resueltos) cuyo LeadField es
    de tipo SELECTOR/CHECKBOX con nomenclator_id asociado -- son los únicos campos cuyo
    value/condition.value necesita resolución de NomenclatorItem (public_uuid -> id
    interno). Usado tanto para condiciones como para acciones, ver comentarios en
    _resolve_condition_tree_selector_values y _resolve_actions_field_ids."""
    if not field_ids:
        return set()
    from app.models.lead_field import LeadField
    rows = session.query(LeadField.id).filter(
        LeadField.id.in_(field_ids),
        LeadField.field_type_code.in_(("SELECTOR", "CHECKBOX")),
        LeadField.nomenclator_id.isnot(None),
    ).all()
    return {r[0] for r in rows}


def _resolve_condition_tree_field_ids(session, node):
    """Recorre recursivamente el árbol de condiciones (RuleGroup/RuleCondition) resolviendo
    field_id al id interno de LeadField, mutando el objeto Pydantic in-place."""
    if hasattr(node, "rules"):
        for child in node.rules:
            _resolve_condition_tree_field_ids(session, child)
    else:
        node.field_id = _resolve_one_field_id(session, node.field_id, "conditions")


def _collect_condition_field_ids(node, out: set):
    """Recorre el árbol de condiciones (ya con field_id resuelto a id interno) juntando
    todos los field_id en `out`. Paso previo para saber cuáles son SELECTOR/CHECKBOX."""
    if hasattr(node, "rules"):
        for child in node.rules:
            _collect_condition_field_ids(child, out)
    elif node.field_id is not None:
        out.add(node.field_id)


def _resolve_condition_tree_selector_values(session, node, selector_field_ids: set):
    """Recorre el árbol de condiciones resolviendo node.value de public_uuid de
    NomenclatorItem a id interno, para condiciones sobre campos SELECTOR/CHECKBOX.
    Requiere que _resolve_condition_tree_field_ids ya haya corrido (field_id ya es id
    interno) y que selector_field_ids venga de _get_selector_field_ids.

    Bug real encontrado 2026-08-01 (ver backend/AGENTS.md): ninguna condición sobre un
    campo SELECTOR podía matchear nunca -- el motor (automation_engine.py::
    _evaluate_condition) compara node.value contra el valor guardado en LeadFieldValue
    (id interno, Fase 3), pero node.value llegaba tal cual del front como public_uuid
    (ConditionRow.tsx arma el <Select> con los NomenclatorItem reales, value={opt.id}).
    Mismo bug de fondo que _resolve_native_condition_values/_resolve_selector_condition_values
    en lead_routing_policy_service.py, pero del lado de las condiciones de automatizaciones,
    que nunca se tocó en ese barrido."""
    if hasattr(node, "rules"):
        for child in node.rules:
            _resolve_condition_tree_selector_values(session, child, selector_field_ids)
        return
    if node.field_id in selector_field_ids and node.value is not None:
        if isinstance(node.value, list):
            node.value = [_resolve_one_nomenclator_item_id(session, v) for v in node.value]
        else:
            node.value = _resolve_one_nomenclator_item_id(session, node.value)


def _resolve_one_nomenclator_item_id(session, raw_value):
    """Mismo criterio que _resolve_one_field_id, pero resolviendo contra NomenclatorItem
    (usado por APPEND_TO_LIST/REMOVE_FROM_LIST, cuyo `value` es una lista de ids de opción,
    no de campo)."""
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value
    raw_str = str(raw_value)
    if raw_str.lstrip("-").isdigit():
        return int(raw_str)
    resolved = NomenclatorItemRepository.get_internal_id_by_public_uuid(session, raw_str)
    if resolved is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=[{"field": "value", "message": f"La opción referenciada ('{raw_str}') no existe."}]
        )
    return resolved


def _resolve_native_id_value(session, repo, raw_value, field_name: str):
    """Resuelve un value de condición/acción sobre un campo nativo tipo NATIVE_ID (Etapa/Estado/
    Equipo/Asignado a/Creador/Modificación) de public_uuid a id interno, contra el repositorio
    real de esa entidad (`_NATIVE_ID_REPOSITORIES_BY_ATTR`). Mismo criterio que
    _resolve_one_nomenclator_item_id.

    Bug real encontrado 2026-08-06 (reportado por el usuario): a diferencia de los campos
    SELECTOR/CHECKBOX (LeadField custom, resueltos por _get_selector_field_ids/
    _resolve_condition_tree_selector_values), los 4 campos nativos tipo NATIVE_ID nunca tuvieron
    esta resolución -- ConditionRow.tsx/ActionRow.tsx arman el <Select> con las opciones reales
    (LeadState/LeadContactState/Team/User), value={opt.id}, que a nivel API siempre es el
    public_uuid (aunque `NativeFieldOptions`/`LeadTeam`/`LeadUser` en el frontend lo tipan como
    `number` -- tipos desactualizados de antes de la migración a uuid, ver
    frontend/src/features/lead/nativeLeadFields.ts). Sin resolver, una condición "Estado = X"
    comparaba el uuid crudo contra el id interno real del lead (automation_engine.py::
    _evaluate_condition) y nunca matcheaba -- la regla completa nunca se disparaba, sin ningún
    error visible."""
    if raw_value is None:
        return None
    raw_str = str(raw_value)
    if raw_str.lstrip("-").isdigit():
        return int(raw_str)
    resolved = repo.get_internal_id_by_public_uuid(session, raw_str)
    if resolved is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=[{"field": field_name, "message": f"El valor referenciado ('{raw_str}') no existe."}]
        )
    return resolved


def _resolve_condition_tree_native_values(session, node):
    """Recorre el árbol de condiciones resolviendo node.value de public_uuid a id interno para
    condiciones sobre campos nativos tipo NATIVE_ID (Etapa/Estado/Equipo/Asignado a/Creador/
    Modificación) -- ver _resolve_native_id_value. Requiere que field_id ya sea el id nativo
    negativo (siempre lo es, nunca llega como uuid -- son constantes fijas del front)."""
    if hasattr(node, "rules"):
        for child in node.rules:
            _resolve_condition_tree_native_values(session, child)
        return
    if node.value is None or not isinstance(node.field_id, int):
        return
    native_field = NATIVE_LEAD_FIELDS.get(node.field_id)
    if native_field is None:
        return
    repo = _NATIVE_ID_REPOSITORIES_BY_ATTR.get(native_field.attr)
    if repo is None:
        return
    if isinstance(node.value, list):
        node.value = [_resolve_native_id_value(session, repo, v, "conditions") for v in node.value]
    else:
        node.value = _resolve_native_id_value(session, repo, node.value, "conditions")


def _resolve_actions_field_ids(session, actions):
    """Recorre la lista de acciones resolviendo target_field_id/source_field_id/
    source_field_ids al id interno de LeadField, mutando los objetos Pydantic in-place.

    Bug real encontrado 2026-07-30: para APPEND_TO_LIST/REMOVE_FROM_LIST (que solo tienen
    sentido sobre campos SELECTOR/CHECKBOX), `value` es una lista de ids de NomenclatorItem,
    no un literal a asignar -- así que necesita el mismo tipo de resolución uuid->interno,
    pero contra NomenclatorItem en vez de LeadField."""
    for action in actions:
        action.target_field_id = _resolve_one_field_id(session, action.target_field_id, "target_field_id")
        if action.source_field_id is not None:
            action.source_field_id = _resolve_one_field_id(session, action.source_field_id, "source_field_id")
        if action.source_field_ids:
            action.source_field_ids = [
                _resolve_one_field_id(session, v, "source_field_ids") for v in action.source_field_ids
            ]
        if action.type in (ActionTypeEnum.APPEND_TO_LIST, ActionTypeEnum.REMOVE_FROM_LIST) and action.value is not None:
            values = action.value if isinstance(action.value, list) else [action.value]
            action.value = [_resolve_one_nomenclator_item_id(session, v) for v in values]

    # Bug real encontrado 2026-08-01 (ver backend/AGENTS.md): SET_VALUE/SET_VALUE_IF_EMPTY
    # sobre un campo SELECTOR/CHECKBOX también necesitan esta misma resolución -- el fix de
    # 2026-07-30 de arriba solo cubrió APPEND_TO_LIST/REMOVE_FROM_LIST. El front (ActionRow.tsx)
    # permite setear directamente un NomenclatorItem con SET_VALUE (mismo <Select> con
    # value={item.id}, el public_uuid) -- sin resolver, se guardaría el uuid crudo en
    # LeadFieldValue.value, inconsistente con cómo se guarda un SELECTOR en cualquier otro
    # camino (lead_service.py sí resuelve). Se resuelve en un segundo paso porque necesita
    # target_field_id ya resuelto a id interno (loop de arriba).
    target_ids = {a.target_field_id for a in actions if a.target_field_id is not None}
    selector_target_ids = _get_selector_field_ids(session, target_ids)
    for action in actions:
        if (action.type in (ActionTypeEnum.SET_VALUE, ActionTypeEnum.SET_VALUE_IF_EMPTY)
                and action.target_field_id in selector_target_ids
                and action.value is not None):
            if isinstance(action.value, list):
                action.value = [_resolve_one_nomenclator_item_id(session, v) for v in action.value]
            else:
                action.value = _resolve_one_nomenclator_item_id(session, action.value)

    # Bug real encontrado 2026-08-06 (reportado por el usuario, ver _resolve_native_id_value):
    # mismo caso que el bloque SELECTOR/CHECKBOX de arriba, pero para SET_VALUE/
    # SET_VALUE_IF_EMPTY sobre un campo nativo tipo NATIVE_ID (Etapa/Estado/Equipo/Asignado a).
    # target_field_id ya está resuelto a id interno (negativo, constante) por el loop de arriba.
    for action in actions:
        if (action.type in (ActionTypeEnum.SET_VALUE, ActionTypeEnum.SET_VALUE_IF_EMPTY)
                and action.value is not None
                and isinstance(action.target_field_id, int)):
            native_field = NATIVE_LEAD_FIELDS.get(action.target_field_id)
            if native_field is None:
                continue
            repo = _NATIVE_ID_REPOSITORIES_BY_ATTR.get(native_field.attr)
            if repo is None:
                continue
            if isinstance(action.value, list):
                action.value = [_resolve_native_id_value(session, repo, v, "value") for v in action.value]
            else:
                action.value = _resolve_native_id_value(session, repo, action.value, "value")


class FieldAutomationService(BaseService):
    repository = FieldAutomationRepository

    @classmethod
    def create(cls, obj_data, user_context: Optional[UserContext] = None):
        def do_create(uow):
            # obj_data.campaign_id llega como public_uuid de Campaign desde Fase 3 (el front ya
            # no conoce el id interno). Se resuelve acá porque esta validación corre ANTES de
            # cls.repository.create -- que ya resuelve el mismo campo genéricamente vía
            # BaseRepository._resolve_fk_payload_fields, pero eso pasaría demasiado tarde para
            # este chequeo puntual del Hallazgo #20.
            from app.db.repository.campaign_repository import CampaignRepository
            campaign_internal_id = CampaignRepository.get_internal_id_by_public_uuid(uow.session, obj_data.campaign_id)

            # Hallazgo #20: FieldAutomation no tiene organization_id propio, así que hay
            # que validar acá que el campaign_id recibido pertenezca a la organización activa.
            if user_context is not None and not user_context.is_superuser and user_context.organization_id is not None:
                campaign = uow.session.query(Campaign).filter_by(
                    id=campaign_internal_id, organization_id=user_context.organization_id
                ).first()
                if not campaign:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=[{"field": "campaign_id", "message": "La campaña no existe o no pertenece a esta organización."}]
                    )

            # Bug real encontrado 2026-07-30: RuleCondition.field_id/AutomationAction.
            # target_field_id/source_field_id(s) llegan como public_uuid de LeadField desde
            # Fase 3/4 (el front ya no conoce el id interno), pero se guardan crudos en las
            # columnas JSONB conditions/actions -- había que resolverlos acá, antes de persistir,
            # o la creación de CUALQUIER regla con field_ids reales rompía con 422.
            _resolve_condition_tree_field_ids(uow.session, obj_data.conditions)
            _resolve_actions_field_ids(uow.session, obj_data.actions)
            # Bug real encontrado 2026-08-01 (ver AGENTS.md): condiciones sobre campos
            # SELECTOR/CHECKBOX también necesitan resolver su value (public_uuid de
            # NomenclatorItem -> id interno), igual que ya se hace para las acciones arriba.
            cond_field_ids = set()
            _collect_condition_field_ids(obj_data.conditions, cond_field_ids)
            selector_field_ids = _get_selector_field_ids(uow.session, cond_field_ids)
            _resolve_condition_tree_selector_values(uow.session, obj_data.conditions, selector_field_ids)
            # Bug real encontrado 2026-08-06 (reportado por el usuario): mismo caso que arriba,
            # pero para condiciones sobre campos nativos tipo NATIVE_ID (Etapa/Estado/Equipo/
            # Asignado a/Creador/Modificación) -- ver _resolve_native_id_value.
            _resolve_condition_tree_native_values(uow.session, obj_data.conditions)

            new_obj = cls.repository.create(uow.session, obj_data, user_context=user_context)
            uow.session.flush()

            payload = cls.repository._normalize_data(obj_data)
            cls._log_audit(uow.session, new_obj, action=SystemAuditLogAction.CREATED, changes=payload, user_id=user_context.user.id if user_context else None)

            return new_obj

        return cls._execute(action="Creando", func=do_create, success_msg=SUCCESS_CREATE)

    @classmethod
    def update(cls, obj_id: str, obj_data, user_context: Optional[UserContext] = None):
        def do_update(uow):
            internal_id = cls._resolve_id(uow.session, obj_id)
            if internal_id is None:
                cls._not_found(obj_id)

            old_obj = cls.repository.get_by_id(uow.session, internal_id, user_context, detailed=False)
            if not old_obj:
                cls._not_found(obj_id)

            # Mismo bug y mismo fix que en create() -- ver comentario ahí. FieldAutomationUpdate
            # también permite editar conditions/actions con field_ids uuid.
            if obj_data.conditions is not None:
                _resolve_condition_tree_field_ids(uow.session, obj_data.conditions)
                cond_field_ids = set()
                _collect_condition_field_ids(obj_data.conditions, cond_field_ids)
                selector_field_ids = _get_selector_field_ids(uow.session, cond_field_ids)
                _resolve_condition_tree_selector_values(uow.session, obj_data.conditions, selector_field_ids)
                _resolve_condition_tree_native_values(uow.session, obj_data.conditions)
            if obj_data.actions is not None:
                _resolve_actions_field_ids(uow.session, obj_data.actions)

            payload = cls.repository._normalize_data(obj_data)
            old_data = cls.repository._normalize_data(old_obj)

            changes = {}
            for key, new_val in payload.items():
                if key in old_data:
                    old_val = old_data[key]
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}

            updated_obj = cls.repository.update(uow.session, internal_id, payload, user_context=user_context)
            uow.session.flush()

            if changes:
                cls._log_audit(uow.session, updated_obj, action=SystemAuditLogAction.UPDATED, changes=changes, user_id=user_context.user.id if user_context else None, internal_id=internal_id)

            return updated_obj

        return cls._execute(action="Actualizando", obj_id=obj_id, func=do_update, success_msg=SUCCESS_UPDATE)
