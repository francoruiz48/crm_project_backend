"""
Generador de un resumen legible ("Si <condiciones> entonces <acciones>") de lo que hace una
FieldAutomation, a partir de sus `conditions`/`actions` YA RESUELTOS A ID INTERNO -- es decir,
antes de que `_unresolve_field_automation_values` (field_automation_service.py) los convierta
de vuelta a public_uuid para la respuesta al front. Se llama a `build_field_automation_summary`
justo antes de ese paso (ver FieldAutomationService.get_by_id/get_all).

Pedido por el usuario (2026-08-29): mostrar como subtítulo en el listado de automatizaciones
(AutomationList.tsx) un resumen preciso de la regla, en vez de depender de la `description`
manual que el usuario carga a mano (texto libre, puede estar vacía o desactualizada respecto a
lo que la regla realmente hace).

Se calcula al vuelo en cada consulta -- no se persiste en ninguna columna nueva -- para que
nunca quede desactualizado si después se renombra un Estado, una opción de nomenclador, un
campo, etc. (mismo criterio de precisión que AGENTS.md §58 ya aplicó al buscador global).
Costo: 1-3 queries chicas por automatización (batch por tipo de entidad referenciada), nada
comparado con el resto de columnas que ya se resuelven en el mismo método.
"""
from app.core.native_lead_fields import NATIVE_LEAD_FIELDS
from app.models.lead_field import LeadField
from app.models.nomenclator_item import NomenclatorItem
from app.models.lead_state import LeadState
from app.models.lead_contact_state import LeadContactState
from app.models.team import Team
from app.models.security_models import User
from app.schemas.field_automation_schema import ActionTypeEnum, LogicalOperatorEnum

# ==========================================
# PLANTILLAS EN ESPAÑOL
# ==========================================
# Mismo texto/criterio que CONDITION_OPERATOR_LABELS en frontend/src/types/automation.ts,
# pero como plantilla de oración en vez de solo el verbo -- se mantienen sincronizados a mano
# (igual que NATIVE_LEAD_FIELDS entre backend/frontend, ver native_lead_fields.py).
CONDITION_OPERATOR_TEMPLATES = {
    "EQUALS": "{field} es igual a {value}",
    "NOT_EQUALS": "{field} no es igual a {value}",
    "CONTAINS": "{field} contiene {value}",
    "NOT_CONTAINS": "{field} no contiene {value}",
    "GREATER_THAN": "{field} es mayor que {value}",
    "LESS_THAN": "{field} es menor que {value}",
    "IS_EMPTY": "{field} está vacío",
    "IS_NOT_EMPTY": "{field} no está vacío",
    "STARTS_WITH": "{field} empieza con {value}",
    "ENDS_WITH": "{field} termina con {value}",
    "IS_PAST": "{field} es una fecha pasada",
    "IS_FUTURE": "{field} es una fecha futura",
}

# Operadores que no llevan `value` en la oración (chequeos de forma, no de contenido).
_OPERATORS_WITHOUT_VALUE = {"IS_EMPTY", "IS_NOT_EMPTY", "IS_PAST", "IS_FUTURE"}

_NORMALIZE_MODE_LABELS = {
    "UPPERCASE": "mayúsculas",
    "LOWERCASE": "minúsculas",
    "TRIM": "recortar espacios",
}

_LOGICAL_OPERATOR_JOINERS = {
    LogicalOperatorEnum.AND: " y ",
    LogicalOperatorEnum.OR: " o ",
}

# Placeholders especiales que puede traer `value` en condiciones de fecha (ver
# automation_engine.py::_evaluate_condition).
_PLACEHOLDER_VALUE_LABELS = {
    "{{CURRENT_DATE}}": "la fecha actual",
    "{{CURRENT_DATETIME}}": "la fecha y hora actual",
    "{{YESTERDAY}}": "ayer",
    "{{TOMORROW}}": "mañana",
}

# attr nativo (LeadField/NativeLeadField.attr) -> (modelo real, función que arma el label).
# Mismo mapeo conceptual que _NATIVE_ID_REPOSITORIES_BY_ATTR en field_automation_service.py,
# pero acá se resuelve directo contra el modelo (solo necesitamos el nombre, no el repositorio
# completo con sus hooks de tenant/seguridad -- el objeto ya pasó esos filtros al guardarse).
_NATIVE_ENTITY_LOOKUPS = {
    "contact_state_id": (LeadContactState, lambda o: o.name),
    "current_state_id": (LeadState, lambda o: o.name),
    "team_id": (Team, lambda o: o.name),
    "assigned_to_user_id": (User, lambda o: f"{o.name} {o.last_name}".strip()),
    "created_by": (User, lambda o: f"{o.name} {o.last_name}".strip()),
    "updated_by": (User, lambda o: f"{o.name} {o.last_name}".strip()),
}


def _field_info(session, field_id, cache: dict) -> dict:
    """Devuelve {"name", "kind": "native"|"custom"|"unknown", ...} para un field_id ya resuelto
    a id interno (o id nativo negativo, que nunca se resuelve -- es una constante fija)."""
    if field_id in cache["field"]:
        return cache["field"][field_id]

    if isinstance(field_id, int) and field_id in NATIVE_LEAD_FIELDS:
        native = NATIVE_LEAD_FIELDS[field_id]
        info = {"name": native.name, "kind": "native", "attr": native.attr}
    elif field_id is None:
        info = {"name": "el campo", "kind": "unknown"}
    else:
        row = session.query(LeadField.name, LeadField.field_type_code, LeadField.nomenclator_id) \
            .filter(LeadField.id == field_id).first()
        if row is None:
            # Campo borrado después de guardar la regla -- degradación amable, mismo criterio
            # que _unresolve_one_nomenclator_item_id (no romper el resumen por esto).
            info = {"name": "un campo eliminado", "kind": "unknown"}
        else:
            info = {"name": row[0], "kind": "custom", "type_code": row[1], "nomenclator_id": row[2]}

    cache["field"][field_id] = info
    return info


def _nomenclator_item_label(session, item_id, cache: dict) -> str:
    if item_id in cache["nomenclator_item"]:
        return cache["nomenclator_item"][item_id]
    row = session.query(NomenclatorItem.value).filter(NomenclatorItem.id == item_id).first()
    label = row[0] if row else "una opción eliminada"
    cache["nomenclator_item"][item_id] = label
    return label


def _native_entity_label(session, attr, entity_id, cache: dict) -> str:
    key = (attr, entity_id)
    if key in cache["native"]:
        return cache["native"][key]
    lookup = _NATIVE_ENTITY_LOOKUPS.get(attr)
    if lookup is None:
        return str(entity_id)
    model, get_label = lookup
    obj = session.query(model).filter(model.id == entity_id).first()
    label = get_label(obj) if obj is not None else "un valor eliminado"
    cache["native"][key] = label
    return label


def _single_value_label(session, field_info: dict, raw_value, cache: dict) -> str:
    if raw_value is None:
        return "(vacío)"
    if isinstance(raw_value, str) and raw_value in _PLACEHOLDER_VALUE_LABELS:
        return _PLACEHOLDER_VALUE_LABELS[raw_value]

    if field_info["kind"] == "native":
        attr = field_info.get("attr")
        if attr in _NATIVE_ENTITY_LOOKUPS and isinstance(raw_value, int):
            return f"'{_native_entity_label(session, attr, raw_value, cache)}'"
        return f"'{raw_value}'"

    if field_info["kind"] == "custom":
        type_code = field_info.get("type_code")
        if type_code in ("SELECTOR", "CHECKBOX") and field_info.get("nomenclator_id") and isinstance(raw_value, int):
            return f"'{_nomenclator_item_label(session, raw_value, cache)}'"
        if type_code == "BOOL":
            truthy = raw_value in (True, "true", "True", 1, "1")
            return "'Sí'" if truthy else "'No'"

    return f"'{raw_value}'"


def _value_label(session, field_info: dict, raw_value, cache: dict) -> str:
    if isinstance(raw_value, list):
        if not raw_value:
            return "(vacío)"
        return ", ".join(_single_value_label(session, field_info, v, cache) for v in raw_value)
    return _single_value_label(session, field_info, raw_value, cache)


# ==========================================
# CONDICIONES
# ==========================================
def _describe_condition(session, node, cache: dict) -> str:
    field_info = _field_info(session, node.field_id, cache)
    operator = node.operator.value if hasattr(node.operator, "value") else str(node.operator)
    template = CONDITION_OPERATOR_TEMPLATES.get(operator)
    if template is None:
        return f"{field_info['name']} cumple una condición"
    if operator in _OPERATORS_WITHOUT_VALUE:
        return template.format(field=field_info["name"])
    value_label = _value_label(session, field_info, node.value, cache)
    return template.format(field=field_info["name"], value=value_label)


def _describe_group(session, group, cache: dict) -> str:
    if group is None or not getattr(group, "rules", None):
        return ""
    parts = []
    for node in group.rules:
        if hasattr(node, "rules"):
            nested = _describe_group(session, node, cache)
            if nested:
                parts.append(f"({nested})")
        else:
            parts.append(_describe_condition(session, node, cache))
    joiner = _LOGICAL_OPERATOR_JOINERS.get(group.operator, " y ")
    return joiner.join(parts)


# ==========================================
# ACCIONES
# ==========================================
def _describe_action(session, action, cache: dict) -> str:
    target_info = _field_info(session, action.target_field_id, cache)
    target_name = target_info["name"]
    action_type = action.type.value if hasattr(action.type, "value") else str(action.type)

    if action_type == ActionTypeEnum.SET_VALUE.value:
        return f"establecer {target_name} en {_value_label(session, target_info, action.value, cache)}"
    if action_type == ActionTypeEnum.SET_VALUE_IF_EMPTY.value:
        return f"establecer {target_name} en {_value_label(session, target_info, action.value, cache)} si está vacío"
    if action_type == ActionTypeEnum.CLEAR_VALUE.value:
        return f"vaciar {target_name}"
    if action_type == ActionTypeEnum.COPY_FROM_FIELD.value:
        source_info = _field_info(session, action.source_field_id, cache) if action.source_field_id is not None else None
        source_name = source_info["name"] if source_info else "otro campo"
        return f"copiar {source_name} en {target_name}"
    if action_type == ActionTypeEnum.SET_CURRENT_DATE.value:
        return f"establecer {target_name} en la fecha actual"
    if action_type == ActionTypeEnum.SET_CURRENT_DATETIME.value:
        return f"establecer {target_name} en la fecha y hora actual"
    if action_type == ActionTypeEnum.INCREMENT.value:
        step = action.value if action.value is not None else 1
        return f"incrementar {target_name} en {step}"
    if action_type == ActionTypeEnum.DECREMENT.value:
        step = action.value if action.value is not None else 1
        return f"decrementar {target_name} en {step}"
    if action_type == ActionTypeEnum.APPEND_TO_LIST.value:
        return f"agregar {_value_label(session, target_info, action.value, cache)} a {target_name}"
    if action_type == ActionTypeEnum.REMOVE_FROM_LIST.value:
        return f"quitar {_value_label(session, target_info, action.value, cache)} de {target_name}"
    if action_type == ActionTypeEnum.SET_DATE_OFFSET.value:
        try:
            days = int(action.value) if action.value is not None else 0
        except (TypeError, ValueError):
            days = 0
        if days == 0:
            return f"establecer {target_name} en la fecha de hoy"
        plural = "s" if abs(days) != 1 else ""
        if days > 0:
            return f"establecer {target_name} en {days} día{plural} desde hoy"
        return f"establecer {target_name} en {abs(days)} día{plural} atrás"
    if action_type == ActionTypeEnum.NORMALIZE_TEXT.value:
        mode = str(action.value).upper() if action.value else "TRIM"
        mode_label = _NORMALIZE_MODE_LABELS.get(mode, mode.lower())
        return f"normalizar {target_name} a {mode_label}"
    if action_type == ActionTypeEnum.CONCAT_FIELDS.value:
        source_ids = action.source_field_ids or []
        names = [_field_info(session, sid, cache)["name"] for sid in source_ids]
        separator = action.value if action.value not in (None, "") else " "
        joined = " + ".join(names) if names else "los campos de origen"
        return f"establecer {target_name} concatenando {joined} (separados por '{separator}')"

    return f"modificar {target_name}"


def _describe_actions(session, actions, cache: dict) -> str:
    if not actions:
        return ""
    return " y ".join(_describe_action(session, action, cache) for action in actions)


# ==========================================
# PUNTO DE ENTRADA
# ==========================================
def build_field_automation_summary(session, obj) -> str | None:
    """Arma el resumen de una FieldAutomationDetailedResponse ya armada (conditions/actions en
    id interno, ANTES de _unresolve_field_automation_values). Devuelve None si el objeto no
    tiene conditions/actions (respuesta no detallada) -- mismo criterio que
    _unresolve_field_automation_values."""
    conditions = getattr(obj, "conditions", None)
    actions = getattr(obj, "actions", None)
    if conditions is None or actions is None:
        return None

    cache = {"field": {}, "nomenclator_item": {}, "native": {}}
    conditions_text = _describe_group(session, conditions, cache)
    actions_text = _describe_actions(session, actions, cache)

    if not actions_text:
        return f"Si {conditions_text}." if conditions_text else None
    if not conditions_text:
        return f"Siempre: {actions_text}."
    return f"Si {conditions_text}, entonces {actions_text}."
