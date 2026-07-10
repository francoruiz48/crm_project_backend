# Comentarios de Leads (`LeadComment`)

Documentación técnica del módulo de comentarios sobre un `Lead`. Es uno de los módulos más simples del sistema: implementa el patrón genérico de `convenciones_generales.md` sin ninguna lógica de negocio propia. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints de `/lead_comments`](#3-endpoints-de-lead_comments)
4. [Puntos a tener en cuenta](#4-puntos-a-tener-en-cuenta)
5. [Cómo se testea](#5-cómo-se-testea)

---

## 1. Visión general

Un `LeadComment` es una nota de texto libre asociada a un `Lead` (ver `lead.md`), con un `color` opcional (para categorización visual en el frontend, ej. notas rojas = urgente). No tiene service ni controller propios más allá de heredar directamente de las clases base — es el ejemplo más chico del patrón CRUD genérico.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead_comment.py` | Modelo `LeadComment` |
| `app/controllers/lead_comment_controller.py` | Endpoints `/lead_comments/*`, 100% genéricos (`BaseController`) |
| `app/services/lead_comment_service.py` | Vacío salvo por declarar el repositorio (hereda todo de `BaseService`) |
| `app/schemas/lead_comment_shema.py` | Schemas de request/response |
| `app/db/repository/lead_comment_repository.py` | Solo declara `model` y `delete_strategy` |

---

## 2. Modelo de datos

```
Lead ──< LeadComment
```

Campos propios (además de los heredados de `BaseModelDB`, ver `convenciones_generales.md` §2): `content` (string, obligatorio, 1–600 caracteres), `color` (string, opcional), `lead_id` (FK obligatoria a `Lead`).

Cuando se borra un `Lead`, sus comentarios se borran en cascada (`Lead.comments` tiene `cascade="all, delete-orphan"`, ver `lead.md` §2) — no hace falta borrarlos a mano.

`delete_strategy = HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9): `DELETE /lead_comments/{id}` es físico y definitivo, sin soft delete.

---

## 3. Endpoints de `/lead_comments`

100% genéricos vía `BaseController` (`enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3): `GET /`, `GET /{id}`, `POST /`, `PUT /{id}`, `DELETE /{id}`, `POST /bulk-delete`, `PUT /active/{id}`, `POST /bulk-active`.

Único detalle propio del controller: `allowed_filter_fields = {"lead_id"}` — restringe los filtros dinámicos de `GET /` a únicamente `?lead_id=X` (no se puede filtrar por `content` o `color` vía query param).

---

## 4. Puntos a tener en cuenta

- No hay validación explícita de que `lead_id` pertenezca a la organización activa a nivel de `LeadCommentService`/`Repository` — al ser un modelo sin `organization_id` propio, el aislamiento de tenant depende de que el `lead_id` referenciado ya haya pasado el filtro de organización en algún otro punto (típicamente, el frontend solo tiene acceso al `lead_id` de leads que ya pudo ver). No se encontró un caso reproducible de bypass, pero es una diferencia frente a otros módulos donde el repositorio valida explícitamente la pertenencia a organización de las FKs que recibe (ej. `Lead.create` valida `team_id`/`assigned_to_user_id`, ver `lead.md` §4).
- No participa del pipeline de campos dinámicos ni de automatizaciones — es completamente independiente del sistema de `LeadField`.

---

## 5. Cómo se testea

No se encontró ningún test que ejercite `LeadComment` (ni un archivo dedicado, ni referencias en la suite de `Lead`). **Recomendación:** agregar al menos un test funcional de CRUD básico (`POST`/`GET`/`PUT`/`DELETE /lead_comments`) y uno que confirme el borrado en cascada al eliminar el `Lead` padre — hoy ese comportamiento depende únicamente de la relación declarada en el modelo (`cascade="all, delete-orphan"`, ver §2) y no está verificado por ningún test.
