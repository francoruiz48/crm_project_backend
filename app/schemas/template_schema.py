from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ValidationTemplateResponse(BaseModel):
    code: str
    name: str
    description: str
    required_params: List[str]
    error_message: str


class LeadFieldTemplateResponse(BaseModel):
    code: str
    name: str
    field_type_code: str
    rules: List[Dict[str, Any]]
    input_mask: Optional[str] = Field(
        default=None, description="Código de máscara predefinida (Ej: DNI_ARG, MOBILE_AR)"
    )

class ExcelFormulaReponse(BaseModel):
    name_spanish: str
    name_english: str
    description: str
    example: str
    category: str
    note: str = ""