# Vistas de Leads (`LeadView`)

Documentación técnica de las vistas guardadas de leads (filtros + configuración visual persistida, tipo "vista Kanban de mis leads calientes"). Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Visibilidad: `PRIVATE` / `TEAM` / `PUBLIC`](#4-visibilidad-private--team--public)
5. [Quién puede editar o borrar una vista](#5-quién-puede-editar-o-borrar-una-vista)
6. [Cómo se testea](#6-cómo-se-testea)

---

## 1. Visión general

Una `LeadView` guarda una configuración completa de cómo un usuario (o un equipo, o toda la organización) quiere ver los leads de una campaña: tipo de vista (lista, kanban, calendario), filtros aplicados, configuración visual (orden/ancho de columnas) y orden de resultados — todo como JSON libre, para que el frontend lo reconstruya sin tener que rearmar la configuración cada vez.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead_view.py` | Modelo `LeadView` |
| `app/controllers/lead_view_controller.py` | Endpoints `/lead_views/*` (genérico) |
| `app/services/lead_view_service.py` | Reglas de visibilidad y permisos de edición/borrado |
| `app/db/repository/lead_view_repository.py` | `apply_security_filter` (quién puede *ver* una vista) |

---

## 2. Modelo de datos

```
Campaign ──< LeadView >── Team (opcional, solo si visibility="TEAM")
```

Campos propios: `organization_id`, `campaign_id` (obligatoria — una vista siempre pertenece a una campaña puntual, no es cross-campaña), `name`, `visibility` (`PRIVATE`/`TEAM`/`PUBLIC`, default `PRIVATE`), `team_id` (obligatorio solo si `visibility="TEAM"`), `view_type` (`LIST`/`KANBAN`/`CALENDAR`, libre en el modelo — no hay un enum de DB que lo restrinja), `filters` (JSONB), `ui_config` (JSONB, orden/ancho de columnas), `sort_config` (JSONB, default `{"sort_by": "created_at", "ascending": False}`).

`delete_strategy = HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9).

---

## 3. Endpoints

`LeadViewController` es genérico (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3), sin rutas propias. `allowed_filter_fields = {"name", "campaign_id", "team_id", "visibility", "view_type"}`. Toda la lógica particular de este módulo vive en el service (`create`/`update`/`delete` sobreescritos), no en rutas nuevas.

---

## 4. Visibilidad: `PRIVATE` / `TEAM` / `PUBLIC`

Determinada por `LeadViewRepository.apply_security_filter` (quién puede **ver** una vista en `GET /lead_views/`):

- Superadmin y `owner` de la organización ven todas.
- `PUBLIC`: visible para cualquier miembro de la organización.
- `PRIVATE`: visible solo para su creador (`created_by`).
- `TEAM`: visible para los miembros del `team_id` asignado (cualquier rol dentro del equipo, no solo `MANAGER`).

`_validate_team_assignment` (en creación y actualización) impone la integridad de esta relación: `visibility="TEAM"` exige `team_id`, y el usuario que crea/edita debe pertenecer a ese equipo (salvo superadmin/owner); si `visibility` **no** es `TEAM`, no se debe mandar `team_id` en absoluto (se rechaza si viene).

---

## 5. Quién puede editar o borrar una vista

A diferencia de la visibilidad de **lectura** (§4), editar o borrar una vista es más restrictivo (`_can_modify`, usado en `update` y `delete`, no en `create`):

- Superadmin u `owner` de la organización: siempre.
- El creador original de la vista: siempre.
- Si la vista es `TEAM`: los `MANAGER` de ese equipo también pueden (aunque no la hayan creado ellos).
- Cualquier otro caso (incluido un miembro no-manager de una vista `TEAM`, o cualquiera sobre una vista `PUBLIC` que no creó): `403`.

Es decir, una vista `PUBLIC` la puede *ver* cualquiera de la organización, pero solo su creador (o un admin) la puede modificar — ver no implica poder editar, a diferencia de lo que podría sugerir el nombre "pública".

---

## 6. Cómo se testea

`tests/functional/test_lead_views.py`: visibilidad `PRIVATE` (no visible a otro miembro, visible al creador, visible al owner), `TEAM` (visible a miembro del equipo, no visible a alguien de afuera, visible al owner), `PUBLIC` (visible a todos los miembros, incluidos los que no pertenecen a ningún equipo). No se encontraron tests específicos para las reglas de `_can_modify` (edición/borrado restringido a creador/manager/admin) ni para `_validate_team_assignment` (falta de `team_id` en `TEAM`, o `team_id` enviado sin ser `TEAM`) — son las dos piezas de lógica de negocio con más ramas de este módulo y hoy dependen solo de la revisión manual del código.
