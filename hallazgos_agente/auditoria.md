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
