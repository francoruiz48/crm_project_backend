# Estados de Contacto (`LeadContactState`)

Documentación técnica de los estados de contacto de un lead (ej. "Sin contactar", "Contactado", "No responde"). Es un concepto **distinto** del estado dentro del `LeadFlow` (ver `flujo_de_leads.md`): el estado de `LeadFlow` describe en qué etapa del embudo comercial está el lead (Nuevo, Calificado, Ganado...), mientras que `LeadContactState` describe el resultado del último intento de contacto, y es transversal a toda la organización (no depende de la campaña). Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Reglas de negocio](#4-reglas-de-negocio)
5. [RESUELTO: bug de `org_id` no definido en `update`](#5-resuelto-bug-de-org_id-no-definido-en-update)
6. [RESUELTO: `update` lee el objeto sin filtro de tenant](#6-resuelto-2026-07-11-update-lee-el-objeto-sin-filtro-de-tenant)
7. [RESUELTO: `lead_contact_state` no tenía permisos dados de alta](#7-resuelto-2026-07-11-lead_contact_state-no-tenía-permisos-dados-de-alta--solo-el-superadmin-podía-usarlo)
8. [Cómo se testea](#8-cómo-se-testea)

---

## 1. Visión general

`LeadContactState` pertenece directamente a una `Organization` (no a una campaña ni a un `LeadFlow`) — todas las campañas de una organización comparten el mismo catálogo de estados de contacto. Un lead recién creado recibe automáticamente el estado de contacto marcado como `is_initial=True` de su organización, si existe uno (ver `lead.md` §4, paso 4). `OrganizationService.create` siembra estados de contacto por defecto al crear una organización nueva (ver `autenticacion.md` §10).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead_contact_state.py` | Modelo |
| `app/controllers/lead_contact_state_controller.py` | Endpoints `/lead_contact_states/*` |
| `app/services/lead_contact_state_service.py` | Reglas de unicidad de nombre y de estado inicial |

---

## 2. Modelo de datos

```
Organization ──< LeadContactState ──< Lead (contact_state_id)
```

Campos propios: `name` (máx. 100 caracteres), `color` (opcional), `is_initial` (booleano, default `False`), `order` (entero, se auto-asigna al crear), `organization_id` (`ondelete="CASCADE"` — si se borra la organización, sus estados de contacto se van con ella a nivel de base).

`delete_strategy = SOFT_DELETE_ALWAYS` (ver `convenciones_generales.md` §9): nunca se puede hard-delete un estado de contacto, solo desactivarlo — tiene sentido porque leads históricos pueden seguir referenciando el estado por `contact_state_id`.

---

## 3. Endpoints

`LeadContactStateController` es genérico (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3), sin `ACTIVE`/`DEACTIVATE` explícitos en la lista pero heredados igual por el default de `BaseController.enabled_methods` si no se restringe — en la práctica, como es `READ_WRITE` puro (sin agregar `DEACTIVATE`), el soft delete se maneja únicamente vía `DELETE /{id}` (que ya es soft por `delete_strategy`), no hay ruta separada de desactivación explícita para este módulo. `allowed_filter_fields = {"name", "is_initial", "order"}`.

---

## 4. Reglas de negocio

`LeadContactStateService` agrega, sobre el CRUD genérico:

- **Nombre único por organización** (case-insensitive, `ilike`) — tanto en creación como en actualización.
- **Un único estado inicial por organización**: al crear o actualizar con `is_initial=True`, rechaza si ya existe otro estado marcado como inicial (pide desmarcarlo primero explícitamente, no lo reemplaza automáticamente).
- **No se puede desmarcar el único estado inicial**: si se intenta actualizar el estado que actualmente es `is_initial=True` a `is_initial=False`, se rechaza — siempre tiene que haber exactamente un estado inicial en la organización (o cero, si nunca se configuró ninguno).
- **`order` autoincremental**: se calcula solo en creación (`MAX(order) + 1` dentro de la organización), no es editable a través del payload de creación.

---

## 5. [RESUELTO] Bug de `org_id` no definido en `update`

**Bug (hasta 2026-07-10):** en `LeadContactStateService.update` (`app/services/lead_contact_state_service.py`), la variable `org_id` se calculaba **solo dentro** del bloque `if obj_in.name and obj_in.name.lower() != current_obj.name.lower():` (Regla 1), pero se **volvía a usar** más abajo, fuera de ese bloque, dentro de la Regla 2 (`LeadContactState.organization_id == org_id`).

Si un `PUT /lead_contact_states/{id}` cambiaba `is_initial` a `True` **sin** cambiar el `name` (el caso más común: "marcar este estado como inicial" desde la UI), la Regla 1 nunca se ejecutaba, `org_id` nunca quedaba definido, y la Regla 2 lanzaba `NameError: name 'org_id' is not defined` — un `500` en vez del `400` de validación esperado.

**Fix aplicado:** se movió el cálculo de `org_id` al principio de `do_update`, antes de la Regla 1, para que esté disponible sin importar qué combinación de campos venga en el `PUT` — mismo patrón de una línea que ya usa `create`.

---

## 6. [RESUELTO 2026-07-11] `update` lee el objeto sin filtro de tenant

`LeadContactStateService.update` resolvía el objeto a editar con `uow.session.query(LeadContactState).filter_by(id=obj_id).first()` — una consulta cruda, sin `_apply_tenant_filter` ni `apply_security_filter`, a diferencia del resto del sistema que resuelve el objeto vía el repositorio (tenant-aware). Si `obj_id` pertenecía a otra organización, `current_obj` igual se encontraba, y las reglas de negocio (unicidad de nombre, único estado inicial) corrían usando datos de ese objeto ajeno para decidir si aceptar o rechazar el cambio.

La persistencia real ya estaba protegida (`cls.repository.update(...)` aplica `_apply_tenant_filter` porque `LeadContactState` sí tiene `organization_id`), así que **no era un cross-tenant write completo** como los hallazgos #18/#20/#21 — el `UPDATE` en sí no llegaba a pisar la fila ajena. Pero como `repository.update` devuelve `None` cuando no encuentra la fila bajo el filtro de tenant, el código que seguía (`cls._log_audit(uow.session, updated_obj, ...)`) terminaba en un error no manejado en vez de devolver un `404` prolijo. Detalle en `hallazgos_agente/flujo_de_leads.md` (mismo criterio de revisión aplicado a `LeadStateTransition`, encontrado en simultáneo).

**Fix:** `current_obj` ahora se resuelve con `cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)` (tenant-aware) en vez de la query cruda — si no se encuentra, `404` inmediato con `cls._not_found(obj_id)`, antes de correr cualquier regla de negocio. Resuelto junto con los hallazgos #24 y #25 (mismo patrón mecánico en otros 4 puntos) — detalle completo en `hallazgos_agente/patron_queries_sin_tenant_filter.md`. Test de regresión: `tests/functional/test_tenant_isolation.py::TestLeadContactStateIsolation`.

---

## 7. [RESUELTO 2026-07-11] `lead_contact_state` no tenía permisos dados de alta — solo el superadmin podía usarlo

`SYSTEM_ENTITIES_REGISTRY` (`app/core/dictionaries.py`) es la única fuente desde la que se generan los permisos `<entidad>:<acción>` en la base. `"lead_contact_state"` **no estaba registrado ahí** — no existía ninguna fila `Permission` con codename `lead_contact_state:*`, en ninguna organización, ni siquiera en el rol `admin`. Consecuencia: **todos** los endpoints de `/lead_contact_states/*` (`GET`, `POST`, `PUT`, `DELETE`, activar/desactivar) eran, en la práctica, accesibles únicamente por el superadmin — ningún dueño ni admin de una organización podía gestionar sus propios estados de contacto vía API, a pesar de ser una entidad pensada como CRUD completo scoped a la organización.

Encontrado el 2026-07-11 al escribir un test de regresión para el hallazgo #22 con un usuario real de organización (no superadmin) — todos los tests anteriores de este módulo usaban el fixture superadmin, por eso no se había detectado.

**Fix:** se agregó `"lead_contact_state": {"model": "LeadContactState", "name": "Estado de Contacto", "crud_type": "FULL"}` a `SYSTEM_ENTITIES_REGISTRY`, lo que genera automáticamente `lead_contact_state:create/view/update/delete/view_all`. Niveles de permiso por rol (decisión del usuario): `admin` mantiene CRUD completo (automático — obtiene todos los permisos que existan); `agent` puede crear y editar pero no borrar (`AGENT_PERMS` suma `view`/`view_all`/`create`/`update`); `viewer` solo puede ver (`VIEWER_PERMS` suma `view`/`view_all`).

**Organizaciones ya existentes:** decisión explícita del usuario, sin script de migración — los roles clonados por organización (`_clone_default_roles_for_org`, ver `organizaciones.md` §4) son una plantilla de un momento dado, no una referencia viva a la plantilla global; es el diseño esperado. Si el dueño de una organización quiere permisos distintos, la vía es editar los roles de su propia organización directamente.

---

## 8. Cómo se testea

`tests/functional/test_lead_contact_states.py`: inyección de estados por defecto al crear una organización, creación exitosa, nombre duplicado (create y update), segundo estado inicial rechazado, y `test_lead_contact_state_prevent_uncheck_initial` (no se puede desmarcar el único inicial). Desde 2026-07-10 también incluye `test_lead_contact_state_set_initial_without_changing_name_returns_400`, regresión del bug de §5: hace un `PUT` con `is_initial=True` sin tocar `name` y verifica que devuelva `400` (antes rompía con `500`).

`tests/functional/test_tenant_isolation.py::TestLeadContactStateIsolation`: regresión del hallazgo #22 (tenant-filter en `update`), usando `as_user(ctx_alpha.owner)`/`as_user(ctx_beta.owner)` (usuarios reales de organización, no superadmin — posible desde que se resolvió el hallazgo #27).

`tests/functional/test_lead_contact_states.py`: `test_lead_contact_state_org_admin_can_manage`, `test_lead_contact_state_agent_can_create_and_update_but_not_delete`, `test_lead_contact_state_viewer_can_only_view` — regresión del hallazgo #27 (permisos por rol, §7).
