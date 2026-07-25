# Convenciones Generales del Backend

Documento transversal (no es un módulo de negocio en sí) que describe el patrón común sobre el que están construidos casi todos los módulos del CRM: `BaseModelDB`, `BaseRepository`, `BaseService` y `BaseController`. Se armó a partir de la ronda de documentación de todos los módulos (2026-07-10) porque el mismo patrón se repetía en cada uno; en vez de explicarlo 20 veces, cada doc de módulo referencia este archivo y solo describe sus particularidades. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [`BaseModelDB`: columnas comunes](#2-basemodeldb-columnas-comunes)
3. [`BaseController`: endpoints genéricos](#3-basecontroller-endpoints-genéricos)
4. [`BaseService`: CRUD + auditoría automática](#4-baseservice-crud--auditoría-automática)
5. [`BaseRepository`: estrategias de borrado (`delete_strategy`)](#5-baserepository-estrategias-de-borrado-delete_strategy)
6. [Multi-tenancy en repositorios](#6-multi-tenancy-en-repositorios)
7. [Permisos automáticos por entidad](#7-permisos-automáticos-por-entidad)
8. [Paginación y filtros](#8-paginación-y-filtros)
9. [Mapa de `delete_strategy` por entidad](#9-mapa-de-delete_strategy-por-entidad)

---

## 1. Visión general

La gran mayoría de los módulos del CRM (Lead, Campaign, Tag, Nomenclator, Team, etc.) no reimplementan CRUD desde cero: heredan de cuatro clases base que ya resuelven paginación, filtros, multi-tenancy, permisos y auditoría. Un módulo "simple" (por ejemplo Tags) puede consistir en apenas 3 archivos de ~15 líneas cada uno (modelo, controller, service) porque todo lo demás lo hereda.

Capas, de arriba hacia abajo:

```
Controller (FastAPI router, HTTP)
    │  usa
Service (reglas de negocio, auditoría, UnitOfWork)
    │  usa
Repository (queries SQLAlchemy, tenant filter, delete_strategy)
    │  opera sobre
Model (tabla, columnas comunes de BaseModelDB)
```

Cuando un módulo necesita algo que no encaja en el patrón genérico (ej. `LeadController`, `LeadRoutingPolicyController`), el controller se escribe a mano en vez de heredar `BaseController.get_router()` directamente — eso se nota en cada doc de módulo.

---

## 2. `BaseModelDB`: columnas comunes

`app/models/base_model.py`. Toda entidad que hereda de `BaseModelDB` (la inmensa mayoría) tiene automáticamente:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `Integer`, PK | |
| `created_at` | `DateTime(timezone=True)` | `server_default=func.now()` |
| `updated_at` | `DateTime(timezone=True)` | Se actualiza solo (`onupdate=func.now()`) |
| `active` | `Boolean` | `default=True`. Es la columna que usan los soft deletes. |
| `created_by` / `updated_by` | `Integer`, FK a `user.id` | Nullable. Relaciones `creator`/`updater` (`viewonly=True`) |

El nombre de tabla es automático: `__tablename__` = nombre de la clase en minúsculas (ej. `Lead` → `lead`).

Los modelos de auditoría (`LeadActivityHistory`, `LeadStateHistory`, `SystemAuditLog`) también heredan esto, aunque conceptualmente son inmutables (ver `auditoria.md`).

---

## 3. `BaseController`: endpoints genéricos

`app/controllers/base_controller.py`. Un controller que hereda `BaseController` declara: `router_prefix`, `service`, `schema_in`, `schema_update`, `schema_out`, `schema_out_detail`, y opcionalmente `enabled_methods` (default: `{"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE", "PATCH"}`) y `allowed_filter_fields`.

Según qué esté en `enabled_methods`, `get_router()` registra:

| Método/ruta | Flag en `enabled_methods` | Qué hace |
|---|---|---|
| `GET /` | `GET_ALL` | Paginado, con `search`, `search_fields`, `order_by`/`ascending`, rango de fechas (`start_date`/`end_date`/`date_field`), filtros por `creator_name`/`creator_email`/`updater_name`/`updater_email` (cada uno exige match exacto de ESE campo, y si se combinan varios se aplican con AND), filtros combinados `creator_search`/`updater_search` (uno solo, hace OR entre nombre, apellido, email y "nombre apellido" del creador/actualizador — pensado para búsquedas de usuario en pantallas de auditoría), y **cualquier query param extra se trata como filtro de columna** (`?campaign_id=5`), salvo que `allowed_filter_fields` lo restrinja. |
| `GET /{obj_id}` | `GET_ONE` | `detailed=true` trae la versión "detallada" (`schema_out_detail`) si existe. |
| `POST /` | `POST` | Crea, valida contra `schema_in`. |
| `PUT /{obj_id}` | `PUT` | Actualiza, valida contra `schema_update`. |
| `DELETE /{obj_id}` | `DELETE` | Borra según `delete_strategy` del repositorio (ver §5). Acepta `?force=true`. |
| `POST /bulk-delete` | `DELETE` | Borra una lista de `ids` en batch. |
| `PUT /active/{obj_id}` | `ACTIVE` | Reactiva (`active=True`). |
| `POST /bulk-active` | `ACTIVE` | Reactiva en batch. |
| `DELETE /active/{obj_id}` | `DEACTIVATE` | Desactiva (`active=False`) **sin** pasar por `delete_strategy` — siempre disponible como soft delete explícito, independiente de la estrategia configurada. |

Cuando un módulo necesita rutas que no encajan acá (parseo híbrido JSON/multipart en `Lead`, `/active/{id}` con `PUT` en `LeadRoutingPolicy`, etc.), sobreescribe `get_router()` llamando a `super().get_router()` y agrega rutas extra a mano — el patrón que usan `LeadController` y `LeadRoutingPolicyController`.

---

## 4. `BaseService`: CRUD + auditoría automática

`app/services/base_service.py`. Cada método (`create`, `update`, `delete`, `deactivate`, `set_active`, `bulk_delete`, `bulk_set_active`, `get_all`, `get_by_id`) corre dentro de un `UnitOfWork` (transacción) vía `cls._execute(...)`, y **loguea automáticamente en `SystemAuditLog`** (`_log_audit`) en creación, actualización (solo si hubo diffs reales), borrado/desactivación y reactivación — ver `auditoria.md` para el modelo de `SystemAuditLog`. Los propios modelos de auditoría (`LeadActivityHistory`, `LeadStateHistory`, `SystemAuditLog`) están en una lista de exclusión (`ignored_models`) para no auditarse a sí mismos en bucle.

En `update`, el diff se calcula comparando `_normalize_data(old_obj)` vs. el payload nuevo, campo por campo — solo entra al log lo que efectivamente cambió.

Los módulos con lógica propia (Lead, LeadRoutingPolicy, Team, etc.) sobreescriben estos métodos o agregan otros nuevos, pero casi siempre siguen llamando a `cls._log_audit(...)` a mano en los puntos relevantes — es la convención para que cualquier cambio de negocio quede en la auditoría del sistema, no solo el CRUD genérico.

---

## 5. `BaseRepository`: estrategias de borrado (`delete_strategy`)

`app/db/repository/base_repository.py`. Cada repositorio declara `delete_strategy` (default `HARD_DELETE_ALWAYS` si no se especifica). Seis variantes (`app/core/constans.py::DeleteStrategy`):

| Estrategia | Comportamiento de `DELETE /{id}` |
|---|---|
| `HARD_DELETE_ALWAYS` | Borra físicamente siempre. Si hay una FK que lo referencia, `409`. |
| `SOFT_DELETE_ALWAYS` | Siempre `active=False`. No existe hard delete para esta entidad. |
| `SOFT_DELETE_HARD_OPT` | Soft delete por default; con `?force=true` hace hard delete (con cascade según las relaciones del modelo). |
| `PROTECTED` | Nunca se puede borrar, ni soft ni hard — pensado para audit trails. Cualquier intento tira error. |
| `SMART_DELETE` | Soft por default; con `?force=true` hace hard delete **solo si** no hay registros dependientes (`delete_blockers`); si hay, cae a soft delete igual. |
| `HARD_DELETE_WITH_TOGGLE` | `DELETE /{id}` es **siempre** hard delete e irreversible. El "pausar sin borrar" vive en la ruta separada `DELETE /active/{id}` (`deactivate`), no en el `DELETE` genérico. Es la estrategia más propensa a confusión en el frontend (ver el caso ya resuelto en `equipos_y_enrutamiento.md` §13 para `LeadRoutingPolicy`). |

`DELETE /active/{id}` (`deactivate`) es una ruta aparte que siempre hace soft delete explícito, sin importar la estrategia — está disponible mientras el modelo tenga columna `active`.

---

## 6. Multi-tenancy en repositorios

Complementa `autenticacion.md` §8 (header `X-Organization-Id` → `TENANT_ORG_ID`). A nivel de repositorio, `_apply_tenant_filter(query, is_read_operation)` distingue lectura de escritura:

- **Lectura** (`is_read_operation=True`, default en `get_all`/`get_by_id`): trae registros del tenant actual **o** de la organización admin (`ADMIN_ORG_ID`) — así los catálogos "globales" sembrados en la org admin (nomencladores base, roles plantilla) se ven desde cualquier organización.
- **Escritura** (`is_read_operation=False`, usado en `delete`/`deactivate`/`bulk_delete`/`bulk_set_active`): filtra **solo** el tenant actual, nunca toca registros de la org admin aunque el usuario los vea en lectura.

`apply_security_filter(session, query, user_context)` es un método "hook" que por default no hace nada (devuelve la query intacta) — los repositorios que necesitan reglas de visibilidad más finas que "misma organización" lo sobreescriben (ej. `CampaignRepository`/`LeadRepository` con el bypass de `is_public`, ver `equipos_y_enrutamiento.md` §5).

---

## 7. Permisos automáticos por entidad

`BaseController._get_deps(action)` arma el `codename` de permiso automáticamente si no está explícito en `required_permissions`: `f"{table_name}:{suffix}"`, donde `suffix` sale de `{"create": "create", "read": "view", "update": "update", "delete": "delete", "disable": "update", "active": "update"}`. Es decir, para el modelo `Tag` (tabla `tag`), el permiso de creación es `tag:create` sin que nadie lo declare a mano — coincide con `SYSTEM_ENTITIES_REGISTRY` que genera estos permisos automáticamente (`autenticacion.md` §7).

---

## 8. Paginación y filtros

`GET /` genérico soporta (ver `PaginatedResponse` en `app/schemas/pagination_schema.py`): `page`/`page_size`, `only_active` (default `true`), `detailed`, `search` + `search_fields` (búsqueda global sobre columnas), `order_by`/`ascending`, filtro por rango de fechas (`start_date`/`end_date`/`date_field`, default `created_at`), filtro por creador/actualizador (nombre o email), y filtros de columna dinámicos vía query params sueltos (`?campaign_id=5&name__ilike=juan`) — este último respeta `allowed_filter_fields` si el controller lo define, para no exponer filtros sobre columnas sensibles.

---

## 9. Mapa de `delete_strategy` por entidad

Referencia rápida (repositorios en `app/db/repository/`), completa a la fecha de esta revisión:

| Entidad | `delete_strategy` |
|---|---|
| `Lead` | `HARD_DELETE_ALWAYS` |
| `LeadComment` | `HARD_DELETE_ALWAYS` |
| `LeadField` | `SMART_DELETE` |
| `LeadFieldSection` | `SOFT_DELETE_ALWAYS` |
| `LeadFieldSubtype` | `PROTECTED` |
| `LeadFieldType` | `PROTECTED` |
| `LeadFieldValue` | `HARD_DELETE_ALWAYS` |
| `Campaign` | `SOFT_DELETE_HARD_OPT` |
| `Workspace` | `SMART_DELETE` |
| `FieldAutomation` | `HARD_DELETE_WITH_TOGGLE` |
| `LeadContactState` | `SOFT_DELETE_ALWAYS` |
| `LeadFlow` | `SOFT_DELETE_ALWAYS` |
| `LeadState` | `SOFT_DELETE_ALWAYS` |
| `LeadStateTransition` | `HARD_DELETE_ALWAYS` |
| `LeadView` | `HARD_DELETE_ALWAYS` |
| `Nomenclator` | `SOFT_DELETE_ALWAYS` |
| `NomenclatorItem` | `SOFT_DELETE_ALWAYS` |
| `Tag` | `HARD_DELETE_ALWAYS` |
| `ValidationRule` | `HARD_DELETE_ALWAYS` |
| `WebForm` | `SOFT_DELETE_HARD_OPT` |
| `WebFormField` | `HARD_DELETE_ALWAYS` |
| `User` | `SOFT_DELETE_HARD_OPT` |
| `Role` | `SOFT_DELETE_ALWAYS` |
| `Permission` | `PROTECTED` |
| `Organization` | `PROTECTED` |
| `Team` | `SOFT_DELETE_HARD_OPT` |
| `TeamMember` | `HARD_DELETE_ALWAYS` |
| `TeamWorkspaceAccess` / `TeamCampaignAccess` | `HARD_DELETE_ALWAYS` |
| `LeadRoutingPolicy` | `HARD_DELETE_WITH_TOGGLE` |
| `LeadActivityHistory` / `LeadStateHistory` / `SystemAuditLog` | `PROTECTED` |

Los docs de cada módulo repiten solo la fila que les corresponde, con el detalle de por qué se eligió esa estrategia si es relevante.
