from typing import Any, Dict, List
from pydantic import BaseModel


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

class ExcelFormulaReponse(BaseModel):
    name_spanish: str
    name_english: str
    description: str
    example: str
    category: str
    note: str = ""