# Campañas y Workspaces

Documentación técnica de `Workspace` (espacio de trabajo, contenedor de campañas) y `Campaign` (la unidad real donde se cargan leads). Se documentan juntos porque `Campaign` no existe sin un `Workspace` padre y comparten el mismo concepto de visibilidad (`is_public`). Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Creación de un Workspace](#4-creación-de-un-workspace)
5. [Creación de una Campaign: resolución de flujo y campos por defecto](#5-creación-de-una-campaign-resolución-de-flujo-y-campos-por-defecto)
6. [Actualización de una Campaign: permisos y bloqueo de `lead_flow_id`](#6-actualización-de-una-campaign-permisos-y-bloqueo-de-lead_flow_id)
7. [`is_public`: el interruptor que anula equipos y enrutamiento](#7-is_public-el-interruptor-que-anula-equipos-y-enrutamiento)
8. [Borrado](#8-borrado)
9. [Cómo se testea](#9-cómo-se-testea)

---

## 1. Visión general

`Workspace` agrupa campañas dentro de una organización (ej. "Ventas", "Soporte"). `Campaign` es donde efectivamente se configuran los `LeadField` (ver `campos_personalizados.md`) y se cargan los `Lead` (ver `lead.md`); cada campaña apunta a exactamente un `LeadFlow` (ver `flujo_de_leads.md`) que define sus estados posibles.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/workspace.py`, `campaign.py` | Modelos |
| `app/controllers/workspace_controller.py`, `campaign_controller.py` | Endpoints `/workspaces`, `/campaigns` (genéricos) |
| `app/services/workspace_service.py`, `campaign_service.py` | Reglas de negocio propias de creación/actualización |

---

## 2. Modelo de datos

```
Organization ──< Workspace >── Campaign ──> LeadFlow
                     │              │
                     │              └──< Lead
                     │              └──< LeadField
                     ├──< TeamWorkspaceAccess >── Team
                     └── Campaign ──< TeamCampaignAccess >── Team
```

- **`Workspace`**: `name`, `description`, `is_public` (default `True`), `organization_id`. `campaigns` con `passive_deletes="all"` (el borrado en cascada lo maneja la base, no el ORM en memoria).
- **`Campaign`**: `name`, `description`, `is_public` (default `True`), `workspace_id`, `organization_id`, `lead_flow_id` (obligatorio). Constraint de DB: `UniqueConstraint('name', 'workspace_id')` — nombre único por workspace (a nivel de tabla completa, activas e inactivas; el service replica esta validación distinguiendo el mensaje según si el conflicto es con una campaña activa o desactivada, ver §5).
- `Campaign.team_access` / `Workspace.team_access` → `TeamCampaignAccess`/`TeamWorkspaceAccess`, documentado desde el ángulo de equipos en `equipos_y_enrutamiento.md` §5.

`delete_strategy`: `Campaign` → `SOFT_DELETE_HARD_OPT`; `Workspace` → `SMART_DELETE` (hard delete solo si no tiene campañas asociadas, ver `convenciones_generales.md` §5 y §9).

---

## 3. Endpoints

Ambos controllers son genéricos (`BaseController`, `enabled_methods = READ_WRITE | {"DEACTIVATE"}`, ver `convenciones_generales.md` §3) sin rutas propias. Filtros habilitados en `GET /`:

- `/campaigns`: `workspace_id`, `name`, `is_public`, `lead_flow_id`.
- `/workspaces`: `name`, `description`, `is_public`.

Toda la lógica particular de estos módulos vive en `create`/`update` de los services, no en rutas nuevas.

---

## 4. Creación de un Workspace

`WorkspaceService.create` solo agrega una validación sobre el genérico de `BaseService`: nombre único entre workspaces **activos** (a diferencia de `Campaign`, acá no se distingue el mensaje de error si el nombre está tomado por uno desactivado — simplemente rechaza).

---

## 5. Creación de una Campaign: resolución de flujo y campos por defecto

`CampaignService.create` hace bastante más que un insert:

1. Valida que el `workspace_id` exista.
2. Valida nombre único dentro del workspace (activas e inactivas — si el conflicto es con una campaña desactivada, el mensaje de error sugiere reactivarla en vez de simplemente rechazar).
3. **Resolución de `lead_flow_id`**: si no se envía, busca el flujo **más antiguo** (`created_at asc`) de la organización y lo usa como default — asume que toda organización tiene al menos un `LeadFlow` (lo crea `OrganizationService.create`, ver `autenticacion.md` §10). Si se envía explícito, valida que exista y pertenezca a la misma organización que el workspace.
4. **Campos por defecto según `target_audience`** (`_create_default_fields`): es un parámetro del request (`"B2B"` o `"B2C"`, no se persiste como columna) que precarga un set de `LeadField` típico:
   - `B2B`: Nombre, Razón Social, Teléfono, Email, Sitio Web.
   - `B2C`: Nombre Completo, Email, Celular, Fecha de Nacimiento.
   
   Se crean llamando directamente a `LeadFieldService.create_within_session` (mismo pipeline de validación que crear un campo a mano, ver `campos_personalizados.md` §5) — si no se manda `target_audience`, la campaña queda sin campos precargados y hay que crearlos uno por uno después.

---

## 6. Actualización de una Campaign: permisos y bloqueo de `lead_flow_id`

- **Permiso adicional además del RBAC estándar**: solo puede editar una campaña su creador (`created_by`), el `owner` de la organización, o un superadmin — aunque el usuario tenga el permiso genérico `campaign:update` vía rol. Es una capa de autorización extra, específica de este servicio, no cubierta por `PermissionChecker`.
- **`lead_flow_id` es inmutable una vez que la campaña tiene leads**: si se intenta cambiar y `Lead.count(campaign_id=...) > 0`, se rechaza con el mensaje "cree una nueva campaña" — no hay soporte para migrar leads existentes a un flujo distinto.
- Si la campaña todavía no tiene leads, sí se puede cambiar el flujo, validando que el nuevo pertenezca a la misma organización.

---

## 7. `is_public`: el interruptor que anula equipos y enrutamiento

Documentado en detalle desde el lado de `Team` en `equipos_y_enrutamiento.md` §5, pero es central para este módulo: tanto `Campaign.is_public` como `Workspace.is_public` tienen **default `True`**. Mientras una campaña sea pública, cualquier usuario de la organización ve todos sus leads sin importar accesos de equipo (`TeamCampaignAccess`) ni políticas de enrutamiento. Para que la segmentación por equipos tenga efecto real, hay que crear la campaña explícitamente con `is_public=False`.

---

## 8. Borrado

- `Campaign`: `SOFT_DELETE_HARD_OPT` — `DELETE /campaigns/{id}` desactiva por default; `?force=true` intenta hard delete con cascada de sus relaciones (leads, campos, etc. — operación destructiva de todo lo cargado en la campaña).
- `Workspace`: `SMART_DELETE` — hard delete automático solo si no tiene ninguna `Campaign` asociada (activa o no, según cómo esté declarado `delete_blockers` en el repositorio); si tiene, cae a soft delete aunque se pida `force=true`.

---

## 9. Cómo se testea

- `tests/functional/test_campaign.py`: creación (éxito, inyección de campos B2B/5 campos y B2C/4 campos, `target_audience` desconocido no inyecta nada, workspace inválido, resolución de flujo por default, flujo de otra organización rechazado, nombre duplicado en mismo/distinto workspace), actualización (por creador, por no-creador → `403`, por superuser sin importar creador, nombre duplicado, cambio de flujo con/sin leads existentes, flujo de otra organización, campaña inexistente → `404`), y filtros (`workspace_id`, `is_public`, filtro no permitido se ignora sin error).
- `tests/functional/test_workspace_and_campaign.py`: CRUD básico de workspace, y el caso `SMART_DELETE` (`test_workspace_delete_when_exists_campaign` — confirma que no se puede hard-delete un workspace con campañas asociadas).
- `tests/functional/test_campaign_access.py`: accesos de equipo a campañas (complementa `equipos_y_enrutamiento.md`).
