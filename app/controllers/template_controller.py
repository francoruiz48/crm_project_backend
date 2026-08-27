from fastapi import APIRouter
from app.schemas.template_schema import LeadFieldTemplateResponse
from app.core.templates.field_templates import STANDARD_FIELD_TEMPLATES
from app.schemas.template_schema import ValidationTemplateResponse
from app.core.templates.rule_templates import STANDARD_RULES
from app.core.templates.excel_formulas import EXCEL_FORMULAS
from app.schemas.template_schema import ExcelFormulaReponse
from app.core.templates.field_rules_map import STANDARD_INPUT_MASKS

class TemplateController:
    router_prefix = "/templates"

    @classmethod
    def get_router(cls):
        router = APIRouter(prefix=cls.router_prefix)

        @router.get("/lead_fields", response_model=list[LeadFieldTemplateResponse])
        def get_lead_fields_templates():
            templates = []
            for key, t in STANDARD_FIELD_TEMPLATES.items():
                templates.append({
                    "code": key,
                    "name": t.name,
                    "field_type_code": t.field_type_code,
                    "rules": t.rules,
                    "input_mask": t.input_mask
                })
            return templates
        
        @router.get("/lead_fields/input_masks")
        def get_available_input_masks():
            """Retorna las plantillas de máscaras para usar en el frontend"""
            return [
                {"code": code, "name": data["name"], "mask": data["mask"]} 
                for code, data in STANDARD_INPUT_MASKS.items()
            ]

        @router.get("/validation_rules", response_model=list[ValidationTemplateResponse])
        def get_validation_templates():
            """Devuelve la lista de reglas predefinidas disponibles."""
            templates = []
            for key, t in STANDARD_RULES.items():
                templates.append({
                    "code": t.code,
                    "name": t.name,
                    "description": t.description,
                    "required_params": t.params,
                    "error_message": t.error_message
                })
            return templates
    
        @router.get("/excel_formulas", response_model=list[ExcelFormulaReponse])
        def get_excel_formulas():
            """Devuelve la lista de formulas de excel disponibles."""
            templates = []
            for key, t in EXCEL_FORMULAS.items():
                templates.append({
                    "name_spanish": t.name_spanish,
                    "name_english": t.name_english,
                    "description": t.description,
                    "syntax": t.syntax,
                    "example": t.example,
                    "category": t.category,
                    "note": t.note
                })
            return templates
        return router
    
router = TemplateController.get_router()