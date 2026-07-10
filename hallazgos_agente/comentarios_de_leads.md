# Hallazgo #18 — Comentarios de leads: IDOR cross-tenant confirmado (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/comentarios_de_leads.md` §4
**Estado:** [RESUELTO] 2026-07-10 — confirmado con lectura de código y corregido (ver "Fix aplicado" al final). Mayor severidad encontrada en toda esta ronda de auditoría.

## Qué se encontró

`LeadComment` (`app/models/lead_comment.py`) **no tiene columna `organization_id`** — solo `lead_id` (FK a `Lead`). `LeadCommentController`/`Service`/`Repository` son 100% genéricos, sin ningún override.

Esto importa porque el mecanismo de aislamiento de tenant del sistema depende enteramente de que el modelo tenga `organization_id`:

- `BaseRepository._apply_tenant_filter` (usado en `get_all`/`get_by_id`/`update`/`delete`/`deactivate`): `if hasattr(cls.model, "organization_id"): ...` — para `LeadComment`, este `hasattr` es `False`, así que el método **no aplica ningún filtro**, la query queda intacta.
- `BaseRepository.apply_security_filter` (el hook fino, usado en `get_all`/`get_by_id`): por default es un no-op (`return query`) salvo que el repositorio lo sobreescriba — `LeadCommentRepository` no lo hace (a diferencia de `OrganizationRepository`, que sí lo sobreescribe para su propio caso especial, ver hallazgo #15).
- `BaseRepository.create` (usado en `POST`): solo inyecta `organization_id` si `hasattr(cls.model, "organization_id")` es `True` — para `LeadComment` tampoco hace nada. No hay ninguna validación de que el `lead_id` recibido pertenezca a la organización del que llama.

**Resultado confirmado:** cualquier usuario autenticado con el permiso genérico `lead_comment:create`/`lead_comment:view`/`lead_comment:update`/`lead_comment:delete` (que el rol `agent` tiene por default en **cualquier** organización, según `docs/autenticacion.md` §7: "agent: operación diaria (leads, comentarios, ...)") puede:

1. **Leer** comentarios de un lead de **cualquier otra organización** — `GET /lead_comments/?lead_id=<id_de_lead_ajeno>` no filtra por organización en ningún punto.
2. **Crear** un comentario en un lead de **cualquier otra organización** — `POST /lead_comments/` con un `lead_id` ajeno no lo rechaza en ningún punto (a diferencia de `LeadService.create`, que sí valida `team_id`/`assigned_to_user_id`/tags contra la organización — ver `hallazgos_agente/lead.md`).
3. **Editar/borrar** cualquier comentario existente por su `id`, sin importar de qué organización sea — `GET /lead_comments/{id}`, `PUT /lead_comments/{id}`, `DELETE /lead_comments/{id}` tampoco filtran por organización.

Los `lead_id` son enteros autoincrementales — fácilmente enumerables/adivinables (no son UUIDs como en `WebForm`), lo que hace este IDOR trivialmente explotable con solo tener una cuenta válida en el sistema (cualquier organización, cualquier rol con permisos por default de `agent`).

## Por qué es más grave que los otros hallazgos de esta ronda

A diferencia del hallazgo #15 (Organizaciones, requiere pertenecer a 2+ orgs) o el #16 (rutas de enrutamiento, requiere pertenecer a la misma org), este no requiere ninguna relación previa con la organización víctima — solo tener **cualquier** cuenta en el sistema con el permiso default de `agent`, que se autoasigna a cualquiera que cree su propia organización (`OrganizationService.create` corona al creador como `admin`, que tiene *todos* los permisos, incluyendo los de `agent`).

## Solución recomendada

Agregar el mismo patrón que ya usa `LeadService.create`/`update` para otras FKs: en `LeadCommentService`, sobreescribir `create`, `update`, `delete` (y opcionalmente `get_all`/`get_by_id` si se quiere reforzar también la lectura) para validar explícitamente que el `Lead` referenciado por `lead_id` pertenece a `user_context.organization_id` antes de operar — con un `404`/`400` genérico si no, igual que hace `_validate_processed_data` para el campo tipo `LEAD` ("no revelamos si el lead existe en otro tenant"). Alternativa más robusta a largo plazo: agregar una columna `organization_id` real a `LeadComment` (se puede derivar de `Lead.organization_id` al crear) para que el mecanismo genérico de `_apply_tenant_filter`/`apply_security_filter` lo cubra automáticamente, igual que el resto de las entidades del sistema — evita tener que reimplementar el chequeo a mano y previene que el mismo patrón de bug reaparezca si se agrega una nueva entidad "colgada" de `Lead` sin pensar en esto.

Tests recomendados: usuario de la Org A crea un lead; usuario de la Org B (cuenta distinta, cualquier rol) intenta `GET`/`POST`/`PUT`/`DELETE /lead_comments` usando el `lead_id` del lead de la Org A → debe dar `403`/`404`, no `200`.

## Nota para revisar en otros módulos

Este mismo patrón de bug (modelo "colgado" de `Lead`/otra entidad tenant-scoped, sin su propia columna `organization_id`, sin override de servicio que valide la FK) podría repetirse en otras entidades similares del sistema. Al revisar los módulos pendientes, vale la pena revisar puntualmente: ¿el modelo tiene `organization_id` propio? Si no, ¿el service valida a mano que las FKs que recibe pertenecen a la organización activa? Si ninguna de las dos cosas es cierta, es el mismo bug. (Confirmado: el mismo patrón exacto apareció en #20 `FieldAutomation`, #21 `LeadStateTransition`, #26 `LeadActivityHistory`/`LeadStateHistory` — ver esos hallazgos.)

## Fix aplicado (2026-07-10)

No se agregó columna `organization_id` real (el proyecto no tiene Alembic; un cambio de schema requeriría recrear la base de forma destructiva) — se optó por la solución de menor riesgo, consistente con el patrón "template method" que ya usa `OrganizationRepository`:

1. **`app/db/repository/lead_comment_repository.py`**: se agregó `apply_security_filter` — hace `join` contra `Lead` y filtra por `Lead.organization_id == user_context.organization_id` (bypass para superusuario). Esto protege automáticamente `GET_ALL`/`GET_ONE`, y por el patrón de dos capas de `BaseService` (`update`/`delete` llaman primero a `get_by_id` como gatekeeper, ver `AGENTS.md` §2), también protege `PUT`/`DELETE`.
2. **`app/services/lead_comment_service.py`**: se sobreescribió `create` para validar explícitamente que `obj_data.lead_id` pertenece a `user_context.organization_id` (query directa a `Lead` filtrada por `id` + `organization_id`) antes de crear el comentario — devuelve `400` si no. Esto era necesario porque `create` no tiene una fila previa sobre la que aplicar el gatekeeper de `apply_security_filter`.

**Test de regresión:** `tests/functional/test_tenant_isolation.py::TestLeadCommentIsolation` — cubre creación bloqueada sobre lead ajeno (`test_create_comment_blocked_for_foreign_lead`), no-visibilidad de comentarios ajenos (`test_comment_not_visible_from_other_org`) y visibilidad normal dentro de la propia org (`test_comment_visible_from_own_org`).
