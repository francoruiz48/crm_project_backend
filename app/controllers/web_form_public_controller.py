from fastapi import APIRouter, Request, HTTPException, status
from typing import Dict, Any
import httpx
from slowapi import Limiter
from app.core.config import settings
from app.core.context import TENANT_ORG_ID
from app.core.security import get_client_ip
from app.services.web_form_service import WebFormService
from app.services.lead_service import LeadService
from app.schemas.web_form_schema import WebFormPublicResponse
from app.schemas.lead_schema import LeadCreate
from app.schemas.lead_field_value_schema import LeadFieldValueCreate

router = APIRouter(prefix="/public/forms", tags=["Public Web Forms"])

# Instanciamos el mismo limitador para usarlo en el decorador
# Hallazgo #11: key_func usa get_client_ip (X-Forwarded-For/X-Real-IP con
# fallback a request.client.host) en vez de get_remote_address de slowapi
# (que solo lee request.client.host) — necesario si hay un proxy delante,
# ver app/core/security.py para el detalle.
limiter = Limiter(key_func=get_client_ip)

# Nombre del campo falso (Honeypot). El frontend debe incluirlo en el HTML pero oculto con CSS.
HONEYPOT_FIELD_NAME = "website_url_ext" 

@router.get("/{uuid}", response_model=WebFormPublicResponse)
def get_public_form(uuid: str):
    form = WebFormService.get_public_form_by_uuid(uuid)
    return form


@router.post("/{uuid}/submit")
@limiter.limit("5/minute") # BARRERA 1: Rate Limiting (Máx 5 envíos por IP cada minuto)
async def submit_public_form(uuid: str, request: Request, payload: Dict[str, Any]):
    
    # BARRERA 2: Honeypot (Caza-bobos)
    # Extraemos el campo falso. Si el bot lo llenó, fingimos éxito y cortamos la ejecución.
    honeypot_value = payload.pop(HONEYPOT_FIELD_NAME, None)
    if honeypot_value:
        return {"success": True, "message": "Formulario enviado exitosamente."}

    # 1. Recuperar Formulario
    form = WebFormService.get_public_form_by_uuid(uuid)

    # BARRERA 3: Validación Server-Side del CAPTCHA
    if form.require_captcha:
        # El frontend debe inyectar el token del captcha en el JSON
        captcha_token = payload.pop("captcha_token", None)
        if not captcha_token:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, 
                detail="Falta el token de verificación de seguridad."
            )
        
        # Validación asíncrona (Ejemplo usando Cloudflare Turnstile, funciona igual para reCAPTCHA v3)
        # Hallazgo #10: la llamada al proveedor externo puede fallar por su cuenta
        # (caído, lento, responde algo no-JSON) — sin timeout explícito y sin
        # try/except esto colgaba el request y terminaba en un 500 crudo.
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # NOTA: En un entorno real, el 'secret' debe venir de tus variables de entorno (settings.CAPTCHA_SECRET_KEY)
                res = await client.post(
                    str(settings.CAPTCHA_VERIFY_URL),
                    data={
                        "secret": settings.CAPTCHA_SECRET_KEY,
                        "response": captcha_token,
                        "remoteip": get_client_ip(request)  # Hallazgo #11
                    }
                )
                verification = res.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo verificar el CAPTCHA, intenta de nuevo en unos segundos."
            )

        if not verification.get("success"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="No se pudo verificar que seas humano. Intenta de nuevo."
            )

    # 2. CORS Manual (Validación de Origen)
    origin = request.headers.get("origin") or request.headers.get("referer")
    if form.allowed_domains and len(form.allowed_domains) > 0:
        if not origin or not any(domain in origin for domain in form.allowed_domains):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Origen no autorizado para enviar leads.")

    # 3. Validación de campos requeridos (Hallazgo #9)
    # is_required se declara por campo del FORMULARIO (no confundir con LeadField.required,
    # que es un flag distinto a nivel de CRM). Un campo con hidden_value nunca se exige acá
    # porque el backend lo autocompleta más abajo, sin importar lo que mande el payload.
    #
    # Bug real encontrado 2026-08-15 (reportado por el usuario, al diseñar el frontend público):
    # esto comparaba contra field_config.id, el id INTERNO de WebFormField (columna cruda de la
    # tabla) -- pero GET /public/forms/{uuid} (WebFormFieldResponse, BaseResponse.id) expone cada
    # campo con su `id` = public_uuid, no el interno. Un frontend armado correctamente contra el
    # GET público (usando field.id tal como lo devuelve) nunca iba a matchear ningún campo acá:
    # todos los valores se perdían y cualquier campo obligatorio tiraba "falta" siempre. Se
    # corrige usando field_config.public_uuid (columna directa del modelo, sin resolución extra)
    # en los 3 puntos de este endpoint que antes usaban field_config.id.
    missing_labels = []
    for field_config in form.fields:
        if not field_config.is_required or field_config.hidden_value is not None:
            continue
        value = payload.get(field_config.public_uuid)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_labels.append(
                field_config.custom_label
                or (field_config.lead_field.name if field_config.lead_field else f"Campo #{field_config.public_uuid}")
            )

    if missing_labels:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Faltan campos requeridos: {', '.join(missing_labels)}."
        )

    # 4. 🛡️ INYECCIÓN DE CONTEXTO (Súper importante)
    # Como saltamos el security.py, seteamos la Organización a mano para que el LeadService funcione.
    TENANT_ORG_ID.set(form.organization_id)

    # 5. Mapeo Seguro e Inyección de Valores Ocultos
    # Mismo bug de public_uuid vs id interno explicado arriba -- este mapa es la clave real de
    # todo el submit (sin esto matcheado, ningún valor llega a crear el lead).
    form_fields_map = {f.public_uuid: f for f in form.fields}
    lead_values = []

    for key_id, value in payload.items():
        if key_id in form_fields_map:
            field_config = form_fields_map[key_id]
            final_value = field_config.hidden_value if field_config.hidden_value is not None else value

            lead_values.append(
                LeadFieldValueCreate(
                    field_id=field_config.lead_field_id,
                    value=str(final_value) if final_value is not None else None
                )
            )

    # Forzar Valores Ocultos que no vinieron en el payload
    sent_keys = payload.keys()
    for f in form.fields:
        if f.public_uuid not in sent_keys and f.hidden_value is not None:
            lead_values.append(LeadFieldValueCreate(field_id=f.lead_field_id, value=f.hidden_value))

    # 6. Estructurar payload final e inyectar al Core
    # LeadCreate.campaign_id es public_uuid desde Fase 3 (LeadService.create resuelve el id
    # interno). `form` es el WebForm ORM crudo (WebFormService.get_public_form_by_uuid), así que
    # form.campaign_id es el int interno -- hay que usar form.campaign.public_uuid, no el FK
    # crudo. Sin esto, cualquier envío de formulario público rompía con 422 al construir
    # LeadCreate (bug preexistente, no de esta sesión, ver backend/AGENTS.md §18-decies).
    lead_in = LeadCreate(
        campaign_id=form.campaign.public_uuid,
        values=lead_values
    )

    try:
        LeadService.create(obj_in=lead_in, user_context=None)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Ocurrió un error al procesar el formulario. Intente nuevamente más tarde."
        )

    # 7. Respuesta final
    return {
        "success": True,
        "message": form.success_message or "Formulario enviado exitosamente."
    }