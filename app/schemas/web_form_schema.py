from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseResponse, BaseDetailedResponse
from app.schemas.web_form_field_schema import WebFormFieldCreate, WebFormFieldResponse

class ThemeConfig(BaseModel):
    primary_color: str = Field(default="#3B82F6", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    background_color: str = Field(default="#FFFFFF", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    text_color: str = Field(default="#1F2937", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    button_text_color: str = Field(default="#FFFFFF", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    border_radius: str = Field(default="6px", max_length=20)
    font_family: str = Field(default="Inter, sans-serif", max_length=100)

# --- MODELOS BASE ---
class WebFormBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    
    theme_config: Optional[ThemeConfig] = None
    success_message: Optional[str] = Field(default="¡Gracias por registrarte! Nos contactaremos pronto.")
    
    # 🛡️ BLINDAJE DE URL: Solo permitimos URLs absolutas seguras
    redirect_url: Optional[str] = Field(default=None, max_length=500, pattern=r"^(https?)://[^\s/$.?#].[^\s]*$")
    
    # Lista de dominios desde donde se puede embeber el iframe
    allowed_domains: Optional[List[str]] = Field(default_factory=list)
    require_captcha: bool = False
    active: bool = True

class WebFormCreate(WebFormBase, BaseCreate):
    campaign_id: int = Field(gt=0)
    # Permite crear el formulario y sus campos en una sola petición
    fields: Optional[List[WebFormFieldCreate]] = Field(default_factory=list)

class WebFormUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=150)
    title: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    theme_config: Optional[ThemeConfig] = None
    success_message: Optional[str] = None
    redirect_url: Optional[str] = Field(default=None, max_length=500, pattern=r"^(https?)://[^\s/$.?#].[^\s]*$")
    allowed_domains: Optional[List[str]] = None
    require_captcha: Optional[bool] = None
    active: Optional[bool] = None
    
    # Fíjate que excluí intencionalmente `campaign_id` aquí. 
    # Un formulario web NUNCA debería cambiar de campaña una vez creado, 
    # porque los `lead_field_id` de sus campos quedarían apuntando a la nada.
    
    # Para los campos, lo mejor es reemplazarlos por completo
    fields: Optional[List[WebFormFieldCreate]] = None

# --- RESPUESTAS ---
class WebFormResponse(WebFormBase, BaseResponse):
    organization_id: int
    campaign_id: int
    public_uuid: str

class WebFormDetailedResponse(WebFormResponse, BaseDetailedResponse):
    fields: List[WebFormFieldResponse] = Field(default_factory=list)

# --- RESPUESTA PÚBLICA (Para el endpoint expuesto) ---
# Este esquema recorta la información sensible. El Iframe público NO NECESITA saber 
# de qué organización o campaña es el formulario, solo necesita pintarlo.
class WebFormPublicResponse(BaseModel):
    public_uuid: str
    title: Optional[str] = None
    description: Optional[str] = None
    theme_config: Optional[ThemeConfig] = None
    success_message: Optional[str] = None
    redirect_url: Optional[str] = None
    require_captcha: bool
    fields: List[WebFormFieldResponse] = Field(default_factory=list)