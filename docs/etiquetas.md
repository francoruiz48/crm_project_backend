# Etiquetas (`Tag`)

Documentación técnica del sistema de etiquetas libres sobre leads. Es otro módulo casi enteramente genérico. Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Reglas de negocio](#4-reglas-de-negocio)
5. [Cómo se testea](#5-cómo-se-testea)

---

## 1. Visión general

Un `Tag` es una etiqueta de texto + color, de alcance organización, que se puede asignar a cualquier `Lead` (relación M2M). La asignación de tags a un lead no se gestiona desde este módulo — se hace desde `Lead` (`tag_ids` en `LeadCreate`/`LeadUpdate`, ver `lead.md` §4 y §8, método `_assign_tags`).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/tag.py` | Modelo `Tag` y tabla puente `lead_tag_association` |
| `app/controllers/tag_controller.py` | Endpoints `/tags/*` (genérico) |
| `app/services/tag_service.py` | Unicidad de nombre por organización |

---

## 2. Modelo de datos

```
Organization ──< Tag >──M2M── Lead  (tabla puente lead_tag)
```

Campos propios: `name`, `color` (default `#3B82F6`), `organization_id` (`ondelete="CASCADE"`). La tabla puente `lead_tag` tiene `ondelete="CASCADE"` en ambos extremos — si se borra el lead o la etiqueta, la asociación se limpia sola a nivel de base, sin necesidad de lógica extra en la aplicación.

`delete_strategy = HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9): a diferencia de `Nomenclator`/`LeadContactState`, acá sí se permite borrado físico — probablemente porque una etiqueta no dejaría "huecos" de integridad relevantes al desaparecer de leads históricos (a diferencia de un estado o una opción de nomenclador, que son parte del significado de un dato guardado).

---

## 3. Endpoints

`TagController` es genérico (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3), sin rutas propias. `allowed_filter_fields = {"name"}`.

---

## 4. Reglas de negocio

Única regla propia: **nombre único por organización** (case-insensitive), tanto en creación como en actualización (solo revalida si el nombre efectivamente cambió). No hay jerarquía, ni protección especial para tags "globales" (no existe el concepto acá, a diferencia de `Nomenclator`).

**[RESUELTO 2026-07-11, hallazgo #25]** `TagService.update` resolvía el objeto con una query cruda (`session.query(Tag).filter_by(id=obj_id)`), sin pasar por el repositorio tenant-aware — mismo patrón sistémico documentado en `hallazgos_agente/patron_queries_sin_tenant_filter.md` (afectaba también a `LeadContactState`, `NomenclatorItem`, `Nomenclator`, `LeadFlow`). Un `obj_id` de otra organización daba `500` en vez de `404`. Fix: ahora usa `cls.repository.get_by_id(...)`. Test de regresión: `tests/functional/test_tenant_isolation.py::TestTagIsolation::test_update_blocked_for_foreign_tag`.

---

## 5. Cómo se testea

`tests/functional/test_tags.py`: creación (éxito, nombre duplicado rechazado), actualización (éxito, nombre duplicado rechazado), y la asignación desde `Lead` (`_assign_tags`, ver `lead.md` §4/§8): asignación exitosa, limpieza de tags (`tag_ids: []`), intento de asignar una etiqueta de otra organización rechazado (`test_lead_assign_tags_hacker_fails` — confirma el aislamiento de tenant de `_assign_tags`), e ID de etiqueta inexistente rechazado.
