from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.base_schema import BaseCreate, BaseResponse, BaseDetailedResponse
from app.schemas.web_form_field_schema import WebFormFieldCreate, WebFormFieldResponse

# Elemento del formulario público al que se le aplica una regla de CSS (ver TARGET_CLASS_MAP /
# CUSTOM_CSS_TARGET_OPTIONS en el frontend, webFormCssTargets.ts). Reemplaza el cuadro único de
# CSS libre (agregado 2026-08-18, revertido el mismo día por pedido del usuario: "no me cierra" un
# solo cuadro de texto) por reglas separadas por elemento, para que el usuario no tenga que escribir
# selectores CSS él mismo. `ADVANCED` es la única excepción: no se envuelve en ningún selector, se
# inyecta tal cual (para quien ya sabe CSS y quiere algo que las clases fijas no cubren, ej. :hover).
class CustomCssTarget(str, Enum):
    # CONTAINER y TEXT apuntan al mismo elemento del DOM público (el contenedor raíz) -- se
    # separan en dos opciones distintas (2026-08-18, pedido del usuario) solo para que el usuario
    # no tenga que pensar en "es lo mismo": una es para el fondo (background, gradientes, tamaño de
    # fondo) y la otra para el texto general (color, tipografía) de título/descripción/mensajes.
    # Los campos y el botón tienen sus propios targets y no se ven afectados por TEXT.
    CONTAINER = "container"
    TEXT = "text"
    IMAGE = "image"
    TITLE = "title"
    DESCRIPTION = "description"
    FIELD = "field"
    SUBMIT_BUTTON = "submit_button"
    REQUIRED_LEGEND = "required_legend"
    SUCCESS_MESSAGE = "success_message"
    ADVANCED = "advanced"

class CustomCssRule(BaseModel):
    target: CustomCssTarget
    css: str = Field(..., max_length=5000)

class ThemeConfig(BaseModel):
    primary_color: str = Field(default="#3B82F6", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    background_color: str = Field(default="#FFFFFF", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    text_color: str = Field(default="#1F2937", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    button_text_color: str = Field(default="#FFFFFF", pattern=r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
    border_radius: str = Field(default="6px", max_length=20)
    font_family: str = Field(default="Inter, sans-serif", max_length=100)
    # URL pública de una imagen (logo u otra) para mostrar arriba del título -- se sube mediante el
    # endpoint genérico /storage/upload (StorageService, ya usado para fotos de lead) y acá solo se
    # guarda la URL resultante. Vive en theme_config (columna JSON, sin migración) en vez de un
    # campo nuevo en WebForm -- decisión pragmática 2026-08-18, ver conversación con el usuario.
    image_url: Optional[str] = Field(default=None, max_length=1000)
    # Reglas de CSS por elemento (ver CustomCssTarget). Se aplican tal cual dentro de un <style> en
    # la página pública real (PublicWebFormPage.tsx) -- no hay sanitización porque quien lo escribe
    # es el dueño del formulario, configurando su propia página pública (mismo nivel de confianza
    # que redirect_url/allowed_domains). No se reflejan en la vista previa del editor por seguridad:
    # esa vista comparte DOM con el resto del CRM, e inyectar CSS arbitrario ahí podría romper la
    # UI del editor (ver WebFormThemeTab.tsx) -- esto sigue aplicando aunque ahora esté "por clase",
    # porque la opción ADVANCED sigue permitiendo CSS sin ningún tipo de scoping.
    custom_css_rules: Optional[List[CustomCssRule]] = Field(default_factory=list)

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
    # Override: público_uuid de Campaign (Fase 3, nunca migrado en este módulo hasta ahora --
    # ver backend/AGENTS.md §18-undecies). Se resuelve a id interno en WebFormService.create.
    campaign_id: str
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