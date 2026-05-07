import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, model_validator
from app.schemas.base_schema import BaseDetailedResponse, BaseCreate, BaseResponse


class ValidationRuleBase(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    expression: Optional[str] = Field(default=None, min_length=1)
    error_message: Optional[str] = Field(default=None, max_length=255)
    field_id: Optional[int] = Field(default=None, gt=0)
    template_code: Optional[str] = None
    template_params: Optional[Dict[str, Any]] = None

class ValidationRuleCreate(ValidationRuleBase, BaseCreate):
    @model_validator(mode='before')
    @classmethod
    def check_creation_method(cls, data: Any) -> Any:
        """
        Valida que envíe O BIEN la expresión, O BIEN el template.
        """
        if isinstance(data, dict):
            expr = data.get("expression")
            tmpl = data.get("template_code")
            
            # Validación: Debe existir al menos uno de los dos
            if not expr and not tmpl:
                raise ValueError("Debes proporcionar una 'expression' (Modo Experto) o un 'template_code' (Modo Asistente).")
            
            # Validación extra: Si manda template, idealmente debería mandar params (aunque sea dict vacío)
            if tmpl and "template_params" not in data:
                # Podemos ser permisivos y setearlo a vacío si no viene
                data["template_params"] = {}
            
                
        return data

class ValidationRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    expression: Optional[str] = Field(default=None, min_length=1)
    error_message: Optional[str] = Field(default=None, max_length=255)
    template_params: Optional[Dict[str, Any]] = None

class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    pass

class ValidationRuleDetailedResponse(ValidationRuleBase, BaseDetailedResponse):
    pass    
