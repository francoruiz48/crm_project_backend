# Hallazgo #2 — Estados de contacto (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/estados_de_contacto.md` §5
**Estado:** RESUELTO (2026-07-10)

## Qué se encontró

En `LeadContactStateService.update` (`app/services/lead_contact_state_service.py`), la variable `org_id` se calculaba **solo dentro** del bloque `if obj_in.name and obj_in.name.lower() != current_obj.name.lower():` (Regla 1, unicidad de nombre), pero se reusaba más abajo, fuera de ese bloque, dentro de la Regla 2 (`LeadContactState.organization_id == org_id`, chequeo de estado inicial único).

Si un `PUT /lead_contact_states/{id}` cambiaba `is_initial` a `True` **sin** cambiar el `name` (el caso más común: "marcar este estado como inicial" desde la UI), la Regla 1 nunca se ejecutaba, `org_id` nunca quedaba definido, y la Regla 2 lanzaba `NameError: name 'org_id' is not defined` — un `500` en vez del `400` de validación esperado.

## Fix aplicado

Se movió el cálculo de `org_id` al principio de `do_update`, antes de la Regla 1, para que esté disponible sin importar qué combinación de campos venga en el `PUT` — mismo patrón de una línea que ya usa `create`.

## Tests

`tests/functional/test_lead_contact_states.py::test_lead_contact_state_set_initial_without_changing_name_returns_400`: hace un `PUT` con `is_initial=True` sin tocar `name` y verifica que devuelva `400` (antes rompía con `500`).

Confirmado por el usuario: suite completa OK.

---

# Hallazgo #22 — `update` lee el objeto sin filtro de tenant (ronda de bug-hunting, 2026-07-10)

**Doc de usuario:** `docs/estados_de_contacto.md` §6
**Estado:** [RESUELTO] 2026-07-11.

`LeadContactStateService.update` resuelve `current_obj` con `uow.session.query(LeadContactState).filter_by(id=obj_id).first()` — consulta cruda, sin pasar por el repositorio (que sí es tenant-aware). Si `obj_id` pertenece a otra organización, `current_obj` se encuentra igual, y las reglas de unicidad de nombre / único estado inicial corren usando ese objeto ajeno. La persistencia final (`cls.repository.update(...)`) sí filtra por tenant (`LeadContactState` tiene `organization_id`), así que el `UPDATE` real no llega a pisar la fila ajena — pero `repository.update` devuelve `None` en ese caso, y el código que sigue (`cls._log_audit(uow.session, updated_obj, ...)`) probablemente rompe con un error no manejado en vez de un `404` limpio.

**Solución recomendada:** resolver `current_obj` con `cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)` en vez de la query cruda; si no se encuentra, `cls._not_found(obj_id)` inmediatamente. Test: `PUT /lead_contact_states/{id}` de otra organización → `404`, no `500`.

Encontrado en simultáneo con el hallazgo #21 (`hallazgos_agente/flujo_de_leads.md`), mismo patrón de revisión (queries crudas sin tenant filter en vez de usar el repositorio).

**Fix aplicado (2026-07-11):** exactamente la solución recomendada — `app/services/lead_contact_state_service.py:62`. Resuelto junto con #24/#25 (mismo patrón mecánico) en `hallazgos_agente/patron_queries_sin_tenant_filter.md`, que tiene el detalle completo de los 5 puntos corregidos. Test de regresión: `tests/functional/test_tenant_isolation.py::TestLeadContactStateIsolation::test_update_blocked_for_foreign_lead_contact_state`.

---

# Hallazgo #27 — `lead_contact_state` no está en `SYSTEM_ENTITIES_REGISTRY`: ningún usuario no-superadmin puede gestionarlo vía API (encontrado 2026-07-11, al escribir el test de regresión del #22)

**Doc de usuario:** `docs/estados_de_contacto.md` §7
**Estado:** [RESUELTO 2026-07-11]

## Cómo se encontró

Al escribir el test de regresión del hallazgo #22 (`tests/functional/test_tenant_isolation.py::TestLeadContactStateIsolation`), usando el patrón estándar `as_user(api, ctx_alpha.owner)` (un usuario con rol `admin`, no superadmin) para crear un `LeadContactState`, el `POST /lead_contact_states/` devolvió `403` en vez de `200` — con un usuario que en cualquier otro módulo del sistema tiene permiso de sobra.

## Causa raíz (confirmada leyendo código, no solo el síntoma)

`app/core/dictionaries.py::SYSTEM_ENTITIES_REGISTRY` es la **única fuente de verdad** desde la que `app/db/init_data.py` genera las filas de `Permission` en la base (`codename = f"{entity_code}:{action}"`, ver función de sync ~línea 229-251). `"lead_contact_state"` **no es una clave de ese diccionario** — se confirmó con `grep -n "contact_state" app/core/dictionaries.py`, cero resultados. Consecuencia: **no existe ninguna fila `Permission` con codename `lead_contact_state:create/update/delete/view/view_all`, en ninguna organización, ni siquiera en la plantilla `admin` global** — el rol `admin` obtiene "todos los permisos que existen" (`r_admin.permissions = db.query(Permission).all()`), pero si la fila nunca se creó, no hay nada que asignarle.

`LeadContactStateController` es un `BaseController` genérico con `enabled_methods = READ_WRITE` (CRUD completo), y como cualquier controller genérico, `_get_deps` arma automáticamente el permiso `lead_contact_state:<acción>` sin que el controller lo sepa — no hay forma de que un router genérico "note" que el permiso no existe; simplemente el `PermissionChecker` siempre falla el `if self.required_permission not in user_permissions` para cualquier usuario no-superadmin, en cualquier organización.

**Impacto:** todos los endpoints de `/lead_contact_states/*` (`GET`, `POST`, `PUT`, `DELETE`, `PUT /active/{id}`) son, en la práctica, **solo accesibles por superadmin** — ningún dueño/admin de una organización puede crear, editar, listar ni desactivar sus propios estados de contacto vía API, a pesar de que `LeadContactState` es una entidad completamente scoped a la organización (se crean 4 por defecto al dar de alta una org, ver `docs/organizaciones.md` §4) y el controller está diseñado como CRUD completo, no de solo lectura. No se detectó antes porque **todos** los tests existentes de este módulo (`test_lead_contact_states.py`) operan con el fixture `api`/`client`, que actúa como superadmin — nunca se ejercitó este endpoint con un usuario real de organización hasta este test.

## Solución recomendada

1. Agregar `"lead_contact_state": {"model": "LeadContactState", "name": "Estado de Contacto", "crud_type": "FULL"}` a `SYSTEM_ENTITIES_REGISTRY` (`app/core/dictionaries.py`).
2. Correr de nuevo la sincronización de permisos (la función de `init_data.py` que arma `all_permissions` desde el registro) para que se creen las filas `Permission` nuevas y la plantilla `admin` (global, `ADMIN_ORG_ID`) las herede automáticamente (`r_admin.permissions = all_db_perms` las recoge solas la próxima vez que corra). Decidir también si `agent`/`viewer` deberían tener algo de este entity en `AGENT_PERMS`/`VIEWER_PERMS` (hoy ninguna de las dos listas menciona `lead_contact_state` — probablemente `viewer` debería tener al menos `lead_contact_state:view`, a definir con el usuario).
3. **Punto importante que sí requiere decisión, no es mecánico:** las organizaciones que ya existen tienen sus propios roles `admin`/`agent`/`viewer` **clonados** (`_clone_default_roles_for_org`, ver `docs/organizaciones.md` §4) con una foto fija de los permisos que tenía la plantilla en el momento del clonado — agregar el permiso a la plantilla global **no se retro-propaga** a esas organizaciones ya creadas (ver nota explícita en `docs/organizaciones.md` §4). Haría falta un script de migración de datos (mismo patrón que `scripts/migrate_add_user_profile_fields.py`) que recorra los roles `admin`/`agent`/`viewer` de cada organización existente y les agregue el/los permiso(s) nuevo(s) correspondientes.
4. Test: usuario `admin` de una organización (no superadmin) hace `POST`/`PUT`/`GET`/`DELETE` sobre `/lead_contact_states/` de su propia organización → debe funcionar (hoy da `403`).

## Fix aplicado (2026-07-11)

Se le explicó al usuario la causa raíz y las dos decisiones pendientes. Resolvió:

1. **Niveles de permiso:** `viewer` solo puede ver (`view`/`view_all`); `agent` puede crear y editar pero **no** borrar; `admin` mantiene CRUD completo (automático, porque el rol `admin` obtiene "todos los permisos que existan" — no requiere listarlo aparte).
2. **Organizaciones ya existentes, sin script de migración:** confirmado explícitamente por el usuario que esto es el diseño esperado — los roles clonados por organización son una plantilla de un momento dado, no una referencia viva a la plantilla global. Si el dueño de una organización quiere permisos distintos a los de la plantilla, la vía es que edite los roles de su propia organización directamente (quedan "pisados" respecto de la plantilla, intencionalmente). No se escribió ningún script de backfill.

**Cambios:**
- `app/core/dictionaries.py::SYSTEM_ENTITIES_REGISTRY`: se agregó `"lead_contact_state": {"model": "LeadContactState", "name": "Estado de Contacto", "crud_type": "FULL"}`.
- `app/db/init_data.py`: `AGENT_PERMS` suma `lead_contact_state:view`, `view_all`, `create`, `update` (sin `delete`); `VIEWER_PERMS` suma `lead_contact_state:view`, `view_all`.
- `tests/functional/test_tenant_isolation.py::TestLeadContactStateIsolation::test_update_blocked_for_foreign_lead_contact_state`: se revirtió al patrón estándar `as_user(ctx_alpha.owner)`/`as_user(ctx_beta.owner)` (ya no hace falta el cliente superadmin directo — el `owner` con rol `admin` ahora tiene el permiso).

**Test de regresión:** `tests/functional/test_lead_contact_states.py` — `test_lead_contact_state_org_admin_can_manage` (admin no-superadmin: crea/edita/borra, todo `200`), `test_lead_contact_state_agent_can_create_and_update_but_not_delete` (agent: crea/edita `200`, borra `403`), `test_lead_contact_state_viewer_can_only_view` (viewer: `GET` `200`, `POST` `403`).

**Nota operativa:** `run_seeds()` corre en cada arranque del backend (`app/main.py::lifespan`) y es idempotente (`_get_or_create_permission`) — alcanza con reiniciar el backend para que existan las filas `Permission` nuevas y para que la plantilla global (`ADMIN_ORG_ID`) las tenga. Esto NO retro-propaga el permiso a roles ya clonados en organizaciones existentes (ver decisión arriba) — si el usuario quiere que sus organizaciones de prueba actuales tengan estos permisos, tiene que recrearlas (o borrar/recrear la base, regla ya documentada en `AGENTS.md` §6).
