from __future__ import annotations
from typing import List, Union, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from datetime import datetime

from app.schemas.base_schema import BaseDetailedResponse, BaseResponse

# ==========================================
# 1. DICCIONARIO DE OPERACIONES (ENUMS)
# ==========================================
class TriggerEventEnum(str, Enum):
    ON_CREATE = "ON_CREATE"
    ON_UPDATE = "ON_UPDATE"

class LogicalOperatorEnum(str, Enum):
    AND = "AND"
    OR = "OR"

class ConditionOperatorEnum(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    CONTAINS = "CONTAINS"
    NOT_CONTAINS = "NOT_CONTAINS"
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    IS_EMPTY = "IS_EMPTY"
    IS_NOT_EMPTY = "IS_NOT_EMPTY"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    IS_PAST = "IS_PAST"
    IS_FUTURE = "IS_FUTURE"

class ActionTypeEnum(str, Enum):
    SET_VALUE = "SET_VALUE"
    CLEAR_VALUE = "CLEAR_VALUE"
    COPY_FROM_FIELD = "COPY_FROM_FIELD"
    SET_CURRENT_DATE = "SET_CURRENT_DATE"
    SET_CURRENT_DATETIME = "SET_CURRENT_DATETIME"
    INCREMENT = "INCREMENT"
    DECREMENT = "DECREMENT"
    APPEND_TO_LIST = "APPEND_TO_LIST"
    REMOVE_FROM_LIST = "REMOVE_FROM_LIST"
    SET_DATE_OFFSET = "SET_DATE_OFFSET"
    SET_VALUE_IF_EMPTY = "SET_VALUE_IF_EMPTY"
    NORMALIZE_TEXT = "NORMALIZE_TEXT"
    CONCAT_FIELDS = "CONCAT_FIELDS"

# ==========================================
# 2. ESQUEMAS DEL ARBOL JSONB
# ==========================================
class RuleCondition(BaseModel):
    # Bug real encontrado 2026-07-30: field_id era `int` puro, pero desde Fase 3/4
    # LeadField.id que devuelve la API (y el que manda el front) es un public_uuid --
    # cualquier regla armada con field_ids reales rompía con 422 ("unable to parse
    # string as an integer"). Mismo criterio ya usado en LeadFieldValueCreate.field_id:
    # se acepta también el id interno como int-string (callers internos ya resueltos),
    # FieldAutomationService resuelve el uuid real al id interno antes de persistir.
    field_id: Union[int, str]
    operator: ConditionOperatorEnum
    value: Optional[Any] = None

class RuleGroup(BaseModel):
    operator: LogicalOperatorEnum
    rules: List[Union[RuleCondition, RuleGroup]]

RuleGroup.model_rebuild()

class AutomationAction(BaseModel):
    type: ActionTypeEnum
    # Mismo bug y mismo criterio que RuleCondition.field_id de arriba.
    target_field_id: Union[int, str]
    value: Optional[Any] = Field(default=None)
    source_field_id: Optional[Union[int, str]] = Field(default=None)
    source_field_ids: Optional[List[Union[int, str]]] = Field(default=None)

# ==========================================
# 3. ESQUEMAS CRUD
# ==========================================
class FieldAutomationBase(BaseModel):
    name: str = Field(..., max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    trigger_events: List[TriggerEventEnum] = Field(min_length=1)
    priority: Optional[int] = 1

class FieldAutomationCreate(FieldAutomationBase):
    # public_uuid de Campaign desde Fase 3 (el front ya no conoce el id interno). Se resuelve
    # en FieldAutomationService.create (validación puntual) y de nuevo, genéricamente, en
    # BaseRepository.create.
    campaign_id: str
    conditions: RuleGroup
    actions: List[AutomationAction] = Field(min_length=1)

class FieldAutomationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    trigger_events: Optional[List[TriggerEventEnum]] = None
    conditions: Optional[RuleGroup] = None
    actions: Optional[List[AutomationAction]] = None
    priority: Optional[int] = None

class FieldAutomationResponse(FieldAutomationBase, BaseResponse):
    campaign_id: int

class FieldAutomationDetailedResponse(BaseDetailedResponse, FieldAutomationResponse):
    conditions: RuleGroup
    actions: List[AutomationAction]
