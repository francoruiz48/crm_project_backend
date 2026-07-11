# Hallazgo #4 — Formularios web (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/formularios_web.md` §7
**Estado:** RESUELTO (2026-07-10) — no era un bug, era un hueco de cobertura de riesgo alto.

## Qué se encontró

No existía **ningún** test (funcional o de otro tipo) que ejercitara `WebForm`, `WebFormField`, ni el router público `/public/forms/*` — ni siquiera el caso feliz de crear un formulario y enviarlo. Era el único de los 21 módulos documentados sin cobertura alguna, y el de mayor superficie de ataque del sistema (único endpoint de escritura sin autenticación, con 4 capas de seguridad propias: honeypot, rate limit, CAPTCHA, validación de dominio).

## Cobertura agregada

`tests/functional/test_web_forms.py`:

- **CRUD privado** (`TestWebFormPrivateCRUD`): creación exitosa, rechazo de `lead_field_id` duplicado, rechazo anti-IDOR de un campo que pertenece a otra campaña, rechazo de campo inactivo, reemplazo total de campos en `update`.
- **`GET /public/forms/{uuid}`**: config pública sin exponer `organization_id`/`campaign_id`, `404` con UUID inexistente, `404` con formulario inactivo.
- **`POST /public/forms/{uuid}/submit`**: caso feliz (`created_by=None`), honeypot relleno (éxito simulado sin crear lead), inyección forzada de `hidden_value` (no se puede sobreescribir), CAPTCHA requerido sin token (`400`), CAPTCHA rechazado/aprobado por verificador mockeado, origen no permitido (`403`)/permitido (`200`), rate limit `5/min` (6to intento → `429`).

## Decisiones de testing

- CAPTCHA mockeado vía `httpx.AsyncClient.post` — no depende de red real ni de env vars `CAPTCHA_SECRET_KEY`/`CAPTCHA_VERIFY_URL`.
- El test de rate limit resetea `web_form_public_controller.limiter` antes de cada test de `TestPublicFormSubmit` (fixture `autouse`) — esa instancia de `Limiter` vive a nivel de módulo/proceso y sus contadores persisten entre tests. Funcionó bien en la corrida real del usuario.

## Regresión detectada en la primera corrida (2026-07-10)

Falló `TestWebFormPrivateCRUD::test_create_web_form_rejects_field_from_other_campaign`. No era un bug del fix de producción, sino del propio test: llamaba a `api.create_campaign(...)` sin pasar `lead_flow_id`, y el helper (`tests/helpers/api_helpers.py`) usa un default hardcodeado (`lead_flow_id=1`) que no coincide con el `LeadFlow` real creado por el fixture `initial_structure` (los IDs son dinámicos/autoincrementales entre tests). Se corrigió pasando `lead_flow_id=initial_structure["lead_flow_id"]` explícitamente.

Diagnosticado leyendo `tests/logs/summary.log` → `tests/logs/functional/test_web_forms.log` (ver `AGENTS.md` §4 para el flujo general de cómo leer esos logs).

Confirmado por el usuario: 17/17 tests pasan, suite completa (471 tests) también.

---

# Hallazgos #9, #10, #11 — Formularios web (ronda de bug-hunting, 2026-07-10)

**Doc de usuario:** `docs/formularios_web.md` §8
**Estado:** #9 [RESUELTO] 2026-07-10. #10 y #11 PENDIENTES — investigados y documentados, sin aplicar fix. No tocar código sin antes preguntar (regla del proyecto).

Contexto: el usuario pidió arrancar una segunda ronda de auditoría, ahora buscando bugs funcionales/de seguridad módulo por módulo (no solo huecos de tests como la ronda anterior). Se re-leyeron enteros: `web_form_service.py`, `web_form_public_controller.py`, `web_form_controller.py`, `web_form_repository.py`, `web_form_schema.py`, `web_form_field_schema.py`, `web_form.py` (modelo), `web_form_field.py` (modelo), `app/core/config.py`.

## Hallazgo #9 — `WebFormField.is_required` nunca se aplica (confirmado, mayor impacto) — [RESUELTO] 2026-07-10

`is_required` existe en el modelo (`web_form_field.py:20`) y en el schema (`web_form_field_schema.py:11`), se manda al frontend público vía `GET /public/forms/{uuid}` (`WebFormFieldResponse` lo incluye), pero **nada en `submit_public_form` lo lee** — confirmado con `grep -rn is_required app/`, el único uso real es la declaración en modelo/schema. La única validación de "obligatorio" que sobrevive del lado del backend es el `LeadField.required` original (un flag distinto, a nivel de campo del CRM, no del formulario puntual).

Consecuencia: un visitante puede omitir o mandar vacío un campo marcado `is_required=True` en ese formulario y el lead se crea igual, salvo que el `LeadField` subyacente también sea `required=True` por otra razón. Como el submit es un endpoint público sin login, esto es trivial de explotar llamando directo a la API (sin pasar por el frontend que sí validaría en el cliente).

**Solución recomendada:** en `submit_public_form`, después de armar `form_fields_map`, iterar los `form.fields` con `field_config.is_required=True` y validar que su `key_id` esté en `payload` con un valor no vacío (después de descontar `hidden_value`, que ya se autocompleta y no debería contar como "faltante"); si falta, `400` con detalle del campo. Agregar tests: envío sin un campo requerido → `400`; envío con el campo requerido presente → `200`; campo requerido con `hidden_value` (no debería exigir que venga en el payload, ya se autocompleta).

### Fix aplicado (2026-07-11)

`app/controllers/web_form_public_controller.py::submit_public_form`: se agregó, antes de la inyección de `TENANT_ORG_ID`, un bloque que itera `form.fields` y por cada uno con `is_required=True` y `hidden_value is None` verifica que `payload.get(str(field.id))` no sea `None` ni un string vacío/solo-espacios. Si falta alguno, `400` con `detail="Faltan campos requeridos: <lista de labels>."` (decisión del usuario: listar los campos faltantes, no un mensaje genérico). El label usado es `custom_label` si está seteado, si no `lead_field.name` (accesible sin `DetachedInstanceError` porque el mismo patrón ya funciona hoy en `GET /public/forms/{uuid}` vía `WebFormFieldResponse.lead_field`), y como último fallback `f"Campo #{id}"`.

Un campo con `hidden_value` seteado nunca se exige en el payload, sin importar `is_required` — el backend ya lo autocompleta más abajo en el mismo endpoint (bloque "Forzar Valores Ocultos").

**Test de regresión:** `tests/functional/test_web_forms.py::TestPublicFormSubmit` — `test_submit_missing_required_field_returns_400` (ausencia de la clave y string vacío/blanco, ambos → 400, no se crea lead), `test_submit_required_field_present_succeeds` (valor presente → 200), `test_submit_required_field_with_hidden_value_not_demanded_from_payload` (is_required + hidden_value juntos → 200 sin mandarlo, se autocompleta).

## Hallazgo #10 — Llamada al proveedor de CAPTCHA sin manejo de errores ni timeout explícito (confirmado)

En `web_form_public_controller.py` líneas ~52-67, el `httpx.AsyncClient().post(...)` a `settings.CAPTCHA_VERIFY_URL` y el `res.json()` posterior no están dentro de ningún `try/except`, y no se pasa `timeout=` (queda en el default de `httpx`). El único `try/except` del endpoint (líneas 107-115) envuelve solamente `LeadService.create`, más abajo. Si el proveedor de CAPTCHA está caído, responde lento, o devuelve algo que no es JSON válido, la excepción se propaga sin capturar y el endpoint responde `500` crudo (sin el mensaje prolijo que sí se usa para el resto de los errores del submit) — y mientras tanto el request queda colgado hasta el timeout default de `httpx`.

**Solución recomendada:** envolver ese bloque en `try/except (httpx.HTTPError, ValueError)` (`ValueError` cubre `res.json()` fallando por respuesta no-JSON) y devolver `400`/`503` con un mensaje del estilo "No se pudo verificar el CAPTCHA, intenta de nuevo" en vez de dejar que reviente como `500`. Agregar `timeout=10.0` (o el valor que el usuario prefiera) explícito en el `client.post`. Test: mockear `httpx.AsyncClient.post` para que tire `httpx.ConnectError` o devuelva texto no-JSON, verificar que el endpoint responde con un error controlado (400/503) y no un 500 sin manejar.

## Hallazgo #11 — `request.client.host` como fuente de IP para rate limit y CAPTCHA `remoteip` (menor confianza, no confirmado)

El rate limit (`@limiter.limit("5/minute")`, vía `get_remote_address` de `slowapi`) y el `remoteip` que se le manda al verificador de CAPTCHA usan ambos `request.client.host`. Si la app corre detrás de un proxy/balanceador (nginx, load balancer, etc. — probable dado que los logs de producción que compartió el usuario mostraban contenedores `crm_backend`/`crm_db`, sugiriendo despliegue con docker-compose y probablemente un proxy delante), esa IP sería la del proxy y no la del visitante real. Efecto: el rate limit de `5/minuto` terminaría compartido por *todos* los visitantes (fácil de agotar por cualquiera, o bloquea a todos por igual si uno abusa), y el `remoteip` mandado al CAPTCHA sería inútil para su propia heurística anti-bot.

**No se pudo confirmar** si el despliegue real efectivamente pasa por un proxy inverso — depende de infraestructura que no es visible desde el código. Antes de tocar esto habría que preguntarle al usuario cómo está desplegado el backend en producción.

**Solución recomendada (si se confirma que hay proxy delante):** usar el header `X-Forwarded-For` (primer IP de la lista) o `X-Real-IP` si el proxy los setea, con `get_remote_address` reemplazado por una función custom que los lea con fallback a `request.client.host`. Si no hay proxy, no hace falta cambiar nada.
