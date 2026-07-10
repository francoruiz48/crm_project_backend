# Formularios Web (`WebForm`)

Documentación técnica de los formularios embebibles (landing pages, iframes) que crean leads públicamente, sin autenticación. Es el único módulo del sistema con un endpoint de escritura completamente público (`POST /public/forms/{uuid}/submit`). Asume conocido `lead.md` (cada envío termina en `LeadService.create`) y `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints privados (`/web_forms`)](#3-endpoints-privados-web_forms)
4. [Endpoints públicos (`/public/forms`)](#4-endpoints-públicos-publicforms)
5. [Las 4 barreras de seguridad del submit público](#5-las-4-barreras-de-seguridad-del-submit-público)
6. [Campos ocultos (`hidden_value`)](#6-campos-ocultos-hidden_value)
7. [RESUELTO: cobertura de tests](#7-resuelto-cobertura-de-tests)

---

## 1. Visión general

Un `WebForm` pertenece a una `Campaign` y expone un subconjunto de sus `LeadField` (vía `WebFormField`) para que un visitante externo cargue un lead sin tener cuenta en el sistema — pensado para incrustar en una landing page como `<iframe>`. Se identifica públicamente por un `public_uuid` (no por su `id` interno, para no exponer ni permitir enumerar formularios).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/web_form.py`, `web_form_field.py` | Modelos |
| `app/controllers/web_form_controller.py` | CRUD privado, `/web_forms/*` (requiere login) |
| `app/controllers/web_form_public_controller.py` | `/public/forms/*` — sin autenticación |
| `app/services/web_form_service.py` | Reglas de negocio del área privada y pública |

---

## 2. Modelo de datos

```
Campaign ──< WebForm >── WebFormField >── LeadField
```

- **`WebForm`**: `public_uuid` (UUID v4 autogenerado, único, es la clave de acceso público), `organization_id`/`campaign_id` (`ondelete="CASCADE"`), `name` (interno), `title`/`description` (públicos), `theme_config` (JSON libre de estilos), `success_message`, `redirect_url`, `allowed_domains` (JSON, lista de orígenes permitidos — ver §5), `require_captcha`, `active`.
- **`WebFormField`**: `web_form_id`, `lead_field_id` (`ondelete="CASCADE"` en ambos), `order`, `custom_label`/`custom_placeholder` (sobrescrituras visuales opcionales sobre el `LeadField` original), `is_required` (regla propia del formulario, independiente del `required` del `LeadField`), `hidden_value` (ver §6).

`delete_strategy = SOFT_DELETE_HARD_OPT` para `WebForm` (ver `convenciones_generales.md` §9); `WebFormField` → `HARD_DELETE_ALWAYS`, aunque en la práctica sus filas se reemplazan en bloque en cada `update` del formulario (ver §3), no se borran una por una vía API.

---

## 3. Endpoints privados (`/web_forms`)

`WebFormController` es genérico (`BaseController`, `enabled_methods = READ_WRITE | {"DEACTIVATE"}`), pero el service sobreescribe `create`/`update`/`delete` con reglas propias:

- **Al crear**: valida que la `campaign_id` pertenezca a la organización del usuario, e inyecta `organization_id` en el payload (no confía en lo que mande el cliente). Los `WebFormField` hijos se validan con `_validate_form_fields`: sin duplicados de `lead_field_id` en el mismo payload, todos deben existir, pertenecer **exactamente** a la campaña del formulario (protección anti-IDOR — no se puede exponer un campo de otra campaña) y estar activos.
- **Al actualizar**: si el payload trae `fields`, es un **reemplazo total** — se borran todos los `WebFormField` existentes (bulk delete SQL) y se insertan los nuevos, no hay merge parcial.
- **Al actualizar/borrar**: doble chequeo de organización a mano (`WebForm.organization_id == org_id`) además del filtro de tenant estándar — el comentario en el código lo marca explícitamente como "seguridad estricta".

---

## 4. Endpoints públicos (`/public/forms`)

Router aparte (`web_form_public_controller.py`), sin ningún `Depends(get_current_user_roles)` — deliberadamente público, para que un visitante sin cuenta pueda enviar el formulario:

| Método y ruta | Qué hace |
|---|---|
| `GET /public/forms/{uuid}` | Devuelve la configuración pública del formulario (título, campos, tema) para que el frontend externo lo renderice. |
| `POST /public/forms/{uuid}/submit` | Procesa el envío y crea un `Lead`. |

`get_public_form_by_uuid` (usado por ambos endpoints) valida que el formulario esté `active=True` **y** que tanto su organización como su campaña sigan activas — un formulario de una organización suspendida deja de funcionar automáticamente, sin necesidad de desactivarlo uno por uno.

---

## 5. Las 4 barreras de seguridad del submit público

Al no requerir login, `submit_public_form` es la superficie de ataque más expuesta del sistema. Corre, en orden:

1. **Rate limiting**: `5/minute` por IP (`slowapi`, `get_remote_address`).
2. **Honeypot**: un campo falso (`website_url_ext`) que el frontend público debe incluir oculto vía CSS. Si viene relleno, es casi seguro un bot rellenando todos los campos del formulario a ciegas — se responde `200` con éxito simulado (para no delatar al bot que fue detectado) sin crear ningún lead.
3. **CAPTCHA server-side** (opcional, si `form.require_captcha=True`): valida el token contra un servicio externo (Cloudflare Turnstile / reCAPTCHA v3 vía `settings.CAPTCHA_VERIFY_URL`). Sin token o con verificación fallida, `400`.
4. **Validación de origen** (`allowed_domains`): si el formulario tiene dominios configurados, exige que el header `Origin` o `Referer` contenga alguno de ellos (chequeo de substring, no de dominio exacto — ver nota abajo). Sin ese header o sin matchear, `403`.

**Nota de precisión:** la validación de dominio usa `domain in origin` (substring), no comparación exacta de host — un `allowed_domains = ["miweb.com"]` también dejaría pasar un origen como `https://noesmiweb.com.atacante.com` si ese string completo apareciera en el header. No se confirmó si esto es explotable en la práctica (depende de qué tan predecible sea el dominio configurado), pero es una implementación más laxa de lo que "dominio permitido" sugiere.

Después de estas barreras: el endpoint pisa `TENANT_ORG_ID` manualmente (`TENANT_ORG_ID.set(form.organization_id)`) porque no hay JWT que lo haga automáticamente, arma el `LeadCreate` mapeando `{lead_field_id: valor}` desde el payload, e invoca `LeadService.create(user_context=None)` — el lead resultante queda con `created_by=None` (nadie logueado lo creó), pasando igualmente por todo el pipeline de validación/automatización de `lead.md` §4.

---

## 6. Campos ocultos (`hidden_value`)

Un `WebFormField` con `hidden_value` no se muestra al visitante (el frontend público debe omitirlo del formulario visible), pero el backend lo inyecta automáticamente al crear el lead — típico para "de qué campaña/UTM vino este formulario" sin que el usuario final lo vea ni pueda manipularlo. El submit fuerza el valor oculto **incluso si el payload no trae esa clave**, y si el payload sí trae un valor para ese campo, el oculto **lo pisa** (`field_config.hidden_value if ... is not None else value`) — el visitante no puede sobreescribir un campo oculto aunque intente mandarlo en el JSON.

---

## 7. [RESUELTO] Cobertura de tests

**Antes (hasta 2026-07-10):** no existía **ningún** test (funcional o de otro tipo) que ejercitara `WebForm`, `WebFormField`, ni el router público `/public/forms/*` — ni siquiera el caso feliz de crear un formulario y enviarlo. Era el único de los 21 módulos de esta ronda de documentación sin cobertura alguna, y además el de mayor superficie de ataque (endpoint de escritura sin autenticación, con 4 capas de seguridad propias que hasta entonces dependían únicamente de revisión manual del código).

**Cobertura agregada:** `tests/functional/test_web_forms.py`:

- **CRUD privado** (`TestWebFormPrivateCRUD`): creación exitosa, rechazo de `lead_field_id` duplicado en el mismo payload, rechazo anti-IDOR de un campo que pertenece a otra campaña, rechazo de campo inactivo, reemplazo total de campos en `update`.
- **`GET /public/forms/{uuid}`** (`TestPublicFormGet`): devuelve la config pública sin exponer `organization_id`/`campaign_id`, `404` con UUID inexistente, `404` con formulario inactivo.
- **`POST /public/forms/{uuid}/submit`** (`TestPublicFormSubmit`): caso feliz (crea el lead, `created_by=None`), honeypot relleno (responde éxito simulado sin crear lead), inyección forzada de `hidden_value` (no se puede sobreescribir), CAPTCHA requerido sin token (`400`), CAPTCHA rechazado por el verificador externo mockeado (`400`), CAPTCHA aprobado por el verificador mockeado (crea el lead), origen no permitido (`403`), origen permitido (`200`), y rate limit de `5/minuto` (el 6to intento en la misma ventana da `429`).

**Decisiones de testing a tener en cuenta:**

- El CAPTCHA se testea mockeando `httpx.AsyncClient.post` (no se llama a ningún servicio externo real, ni depende de `CAPTCHA_SECRET_KEY`/`CAPTCHA_VERIFY_URL`).
- El test de rate limit resetea el `Limiter` del router (`web_form_public_controller.limiter`) antes de cada test de la clase `TestPublicFormSubmit` (vía fixture `autouse`) — ese `Limiter` es una instancia separada de la de `app.main` y sus contadores viven a nivel de módulo/proceso, así que sin el reset los tests de la clase se pisarían la cuota entre sí. No se pudo confirmar en este entorno (sin poder correr pytest) que el comportamiento sea idéntico al de producción — es el test más probable de fallar si algo no es como se documentó acá; revisarlo primero si falla.
- Sigue habiendo margen para más casos (ej. múltiples formularios por campaña, campos con `custom_label`/`custom_placeholder`, mapeo de campos por combinación multi-criterio como en `importacion_y_exportacion.md`), pero se priorizaron los escenarios de seguridad por ser los de mayor riesgo.
