# Autenticación y Autorización

Documentación técnica del módulo de seguridad del CRM: login, tokens, invitaciones, permisos, roles y multi-tenancy. Última revisión: 2026-07-01.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Contraseñas](#3-contraseñas)
4. [Tokens](#4-tokens)
5. [Endpoints de `/auth`](#5-endpoints-de-auth)
6. [Flujo de invitaciones](#6-flujo-de-invitaciones)
7. [Autorización: permisos y roles](#7-autorización-permisos-y-roles)
8. [Multi-tenancy: header `X-Organization-Id`](#8-multi-tenancy-header-x-organization-id)
9. [Superadmin](#9-superadmin)
10. [Organizaciones y sus reglas](#10-organizaciones-y-sus-reglas)
11. [Decisiones de seguridad y puntos pendientes](#11-decisiones-de-seguridad-y-puntos-pendientes)
12. [Cómo se testea](#12-cómo-se-testea)
13. [Changelog](#13-changelog)

---

## 1. Visión general

El sistema es multi-tenant: una misma cuenta de usuario (`User`) puede pertenecer a varias organizaciones (`Organization`), con un rol distinto en cada una. La autenticación es stateless vía JWT (access token de corta duración + refresh token opaco guardado en DB), y la autorización combina dos cosas en cada request:

- **Quién sos** → `_get_current_user` (decodifica el JWT del header `Authorization`).
- **En qué organización estás operando ahora** → header `X-Organization-Id`, obligatorio en casi todos los endpoints protegidos, incluso para el superadmin.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/core/security.py` | JWT, hashing, dependencias `_get_current_user`, `require_superuser`, `PermissionChecker`, `get_current_user_roles` |
| `app/core/context.py` | `TENANT_ORG_ID`: contextvar con la organización activa del request |
| `app/services/security_services/auth_service.py` | Lógica de register / login / refresh / logout / invite / accept-invite / change-password |
| `app/controllers/security_controllers/auth_controller.py` | Endpoints `/auth/*` |
| `app/schemas/security_schemas/auth_schema.py` | Schemas de request/response de `/auth/*` |
| `app/models/security_models.py` | `User`, `Role`, `Permission`, `UserOrganization` |
| `app/models/refresh_token_model.py` | `RefreshToken` |
| `app/db/init_data.py` | Seed de permisos, roles plantilla (admin/agent/viewer) y superadmins |
| `app/services/organization_service.py` | Alta de organizaciones (clona roles, límite de 1 org propia por usuario) |

---

## 2. Modelo de datos

```
User ──< UserOrganization >── Organization
                │
                └──< roles >── Role ──< permissions >── Permission
```

- **`User`**: cuenta global, no pertenece a una sola organización. Campos: `name`, `last_name` (obligatorio, `NOT NULL` en DB y en `RegisterRequest`), `email` (único), `phone`, `date_of_birth`, `hashed_password`, `is_superuser`.
- **`UserOrganization`**: la membresía. Une un `User` a una `Organization`, con `is_owner` (dueño de esa org) y una lista de `roles` (puede tener más de uno). Tiene `uq_user_per_org`: un usuario no puede estar dos veces en la misma org.
- **`Role`**: pertenece a una organización (`organization_id`). Tiene una lista de `permissions`. Los roles "plantilla" viven en la organización especial `ADMIN_ORG_ID=1` (ver [§9](#9-superadmin)) y se clonan a cada organización nueva.
- **`Permission`**: string único (`codename`), ej. `lead:create`, `user:view_all`, `user:invite`. Se generan automáticamente por entidad del sistema (`SYSTEM_ENTITIES_REGISTRY`) más el permiso especial `user:invite`.
- **`RefreshToken`**: un registro por sesión activa. Guarda el **hash** del refresh token (nunca el valor plano), `expires_at`, y `revoked`.

Métodos clave en `User` (`app/models/security_models.py`):

- `get_roles_for_org(org_id)` → lista de `Role` que tiene en esa org (o `[]` si no pertenece o la membresía está inactiva).
- `get_permissions(org_id)` → lista de codenames. Si `is_superuser`, devuelve `["*"]` sin consultar roles.

---

## 3. Contraseñas

- Hasheo con `bcrypt` vía `passlib` (`hash_password` / `verify_password` en `core/security.py`).
- `hashed_password` es `nullable=True` a propósito: hay usuarios creados sin login habilitado (ej. seeds internos, o el hueco histórico de `accept_invite` antes de la corrección — ver [§13](#13-changelog)).
- **Política de fortaleza** (`validate_password_strength` en `core/security.py`): mínimo 10 caracteres, máximo 72 (bcrypt trunca lo que exceda), al menos una mayúscula, una minúscula y un número. Es la **única fuente de verdad** — se usa como `@field_validator` tanto en `RegisterRequest.password` como en `ChangePasswordRequest.new_password`. Para endurecer o relajar la regla alcanza con tocar esa función, no hay que buscar duplicados.
- El login (`AuthService.login`) siempre corre `verify_password` — incluso si el email no existe, usando un hash dummy precalculado (`_DUMMY_HASH`) — para que un email inexistente y una contraseña incorrecta tarden lo mismo (mitigación de timing attack para no poder enumerar emails registrados). El login **no** valida la política de fortaleza (solo aplica al crear/cambiar contraseña), para no romper el ingreso de cuentas viejas con contraseñas más débiles.

---

## 4. Tokens

| Tipo | Formato | Dónde vive | Expiración | Contenido (claims) |
|---|---|---|---|---|
| **Access token** | JWT firmado (`SECRET_KEY`/`ALGORITHM`) | Solo en el cliente (header `Authorization: Bearer`) | `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30 min) | `sub` (user id), `type: "access"`, `exp` |
| **Refresh token** | String random opaco (`secrets.token_urlsafe(64)`) | El valor plano solo lo tiene el cliente; en DB se guarda `sha256(token)` en `RefreshToken.token_hash` | `REFRESH_TOKEN_EXPIRE_DAYS` (default 7 días) | No es JWT, no lleva claims — es un puntero a la fila en `refresh_token` |
| **Invite token** | JWT firmado | Se devuelve en la respuesta de `POST /auth/invite`; quien invita se lo pasa al invitado por fuera del sistema (email, chat, etc.) | 72 horas (`create_invite_token`) | `email`, `org_id`, `invited_by`, `role_code`, `type: "invite"`, `exp` |

Notas:

- `decode_token` valida firma y expiración; si falla, lanza `401`.
- El refresh **rota**: cada `POST /auth/refresh` marca el token viejo como `revoked=True` y emite un par nuevo. Si alguien reusa un refresh token ya revocado, se rechaza (protección básica contra robo de refresh tokens).
- `POST /auth/logout` revoca el refresh token recibido.
- `POST /auth/change-password` revoca **todos** los refresh tokens del usuario (cierra todas las demás sesiones).
- El invite token **no se invalida al usarse**. No es un problema de seguridad porque va atado a un email específico: si alguien más lo reutiliza con otro email, `accept-invite`/`register` lo rechazan por mismatch de email (ver [§6](#6-flujo-de-invitaciones)). Si el mismo invitado lo manda dos veces, la segunda vez es inofensiva (la cuenta ya existe o la membresía ya existe).

---

## 5. Endpoints de `/auth`

| Método y ruta | Auth requerida | Qué hace |
|---|---|---|
| `POST /auth/register` | Ninguna (público) | Crea una cuenta nueva. Devuelve `TokenResponse` (ya queda logueado). Acepta `invite_token` opcional (ver [§6](#6-flujo-de-invitaciones)). |
| `POST /auth/login` | Ninguna | Valida email + password, devuelve `TokenResponse`. |
| `POST /auth/refresh` | Refresh token en el body | Rota el refresh token, devuelve un par nuevo. |
| `POST /auth/logout` | Refresh token en el body | Revoca ese refresh token. |
| `GET /auth/me` | Access token | Devuelve el usuario autenticado. |
| `PUT /auth/me` | Access token | Actualiza `name`, `last_name`, `email`, `phone`, `date_of_birth` del propio usuario. |
| `POST /auth/change-password` | Access token | Cambia contraseña, exige la actual, revoca otras sesiones. |
| `POST /auth/invite` | Access token + permiso `user:invite` en la org (header `X-Organization-Id`) | Genera un invite token para sumar a alguien (por email) a la organización, con un `role_code` (default `agent`). No crea nada todavía. |
| `POST /auth/accept-invite` | Access token (usuario ya logueado) | Usa un invite token para **unirse** a la organización indicada. Ver [§6](#6-flujo-de-invitaciones). |

### Ejemplo `POST /auth/register`

```json
// Request
{
  "name": "Franco",
  "last_name": "Ruiz",
  "email": "franco@empresa.com",
  "password": "unaClaveSegura123",
  "invite_token": null
}

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "9f3a...",
  "token_type": "bearer",
  "expires_in": 1800,
  "invite_warning": null
}
```

`invite_warning` solo trae texto cuando se mandó un `invite_token` que no se pudo usar (inválido, vencido, o de otro email) — el registro **igual se completa**, solo avisa que no quedó unido a ninguna organización.

### Ejemplo `POST /auth/accept-invite`

```json
// Request (con Authorization: Bearer <access_token propio>)
{ "invite_token": "eyJ..." }

// Response 200
{ "message": "Te uniste a 'Mi Empresa' con el rol 'agent'.", "organization_id": 12 }
```

---

## 6. Flujo de invitaciones

Quien invita **nunca** elige nombre, apellido ni contraseña del invitado — solo indica **a qué email** y **con qué rol**. El resto se resuelve distinto según si ese email ya tiene cuenta o no:

```
Admin de la org               Sistema                      Invitado
      │  POST /auth/invite        │                             │
      │  {email, org_id, role}    │                             │
      │──────────────────────────▶│                             │
      │◀── invite_token (JWT) ────│                             │
      │                           │                             │
      │  (se lo pasa al invitado por fuera del sistema)          │
      │───────────────────────────────────────────────────────▶ │
      │                           │                             │
      │                           │        ¿el email ya         │
      │                           │        tiene cuenta?         │
      │                           │                             │
      │                           │   NO ──▶ POST /auth/register │
      │                           │          (name, last_name,   │
      │                           │           password, email,   │
      │                           │           invite_token)      │
      │                           │          → cuenta creada Y   │
      │                           │            unida a la org    │
      │                           │                             │
      │                           │   SÍ ──▶ login normal, luego │
      │                           │          POST /auth/accept-  │
      │                           │          invite autenticado  │
      │                           │          (solo invite_token) │
      │                           │          → se une a la org   │
```

Reglas de validación (`_try_join_org_from_invite` en `register`, y `AuthService.accept_invite`):

- El `email` dentro del token debe coincidir (case-insensitive) con el email de la cuenta que se está uniendo. Si no coincide → `403` en `accept-invite`, o `invite_warning` (sin bloquear el registro) en `register`.
- El rol a asignar es `role_code` del token; si no existe ese código en la org, se busca como rol global (`ADMIN_ORG_ID`) de fallback; si tampoco existe, la membresía se crea sin roles (sin permisos).
- Si la membresía ya existía (invitación repetida), `accept-invite` responde igual con `200` sin duplicar nada.

Este diseño reemplazó una versión anterior donde `accept-invite` aceptaba `name`/`password` como query params y, si el email ya tenía cuenta, **ignoraba la contraseña recibida y devolvía tokens válidos igual** — un account-takeover completo para cualquiera con permiso `user:invite`. Ver [§13](#13-changelog).

---

## 7. Autorización: permisos y roles

- Los **permisos** son strings `entidad:acción` (ej. `lead:create`, `campaign:view_all`) generados automáticamente para cada entidad del sistema (`SYSTEM_ENTITIES_REGISTRY` en `app/core/dictionaries.py`), más el permiso especial `user:invite`.
- Los **roles plantilla** (`admin`, `agent`, `viewer`) se crean una única vez en la organización especial `ADMIN_ORG_ID=1` (`app/db/init_data.py::seed_rbac`):
  - `admin`: todos los permisos existentes.
  - `agent`: operación diaria (leads, comentarios, vistas, tags, lectura de catálogos) sin permisos de configuración.
  - `viewer`: solo lectura.
- Cuando se crea una organización nueva (`OrganizationService.create` → `_clone_default_roles_for_org`), estos 3 roles se **clonan** (mismo `code`, mismos permisos) a esa organización. Es decir, cada organización tiene su propia copia editable de `admin`/`agent`/`viewer`, no comparten la fila con la plantilla.
- Un usuario puede tener más de un rol por organización (`UserOrganization.roles` es una lista). `get_permissions` une los permisos de todos sus roles en esa org.

### Dependencias de FastAPI relevantes (`app/core/security.py`)

| Dependencia | Qué valida | Uso típico |
|---|---|---|
| `_get_current_user` | JWT válido, tipo `access`, usuario existe y está activo | Base de todo lo demás |
| `require_superuser` | `current_user.is_superuser == True` | Endpoints solo-superadmin (ej. `promote_to_superuser`) |
| `get_current_user_roles` | Arma un `UserContext` (usuario, `is_superuser`, `is_owner` en la org del header, `organization_id`, `permissions`) | Endpoints que necesitan saber el contexto completo, no solo permitir/denegar |
| `PermissionChecker("codename")` | Exige el header `X-Organization-Id`, y que el usuario tenga ese permiso en esa org (o sea superadmin) | La forma más común de proteger un endpoint |

`PermissionChecker` siempre exige `X-Organization-Id`, **incluso para el superadmin** — es a propósito, para que nunca haya una operación sin un contexto de organización explícito (aislamiento de datos).

---

## 8. Multi-tenancy: header `X-Organization-Id`

- Casi todos los endpoints protegidos requieren el header `X-Organization-Id`.
- Al llegar, se guarda en `TENANT_ORG_ID` (`app/core/context.py`), un `ContextVar` — seguro para requests concurrentes en async.
- Los repositorios/servicios leen `TENANT_ORG_ID` para filtrar automáticamente por organización (aislamiento de datos entre tenants). Ver tests en `tests/functional/test_tenant_isolation.py`.
- El superadmin también manda este header: sus permisos son globales (`["*"]`), pero sigue operando "dentro de" una organización en cada request.

---

## 9. Superadmin

- Es un `User` con `is_superuser=True`. `get_permissions()` le devuelve `["*"]` sin mirar roles, y `PermissionChecker` lo deja pasar sin chequear el permiso puntual (pero igual exige el header de organización).
- Se siembran dos superadmins en `app/db/init_data.py::seed_rbac` (idempotente, `_get_or_create_superadmin`):

  | Nombre | Email | Contraseña (seed) |
  |---|---|---|
  | Franco Ruiz | `francoruiz.admin@crm.com` | `ADQSilR4aAKCO%a^` |
  | Gonzalo Maunas | `gonzalomaunas.admin@crm.com` | `e&Kr**JtgoK5aNmy` |

  Ambos quedan como `owner` de la organización `ADMIN_ORG_ID=1` ("Panel Global").

- **Cambiar contraseñas de seed:** están hardcodeadas en `init_data.py`. Si se cambian ahí, hay que rotarlas también donde se usan (ej. `scripts/seed_data_v1.py` tiene `SEED_EMAIL`/`SEED_PASSWORD` apuntando al primer superadmin).
- Endpoints de promoción (`app/controllers/security_controllers/user_controller.py`):
  - `PATCH /users/promote_to_superuser/{id}` — solo un superadmin puede ejecutar esto (`require_superuser` + valida de nuevo adentro del servicio).
  - `PATCH /users/organization/{org_id}/promote-owner/{user_id}` — solo un superadmin, o el `owner` actual de **esa misma** organización.

---

## 10. Organizaciones y sus reglas

`OrganizationService.create` (`app/services/organization_service.py`), al crear una organización:

1. Valida que un usuario **no superadmin** no sea ya `owner` de otra organización (**límite: 1 organización propia por usuario**). El superadmin no tiene ese límite.
2. Crea el flujo de ventas por defecto (`LeadFlow` + estados + transiciones), estados de contacto, y una sección de campos ("Información básica").
3. Clona los roles plantilla (`admin`/`agent`/`viewer`) a la nueva organización.
4. Corona al creador como `owner` y le asigna el rol `admin` de esa organización.

Importante: **el registro (`/auth/register`) no crea una organización.** Son dos pasos separados: primero se registra la cuenta, después esa cuenta llama a `POST /organizations/` para crear (y quedarse como dueña de) su propia organización. La única forma de "entrar" a una organización sin crearla es vía invitación (§6).

---

## 11. Decisiones de seguridad y puntos pendientes

**Ya resuelto:**

- Timing attack en login (hash dummy cuando el email no existe).
- Refresh tokens: se guardan hasheados, rotan en cada uso, y se revocan en logout / cambio de contraseña.
- Account-takeover en `accept-invite` (ver [§13](#13-changelog)): ya no acepta contraseña para usuarios existentes; exige sesión autenticada + email coincidente.
- Contraseña ya no viaja por querystring en `accept-invite` (ahora es JSON body).
- Política de fortaleza de contraseña (mín. 10, mayúscula + minúscula + número, tope 72 por bcrypt), unificada en `validate_password_strength` y aplicada tanto en `/auth/register` como en `/auth/change-password` (ver [§3](#3-contraseñas)).
- `last_name` es `NOT NULL` tanto en `RegisterRequest` como en la columna `User.last_name` — ya no es solo una validación de API que se puede esquivar creando el `User` directo por otro camino (ver [§13](#13-changelog)).
- **[RESUELTO, hallazgo #12, 2026-07-10]** `/auth/login` y `/auth/register` tienen rate limiting (`10/minuto` por IP, vía `slowapi` — misma infraestructura que ya usaba `WebForm`). Antes no había ningún freno a la cantidad de intentos (fuerza bruta / credential stuffing en login, spam de cuentas en register).
- **[RESUELTO, hallazgo #13, 2026-07-11]** El email se normaliza (`.strip().lower()`) antes de guardarlo o compararlo, en `LoginRequest`/`RegisterRequest`/`UserUpdate` (`app/core/security.py::normalize_email`, única fuente de verdad). Registrarse con una capitalización y loguearse con otra ahora funciona; dos registros del mismo email en distinta capitalización se tratan como duplicado. El fix es solo hacia adelante (no hay migración de datos existentes — el proyecto todavía no tiene datos reales, ver `AGENTS.md` §6).
- **[RESUELTO, hallazgo #14, 2026-07-11]** `PUT /auth/me` ahora valida formato de email (`EmailStr`) y unicidad (`400` si ya está en uso por otra cuenta, chequeado antes del `commit()` — antes terminaba en `500` sin manejar por la constraint `unique` de `User.email`).

**Pendiente / a tener en cuenta:**

- `POST /auth/invite` devuelve el `invite_token` directo en la respuesta HTTP — asume que el front/quien invita lo va a compartir por un canal seguro (email, etc.) fuera del sistema. No hay envío de mail automático todavía.

---

## 12. Cómo se testea

- Los tests **no** pasan por JWT real en la mayoría de los casos: `tests/fixtures/client.py` overridea `_get_current_user` para que devuelva directamente el superadmin de test (`francoruiz.admin@crm.com`, sembrado por `run_seeds` en `tests/fixtures/db_fixtures.py::db_engine`, que corre una vez por sesión de tests).
- `tests/fixtures/user_fixtures.py` tiene:
  - `_apply_user_overrides(app, user, org_id, is_owner)` / `as_user(...)`: simulan "estar logueado como" cualquier usuario, sin pasar por login real.
  - `MultiUserApiClient`: cliente de test que permite cambiar de usuario simulado a mitad de un test (`switch_user`, `as_user`).
- Para probar los endpoints reales de `/auth/*` (register, login, refresh, invite, accept-invite) hay un fixture separado, `plain_client`, que **no** overridea `_get_current_user` — ahí sí se usa JWT real de punta a punta (login real, header `Authorization` real). Está en `tests/functional/test_security_auth.py` y se reutiliza en otros archivos.
- ⚠️ **Cuidado**: como el superadmin de test está hardcodeado por email en varios lugares (`tests/fixtures/client.py`, y varios tests que hacen `db_session.query(User).filter_by(email="...")`), si el día de mañana cambia el email/seed del superadmin en `init_data.py` sin actualizar esos lugares, se rompen en cadena un montón de tests con `AttributeError: 'NoneType' object has no attribute ...` (ya pasó, ver Changelog).
- `tests/functional/test_security_auth.py::TestAuthRateLimiting` cubre el rate limit del hallazgo #12 (11 intentos en la misma ventana → al menos un `429` entre login y entre register). El `Limiter` de `/auth/*` vive a nivel de módulo y sus contadores persisten mientras dure el proceso de test — como casi todo este archivo (y `test_permissions_and_roles.py`) llama a `/auth/login`/`/auth/register` repetidamente, ambos archivos tienen un fixture `autouse` que resetea el limiter antes de cada test, para que la cuota de un test no se filtre a otro.

---

## 13. Changelog

**2026-07-01 — Bug de seed + registro obligatorio de `last_name`**
Un commit (`0cfe7e1`) cambió simultáneamente el email del superadmin sembrado (de `admin@crm.com` a `francoruiz.admin@crm.com` / `gonzalomaunas.admin@crm.com`) e hizo `last_name` obligatorio en `RegisterRequest`, sin actualizar los tests. Resultado: 14 tests rotos (`NoneType has no attribute 'is_superuser'/'id'` por el email hardcodeado, y `422` en register/refresh/logout por el campo faltante). Se corrigieron los fixtures/tests para usar `francoruiz.admin@crm.com` y se agregó `last_name` a los payloads de registro.

**2026-07-01 — Rediseño del flujo de invitaciones (vulnerabilidad de account-takeover)**
`accept-invite` recibía `name`/`password` por query string y, si el email invitado ya tenía cuenta, **ignoraba la contraseña recibida** y devolvía tokens válidos para esa cuenta — cualquiera con permiso `user:invite` podía tomar control de cualquier cuenta existente invitándola a una org propia. Se rediseñó: usuarios nuevos se dan de alta por `/auth/register` (con `invite_token` opcional), usuarios existentes usan `/auth/accept-invite` ya autenticados (sin contraseña), validando que el email del token coincida con el usuario logueado.

**2026-07-01 — Política de fortaleza de contraseña**
Se agregó `validate_password_strength` en `core/security.py` (mín. 10 caracteres, máx. 72, mayúscula + minúscula + número) como única fuente de verdad, usada por `RegisterRequest.password` y `ChangePasswordRequest.new_password`. Se eliminó el chequeo redundante de "mínimo 8 caracteres" que estaba hardcodeado dentro de `AuthService.change_password`. Se actualizaron los tests existentes que usaban contraseñas débiles (ej. `"pass123"`, `"pass1234"`) en llamadas a `/auth/register`, y se agregaron tests nuevos para la política (registro y cambio de contraseña).

**2026-07-01 — `last_name` ahora es `NOT NULL` también en la DB**
La columna `User.last_name` pasó de `nullable=True` a `nullable=False`, para que la regla "todo usuario tiene apellido" sea una garantía real de integridad de datos y no solo una validación del endpoint público `/auth/register` (que cualquier otro código interno podía esquivar creando el `User` directo). Se actualizaron ~20 instanciaciones directas de `User(...)` en tests (`test_security_auth.py`, `test_permissions_and_roles.py`, `test_lead_fixes.py`, y el helper `_make_user` de `tests/fixtures/user_fixtures.py`, que ahora tiene `last_name: str = "Test"` por defecto) para que pasen `last_name`. No requiere migración (no hay Alembic en el proyecto): alcanza con recrear el schema de la base.

**2026-07-01 — Política de fortaleza de contraseña**
Se agregó `validate_password_strength` en `core/security.py` (mín. 10 caracteres, máx. 72, mayúscula + minúscula + número) como única fuente de verdad, usada por `RegisterRequest.password` y `ChangePasswordRequest.new_password`. Se eliminó el chequeo redundante de "mínimo 8 caracteres" que estaba hardcodeado dentro de `AuthService.change_password`. Se actualizaron los tests existentes que usaban contraseñas débiles (ej. `"pass123"`, `"pass1234"`) en llamadas a `/auth/register`, y se agregaron tests nuevos para la política (registro y cambio de contraseña).
