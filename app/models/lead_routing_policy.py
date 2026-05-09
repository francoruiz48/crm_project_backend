"""
Modelos del sistema de enrutamiento v3 (simplificado).

Estructura:
  LeadRoutingPolicy     → contenedor (prioridad, equipo destino, operador AND/OR global)
  LeadRoutingCondition  → condición atómica (un campo + operador + valor)

Sin árbol, sin símbolos, sin condition_type.
El campo puede ser dinámico (lead_field_id) o nativo (native_field).
"""
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB


# ---------------------------------------------------------------------------
# Catálogos de constantes (usados también en schemas y service)
# ---------------------------------------------------------------------------

# Campos nativos del modelo Lead que se pueden usar como condición
NATIVE_FIELDS = {
    "assigned_to_user_id",
    "team_id",
    "created_at",
    "updated_at",
    "campaign_id",
    "current_state_id",
}

# Tipos de campo dinámico no permitidos en condiciones de enrutamiento
ROUTING_FORBIDDEN_FIELD_TYPES = {
    "FILE", "URL", "ADDRESS", "RICH_TEXT", "TAGS", "PASSWORD"
}

# Operadores válidos según tipo de campo
OPERATOR_RULES: dict[str, set[str]] = {
    "STRING":    {"eq", "neq", "like", "ilike"},
    "INT":       {"eq", "neq", "gt", "lt", "gte", "lte"},
    "NUMBER":    {"eq", "neq", "gt", "lt", "gte", "lte"},
    "DATE":      {"eq", "neq", "gt", "lt", "gte", "lte"},
    "DATE_TIME": {"eq", "neq", "gt", "lt", "gte", "lte"},
    "BOOL":      {"eq", "neq"},
    "SELECTOR":  {"eq", "eq_strict", "neq", "in", "not_in"},
    "CALCULATED":{"eq", "neq", "gt", "lt", "gte", "lte", "like", "ilike"},
    # Nativos
    "_NATIVE_DATE": {"eq", "neq", "gt", "lt", "gte", "lte"},
    "_NATIVE_ID":   {"eq", "neq"},
}

VALID_OPERATORS     = {"eq", "eq_strict", "neq", "gt", "lt", "gte", "lte",
                       "like", "ilike", "in", "not_in"}
VALID_RANGE_OPS_MIN = {"gt", "gte"}
VALID_RANGE_OPS_MAX = {"lt", "lte"}
VALID_LOGICAL_OPS   = {"AND", "OR"}

# Operadores que requieren value_list en lugar de value_str
LIST_OPERATORS = {"in", "not_in", "eq_strict"}


class LeadRoutingPolicy(BaseModelDB):
    """
    Política de enrutamiento.
    Agrupa N condiciones unidas por un operador lógico global (AND / OR).
    Si la política evalúa True → se asigna target_team_id al lead.
    Prioridad: menor número = mayor prioridad (1 gana sobre 2).
    campaign_id NULL = política global de la organización.
    """
    __tablename__ = "lead_routing_policy"

    organization_id  = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)
    campaign_id      = Column(Integer, ForeignKey("campaign.id",     ondelete="CASCADE"), nullable=True)
    name             = Column(String,  nullable=False)
    description      = Column(String,  nullable=True)
    priority         = Column(Integer, nullable=False)
    logical_operator = Column(String,  nullable=False, default="AND")  # AND | OR
    target_team_id   = Column(Integer, ForeignKey("team.id", ondelete="CASCADE"), nullable=False)

    conditions   = relationship(
        "LeadRoutingCondition",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="LeadRoutingCondition.position",
    )
    target_team  = relationship("Team",         foreign_keys=[target_team_id])
    campaign     = relationship("Campaign",     foreign_keys=[campaign_id])
    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "campaign_id", "priority",
            name="uix_routing_policy_priority_per_scope",
        ),
    )


class LeadRoutingCondition(BaseModelDB):
    """
    Condición atómica dentro de una política.

    Modos (mutuamente excluyentes):
      A) Valor simple:  operator + value_str
      B) Lista:         operator (in/not_in/eq_strict) + value_list
      C) Rango:         operator_min + value_min + operator_max + value_max

    Campo (mutuamente excluyentes):
      - lead_field_id  →  campo dinámico de la campaña
      - native_field   →  atributo nativo del Lead (assigned_to_user_id, etc.)
    """
    __tablename__ = "lead_routing_condition"

    policy_id    = Column(Integer, ForeignKey("lead_routing_policy.id", ondelete="CASCADE"), nullable=False)
    position     = Column(Integer, nullable=False, default=0)

    # Campo
    lead_field_id = Column(Integer, ForeignKey("lead_field.id", ondelete="CASCADE"), nullable=True)
    native_field  = Column(String,  nullable=True)

    # Modo A / B
    operator   = Column(String,        nullable=True)
    value_str  = Column(String,        nullable=True)
    value_list = Column(ARRAY(String), nullable=True)

    # Modo C (rango)
    operator_min = Column(String, nullable=True)
    value_min    = Column(String, nullable=True)
    operator_max = Column(String, nullable=True)
    value_max    = Column(String, nullable=True)

    # Relaciones
    policy     = relationship("LeadRoutingPolicy", back_populates="conditions")
    lead_field = relationship("LeadField",         foreign_keys=[lead_field_id])