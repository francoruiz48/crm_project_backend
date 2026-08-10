# Hallazgo #20 — Automatización de campos: IDOR cross-tenant confirmado (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/automatizacion_de_campos.md` §3
**Estado:** [RESUELTO] 2026-07-10 — confirmado por lectura de código y corregido (ver "Fix aplicado" al final), misma familia que el hallazgo #18.

## Qué se encontró

Mismo patrón exacto que el hallazgo #18 (`LeadComment`): `FieldAutomation` (`app/models/field_automation.py`) **no tiene columna `organization_id`** — solo `campaign_id` (FK a `Campaign`, que sí es tenant-scoped). `FieldAutomationController` es 100% genérico (`BaseController`, sin overrides) y `FieldAutomationService` está vacío (hereda todo de `BaseService`, sin validación propia más allá de lo que valida Pydantic sobre la forma del JSON de condiciones/acciones — confirmado, ya lo señalaba `docs/automatizacion_de_campos.md` §1 aunque sin identificar la consecuencia de tenant-isolation).

`FieldAutomationCreate`/`Update` (`app/schemas/field_automation_schema.py`) reciben `campaign_id: int` directo del cliente, sin acotar. Como el modelo no tiene `organization_id`, ni `_apply_tenant_filter` ni la inyección automática de organización en `create` hacen nada (mismo mecanismo descripto en el hallazgo #18), y `FieldAutomationRepository` no sobreescribe `apply_security_filter`.

**Resultado confirmado:** cualquier usuario autenticado con el permiso `field_automation:create`/`update`/`delete`/`view` (que el rol `admin` de **cualquier** organización tiene, y probablemente `agent` según cómo esté configurado el rol) puede crear, editar, ver o borrar reglas de automatización apuntando a un `campaign_id` de **otra organización**.

## Por qué esto es potencialmente más grave que el hallazgo #18

`LeadComment` (hallazgo #18) permite leer/escribir texto libre ajeno. `FieldAutomation` permite **inyectar reglas que mutan automáticamente los datos de los leads de otra organización** cada vez que esa organización crea o actualiza un lead (`ON_CREATE`/`ON_UPDATE`) — un atacante con una cuenta en el sistema podría, por ejemplo, crear una regla en la campaña de una organización ajena que borre/corrompa un campo crítico (`CLEAR_VALUE`), o filtre datos hacia un campo visible (`COPY_FROM_FIELD`/`SET_VALUE`) cada vez que esa organización opera con sus propios leads — sin que nadie de esa organización haya hecho nada para provocarlo. Es manipulación de datos activa y persistente, no solo lectura/escritura puntual.

## Solución recomendada

Mismo patrón que el hallazgo #18: la solución más simple y consistente con el resto del sistema es sobreescribir `create`/`update`/`delete`/`deactivate` en `FieldAutomationService` para validar que el `campaign_id` recibido (al crear) o el de la regla existente (al editar/borrar) pertenece a `user_context.organization_id` — resolviendo la organización a través de `Campaign.organization_id` (join simple). Alternativa más robusta a largo plazo, igual que en el hallazgo #18: agregar una columna `organization_id` real a `FieldAutomation` (derivable de `Campaign.organization_id` al crear) para que el mecanismo genérico de aislamiento la cubra automáticamente sin lógica a medida.

Test: usuario de la Org A crea una `FieldAutomation` con `campaign_id` de la Org B (usuario de la Org B, cuenta distinta) → debe rechazarse (`400`/`403`/`404`, no `200`). Mismo test para `update`/`delete`/`get_by_id`.

## Nota — revisar el mismo patrón en el resto del barrido

Como ya se anotó en el hallazgo #18, cualquier modelo "colgado" de `Campaign`/`Lead`/otra entidad tenant-scoped sin su propia columna `organization_id` y sin validación manual de la FK en el service es candidato al mismo bug. Ya se revisó y descartó para `LeadFieldValue` (no tiene controller propio expuesto). Falta revisar con este criterio explícito los módulos que quedan pendientes del barrido (estados de contacto, flujo de leads, vistas de leads, etiquetas, reglas de validación, etc.).

## Fix aplicado (2026-07-10)

Mismo patrón que el hallazgo #18 (sin migración de esquema):

1. **`app/db/repository/field_automation_repository.py`**: se agregó `apply_security_filter` — `join` contra `Campaign` y filtra por `Campaign.organization_id == user_context.organization_id` (bypass superusuario). Protege `GET_ALL`/`GET_ONE` y, vía el gatekeeper de dos capas de `BaseService`, también `PUT`/`DELETE`/`DEACTIVATE`.
2. **`app/services/field_automation_service.py`**: se sobreescribió `create` para validar que `obj_data.campaign_id` pertenece a `user_context.organization_id` (query directa a `Campaign`) antes de crear la automatización — `400` si no.

**Test de regresión:** `tests/functional/test_tenant_isolation.py::TestFieldAutomationIsolation` — creación bloqueada sobre campaña ajena, no-visibilidad cross-tenant, visibilidad normal en la propia org.
