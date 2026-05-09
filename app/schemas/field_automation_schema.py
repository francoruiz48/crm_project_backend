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

class ActionTypeEnum(str, Enum):
    SET_VALUE = "SET_VALUE"
    CLEAR_VALUE = "CLEAR_VALUE"
    COPY_FROM_FIELD = "COPY_FROM_FIELD"
    SET_CURRENT_DATE = "SET_CURRENT_DATE"
    SET_CURRENT_DATETIME = "SET_CURRENT_DATETIME"

# ==========================================
# 2. ESQUEMAS DEL ÁRBOL JSONB
# ==========================================
class RuleCondition(BaseModel):
    """Una condición hoja (Ej: 'Provincia == Mendoza')"""
    field_id: int
    operator: ConditionOperatorEnum
    value: Optional[Any] = None 

class RuleGroup(BaseModel):
    """Un agrupador lógico. Contiene reglas simples o más grupos (recursividad)"""
    operator: LogicalOperatorEnum
    rules: List[Union[RuleCondition, RuleGroup]]

# Le decimos a Pydantic que reconstruya la clase para aceptar la recursividad
RuleGroup.model_rebuild() 

class AutomationAction(BaseModel):
    """El paso a paso de lo que hace el motor si la condición se cumple"""
    type: ActionTypeEnum
    target_field_id: int
    value: Optional[Any] = Field(default=None, description="Valor estático a inyectar")
    source_field_id: Optional[int] = Field(default=None, description="ID del campo de origen si la acción es copiar")

# ==========================================
# 3. ESQUEMAS CRUD (ENTRADA Y SALIDA)
# ==========================================
class FieldAutomationBase(BaseModel):
    name: str = Field(..., max_length=150)
    description: Optional[str] = Field(default=None, max_length=500)
    trigger_events: List[TriggerEventEnum] = Field(min_length=1)
    priority: Optional[int] = 1

class FieldAutomationCreate(FieldAutomationBase):
    campaign_id: int
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