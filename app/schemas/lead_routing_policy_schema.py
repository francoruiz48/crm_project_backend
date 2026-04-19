"""
Schemas para el sistema de enrutamiento v3.
"""
from __future__ import annotations
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

from app.models.lead_routing_policy import (
    VALID_OPERATORS, VALID_RANGE_OPS_MIN, VALID_RANGE_OPS_MAX,
    VALID_LOGICAL_OPS, LIST_OPERATORS, NATIVE_FIELDS,
)
from app.schemas.base_schema import BaseResponse, BaseDetailResponse, BaseCreate


# ===========================================================================
# CONDICIÓN
# ===========================================================================

class LeadRoutingConditionCreate(BaseModel):
    """
    Una condición atómica dentro de la política.
    Exactamente uno de lead_field_id / native_field debe venir.
    Exactamente un modo (simple, lista o rango) debe estar presente.
    """
    position: int = Field(default=0, ge=0)

    # Campo
    lead_field_id: Optional[int] = Field(default=None, gt=0)
    native_field:  Optional[str] = Field(default=None)

    # Modo simple
    operator:  Optional[str] = None
    value_str: Optional[str] = None

    # Modo lista
    value_list: Optional[List[str]] = None

    # Modo rango
    operator_min: Optional[str] = None
    value_min:    Optional[str] = None
    operator_max: Optional[str] = None
    value_max:    Optional[str] = None

    @model_validator(mode="after")
    def validate_condition(self) -> "LeadRoutingConditionCreate":
        # 1. Exactamente un campo
        has_field  = self.lead_field_id is not None
        has_native = self.native_field  is not None
        if has_field == has_native:  # ambos True o ambos False
            raise ValueError(
                "Debe especificar exactamente uno: 'lead_field_id' o 'native_field', no ambos ni ninguno."
            )

        if has_native and self.native_field not in NATIVE_FIELDS:
            raise ValueError(
                f"native_field '{self.native_field}' no es válido. "
                f"Valores permitidos: {sorted(NATIVE_FIELDS)}"
            )

        # 2. Detectar modo
        has_simple = self.operator is not None
        has_list   = self.value_list is not None
        has_range  = any([self.operator_min, self.value_min,
                          self.operator_max, self.value_max])

        active_modes = sum([has_simple, has_range])
        if active_modes == 0:
            raise ValueError(
                "Debe especificar un modo: valor simple (operator + value_str), "
                "lista (operator in/not_in/eq_strict + value_list) o "
                "rango (operator_min/max + value_min/max)."
            )
        if has_simple and has_range:
            raise ValueError("No puede combinar modo valor simple y modo rango en la misma condición.")

        # 3. Validar modo simple / lista
        if has_simple and not has_range:
            if self.operator not in VALID_OPERATORS:
                raise ValueError(f"operator '{self.operator}' no es válido. Opciones: {sorted(VALID_OPERATORS)}")

            if self.operator in LIST_OPERATORS:
                # Requiere value_list
                if not self.value_list:
                    raise ValueError(
                        f"El operador '{self.operator}' requiere 'value_list' (lista de valores)."
                    )
            else:
                # Requiere value_str
                if self.value_str is None:
                    raise ValueError(
                        f"El operador '{self.operator}' requiere 'value_str'."
                    )

        # 4. Validar modo rango
        if has_range:
            if self.operator_min not in VALID_RANGE_OPS_MIN:
                raise ValueError(f"operator_min debe ser uno de {VALID_RANGE_OPS_MIN}.")
            if self.operator_max not in VALID_RANGE_OPS_MAX:
                raise ValueError(f"operator_max debe ser uno de {VALID_RANGE_OPS_MAX}.")
            if self.value_min is None:
                raise ValueError("value_min es requerido en modo rango.")
            if self.value_max is None:
                raise ValueError("value_max es requerido en modo rango.")
            # Nativos de fecha sí soportan rango; IDs no
            if has_native and self.native_field in {
                "assigned_to_user_id", "team_id", "campaign_id", "current_state_id"
            }:
                raise ValueError(
                    f"El campo nativo '{self.native_field}' solo soporta eq / neq, no rangos."
                )

        return self


class LeadRoutingConditionResponse(BaseModel):
    id:           int
    policy_id:    int
    position:     int
    lead_field_id:Optional[int]
    native_field: Optional[str]
    operator:     Optional[str]
    value_str:    Optional[str]
    value_list:   Optional[List[str]]
    operator_min: Optional[str]
    value_min:    Optional[str]
    operator_max: Optional[str]
    value_max:    Optional[str]

    model_config = {"from_attributes": True}


# ===========================================================================
# POLÍTICA
# ===========================================================================

class LeadRoutingPolicyBase(BaseModel):
    name:             str  = Field(..., min_length=3, max_length=150)
    description:      Optional[str] = Field(default=None, max_length=500)
    priority:         int  = Field(..., gt=0)
    logical_operator: Literal["AND", "OR"] = "AND"
    target_team_id:   int  = Field(..., gt=0)
    campaign_id:      Optional[int] = Field(default=None, gt=0)


class LeadRoutingPolicyCreate(LeadRoutingPolicyBase, BaseCreate):
    """
    Crea la política junto con todas sus condiciones en una sola transacción.
    Si conditions está vacío, la política existe pero nunca matcheará
    (se necesita al menos una condición para asignar equipo).
    """
    conditions: List[LeadRoutingConditionCreate] = Field(default_factory=list)


class LeadRoutingPolicyUpdate(BaseModel):
    """
    Actualización completa. Si se envía 'conditions', reemplaza todas las anteriores.
    Si no se envía, las condiciones quedan intactas.
    """
    name:             Optional[str]                          = Field(default=None, min_length=3, max_length=150)
    description:      Optional[str]                          = Field(default=None, max_length=500)
    priority:         Optional[int]                          = Field(default=None, gt=0)
    logical_operator: Optional[Literal["AND", "OR"]]        = None
    target_team_id:   Optional[int]                          = Field(default=None, gt=0)
    conditions:       Optional[List[LeadRoutingConditionCreate]] = None


class LeadRoutingPolicyResponse(LeadRoutingPolicyBase, BaseResponse):
    organization_id: int


class LeadRoutingPolicyDetailedResponse(LeadRoutingPolicyBase, BaseDetailResponse):
    organization_id: int
    conditions: List[LeadRoutingConditionResponse] = []


# ===========================================================================
# VALIDATE (sin persistir)
# ===========================================================================

class LeadRoutingPolicyValidateRequest(BaseModel):
    campaign_id:      Optional[int] = Field(default=None, gt=0)
    target_team_id:   int           = Field(..., gt=0)
    logical_operator: Literal["AND", "OR"] = "AND"
    conditions:       List[LeadRoutingConditionCreate] = Field(default_factory=list)


class LeadRoutingPolicyValidateResponse(BaseModel):
    valid:  bool
    errors: List[str] = []