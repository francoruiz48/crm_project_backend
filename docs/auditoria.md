# Auditoría (`SystemAuditLog`, `LeadActivityHistory`, `LeadStateHistory`)

Documentación técnica de los tres mecanismos de auditoría/historial del sistema. Se documentan juntos porque son "el mismo tema" visto desde tres ángulos distintos, y porque los tres son de solo lectura vía API — se escriben únicamente desde el código de negocio, nunca directamente por el usuario. Asume conocido `convenciones_generales.md` §4 (`_log_audit`). Última revisión: 2026-07-10.

## Índice

1. [Visión general: tres historiales, tres propósitos](#1-visión-general-tres-historiales-tres-propósitos)
2. [`SystemAuditLog`: el log técnico general](#2-systemauditlog-el-log-técnico-general)
3. [`LeadActivityHistory`: el timeline legible del lead](#3-leadactivityhistory-el-timeline-legible-del-lead)
4. [`LeadStateHistory`: historial puro de cambios de estado](#4-leadstatehistory-historial-puro-de-cambios-de-estado)
5. [Endpoints](#5-endpoints)
6. [Inmutabilidad y `delete_strategy`](#6-inmutabilidad-y-delete_strategy)
7. [RESUELTO: filtro de tenant con `organization_id` nulo](#7-resuelto-filtro-de-tenant-con-organization_id-nulo)
8. [Cómo se testea](#8-cómo-se-testea)

---

## 1. Visión general: tres historiales, tres propósitos

El sistema no tiene un único log de auditoría — tiene tres, con alcances distintos y complementarios:

| Modelo | Alcance | Para quién |
|---|---|---|
| `SystemAuditLog` | **Cualquier entidad del sistema** (no solo `Lead`) | Trazabilidad técnica interna / soporte |
| `LeadActivityHistory` | Solo eventos sobre un `Lead` puntual | Timeline visible en la UI del lead, para el usuario final |
| `LeadStateHistory` | Solo transiciones de `current_state_id` de un `Lead` | Reconstruir el recorrido de un lead por el `LeadFlow` |

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/audit/system_audit_log.py`, `lead_activity_history.py`, `lead_state_history.py` | Modelos |
| `app/controllers/audit/*.py` | Endpoints de solo lectura |
| `app/services/base_service.py::_log_audit` | Escritura genérica de `SystemAuditLog` (ver `convenciones_generales.md` §4) |
| `app/services/lead_service.py::_log_activity` | Escritura de `LeadActivityHistory` (ver `lead.md` §4/§8) |

---

## 2. `SystemAuditLog`: el log técnico general

Escrito automáticamente por `BaseService` en creación/actualización/borrado/reactivación de **cualquier** entidad (ver `convenciones_generales.md` §4), más llamadas manuales adicionales desde services con lógica propia (`LeadService`, `LeadFieldService`, etc., cuando hacen algo fuera del CRUD genérico como cambios de estado o reasignaciones). Campos: `organization_id` (nullable), `entity_type` (nombre de la clase del modelo, ej. `"Campaign"`), `entity_id`, `action` (`CREATE`/`UPDATE`/`DELETE`/y variantes como `DISABLED`/`ACTIVATED`/`PROMOTE_SUPERUSER`/`PROMOTE_OWNER`), `changes` (JSONB, diff `{"campo": {"old": ..., "new": ...}}`), `created_by`.

Para evitar bucles infinitos de auditoría, `_log_audit` excluye explícitamente a `LeadActivityHistory`, `LeadStateHistory` y al propio `SystemAuditLog` de la lista de modelos auditables (`ignored_models`, ver `convenciones_generales.md` §4) — de otro modo, cada escritura de auditoría generaría una nueva entrada de auditoría sobre sí misma.

---

## 3. `LeadActivityHistory`: el timeline legible del lead

Escrito exclusivamente por `LeadService._log_activity` (ver `lead.md` §4, §7, §8, §10) en puntos específicos del ciclo de vida de un lead: `LEAD_CREATED`, `FIELDS_UPDATED` (con valores traducidos a texto legible, no IDs crudos — ver `lead.md` §8), `STATE_CHANGED`, `LEAD_REASSIGNED`. Campos: `lead_id` (`ondelete="CASCADE"` — se borra junto con el lead), `activity_type`, `details` (JSONB libre, la forma varía según `activity_type`), `created_by`.

A diferencia de `SystemAuditLog` y `LeadStateHistory`, este modelo hereda directamente de `Base` (no de `BaseModelDB`) — no tiene `active`, `updated_at` ni `updated_by`, coherente con ser un registro de solo-inserción que nunca se edita ni desactiva.

---

## 4. `LeadStateHistory`: historial puro de cambios de estado

Escrito por `LeadService.create` (primer estado, `from_state_id=None`) y `LeadService.change_state` (ver `lead.md` §4 y §7). Campos: `lead_id`, `from_state_id` (nullable, `None` en el primer registro de un lead), `to_state_id` (obligatorio), `notes` (motivo opcional del cambio, lo manda quien ejecuta el cambio de estado).

**Nota de inconsistencia menor:** a diferencia de `LeadActivityHistory` y `SystemAuditLog` (que heredan de `Base` puro), `LeadStateHistory` hereda de `BaseModelDB` — por lo tanto sí tiene `active`, `updated_at`, `updated_by`, `creator`, `updater`, aunque en la práctica ninguno de esos campos se usa nunca fuera de su valor por defecto (nunca se actualiza ni desactiva un registro de historial). No es un problema funcional, pero rompe la simetría con los otros dos modelos de auditoría del mismo módulo.

---

## 5. Endpoints

Los tres controllers son `BaseController` con `enabled_methods = READ_ONLY` (`{"GET_ALL", "GET_ONE"}`) — nunca se crean, editan ni borran vía API, solo se consultan:

| Router | Filtro típico de uso |
|---|---|
| `GET /audit-logs/*` | Por `entity_type` + `entity_id` (ver dinámica de filtros, `convenciones_generales.md` §8) |
| `GET /lead-activity-histories/*` | Por `lead_id` |
| `GET /lead_state_history/*` | Por `lead_id` |

**[RESUELTO, hallazgo #26, 2026-07-10]** `LeadActivityHistory` y `LeadStateHistory` no tienen columna `organization_id` propia y sus repositorios no filtraban por tenant de ninguna otra forma — cualquier usuario autenticado de cualquier organización podía leer, vía `?lead_id=<id>`, el timeline y el historial de estados de un lead de otra organización. Fix: ambos repositorios ahora sobreescriben `apply_security_filter` (`join` contra `Lead`, filtro por organización). Detalle en `hallazgos_agente/auditoria.md`.

---

## 6. Inmutabilidad y `delete_strategy`

Los tres tienen `delete_strategy = PROTECTED` (ver `convenciones_generales.md` §9) — ni siquiera un superadmin puede borrar un registro de auditoría a través de la API genérica; cualquier intento de `DELETE` es rechazado. Es consistente con el propósito de estos modelos: si se pudieran editar o borrar, dejarían de ser confiables como rastro de lo que realmente pasó.

---

## 7. [RESUELTO] Filtro de tenant con `organization_id` nulo

**Bug (hasta 2026-07-10):** `SystemAuditLog.organization_id` es `nullable=True`, y `_log_audit` lo llenaba con `getattr(obj, "organization_id", None)` — si el objeto auditado no tenía atributo `organization_id`, la fila de auditoría quedaba con `organization_id = NULL`.

El filtro de tenant estándar en lectura (`_apply_tenant_filter`, ver `convenciones_generales.md` §6) filtra por `organization_id == org_id OR organization_id == ADMIN_ORG_ID` — una fila con `organization_id = NULL` no matchea ninguna de las dos condiciones (semántica SQL de `NULL`), así que quedaba **invisible** en `GET /audit-logs/` para cualquier organización, incluida la que originó el cambio.

**Confirmado que ocurría en la práctica** (no era solo teórico): se relevaron los modelos auditables sin columna `organization_id` propia — `LeadComment`, `FieldAutomation`, `LeadFieldSubtype`, `LeadFieldType`, `LeadStateTransition`, `TeamMember`, `TeamAccess`. De estos, `LeadComment` es el caso más claro: su service (`lead_comment_service.py`) no tiene ningún override sobre el CRUD genérico, así que **cada comentario creado/editado/borrado en el sistema generaba una fila de auditoría huérfana**, invisible por API para siempre.

**Fix aplicado:** en `_log_audit` (`app/services/base_service.py`), cuando el objeto auditado no tiene `organization_id` propio, se usa como fallback `TENANT_ORG_ID.get()` — la organización activa del request que está ejecutando la acción.

**Regresión detectada en producción tras el primer fix (2026-07-10):** la primera versión usaba `TENANT_ORG_ID.get()` sin validar que esa organización existiera. `system_audit_log.organization_id` tiene una **foreign key real** contra `organization.id` (no es solo `nullable=True`), y `OrganizationController._get_deps` devuelve `[]` para `create`/`read` — es decir, `POST /organizations/` no exige que el header `X-Organization-Id` corresponda a una organización real. Al crear una organización con ese header apuntando a un id inexistente, el `INSERT` en `system_audit_log` violaba la FK (`insert or update on table "system_audit_log" violates foreign key constraint`) y **abortaba la creación completa de la organización** con un `500` — una regresión bastante peor que el bug original (que solo afectaba visibilidad, no rompía nada). Se vio en logs de producción real, no en tests: superadmin creando organizaciones y promoviendo usuarios a superadmin ambos dispararon el error.

**Fix definitivo:** dos ajustes en `_log_audit`: (1) si el modelo auditado es la propia `Organization`, se usa `obj.id` — su propio id, ya garantizado válido porque el `flush()` corre antes que `_log_audit` — en vez de depender del header; (2) para cualquier otro modelo, antes de usar `TENANT_ORG_ID.get()` se verifica con una query liviana que esa organización realmente exista; si no existe, se cae de nuevo a `NULL` (el comportamiento original, seguro aunque menos útil) en lugar de romper la operación.

---

## 8. Cómo se testea

No hay un archivo de test dedicado a estos tres módulos como tales; se verifican indirectamente dentro de las suites de los módulos que los generan — por ejemplo `test_automation_engine.py::test_automation_leaves_audit_trace` (confirma que una automatización deja rastro en el historial correspondiente) y aserciones sobre historial dentro de `test_lead_flows_and_states.py` (`test_lead_lifecycle_and_history`). Desde 2026-07-10, `tests/functional/test_system_audit_log.py` cubre el fix de §7 (5 casos): crea un `LeadComment` y verifica que la fila de `SystemAuditLog` resultante tenga `organization_id` correcto (no `NULL`) tanto directo en la DB como visible vía `GET /audit-logs/`; control de que el fallback no pisa el valor real en modelos que sí tienen `organization_id` propio (`Workspace`); y dos tests que cubren específicamente la regresión del FK (crear una organización con un header `X-Organization-Id` inexistente no debe romper, y `_log_audit` no debe reventar si `TENANT_ORG_ID` apunta a una organización que no existe). **Sigue sin haber tests** que ejerciten paginación/filtros/aislamiento de tenant de estos endpoints de forma más exhaustiva, ni cobertura directa de `GET /lead-activity-histories/*` / `GET /lead_state_history/*`.
