# Usuarios y Permisos (gestión)

Documentación técnica de los endpoints de **gestión** de `User`, `Role` y `Permission` (`/users`, `/roles`, `/permissions`). El modelo de datos completo (`User`, `Role`, `Permission`, `UserOrganization`), el sistema de RBAC, los tokens y el flujo de login/invitación **ya están documentados en detalle en `autenticacion.md`** — este doc no los repite, solo cubre lo que `autenticacion.md` no cubre: los endpoints de administración de usuarios/roles/permisos fuera del flujo de `/auth/*`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Endpoints de `/users`](#2-endpoints-de-users)
3. [Quién puede editar/borrar un usuario](#3-quién-puede-editareditar-un-usuario)
4. [Promoción a superadmin y a owner de organización](#4-promoción-a-superadmin-y-a-owner-de-organización)
5. [Endpoints de `/roles` y `/permissions`](#5-endpoints-de-roles-y-permissions)
6. [Cómo se testea](#6-cómo-se-testea)

---

## 1. Visión general

Los tres controllers relacionados con seguridad viven en `app/controllers/security_controllers/`. A diferencia de `autenticacion.md` (que cubre `/auth/*`: login, registro, invitaciones, tokens), este documento cubre la gestión posterior: listar/editar/borrar usuarios, y el catálogo de roles/permisos de una organización.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/controllers/security_controllers/user_controller.py` | Endpoints `/users/*` |
| `app/controllers/security_controllers/role_controller.py` | Endpoints `/roles/*` (genérico) |
| `app/controllers/security_controllers/permission_controller.py` | Endpoints `/permissions/*` (solo lectura) |
| `app/services/security_services/user_service.py`, `role_service.py`, `permission_service.py` | Reglas de negocio |

---

## 2. Endpoints de `/users`

`UserController` hereda `BaseController` pero con `enabled_methods = {"PUT", "DELETE", "ACTIVE"}` — **sin `POST`** (crear cuentas es exclusivo de `POST /auth/register`, ver `autenticacion.md` §5) y **sin `GET_ALL`/`GET_ONE` genéricos** (se redefinen a mano para exigir un permiso específico en vez del automático de `BaseController`):

| Método y ruta | Permiso requerido | Qué hace |
|---|---|---|
| `GET /users/` | `user:view_all` | Listado paginado de usuarios (¡de **todo el sistema**, no solo de la organización activa — ver nota abajo!). |
| `GET /users/{id}` | `user:view_all` | Detalle de un usuario. |
| `GET /users/in-org/members` | Ninguno explícito, solo requiere pertenecer a la organización del header `X-Organization-Id` | Lista los usuarios de **la organización activa** únicamente (`UserPublicResponse`, respuesta reducida). Es la ruta que normalmente usaría un frontend para, por ejemplo, poblar un selector de "asignar a...". |
| `PUT /users/{id}` | Regla propia (ver §3) | Actualiza `name`/`last_name`/`email`/`phone`/`date_of_birth`. |
| `DELETE /users/{id}` | Regla propia (ver §3) | Soft/hard delete según `delete_strategy = SOFT_DELETE_HARD_OPT`. |
| `PUT /users/active/{id}` | Genérico (`user:update`) | Reactiva. |
| `PATCH /users/promote_to_superuser/{id}` | `require_superuser` | Ver §4. |
| `PATCH /users/organization/{org_id}/promote-owner/{user_id}` | `require_superuser` (el chequeo fino de "o soy owner de esa org" está *dentro* del service, no en la dependencia) | Ver §4. |

**Nota sobre `GET /users/`:** al no pasar por el filtro de tenant automático de `BaseController` de la misma forma que otras entidades (no hay `organization_id` en `User`, es una cuenta global — ver `autenticacion.md` §2), este endpoint devuelve usuarios de **cualquier organización** a quien tenga el permiso `user:view_all`. Es intencional dado que `User` es una entidad global, pero vale la pena tenerlo presente: el permiso `user:view_all` de un admin de organización es, en la práctica, "ver todos los usuarios del sistema", no solo los de su empresa — para ver solo los de la propia organización hay que usar `/users/in-org/members`.

---

## 3. Quién puede editar/borrar un usuario

`UserService._assert_can_modify`, aplicado tanto en `update` como en `delete`: **solo el propio usuario o un superadmin** pueden modificar/eliminar una cuenta — ni siquiera el `owner` de la organización puede editar los datos personales de otro miembro. Es una regla más estricta que el RBAC genérico por permisos (`user:update`/`user:delete`): aunque un rol tenga esos permisos asignados, `_assert_can_modify` los bloquea igual si no son ni el dueño de la cuenta ni superadmin.

---

## 4. Promoción a superadmin y a owner de organización

Ambos endpoints están documentados también desde el ángulo de seguridad en `autenticacion.md` §9, acá el detalle de la regla de autorización:

- **`promote_to_superuser`**: la dependencia de ruta ya exige `require_superuser` (o sea, quien llama ya es superadmin), y el service **vuelve a validar** `user_context.is_superuser` adentro — doble chequeo redundante pero inofensivo. Marca `target_user.is_superuser = True` y audita con la acción especial `PROMOTE_SUPERUSER`.
- **`promote_to_org_owner`**: la dependencia de ruta exige `require_superuser`, pero el service acepta un segundo camino: si el llamador **no** es superadmin pero es `is_owner` de la organización indicada en la URL (`organization_id`), también puede — comparando contra `TENANT_ORG_ID.get()` (el header `X-Organization-Id` de la request). Si el usuario destino no tenía membresía en esa organización, se le crea una (`UserOrganization`) directamente con `is_owner=True`; si ya la tenía, solo se le sube el flag. Se audita con `PROMOTE_OWNER`.

  **Nota de consistencia:** la dependencia de ruta declara `require_superuser`, lo cual en teoría bloquearía a un owner-no-superadmin antes de llegar al service — pero el service igual contempla ese caso (`elif user_context.is_owner`). Si `require_superuser` efectivamente corta antes, esa rama del service sería código muerto; si en la práctica un owner puede llegar a ejecutar el endpoint, entonces `require_superuser` no está funcionando como lo sugiere su nombre. No se resolvió cuál de los dos es el comportamiento real (dependería de revisar `require_superuser` en `app/core/security.py` con detalle, fuera del alcance de esta pasada) — vale la pena confirmarlo si se toca este endpoint.

---

## 5. Endpoints de `/roles` y `/permissions`

- **`RoleController`**: 100% genérico (`BaseController`, `enabled_methods = READ_WRITE`), sin reglas propias en `RoleService` (hereda todo de `BaseService`) — crear/editar/borrar roles de la organización activa (clonados de las plantillas `admin`/`agent`/`viewer`, ver `autenticacion.md` §7) y asignarles permisos es CRUD puro.
- **`PermissionController`**: `enabled_methods = READ_ONLY` — el catálogo de permisos (`entidad:acción`, generado automáticamente por `SYSTEM_ENTITIES_REGISTRY`, ver `autenticacion.md` §7) es de solo lectura vía API; no se crean permisos nuevos a mano desde acá.

---

## 6. Cómo se testea

`tests/functional/test_permissions_and_roles.py` cubre ambos ángulos (RBAC y gestión de usuarios) en un solo archivo: clonado de roles plantilla por organización, permisos de `admin`/`agent`/`viewer`, creación de organización clona roles y asigna `admin` al creador, flujo de invitación con roles (`admin`/`agent` pueden o no invitar, rol inválido, rol default), y del lado de este documento específicamente: listar usuarios (`admin` puede, `agent`/`viewer` no pueden — `403`), obtener un usuario puntual (mismo patrón de permisos), promoción a superadmin (no-superadmin no puede, superadmin sí, agente no puede), y `test_superadmin_requires_org_header` (confirma que ni el superadmin escapa la exigencia del header `X-Organization-Id`, ver `autenticacion.md` §8). `GET /users/in-org/members` sí tiene cobertura propia (`TestUsersInOrg` en `test_security_auth.py`): miembro ve a los demás miembros de su organización, alguien ajeno a la organización recibe `403`, y la respuesta usa el schema reducido (`UserPublicResponse`) sin exponer campos sensibles como `is_superuser`. No se encontraron tests específicos para `promote_to_org_owner` ni para la regla `_assert_can_modify` de edición/borrado de la propia cuenta (§3) — esos dos quedan como huecos de cobertura de este módulo.
