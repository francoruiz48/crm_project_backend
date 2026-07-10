# Dashboard

Documentación técnica de los dos endpoints de métricas agregadas del sistema. Módulo agregado a esta ronda de documentación a pedido explícito (no estaba en la lista original de módulos). No tiene modelo propio: son queries de agregación (`func.count`, `group_by`) sobre `Lead`, `SystemAuditLog`, `UserOrganization` y `Organization`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [`GET /dashboard/org`](#2-get-dashboardorg)
3. [`GET /dashboard/admin`](#3-get-dashboardadmin)
4. [Cómo se testea](#4-cómo-se-testea)

---

## 1. Visión general

Dos endpoints de solo lectura, sin filtros ni paginación — cada uno arma un snapshot fijo de métricas. No usan el patrón `BaseController`/`BaseService` (es un `APIRouter` manual), porque no representan una entidad CRUD sino un agregado de varias.

Archivos: `app/controllers/dashboard_controller.py`, `app/services/dashboard_service.py`, `app/schemas/dashboard_schema.py`.

---

## 2. `GET /dashboard/org`

Requiere sesión válida (`get_current_user_roles`), sin permiso adicional explícito — cualquier usuario autenticado de la organización activa (vía `X-Organization-Id`) puede verlo. Devuelve, todo scopeado a `organization_id = user_context.organization_id`:

- `total_leads`: conteo de leads activos.
- `leads_by_flow_state`: leads activos agrupados por `LeadState` (nombre, color, total) — insumo típico para un gráfico de embudo.
- `leads_by_contact_state`: lo mismo pero agrupado por `LeadContactState`.
- `recent_activity`: los últimos 20 `SystemAuditLog` de la organización (con nombre del usuario que hizo el cambio, vía `outerjoin` — si el actor fue `None`, ej. un envío de `WebForm` público, queda sin nombre).
- `org_users`: miembros activos de la organización con su email y si son `owner`.

---

## 3. `GET /dashboard/admin`

Requiere `require_superuser` explícito en la dependencia de ruta — el único de los dos endpoints con esa restricción. Recorre **todas** las organizaciones activas (excluyendo `ADMIN_ORG_ID`, el "Panel Global") y arma, por cada una: cantidad de usuarios, cantidad de leads, fecha del último evento de auditoría, y nombre del `owner`. Agrega también los totales globales (`total_active_orgs`, `total_users`, `total_leads`).

**Nota de rendimiento:** el cálculo por organización corre en un bucle `for org in orgs` con 3 queries separadas por organización (usuarios, leads, último log, más el query del owner) — es decir, `~4 × N` queries donde `N` es la cantidad de organizaciones activas. Para una instancia con muchas organizaciones, este endpoint podría volverse lento; no hay agregación en una sola query ni cacheo.

---

## 4. Cómo se testea

No se encontró ningún test para `/dashboard/org` ni `/dashboard/admin` — ni el caso feliz, ni la restricción de `require_superuser` en el endpoint admin. **Recomendación:** al menos un test por endpoint que confirme el scoping por organización (que `/dashboard/org` no mezcle datos de otra organización) y que un usuario no-superadmin reciba `403` en `/dashboard/admin`.
