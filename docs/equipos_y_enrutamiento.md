# Equipos y Enrutamiento de Leads

Documentación técnica de dos módulos relacionados del CRM: gestión de equipos (`Team`) y el motor de enrutamiento automático de leads a equipos (`LeadRoutingPolicy` v3). Se documentan juntos porque el segundo depende directamente del primero (`target_team_id`, permisos de `MANAGER`). Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Equipos: endpoints y reglas de negocio](#3-equipos-endpoints-y-reglas-de-negocio)
4. [Miembros de equipo: roles y permisos](#4-miembros-de-equipo-roles-y-permisos)
5. [Accesos de equipo a Workspaces y Campañas](#5-accesos-de-equipo-a-workspaces-y-campañas)
6. [Políticas de enrutamiento (v3): modelo](#6-políticas-de-enrutamiento-v3-modelo)
7. [Endpoints de `/lead_routing_policies`](#7-endpoints-de-lead_routing_policies)
8. [Motor de evaluación (`RoutingRuleEvaluatorService`)](#8-motor-de-evaluación-routingruleevaluatorservice)
9. [Reasignación masiva de leads](#9-reasignación-masiva-de-leads)
10. [Multi-tenancy y estrategias de borrado](#10-multi-tenancy-y-estrategias-de-borrado)
11. [Decisiones y puntos pendientes](#11-decisiones-y-puntos-pendientes)
12. [Cómo se testea](#12-cómo-se-testea)
13. [Changelog](#13-changelog)

---

## 1. Visión general

Un **equipo** (`Team`) agrupa usuarios dentro de una organización. Cada miembro tiene un rol (`MANAGER` o `AGENT`) que determina qué puede hacer sobre el equipo y sus leads. Un equipo tiene acceso explícito a **workspaces** y **campañas** (sin acceso, no ve leads de esa campaña).

Una **política de enrutamiento** (`LeadRoutingPolicy`) es una regla "si se cumplen estas condiciones, asignar el lead al equipo X". El motor evalúa todas las políticas activas de la organización (ordenadas por prioridad) cada vez que se crea un lead, y asigna automáticamente el `team_id` — pisando lo que haya mandado el frontend.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/team.py`, `team_member.py`, `team_access.py` | Modelos `Team`, `TeamMember`, `TeamWorkspaceAccess`, `TeamCampaignAccess` |
| `app/services/team_service.py`, `team_member_service.py`, `team_access_service.py` | Reglas de negocio de equipos, miembros y accesos |
| `app/controllers/team_controller.py`, `team_member_controller.py`, `team_campaign_access_controller.py`, `team_workspace_access_controller.py` | Endpoints `/teams`, `/team_members`, `/team_campaign_access`, `/team_workspace_access` |
| `app/models/lead_routing_policy.py` | Modelos `LeadRoutingPolicy`, `LeadRoutingCondition` + catálogos de constantes (`NATIVE_FIELDS`, `OPERATOR_RULES`, etc.) |
| `app/schemas/lead_routing_policy_schema.py` | Schemas de request/response, validación de condiciones a nivel Pydantic |
| `app/services/lead_routing_policy_service.py` | CRUD de políticas + reglas de negocio (permisos, prioridad única) |
| `app/services/routing_rule_evaluator_service.py` | El motor: evalúa condiciones y decide el equipo destino |
| `app/controllers/lead_routing_policy_controller.py` | Endpoints `/lead_routing_policies/*` (controller manual, no usa `BaseController`) |
| `app/services/lead_service.py` (método `create`) | Punto donde se invoca el motor al crear un lead |

---

## 2. Modelo de datos

```
Organization ──< Team >── TeamMember >── User
                 │
                 ├──< TeamWorkspaceAccess >── Workspace
                 └──< TeamCampaignAccess  >── Campaign

Organization ──< LeadRoutingPolicy >── Team (target_team_id)
                        │
                        └──< LeadRoutingCondition
                               (lead_field_id  →  LeadField)
                               (native_field   →  atributo nativo del Lead)
```

- **`Team`**: `name`, `organization_id`, `is_visibility_shared` (si es `True`, todos los miembros ven los leads de todo el equipo; si es `False`, cada agente solo ve los suyos asignados + los sin asignar).
- **`TeamMember`**: une `Team` a `User` con un `role` (`MANAGER` o `AGENT`, `pattern="^(MANAGER|AGENT)$"` en el schema). No tiene restricción de unicidad a nivel de columna, pero el servicio rechaza duplicados (ver [§4](#4-miembros-de-equipo-roles-y-permisos)).
- **`TeamWorkspaceAccess`** / **`TeamCampaignAccess`**: tablas puente simples (`team_id` + `workspace_id`/`campaign_id`), sin campos propios. Determinan qué campañas/workspaces puede operar un equipo.
- **`LeadRoutingPolicy`**: `organization_id`, `campaign_id` (nullable — `NULL` = política global, aplica a cualquier campaña de la org), `name`, `description`, `priority` (entero, **menor número = mayor prioridad**), `logical_operator` (`AND`/`OR`, aplica a todas sus condiciones), `target_team_id`. Constraint de DB: `UniqueConstraint("organization_id", "campaign_id", "priority")` — no puede haber dos políticas con la misma prioridad en el mismo scope (org + campaña, o org + global).
- **`LeadRoutingCondition`**: condición atómica de una política. Dos ejes ortogonales, ambos mutuamente excluyentes:
  - **Campo**: `lead_field_id` (campo dinámico de la campaña) *o* `native_field` (atributo nativo del `Lead`: `assigned_to_user_id`, `team_id`, `created_at`, `updated_at`, `campaign_id`, `current_state_id`).
  - **Modo**: valor simple (`operator` + `value_str`), lista (`operator` en `in`/`not_in`/`eq_strict` + `value_list`), o rango (`operator_min`/`operator_max` + `value_min`/`value_max`).

---

## 3. Equipos: endpoints y reglas de negocio

`TeamController` usa `BaseController` (no es un controller manual) con `enabled_methods = READ_WRITE | {"DEACTIVATE"}`, es decir:

| Método y ruta | Qué hace |
|---|---|
| `GET /teams/` | Lista paginada (`only_active`, `search`, filtros por `name`/`is_visibility_shared`) |
| `GET /teams/{id}` | Detalle (`detailed=true` incluye `members: List[TeamMemberResponse]`) |
| `POST /teams/` | Crea el equipo **y agrega automáticamente al creador como `MANAGER`** |
| `PUT /teams/{id}` | Actualiza `name` / `is_visibility_shared` |
| `DELETE /teams/{id}` | Borrado según `delete_strategy` (ver [§10](#10-multi-tenancy-y-estrategias-de-borrado)) |
| `PUT /teams/active/{id}` | Reactiva (`ACTIVE` en `enabled_methods`) |
| `DELETE /teams/active/{id}` | Desactiva sin borrar (`DEACTIVATE`) |

Reglas de `TeamService.create` (`app/services/team_service.py`):

- **Nombre único por organización** entre equipos activos (`name` + `organization_id`, filtrando `active=True`) — un nombre puede reutilizarse si el equipo anterior con ese nombre fue desactivado, o en otra organización.
- El usuario que crea el equipo queda agregado como `TeamMember` con `role="MANAGER"` en la misma transacción, no hay que agregarlo a mano después.

---

## 4. Miembros de equipo: roles y permisos

`TeamMemberController` usa `BaseController` con `enabled_methods = READ_WRITE` (sin `ACTIVE`/`DEACTIVATE`: la membresía no se desactiva, se borra — `TeamMemberRepository.delete_strategy = HARD_DELETE_ALWAYS`).

Las reglas de autorización viven en `TeamMemberService` (`_caller_role` calcula el rol del que hace la request dentro de ese equipo específico: `"MANAGER"`, `"AGENT"` o `"NONE"` si no pertenece; superadmin y `owner` de la org siempre cuentan como `"MANAGER"`):

| Acción | Quién puede |
|---|---|
| Agregar miembro (`POST /team_members/`) | Un `MANAGER` del equipo. Un `AGENT` no puede agregar a nadie. |
| Agregar como `MANAGER` | Solo otro `MANAGER` puede promover a alguien más a `MANAGER` al agregarlo. |
| Auto-promoverse a `MANAGER` | Prohibido para un `AGENT` (no puede asignarse `role="MANAGER"` a sí mismo). |
| Modificar rol (`PUT /team_members/{id}`) | Solo un `MANAGER` del equipo. Misma restricción de auto-promoción. |
| Eliminar miembro (`DELETE /team_members/{id}`) | Solo un `MANAGER` del equipo. |

Validaciones adicionales al crear: el `team_id` debe existir y pertenecer a la organización activa (`TENANT_ORG_ID`), y el usuario no puede estar ya en ese equipo (no hay constraint de DB para esto, es solo una validación de servicio — ver [§11](#11-decisiones-y-puntos-pendientes)).

---

## 5. Accesos de equipo a Workspaces y Campañas

`TeamWorkspaceAccessController` y `TeamCampaignAccessController` son más chicos: `enabled_methods = {"GET_ALL", "GET_ONE", "POST", "DELETE"}` — no se actualizan, solo se dan de alta o se quitan.

- `TeamWorkspaceAccessRepository.delete_strategy = HARD_DELETE_ALWAYS`.
- `TeamCampaignAccessRepository` no declara `delete_strategy` explícitamente → hereda el default de `BaseRepository`, que también es `HARD_DELETE_ALWAYS`.

Reglas de negocio (en los repositorios, no en el servicio — caso atípico frente al resto del código, ver [§11](#11-decisiones-y-puntos-pendientes)):

- Al crear, se valida que tanto el `team_id` como el `workspace_id`/`campaign_id` pertenezcan a la organización activa (`TENANT_ORG_ID`). **Ojo:** esta validación está detrás de un `if org_id:` — si `TENANT_ORG_ID` viniera vacío, la validación de organización se saltea silenciosamente (no rechaza la petición, solo no valida cross-org).
- No se puede dar acceso duplicado: si el equipo ya tiene acceso a ese workspace/campaña, `400`.

**Importante — `Campaign.is_public` pisa todo lo anterior.** Tanto `CampaignRepository.apply_security_filter` como `LeadRepository.apply_security_filter` (`app/db/repository/`) tratan `is_public == True` como un bypass incondicional: si la campaña es pública, **cualquier usuario ve todas sus campañas/leads**, sin importar `TeamCampaignAccess`, `TeamWorkspaceAccess` ni `is_visibility_shared`. `Campaign.is_public` tiene `default=True` a nivel de modelo — si no se especifica explícitamente al crear la campaña, queda pública y todo el armado de equipos/accesos de esta sección no tiene ningún efecto observable. Para que el acceso por equipo (y el enrutamiento) importen de verdad, la campaña tiene que crearse con `is_public=False`.

---

## 6. Políticas de enrutamiento (v3): modelo

La v3 es deliberadamente plana: **una lista de condiciones + un único operador lógico (`AND`/`OR`) para toda la política.** No hay árbol de grupos anidados (eso existía en una v2 anterior, ya removida — no queda ningún endpoint ni tabla `lead_routing_rule`).

Cada condición (`LeadRoutingConditionCreate`, con validación `@model_validator` en el schema) debe tener:

1. **Exactamente un campo**: `lead_field_id` (campo dinámico) *o* `native_field` (nativo, debe estar en `NATIVE_FIELDS`).
2. **Exactamente un modo**:
   - **Simple**: `operator` + `value_str`.
   - **Lista**: `operator` en `{"in", "not_in", "eq_strict"}` (`LIST_OPERATORS`) + `value_list`.
   - **Rango**: `operator_min` (debe ser `gt`/`gte`) + `value_min`, `operator_max` (`lt`/`lte`) + `value_max`. Los campos nativos de tipo ID (`assigned_to_user_id`, `team_id`, `campaign_id`, `current_state_id`) **no soportan rango**, solo `created_at`/`updated_at`.

Operadores válidos por tipo de campo dinámico (`OPERATOR_RULES` en `app/models/lead_routing_policy.py`):

| Tipo de campo | Operadores permitidos |
|---|---|
| `STRING` | `eq`, `neq`, `like`, `ilike` |
| `INT` / `NUMBER` / `DATE` / `DATE_TIME` | `eq`, `neq`, `gt`, `lt`, `gte`, `lte` |
| `BOOL` | `eq`, `neq` |
| `SELECTOR` | `eq`, `eq_strict`, `neq`, `in`, `not_in` |
| `CALCULATED` | `eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `like`, `ilike` |
| Nativo fecha (`created_at`/`updated_at`) | `eq`, `neq`, `gt`, `lt`, `gte`, `lte` |
| Nativo ID (`assigned_to_user_id`, `team_id`, `campaign_id`, `current_state_id`) | `eq`, `neq` |

Tipos de campo **prohibidos** en condiciones de enrutamiento (`ROUTING_FORBIDDEN_FIELD_TYPES`): `FILE`, `URL`, `ADDRESS`, `RICH_TEXT`, `TAGS`, `PASSWORD`.

Para campos `SELECTOR`/`CHECKBOX` con nomenclador, `value_str`/`value_list` deben ser **IDs de `NomenclatorItem`** (no el texto/label) — se valida contra la DB en `_validate_condition_data`.

---

## 7. Endpoints de `/lead_routing_policies`

Este controller **no** usa `BaseController` (a diferencia de teams): está escrito a mano en `lead_routing_policy_controller.py` porque necesita dos rutas extra (`/active/{id}` con `PUT` y `DELETE`) que no encajaban directamente en el patrón genérico cuando se escribió.

| Método y ruta | Qué hace |
|---|---|
| `GET /lead_routing_policies/` | Lista paginada. Filtro propio `campaign_id` (no hay filtro por `target_team_id` a nivel API — el frontend lo resuelve trayendo todo y filtrando client-side). |
| `GET /lead_routing_policies/{id}` | Detalle (`detailed=true` por default, incluye `conditions`). |
| `POST /lead_routing_policies/` | Crea la política **con sus condiciones** en una sola transacción. |
| `PUT /lead_routing_policies/{id}` | Actualiza. Si se manda `conditions`, **reemplaza todas** las anteriores (no hace merge). |
| `DELETE /lead_routing_policies/{id}` | **Borrado físico e irreversible** (`delete_strategy = HARD_DELETE_WITH_TOGGLE`). No es un "deshabilitar". |
| `PUT /lead_routing_policies/active/{id}` | Reactiva (`active=True`) una política deshabilitada. |
| `DELETE /lead_routing_policies/active/{id}` | Deshabilita (`active=False`) **sin borrar**. Esta es la operación equivalente a "pausar la regla". |
| `POST /lead_routing_policies/validate` | Valida una lista de condiciones **sin persistir nada** — pensado para que el frontend valide mientras arma el formulario. |

Reglas de negocio en `LeadRoutingPolicyService`:

- **Permisos**: solo un `MANAGER` del `target_team_id` (o superadmin/owner) puede crear/actualizar una política que apunte a ese equipo (`_assert_manager`). **[PENDIENTE, hallazgo #16]** Esta regla **no** se aplica a `DELETE /{id}`, `PUT /active/{id}` ni `DELETE /active/{id}` — esos tres solo verifican que la política pertenezca a la organización activa, no que quien llama sea `MANAGER` del equipo destino. Cualquier miembro autenticado de la organización puede hoy borrar/desactivar/reactivar cualquier política. Detalle y solución recomendada en `hallazgos_agente/equipos_y_enrutamiento.md`.
- **Prioridad única por scope**: no puede existir otra política con la misma `priority` dentro del mismo `(organization_id, campaign_id)` — se valida en el servicio (`_validate_priority`) *además* del constraint de DB, por partida doble.
- **Condiciones se validan en el servicio** contra la organización activa antes de guardarlas (`RoutingRuleEvaluatorService.validate_conditions`), no solo a nivel de forma (Pydantic).

---

## 8. Motor de evaluación (`RoutingRuleEvaluatorService`)

**Cuándo corre:** automáticamente en `LeadService.create` (`app/services/lead_service.py`), después de resolver la campaña y el estado inicial, y **antes** de persistir el lead. El resultado tiene prioridad sobre lo que haya mandado el frontend:

```python
lead_data = {
    ...
    'team_id': assigned_team_id if assigned_team_id is not None else obj_in.team_id,
    ...
}
```

Es decir: si ninguna política matchea, se usa el `team_id` que mandó el frontend (o ninguno). Si alguna política matchea, **gana el motor**, incluso si el frontend mandó otro equipo.

**Cómo elige la política (`RoutingRuleEvaluatorService.evaluate`):**

1. Trae todas las políticas **activas** de la organización donde `campaign_id IS NULL` (global) **o** `campaign_id = <campaña del lead>`.
2. Las ordena por `priority` ascendente (**1 gana sobre 2**).
3. Evalúa una por una, en ese orden, y devuelve el `target_team_id` de la **primera** que matchee. Si ninguna matchea, devuelve `None`.
4. Una política sin condiciones **nunca matchea** (se considera "inactiva de hecho", aunque `active=True`).

**Cómo se evalúa una condición individual** (`_evaluate_condition`):

- El valor del lead se busca en un diccionario de contexto: `context_data[lead_field_id]` para campos dinámicos, o `context_data["__native__<campo>"]` para nativos. Si el valor es `None`/no está presente, la condición es `False` (no se puede evaluar "campo vacío coincide con X").
- El casteo (`_cast`) convierte el string crudo al tipo Python correcto según `field_type_code` (`INT`→`int`, `NUMBER`/`MONEY`→`float`, `BOOL`→booleano laxo `"true"/"1"/"yes"/"si"`, `DATE`/`DATE_TIME`→`date`/`datetime`). Si el casteo falla, hace fallback a comparación de strings en vez de romper.
- **Modo lista con `SELECTOR`/`CHECKBOX`**: el lead puede tener una lista de IDs (multi-selección) — `in` matchea si *al menos uno* de los IDs de la regla está en la lista del lead; `eq_strict` exige que sea *exactamente* el mismo conjunto.
- Cualquier excepción evaluando una condición individual se traga y cuenta como `False` (no rompe la evaluación de toda la política).
- La política combina sus condiciones con `all(...)` (AND) o `any(...)` (OR) según `logical_operator`.

---

## 9. Reasignación masiva de leads

No es parte de este módulo en sí, pero está directamente acoplado a `Team`: `PATCH /leads/bulk-assign` (`app/controllers/lead_controller.py`, schema `BulkAssignRequest` en `team_member_schema.py`) reasigna una lista de `lead_ids` a un `target_team_id` y/o `target_user_id`. Exige al menos uno de los dos destinos (`400` si no se manda ninguno). No pasa por el motor de enrutamiento — es una reasignación manual y directa.

---

## 10. Multi-tenancy y estrategias de borrado

Igual que el resto del sistema (ver `docs/autenticacion.md` §8), ambos módulos dependen del header `X-Organization-Id` → `TENANT_ORG_ID` (contextvar). Resumen de `delete_strategy` por entidad:

| Entidad | `delete_strategy` | Efecto de `DELETE` |
|---|---|---|
| `Team` | `SOFT_DELETE_HARD_OPT` | Soft delete por default; `?force=true` para hard delete |
| `TeamMember` | `HARD_DELETE_ALWAYS` | Siempre borrado físico |
| `TeamWorkspaceAccess` / `TeamCampaignAccess` | `HARD_DELETE_ALWAYS` | Siempre borrado físico |
| `LeadRoutingPolicy` | `HARD_DELETE_WITH_TOGGLE` | `DELETE /{id}` es **siempre físico e irreversible**; el toggle vive en `DELETE`/`PUT /active/{id}`, no en el `DELETE` genérico |

`HARD_DELETE_WITH_TOGGLE` es el más propenso a confusión: a diferencia de `SOFT_DELETE_HARD_OPT` (donde el `DELETE` simple es "seguro" por default), acá el `DELETE /{id}` **nunca** es reversible — hay que usar la ruta `/active/{id}` para el equivalente a "pausar sin borrar". El frontend de políticas de enrutamiento originalmente confundía esto (ver [§13](#13-changelog)).

---

## 11. Decisiones y puntos pendientes

**Ya resuelto:**

- El endpoint `PUT /lead_routing_policies/active/{id}` no existía — solo estaba el `DELETE /active/{id}` (deshabilitar), no había forma de reactivar una política sin recrearla. Se agregó (ver [§13](#13-changelog)).
- `LeadRoutingPolicyService.create`/`update` podían fallar con `400 Falta el header X-Organization-Id` aun con el header presente, por leer `TENANT_ORG_ID.get()` (contextvar) en vez de `user_context.organization_id` (atributo ya resuelto, no depende de en qué thread corrió la dependencia). Se agregó fallback a `user_context.organization_id` en ambos métodos (ver [§13](#13-changelog)).
- `routing_condition_types` (diccionario en `app/core/dictionaries.py`, expuesto por `/metadata`) todavía reflejaba el modelo v2 (`NOMENCLATOR`/`CUSTOM_FIELD`). Se actualizó a `NATIVE`/`DYNAMIC`, acorde al modelo real (campo nativo vs. campo dinámico). No se encontró ningún consumidor real de este diccionario en el frontend actual — quedó actualizado por prolijidad y para uso futuro.
- `scripts/seed_data_v1.py` creaba las 3 políticas de ejemplo de la organización Salud **después** de generar los 67 leads de sus 2 campañas — como el motor solo enruta en el momento de crear el lead, ningún lead quedaba con `team_id` asignado. Se movió la creación de cada política a **antes** del loop de leads de la campaña que le corresponde (ver [§13](#13-changelog)).
- Las campañas de la organización Salud (`camp_pacientes`, `camp_estetica`) se creaban sin especificar `is_public`, quedando públicas por default — lo que anulaba el sentido del enrutamiento y los accesos por equipo (ver nota en [§5](#5-accesos-de-equipo-a-workspaces-y-campañas)). Se marcaron ambas como `is_public=False` en el seed.

**Pendiente / a tener en cuenta:**

- El mismo patrón `TENANT_ORG_ID.get()` sin fallback a `user_context.organization_id` se repite en varios servicios más (`TeamService.create`, `TeamMemberService.create`, `TeamWorkspaceAccessRepository.create`, `TeamCampaignAccessRepository.create`, y de forma centralizada en `BaseRepository._apply_tenant_filter`). No se reprodujo el fallo ahí todavía, pero es el mismo riesgo latente — si vuelve a aparecer, el fix es el mismo que en `LeadRoutingPolicyService`.
- En `TeamWorkspaceAccessRepository.create` / `TeamCampaignAccessRepository.create`, la validación de que el equipo y el workspace/campaña pertenezcan a la misma organización está condicionada a `if org_id:` — si `TENANT_ORG_ID` viniera vacío por el punto anterior, esa validación se saltea en silencio en vez de fallar.
- No hay protección de unicidad a nivel de DB para "un usuario no puede estar dos veces en el mismo equipo" (`TeamMember`) — es solo una validación de aplicación en `TeamMemberService.create`.
- `POST /lead_routing_policies/` no valida (a nivel de API) que dos condiciones de la misma política no sean contradictorias o redundantes entre sí (ej. dos condiciones `eq` sobre el mismo campo con valores distintos en `AND`, que nunca puede ser verdadero) — es responsabilidad de quien arma la política.
- **[PENDIENTE, hallazgo #16]** `DELETE /lead_routing_policies/{id}`, `PUT /active/{id}` y `DELETE /active/{id}` no exigen ser `MANAGER` del equipo destino (a diferencia de create/update) — cualquier miembro de la organización puede borrar/pausar/reactivar cualquier política. Ver `hallazgos_agente/equipos_y_enrutamiento.md`.

---

## 12. Cómo se testea

- `tests/functional/test_teams_and_routing.py` cubre ambos módulos en un solo archivo (misma razón que este doc: están acoplados). Categorías cubiertas:
  - **Equipos**: creación (el creador queda como `MANAGER`), nombre único por organización (pero repetible entre organizaciones distintas), cascada de borrado sobre los miembros, permisos de `MANAGER` vs. `AGENT` (agregar, promover, auto-promoción, eliminar miembros), rechazo de miembros duplicados.
  - **Políticas de enrutamiento**: match simple, `ilike` sobre strings, rangos inclusivos/exclusivos, `SELECTOR` con `in`/`not_in`/`eq_strict`, `AND` (deben cumplirse todas) vs. `OR` (alcanza una), prioridad (gana la de menor número), unicidad de prioridad por scope, campos nativos (`current_state_id`, `assigned_to_user_id`), políticas globales (`campaign_id=None` aplican a cualquier campaña), políticas inactivas que no enrutan, permisos (`MANAGER` puede crear/gestionar, `AGENT` no, un `MANAGER` no puede crear políticas para un equipo ajeno).
  - **`/validate`**: rechaza tipos de campo prohibidos, detecta equipo de otra organización, detecta campo de otra campaña, caso válido devuelve `valid=true`.
  - **Accesos**: rechazo de workspace/campaña de otra organización.
  - **Reasignación masiva**: `PATCH /leads/bulk-assign`.
- Usa los mismos fixtures compartidos que el resto de la suite (`api`, `db_session`, `two_users`, `initial_structure` — ver `tests/fixtures/`), no fixtures propios del módulo.

---

## 13. Changelog

**2026-07-09 — Falta `PUT /lead_routing_policies/active/{id}` + confusión disable/delete en el frontend**
Solo existía `DELETE /active/{id}` para deshabilitar una política; no había forma de reactivarla sin recrearla desde cero. Se agregó `PUT /active/{id}` (`set_active`) al controller, espejando el patrón de `BaseController`. Además, el frontend de políticas de enrutamiento (recién construido) llamaba al `DELETE /{id}` genérico para lo que se presentaba como un botón de "deshabilitar" — pero como `delete_strategy = HARD_DELETE_WITH_TOGGLE`, esa ruta borra **para siempre**, no deshabilita. Se separaron en la UI dos acciones distintas: Deshabilitar/Habilitar (usando `/active/{id}`) y Eliminar definitivamente (usando el `DELETE /{id}` real, con confirmación más fuerte).

**2026-07-09 — Bug de precedencia de `TENANT_ORG_ID` en `create`/`update` de políticas**
`LeadRoutingPolicyService.create` y `.update` devolvían `400 Falta el header X-Organization-Id` de forma intermitente aun cuando el request sí incluía el header — reproducido corriendo `scripts/seed_data_v1.py` (3 de 3 llamadas a `POST /lead_routing_policies/` fallaron en la misma corrida, mientras que decenas de otras llamadas en el mismo request context, con el mismo header, funcionaron bien). La causa: ambos métodos leen `org_id = TENANT_ORG_ID.get()` (contextvar) dentro de una función anidada (`do_create`/`do_update`), en vez de usar `user_context.organization_id` (atributo ya resuelto por `get_current_user_roles`, sin depender de en qué thread corrió esa dependencia). El propio archivo ya tenía un fix idéntico aplicado solo en `validate()`, con el comentario `FIX DE PRECEDENCIA: ...está en otro thread` — quedó sin replicar en `create`/`update`. Se agregó el mismo fallback (`TENANT_ORG_ID.get() or user_context.organization_id`) en ambos métodos.

**2026-07-09 — Diccionario `routing_condition_types` desactualizado (v2 → v3)**
`app/core/dictionaries.py::LEAD_ROUTING_RULE_CONDITION_TYPES` todavía tenía los códigos `NOMENCLATOR`/`CUSTOM_FIELD` del modelo v2 (árbol de condiciones). Se actualizó a `NATIVE`/`DYNAMIC`, que es la distinción real del modelo v3 (`native_field` vs. `lead_field_id`).

**2026-07-09 — Frontend: gestión de equipos y políticas de enrutamiento**
Se construyó la UI completa de ambos módulos (antes solo existía el backend): ítem "Equipos" en el sidebar con dos tabs (Equipos / Políticas de Enrutamiento), CRUD de equipos con gestión de miembros y accesos a workspaces/campañas, y CRUD de políticas de enrutamiento con armador de condiciones (soporta los tres modos: simple, lista y rango, y campos nativos o dinámicos) accesible tanto desde el detalle de un equipo como desde un listado global filtrable por campaña.

**2026-07-10 — Bug de secuencia en `seed_data_v1.py`: políticas creadas después de los leads**
Tras una corrida completa del seed, ningún lead de la organización Salud tenía `team_id` ni `assigned_to_user_id` en la DB. Causa: el bloque que crea las 3 políticas de enrutamiento de ejemplo estaba al final de `build_org_salud()`, ejecutándose recién después de generar los 67 leads de ambas campañas — el motor de enrutamiento solo actúa en el momento de `POST /leads/`, así que con cero políticas activas en ese momento, ningún lead podía quedar enrutado. No tiene relación con el bug de `TENANT_ORG_ID` corregido el día anterior. Se movió la creación de cada política a justo antes del loop de leads de la campaña correspondiente: las 2 políticas de "Cobertura Médica" después de crear los campos de `camp_pacientes`, y la política global de Estética después de crear `camp_estetica`.

**2026-07-10 — Seed: campañas privadas (`is_public=False`) y leads con agentes puntuales**
Se detectó que `camp_pacientes` y `camp_estetica` quedaban públicas por default (`is_public` nunca se pasaba al crearlas), lo que hacía irrelevante todo el armado de `TeamCampaignAccess`/`TeamWorkspaceAccess` y la visibilidad por equipo (ver nota en [§5](#5-accesos-de-equipo-a-workspaces-y-campañas)). Se agregó el parámetro `is_public` al helper `create_campaign()` del seed y se marcaron ambas campañas como privadas. Además, `create_lead()` ahora acepta `assigned_to_user_id`: en cada campaña, ~40% de los leads generados quedan asignados a un agente puntual del equipo correspondiente (Admisión: Rodrigo/Julieta/Nicolás; Equipo Médico: Agustina/Franco) y el resto queda sin asignar, para poder probar ambos casos de visibilidad (lead tomado vs. lead libre del equipo).
