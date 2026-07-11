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

**Importante para escribir sobre un catálogo global:** la lectura es compartida, pero la *escritura* no — `_apply_tenant_filter(is_read_operation=False)` (ver `convenciones_generales.md` §6) solo deja tocar filas de la organización activa en el request, **nunca** las de `ADMIN_ORG_ID`, ni siquiera para un superadmin. En la práctica, para editar o borrar un `NomenclatorItem` de un catálogo global (una vez que pasó la protección de superadmin del §6) hay que mandar el request con `X-Organization-Id: <ADMIN_ORG_ID>` — operar "parado en" la organización Panel Global — y no con el header de ninguna otra organización, o el backend no encuentra la fila (`404`/error, no una edición exitosa). Esto se detectó al escribir el test de regresión de este fix (ver §7).

---

## 5. Unicidad y jerarquía

- **`Nomenclator`**: nombre único (case-insensitive) considerando tanto la organización activa **como** `ADMIN_ORG_ID` juntas — no se puede crear un nomenclador de organización que choque de nombre con uno global, ni viceversa.
- **`NomenclatorItem`**: valor único (case-insensitive) **dentro del mismo `nomenclator_id`** — dos catálogos distintos pueden tener ítems con el mismo texto sin problema.
- Al crear un `NomenclatorItem` bajo un nomenclador global (`organization_id == ADMIN_ORG_ID`, ver §6), el service fuerza `organization_id = ADMIN_ORG_ID` en el ítem nuevo también, para que herede la globalidad de su padre — independientemente de bajo qué organización estuviera operando quien lo creó.

---

## 6. [RESUELTO] La protección de nomencladores globales no se disparaba nunca

`NomenclatorItemService` (`create`, `update`, `delete`) tiene una regla explícita: "si el nomenclador padre es global, solo un superadmin puede tocar sus ítems".

**Bug (hasta 2026-07-10):** la regla estaba implementada como `if parent_nom.organization_id is None: ... requiere is_superuser`. Como se documenta en §4, **no existe ningún `Nomenclator` con `organization_id = None`** — la columna es `nullable=False` y los catálogos "globales" reales viven en `organization_id = ADMIN_ORG_ID` (un entero válido, no `None`). La condición nunca era verdadera, así que la protección nunca se activaba: cualquier usuario con permiso `nomenclator_item:create`/`update`/`delete` en su propia organización podía, si conocía el `nomenclator_id` de un catálogo global (ej. "Países"), agregar, editar o borrar ítems ahí — afectando a **todas** las organizaciones que comparten ese catálogo. Además, la lógica de "REGLA A" (herencia de globalidad al crear un item nuevo) forzaba `organization_id = None` en el item, lo cual habría violado la constraint `NOT NULL` de la columna si esa rama alguna vez hubiese llegado a ejecutarse.

**Fix aplicado:** en `app/services/nomenclator_item_service.py`, las tres comparaciones `organization_id is None` pasaron a `organization_id == ADMIN_ORG_ID` (constante importada desde `app.core.constans`), y la asignación de herencia pasó de `db_item.organization_id = None` a `db_item.organization_id = ADMIN_ORG_ID`.

**[RESUELTO 2026-07-11, hallazgo #24]** `update`/`delete` resolvían el ítem con una query cruda (`session.query(NomenclatorItem).filter_by(id=obj_id)`), sin pasar por el repositorio tenant-aware — un `obj_id` de otra organización terminaba en un `500` no manejado en vez de un `404` limpio. Fix: ahora usan `cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)`. Detalle en `hallazgos_agente/nomencladores.md`.

**[RESUELTO 2026-07-11, hallazgo #25]** El mismo patrón aparecía también en `NomenclatorService.update`/`delete` (no solo en `NomenclatorItemService`) — mismo diagnóstico y misma solución, aplicada en la misma tanda. Ver `hallazgos_agente/patron_queries_sin_tenant_filter.md` para el detalle completo (5 instancias corregidas en todo el backend). Test de regresión: `tests/functional/test_tenant_isolation.py` (`TestNomenclatorIsolation`, `TestNomenclatorItemIsolation`).

---

## 7. Cómo se testea

No hay un archivo de test dedicado al CRUD general de `Nomenclator`/`NomenclatorItem` (su uso básico se cubre indirectamente a través de campos `SELECTOR` en `test_leads.py`, `test_lead_fields.py`, `test_automation_engine.py`). La protección de catálogos globales (§6) sí tiene cobertura propia desde 2026-07-10: `tests/functional/test_nomenclators.py` — un admin de organización recibe `403` al intentar crear/editar/borrar ítems de un nomenclador global (`organization_id=ADMIN_ORG_ID`), un superadmin sí puede hacerlo (y el ítem nuevo hereda `organization_id=ADMIN_ORG_ID` correctamente), y un admin de organización sí puede operar sin restricción sobre un nomenclador de su propia organización (control negativo, para confirmar que el fix no sobre-restringe).

**Nota de la primera corrida:** la primera versión de `test_superadmin_can_update_and_delete_item_in_global_nomenclator` fallaba porque mandaba el header `X-Organization-Id` de una organización de prueba cualquiera en vez de `ADMIN_ORG_ID` — no era un bug del fix, sino la restricción de escritura documentada en §4 (la escritura nunca toca filas de `ADMIN_ORG_ID` salvo operando explícitamente "dentro" de esa organización). Se corrigió el test, no el código de producción. El resto de la suite (`test_nomenclators.py`) sigue sin poder ejecutarse en este entorno por falta de PostgreSQL — correr `pytest tests/functional/test_nomenclators.py -v` localmente para confirmar el resto de los casos antes de dar el fix por definitivo.
