import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, model_validator
from app.schemas.base_schema import BaseDetailResponse, BaseCreate, BaseResponse


class ValidationRuleBase(BaseModel):
    name: Optional[str] = None
    expression: Optional[str] = None
    error_message: Optional[str] = None
    field_id : Optional[int] = None

    template_code: Optional[str] = None
    template_params: Optional[Dict[str, Any]] = None


class ValidationTemplateResponse(BaseModel):
    code: str
    name: str
    description: str
    required_params: List[str]
    error_message: str

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


class ValidationRuleResponse(ValidationRuleBase, BaseResponse):
    pass

class ValidationRuleDetailedResponse(ValidationRuleBase, BaseDetailResponse):
    pass    
