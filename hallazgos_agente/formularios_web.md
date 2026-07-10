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
