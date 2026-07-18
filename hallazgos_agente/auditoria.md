# Hallazgo #5 (+ #5b) — Auditoría / `SystemAuditLog` (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/auditoria.md` §7
**Estado:** RESUELTO (2026-07-10) — en dos vueltas, la primera causó una regresión real en producción. Leer las dos secciones completas antes de tocar `_log_audit` de nuevo.

## Hallazgo #5 — `organization_id` NULL vuelve la fila invisible

### Qué se encontró

`SystemAuditLog.organization_id` es `nullable=True`, y `_log_audit` (`app/services/base_service.py`) lo llenaba con `getattr(obj, "organization_id", None)` — si el objeto auditado no tenía atributo `organization_id`, la fila quedaba con `organization_id = NULL`. El filtro de tenant estándar en lectura (`_apply_tenant_filter`) filtra por `organization_id == org_id OR organization_id == ADMIN_ORG_ID` — `NULL` no matchea ninguna de las dos (semántica SQL), así que esas filas quedaban **invisibles** en `GET /audit-logs/` para cualquier organización, para siempre.

**Confirmado que ocurría en la práctica**, no solo en teoría: modelos auditables sin `organization_id` propio: `LeadComment`, `FieldAutomation`, `LeadFieldSubtype`, `LeadFieldType`, `LeadStateTransition`, `TeamMember`, `TeamAccess`. `LeadComment` es el caso más claro: su service no tiene ningún override sobre el CRUD genérico, así que cada comentario creado/editado/borrado generaba una fila de auditoría huérfana.

### Primer fix (con bug, ver #5b abajo)

Usar como fallback `TENANT_ORG_ID.get()` cuando el objeto no tiene `organization_id` propio. **Este fix solo, sin la corrección de #5b, rompe producción — no aplicar así.**

## Hallazgo #5b — Regresión de FK detectada en producción

### Qué pasó

La primera versión del fix usaba `TENANT_ORG_ID.get()` a ciegas, sin validar que esa organización existiera. `system_audit_log.organization_id` tiene una **foreign key real** contra `organization.id` (no es solo `nullable=True`). `OrganizationController._get_deps` devuelve `[]` para las acciones `create`/`read` (ver `app/controllers/organization_controller.py`) — es decir, `POST /organizations/` **no exige** que el header `X-Organization-Id` corresponda a una organización real, aunque `get_current_user_roles` igual hace `TENANT_ORG_ID.set(x_organization_id)` con lo que venga en el header, sin validarlo.

Resultado: crear una organización nueva (o promover a superadmin) con ese header apuntando a un id inexistente hacía que el `INSERT` en `system_audit_log` violara la FK y **abortara la operación completa con `500`** — peor que el bug original (que solo afectaba visibilidad, no rompía nada). Se vio en logs reales de la app (`crm_backend`/`crm_db`, error `violates foreign key constraint "system_audit_log_organization_id_fkey"`), y el único síntoma que llegó a la suite de tests fue `test_security_auth.py::TestOrgLimit::test_superadmin_can_create_multiple_orgs` (5 tests failed en total).

### Fix definitivo aplicado

En `_log_audit` (`app/services/base_service.py`), cuando el objeto auditado no tiene `organization_id` propio:

1. Si el modelo auditado es la propia `Organization`: usar `obj.id` — su propio id, ya garantizado válido porque `uow.session.flush()` corre antes que `_log_audit` en `create`/`update`/`delete`.
2. Para cualquier otro modelo: verificar con una query liviana (`session.query(Organization.id).filter_by(id=candidate_org_id).first()`) que la organización de `TENANT_ORG_ID.get()` realmente exista antes de usarla. Si no existe, cae a `NULL` (el comportamiento original, seguro aunque menos útil) en vez de romper.

### Lección para el agente

Cualquier fallback a `TENANT_ORG_ID.get()` en código que escribe a una columna con FK real necesita verificar existencia primero. El header `X-Organization-Id` **no está garantizado a ser válido** en todos los endpoints — `OrganizationController` es la excepción confirmada (no exige org real para `create`/`read`), pero podría haber otras. No asumir que `TENANT_ORG_ID.get()` siempre apunta a una fila real en base.

## Tests

`tests/functional/test_system_audit_log.py` (5 casos):

1. `test_lead_comment_audit_row_gets_organization_id_not_null` — fila de `LeadComment` con `organization_id` correcto en DB (no `NULL`).
2. `test_lead_comment_audit_row_visible_via_audit_logs_endpoint` — la fila aparece vía `GET /audit-logs/`.
3. `test_audit_row_keeps_real_organization_id_when_object_has_one` — control: el fallback no pisa el valor real en modelos que sí tienen `organization_id` propio (`Workspace`).
4. `test_create_organization_with_nonexistent_org_header_does_not_crash` — reproduce el crash de #5b: crear una org con header `X-Organization-Id` inexistente no debe romper, y la fila de auditoría debe quedar con el id de la organización recién creada (no el del header).
5. `test_log_audit_falls_back_to_null_when_tenant_org_id_does_not_exist` — nivel más bajo: `_log_audit` llamado directamente con `TENANT_ORG_ID` apuntando a una org inexistente no debe lanzar `IntegrityError`, debe caer a `organization_id=NULL`.

Confirmado por el usuario: suite completa OK (después del fix de #5b).

---

# Hallazgo #26 — `LeadActivityHistory`/`LeadStateHistory`: fuga de lectura cross-tenant confirmada (ronda de bug-hunting, 2026-07-10)

**Doc de usuario:** `docs/auditoria.md` §5, §7
**Estado:** [RESUELTO] 2026-07-10 — confirmado por lectura de código y corregido (ver "Fix aplicado" al final), misma familia que #18/#20/#21.

## Qué se encontró

`LeadActivityHistory` (`app/models/audit/lead_activity_history.py`) y `LeadStateHistory` (`app/models/audit/lead_state_history.py`) **no tienen columna `organization_id`** — solo `lead_id`. Sus repositorios no sobreescriben `apply_security_filter`, y sus controllers son `BaseController` genéricos con `enabled_methods = READ_ONLY`, sin `allowed_filter_fields` declarado.

No se detectó en el barrido original del hallazgo #18 porque el grep de esa vez (`grep -q organization_id app/models/*.py`) no bajaba a subcarpetas — estos dos modelos viven en `app/models/audit/`. Se encontró recién al revisar el módulo de Auditoría aplicando el mismo criterio a todos los modelos, incluyendo subcarpetas (ver comando abajo).

**Resultado confirmado:** cualquier usuario autenticado con el permiso genérico `lead_activity_history:view_all`/`lead_state_history:view_all` (que cualquier rol de **cualquier** organización tiene por default) puede leer, vía `GET /lead-activity-histories/?lead_id=<id>` o `GET /lead_state_history/?lead_id=<id>`, el timeline completo y el historial de cambios de estado de **cualquier lead de cualquier organización**. `LeadActivityHistory.details` (JSONB) puede incluir cambios de campos con valores viejos/nuevos (el propio modelo trae como ejemplo en su comentario `{"field_id": 85, "field_name": "Sueldo", "old_value": "1000", "new_value": "2000"}`) — datos potencialmente sensibles de negocio de otra organización, no solo metadata.

## Relación con el hallazgo #5

Es la otra cara de la misma moneda que el hallazgo #5: ahí el bug era que filas de `SystemAuditLog` quedaban con `organization_id = NULL` e **invisibles** para todos. Acá, `LeadActivityHistory`/`LeadStateHistory` ni siquiera tienen la columna — están **visibles para cualquiera**.

## Solución recomendada

Igual que #18/#20: sobreescribir `apply_security_filter` en `LeadActivityHistoryRepository`/`LeadStateHistoryRepository` con un `JOIN` contra `Lead` (`Lead.organization_id == user_context.organization_id`, o `is_superuser`), sin necesidad de migrar el esquema. Alternativa más robusta a largo plazo: agregar `organization_id` real a ambos modelos (derivable de `Lead.organization_id` al crear).

Tests: usuario de la Org A crea un lead con actividad/cambios de estado; usuario de la Org B intenta `GET /lead-activity-histories/?lead_id=<id de A>` y `GET /lead_state_history/?lead_id=<id de A>` → deben devolver vacío/`403`/`404`, no los datos reales.

## Comando de verificación (incluye subcarpetas — el que se usó en la ronda anterior no las cubría)

```bash
find app/models -name '*.py' | grep -v __pycache__ | grep -v __init__ | xargs -I{} sh -c 'grep -q organization_id {} || echo {}'
```

Con este hallazgo, el criterio ya se aplicó a todos los modelos del backend (incluyendo subcarpetas) — no debería quedar ninguna instancia más de esta familia de bug sin revisar.

## Fix aplicado (2026-07-10)

Mismo patrón que #18/#20: se agregó `apply_security_filter` a ambos repositorios (`app/db/repository/audit/lead_activity_history_repository.py` y `.../lead_state_history_repository.py`) — `join` contra `Lead` y filtro por `Lead.organization_id == user_context.organization_id` (bypass superusuario). Como ambos controllers son `READ_ONLY`, no hace falta ninguna validación adicional en el service (no hay `create`/`update`/`delete` expuestos por API para estos modelos).

**Test de regresión:** `tests/functional/test_tenant_isolation.py::TestLeadHistoryIsolation` — no-visibilidad cross-tenant y visibilidad normal en la propia org, para ambos endpoints.

**Nota de test (corrida 2026-07-10, primera vuelta falló):** `test_activity_history_visible_from_own_org` falló con `TypeError: string indices must be integers, not 'str'` — bug del test, no del fix. Asumí que `GET /lead-activity-histories/` devolvía una lista plana; en realidad devuelve la forma paginada (`{"items": [...], "total": ...}`, ver `convenciones_generales.md` §8), así que iterar directo sobre `resp.json()` iteraba las *keys* del dict (strings) en vez de los items. Fix: se agregó el helper `_items(resp)` en `test_tenant_isolation.py` (analógo a `_ids`, ya existente) que maneja ambas formas, y se reescribió el test para usarlo. De paso se fortaleció `test_state_history_visible_from_own_org`, que pasaba pero con un assert vacuo (`resp.json() != []` es siempre `True` para un dict paginado, no verificaba nada real).
