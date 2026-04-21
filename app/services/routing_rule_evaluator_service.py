"""
RoutingRuleEvaluatorService v3
==============================
Motor de evaluación de políticas de enrutamiento simplificado.
Sin árbol recursivo. Evalúa una lista plana de condiciones unidas por AND/OR.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.core.constans import DATE_FORMAT, DATE_TIME_FORMAT
from app.models.lead_routing_policy import (
    LeadRoutingCondition,
    LeadRoutingPolicy,
    LIST_OPERATORS,
    NATIVE_FIELDS,
    OPERATOR_RULES,
    ROUTING_FORBIDDEN_FIELD_TYPES,
    VALID_RANGE_OPS_MIN,
    VALID_RANGE_OPS_MAX,
)


# ---------------------------------------------------------------------------
# Helpers de casteo
# ---------------------------------------------------------------------------

def _cast(raw: str, field_type_code: str) -> Any:
    """Convierte un string a su tipo Python según el tipo de campo."""
    if raw is None:
        return None
    try:
        if field_type_code in ("INT", "RATING"):
            return int(raw)
        if field_type_code in ("NUMBER", "MONEY"):
            return float(raw)
        if field_type_code == "BOOL":
            return str(raw).lower() in ("true", "1", "yes", "si")
        if field_type_code == "DATE":
            return datetime.strptime(str(raw)[:10], DATE_FORMAT).date()
        if field_type_code == "DATE_TIME":
            return datetime.strptime(str(raw), DATE_TIME_FORMAT)
        return str(raw)
    except (ValueError, TypeError):
        return str(raw)


def _apply_op(lead_val: Any, op: str, rule_val: Any) -> bool:
    """Aplica un operador de comparación entre dos valores ya tipados."""
    try:
        if op == "eq":    return lead_val == rule_val
        if op == "neq":   return lead_val != rule_val
        if op == "gt":    return lead_val >  rule_val
        if op == "lt":    return lead_val <  rule_val
        if op == "gte":   return lead_val >= rule_val
        if op == "lte":   return lead_val <= rule_val
        if op == "like":  return str(rule_val).lower() in str(lead_val).lower()
        if op == "ilike": return str(rule_val).lower() in str(lead_val).lower()
    except TypeError:
        return False
    return False


def _native_type(native_field: str) -> str:
    """Retorna la categoría de tipo para campos nativos."""
    if native_field in ("created_at", "updated_at"):
        return "_NATIVE_DATE"
    return "_NATIVE_ID"


# ---------------------------------------------------------------------------
# Evaluación de una condición atómica
# ---------------------------------------------------------------------------

def _evaluate_condition(
    cond: LeadRoutingCondition,
    context_data: dict,      # {field_id: valor}  ∪  {"__native__assigned_to_user_id": valor, ...}
    field_type_map: dict,    # {field_id: field_type_code}
    nom_to_fields: dict,     # {nomenclator_id: [field_id, ...]}  (para SELECTOR)
) -> bool:
    """Evalúa una condición y retorna True/False."""

    # ── Obtener valor del lead ────────────────────────────────────────────────
    if cond.native_field:
        key      = f"__native__{cond.native_field}"
        lead_raw = context_data.get(key)
        type_code= _native_type(cond.native_field)
    else:
        lead_raw  = context_data.get(cond.lead_field_id)
        type_code = field_type_map.get(cond.lead_field_id, "STRING")

    if lead_raw is None:
        return False

    op = cond.operator

    # ── Modo rango ────────────────────────────────────────────────────────────
    if cond.operator_min or cond.operator_max:
        lead_val = _cast(str(lead_raw) if not isinstance(lead_raw, list) else "", type_code)
        result   = True
        if cond.operator_min and cond.value_min is not None:
            result = result and _apply_op(lead_val, cond.operator_min, _cast(cond.value_min, type_code))
        if cond.operator_max and cond.value_max is not None:
            result = result and _apply_op(lead_val, cond.operator_max, _cast(cond.value_max, type_code))
        return result

    # ── Modo lista (in / not_in / eq_strict) ──────────────────────────────────
    if op in LIST_OPERATORS:
        rule_vals = cond.value_list or []

        # Para SELECTOR/CHECKBOX: lead_raw puede ser lista de IDs
        if type_code in ("SELECTOR", "CHECKBOX"):
            if isinstance(lead_raw, list):
                lead_ids = [str(x) for x in lead_raw]
            else:
                lead_ids = [str(lead_raw)]

            rule_ids = [str(v) for v in rule_vals]

            if op == "in":
                # Al menos uno de rule_ids está en lead_ids
                return any(r in lead_ids for r in rule_ids)
            if op == "not_in":
                # Ninguno de rule_ids está en lead_ids
                return not any(r in lead_ids for r in rule_ids)
            if op == "eq_strict":
                # lead_ids es exactamente el mismo conjunto que rule_ids
                return set(lead_ids) == set(rule_ids)

        else:
            # Para campos de texto: comparación string
            lead_str = str(lead_raw)
            if op == "in":
                return lead_str in rule_vals
            if op == "not_in":
                return lead_str not in rule_vals
            if op == "eq_strict":
                return lead_str in rule_vals and len(rule_vals) == 1

        return False

    # ── Modo valor simple ─────────────────────────────────────────────────────
    if op in ("like", "ilike"):
        return _apply_op(str(lead_raw), op, cond.value_str)

    lead_val = _cast(str(lead_raw) if not isinstance(lead_raw, list) else str(lead_raw[0] if lead_raw else ""), type_code)
    rule_val = _cast(cond.value_str, type_code)
    return _apply_op(lead_val, op, rule_val)


# ---------------------------------------------------------------------------
# Evaluación de una política completa
# ---------------------------------------------------------------------------

def _evaluate_policy(
    policy: LeadRoutingPolicy,
    context_data: dict,
    field_type_map: dict,
    nom_to_fields: dict,
) -> bool:
    conditions = sorted(policy.conditions, key=lambda c: c.position)
    if not conditions:
        return False   # Sin condiciones → nunca matchea

    op = (policy.logical_operator or "AND").upper()

    results = []
    for cond in conditions:
        try:
            results.append(_evaluate_condition(cond, context_data, field_type_map, nom_to_fields))
        except Exception:
            results.append(False)

    if op == "AND":
        return all(results)
    return any(results)  # OR


# ---------------------------------------------------------------------------
# Validación de condiciones (sin persistir)
# ---------------------------------------------------------------------------

def _validate_condition_data(
    cond_data: dict,
    session,
    organization_id: int,
    campaign_id: Optional[int],
    errors: list,
    idx: int,
):
    """Valida una condición a nivel de base de datos."""
    from app.models.lead_field import LeadField
    from app.models.nomenclator import Nomenclator
    from app.models.nomenclator_item import NomenclatorItem

    prefix = f"conditions[{idx}]"

    lead_field_id = cond_data.get("lead_field_id")
    native_field  = cond_data.get("native_field")
    op            = cond_data.get("operator")
    op_min        = cond_data.get("operator_min")
    value_list    = cond_data.get("value_list") or []

    if lead_field_id:
        field = session.query(LeadField).filter_by(id=lead_field_id).first()
        if not field:
            errors.append(f"{prefix}: El campo ID={lead_field_id} no existe.")
            return
        if field.organization_id != organization_id:
            errors.append(f"{prefix}: El campo ID={lead_field_id} no pertenece a esta organización.")
            return
        if field.field_type_code in ROUTING_FORBIDDEN_FIELD_TYPES:
            errors.append(
                f"{prefix}: El tipo de campo '{field.field_type_code}' no está permitido "
                f"en condiciones de enrutamiento."
            )
            return
        if campaign_id and field.campaign_id and field.campaign_id != campaign_id:
            errors.append(
                f"{prefix}: El campo ID={lead_field_id} pertenece a la campaña "
                f"{field.campaign_id}, no a la campaña {campaign_id}."
            )

        # Validar operador compatible con el tipo de campo
        allowed_ops = OPERATOR_RULES.get(field.field_type_code, set())
        effective_op = op or op_min
        if effective_op and effective_op not in allowed_ops and effective_op not in {"gt", "gte", "lt", "lte"}:
            errors.append(
                f"{prefix}: El operador '{effective_op}' no es compatible con "
                f"el tipo de campo '{field.field_type_code}'. "
                f"Operadores válidos: {sorted(allowed_ops)}"
            )

        # Para SELECTOR: validar que value_list/value_str sean IDs de ítems del nomenclador
        if field.field_type_code in ("SELECTOR", "CHECKBOX") and field.nomenclator_id:
            ids_to_check = value_list or (
                [cond_data.get("value_str")] if cond_data.get("value_str") else []
            )
            for raw_id in ids_to_check:
                try:
                    item_id = int(raw_id)
                    item = session.query(NomenclatorItem).filter_by(
                        id=item_id, nomenclator_id=field.nomenclator_id
                    ).first()
                    if not item:
                        errors.append(
                            f"{prefix}: El ítem ID={raw_id} no pertenece al "
                            f"nomenclador del campo '{field.name}'."
                        )
                except (ValueError, TypeError):
                    errors.append(f"{prefix}: Los valores para campos SELECTOR deben ser IDs enteros.")


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

class RoutingRuleEvaluatorService:

    @staticmethod
    def evaluate(
        session,
        campaign_id: int,
        organization_id: int,
        context_data: dict,
        field_defs_list: list,
        lead_obj=None,        # Objeto Lead SQLAlchemy (para campos nativos)
    ) -> Optional[int]:
        """
        Evalúa todas las políticas activas en orden de prioridad.
        Retorna target_team_id de la primera política que matchee, o None.

        context_data: {field_id: valor_raw}
        Para campos nativos se inyectan claves "__native__<campo>".
        """
        from sqlalchemy import or_

        # 1. Índices auxiliares
        field_type_map: dict[int, str]      = {}
        nom_to_fields:  dict[int, list[int]] = {}

        for f in field_defs_list:
            field_type_map[f.id] = f.field_type_code
            if getattr(f, "nomenclator_id", None):
                nom_to_fields.setdefault(f.nomenclator_id, []).append(f.id)

        # 2. Inyectar campos nativos al contexto
        enriched = dict(context_data)
        if lead_obj:
            for nf in NATIVE_FIELDS:
                val = getattr(lead_obj, nf, None)
                if val is not None:
                    enriched[f"__native__{nf}"] = val

        # 3. Cargar políticas activas
        policies = (
            session.query(LeadRoutingPolicy)
            .filter(
                LeadRoutingPolicy.organization_id == organization_id,
                LeadRoutingPolicy.active.is_(True),
                or_(
                    LeadRoutingPolicy.campaign_id.is_(None),
                    LeadRoutingPolicy.campaign_id == campaign_id,
                ),
            )
            .order_by(LeadRoutingPolicy.priority.asc())
            .all()
        )

        if not policies:
            return None

        # 4. Evaluar en orden de prioridad
        for policy in policies:
            if _evaluate_policy(policy, enriched, field_type_map, nom_to_fields):
                return policy.target_team_id

        return None

    @staticmethod
    def validate_conditions(
        session,
        conditions_data: list[dict],
        organization_id: int,
        campaign_id: Optional[int],
        target_team_id: int,
    ) -> list[str]:
        """
        Valida una lista de condiciones sin guardarlas.
        Retorna lista de errores (vacía = válido).
        """
        from app.models.team import Team

        errors: list[str] = []

        # Validar equipo
        team = session.query(Team).filter_by(id=target_team_id).first()
        if not team:
            errors.append(f"El equipo destino ID={target_team_id} no existe.")
        elif team.organization_id != organization_id:
            errors.append("El equipo destino no pertenece a esta organización.")

        for idx, cond in enumerate(conditions_data):
            _validate_condition_data(cond, session, organization_id, campaign_id, errors, idx)

        return errors