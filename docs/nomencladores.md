# Nomencladores (`Nomenclator`, `NomenclatorItem`)

Documentación técnica de los catálogos de opciones usados por campos `SELECTOR`/`CHECKBOX` (ver `campos_personalizados.md` §3). Se documentan `Nomenclator` (el catálogo) y `NomenclatorItem` (sus opciones) juntos por ser inseparables. Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Nomencladores globales vs. de organización](#4-nomencladores-globales-vs-de-organización)
5. [Unicidad y jerarquía](#5-unicidad-y-jerarquía)
6. [Punto pendiente: la protección de nomencladores globales no se dispara nunca](#6-punto-pendiente-la-protección-de-nomencladores-globales-no-se-dispara-nunca)
7. [Cómo se testea](#7-cómo-se-testea)

---

## 1. Visión general

Un `Nomenclator` es un catálogo (ej. "Países", "Rubros") con una lista de `NomenclatorItem` (sus opciones, ej. "Argentina", "Brasil"). Ambos soportan jerarquía propia opcional (`parent_nomenclator_id`/`parent_item_id`, auto-referencia) — un catálogo puede tener sub-catálogos, y un ítem puede tener sub-ítems (ej. "Provincia" dependiente de "País").

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/nomenclator.py`, `nomenclator_item.py` | Modelos |
| `app/controllers/nomenclator_controller.py`, `nomenclator_item_controller.py` | Endpoints `/nomenclators/*`, `/nomenclator_items/*` |
| `app/services/nomenclator_service.py` | Unicidad de nombre |
| `app/services/nomenclator_item_service.py` | Unicidad de valor + intento de protección de catálogos globales |

---

## 2. Modelo de datos

```
Organization ──< Nomenclator >── NomenclatorItem
                     │                   │
                     └── (self, parent_nomenclator_id)
                                         └── (self, parent_item_id)
```

- **`Nomenclator`**: `name`, `parent_nomenclator_id` (opcional, auto-referencia), `organization_id` (`nullable=False`).
- **`NomenclatorItem`**: `value`, `nomenclator_id`, `parent_item_id` (opcional, auto-referencia), `organization_id` (`nullable=False`).

`delete_strategy = SOFT_DELETE_ALWAYS` para ambos (ver `convenciones_generales.md` §9) — los ítems de nomenclador quedan referenciados por `LeadFieldValue` de leads históricos (ver `campos_personalizados.md` §9), no tiene sentido borrarlos físicamente.

---

## 3. Endpoints

Ambos controllers son genéricos (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3). `NomenclatorController`: `allowed_filter_fields = {"name", "parent_nomenclator_id"}`. `NomenclatorItemController` filtra por `nomenclator_id` (ver uso en `lead_service.py` y `lead_import_export_service.py`). Toda la lógica particular está en los services, no en rutas nuevas.

---

## 4. Nomencladores globales vs. de organización

No existe un catálogo verdaderamente "sin organización" (`organization_id` es `nullable=False` en ambos modelos). Lo que el sistema llama "nomenclador global" es, en la práctica, un `Nomenclator`/`NomenclatorItem` creado con `organization_id = ADMIN_ORG_ID` (la organización especial "Panel Global", ver `autenticacion.md` §9) — sembrados así en `app/db/init_data.py::get_or_create_nomenclator` (default `org_id=ADMIN_ORG_ID`).

Gracias al comportamiento de lectura multi-tenant descripto en `convenciones_generales.md` §6, cualquier organización **ve** estos catálogos sembrados en `ADMIN_ORG_ID` en sus lecturas (`GET /nomenclators/`, `GET /nomenclator_items/`) sin que se dupliquen por organización — es el mecanismo que permite compartir catálogos como "Países" entre todos los clientes del sistema.

---

## 5. Unicidad y jerarquía

- **`Nomenclator`**: nombre único (case-insensitive) considerando tanto la organización activa **como** `ADMIN_ORG_ID` juntas — no se puede crear un nomenclador de organización que choque de nombre con uno global, ni viceversa.
- **`NomenclatorItem`**: valor único (case-insensitive) **dentro del mismo `nomenclator_id`** — dos catálogos distintos pueden tener ítems con el mismo texto sin problema.
- Al crear un `NomenclatorItem` bajo un nomenclador "global" (`organization_id is None`, ver §6 — condición que en la práctica nunca se cumple), el service intenta forzar `organization_id = None` en el ítem nuevo también, para que herede la globalidad de su padre.

---

## 6. Punto pendiente: la protección de nomencladores globales no se dispara nunca

`NomenclatorItemService` (`create`, `update`, `delete`) tiene una regla explícita: "si el nomenclador padre es global, solo un superadmin puede tocar sus ítems" — implementada como `if parent_nom.organization_id is None: ... requiere is_superuser`.

El problema: como se documenta en §4, **no existe ningún `Nomenclator` con `organization_id = None`** — la columna es `nullable=False` y los catálogos "globales" reales viven en `organization_id = ADMIN_ORG_ID` (un entero válido, no `None`). Es decir, la condición `parent_nom.organization_id is None` nunca es verdadera, y por lo tanto **la protección nunca se activa**: cualquier usuario con permiso `nomenclator_item:create`/`update`/`delete` en su propia organización puede, si conoce el `nomenclator_id` de un catálogo global (por ejemplo "Países", visible desde cualquier organización según §4), agregar, editar o borrar ítems ahí — afectando a **todas** las organizaciones que comparten ese catálogo.

No se encontró (ni se buscó exhaustivamente) si además hay un filtro de tenant a nivel de repositorio que bloquee esto en la práctica (`_apply_tenant_filter` en escritura filtra solo por el tenant actual, ver `convenciones_generales.md` §6 — como el `nomenclator_id` no se valida contra "pertenece a mi organización o soy superadmin" en ningún punto de `NomenclatorItemService.create`, el riesgo parece real).

**Recomendación:** cambiar la condición en las tres funciones de `nomenclator_item_service.py` de `parent_nom.organization_id is None` a `parent_nom.organization_id == ADMIN_ORG_ID` (importando la constante desde `app.core.constans`, ya se usa así en `nomenclator_service.py`). No se aplicó el cambio porque este documento es solo de análisis; avisá si querés que lo corrija — es la corrección con mayor impacto de seguridad encontrada en esta ronda de documentación.

---

## 7. Cómo se testea

No se encontró un archivo de test dedicado a `Nomenclator`/`NomenclatorItem` (su uso se cubre indirectamente a través de campos `SELECTOR` en `test_leads.py`, `test_lead_fields.py`, `test_automation_engine.py`). **No hay ningún test que ejercite la protección de catálogos globales** (ni para confirmar que funciona, ni que hubiera detectado el problema de §6) — es la brecha de cobertura más importante encontrada en este módulo.
