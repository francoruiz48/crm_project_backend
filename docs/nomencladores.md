# Nomencladores (`Nomenclator`, `NomenclatorItem`)

Documentación técnica de los catálogos de opciones usados por campos `SELECTOR`/`CHECKBOX` (ver `campos_personalizados.md` §3). Se documentan `Nomenclator` (el catálogo) y `NomenclatorItem` (sus opciones) juntos por ser inseparables. Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-12.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Nomencladores globales vs. de organización](#4-nomencladores-globales-vs-de-organización)
5. [Unicidad y jerarquía](#5-unicidad-y-jerarquía)
6. [Punto pendiente: la protección de nomencladores globales no se dispara nunca](#6-punto-pendiente-la-protección-de-nomencladores-globales-no-se-dispara-nunca)
7. [Cómo se testea](#7-cómo-se-testea)
8. [Feature: nomencladores dependientes (múltiples padres)](#8-feature-nomencladores-dependientes-múltiples-padres)

---

## 1. Visión general

Un `Nomenclator` es un catálogo (ej. "Países", "Rubros") con una lista de `NomenclatorItem` (sus opciones, ej. "Argentina", "Brasil"). Ambos soportan jerarquía propia opcional — desde 2026-07-12 (ver §8) como una relación **muchos-a-muchos** (`parent_nomenclators`/`parent_items`, auto-referencia vía tabla de asociación) en vez de una columna `parent_*_id` única: un catálogo puede tener sub-catálogos y **más de un catálogo padre a la vez** (ej. "Ciudades" puede depender de "País" o de "Región"), y lo mismo para los ítems.

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
        nomenclator_parent (M2M)   nomenclator_item_parent (M2M)
        (self, N padres)           (self, N padres)
```

- **`Nomenclator`**: `name`, `organization_id` (`nullable=False`), `parent_nomenclators`/`child_nomenclators` (M2M auto-referencia vía tabla `nomenclator_parent`, columnas `nomenclator_id`/`parent_nomenclator_id`, ambas `ondelete="CASCADE"`).
- **`NomenclatorItem`**: `value`, `nomenclator_id`, `organization_id` (`nullable=False`), `parent_items`/`child_items` (M2M auto-referencia vía tabla `nomenclator_item_parent`, columnas `item_id`/`parent_item_id`, ambas `ondelete="CASCADE"`).

Ambas tablas de asociación son `Table` planos (no modelos), siguiendo el mismo patrón M2M que `lead_tag_association`, `role_permissions`, etc. (ver `convenciones_generales.md`).

`delete_strategy = SOFT_DELETE_ALWAYS` para ambos (ver `convenciones_generales.md` §9) — los ítems de nomenclador quedan referenciados por `LeadFieldValue` de leads históricos (ver `campos_personalizados.md` §9), no tiene sentido borrarlos físicamente.

---

## 3. Endpoints

Ambos controllers son genéricos (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3). `NomenclatorController`: `allowed_filter_fields = {"name", "parent_nomenclator_id"}`. `NomenclatorItemController` filtra por `nomenclator_id`, `parent_item_id` (ver uso en `lead_service.py` y `lead_import_export_service.py`). Toda la lógica particular está en los services, no en rutas nuevas.

Los filtros `?parent_nomenclator_id=`/`?parent_item_id=` en `GET /nomenclators/`/`GET /nomenclator_items/` siguen funcionando igual que antes de la migración a M2M (§8) — el frontend no necesita cambiar nada para las cascadas de selects. Por dentro ya no son una comparación de columna (`BaseRepository.get_all` no sabe filtrar por relaciones M2M), sino un `JOIN` explícito contra la tabla de asociación, agregado en overrides de `get_all` en `NomenclatorRepository`/`NomenclatorItemRepository`.

Para declarar/reemplazar los padres de un catálogo o de un ítem se usa `parent_nomenclator_ids`/`parent_item_ids` (listas de ids) en el body de `POST`/`PUT` — ver §8.

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
- Jerarquía (M2M, §8): existencia de los ids de padre declarados (`400` si alguno no existe), sin auto-referencia (`400` si un catálogo/ítem se declara padre de sí mismo) y sin ciclos (`400` si la combinación de padres formaría un ciclo, ej. A→B→A) — ver §8 para el detalle de cada chequeo.

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

La cobertura de la feature de nomencladores dependientes (§8) vive en un archivo aparte: `tests/functional/test_nomenclator_dependencies.py` — ver detalle en §8.

---

## 8. Feature: nomencladores dependientes (múltiples padres)

**Objetivo (pedido por el usuario, 2026-07-12):** que un campo tipo `SELECTOR`/`CHECKBOX` cuyo catálogo depende lógicamente de otro (ej. "Ciudad" depende de "País") solo ofrezca ítems hijos del valor elegido en el campo padre, con dos condiciones explícitas: (1) la dependencia se declara **a nivel de campo** (`LeadField.depends_on_field_id`), no a nivel de catálogo, porque el mismo catálogo puede usarse en más de un campo con relaciones padre distintas o sin relación alguna — declararlo en el catálogo sería ambiguo; (2) un catálogo puede tener **más de un catálogo padre válido** (ej. "Ciudades" depende de "País" *o* de "Región" según el caso), así que la jerarquía de catálogos/ítems pasó de columna única (`parent_nomenclator_id`/`parent_item_id`) a relación M2M (§2).

### 8.1 Diseño (2 niveles)

**Nivel catálogo (M2M, este documento):** `Nomenclator.parent_nomenclators` y `NomenclatorItem.parent_items` — declaran qué catálogos/ítems son ancestros válidos. Es la fuente de verdad para la consistencia estructural.

**Nivel campo (`LeadField.depends_on_field_id`, ver `campos_personalizados.md`):** un único padre por campo (no M2M — Franco confirmó que a nivel de campo alcanza con un solo padre, distinto del nivel catálogo donde sí puede haber varios). Permite cadenas (A depende de B que depende de C). Se valida que el campo padre esté en la misma campaña, sea también de tipo nomenclador, y que su catálogo esté entre los padres válidos declarados del catálogo de este campo.

### 8.2 Validaciones implementadas

| Capa | Validación | Dónde |
|---|---|---|
| `Nomenclator.create`/`update` | Los ids en `parent_nomenclator_ids` existen | `nomenclator_service.py::_resolve_parents` |
| `Nomenclator.update` | Sin auto-referencia, sin ciclos | `nomenclator_service.py::_would_create_cycle` |
| `NomenclatorItem.create`/`update` | Los ids en `parent_item_ids` existen **y** cada ítem padre pertenece a un catálogo declarado como padre válido del catálogo de este ítem | `nomenclator_item_service.py::_resolve_and_validate_parent_items` |
| `NomenclatorItem.update` | Sin auto-referencia, sin ciclos | `nomenclator_item_service.py::_would_create_cycle` |
| `LeadField.create`/`update` (`depends_on_field_id`) | Ambos campos son tipo nomenclador (`NOMENCLATOR_FIELD_TYPES`), misma campaña, catálogo del campo padre es padre válido del catálogo de este campo | `lead_field_service.py::_validate_depends_on_field` |
| `LeadField.update` | Sin auto-referencia, sin ciclos en la cadena de `depends_on_field_id` | `lead_field_service.py::_would_create_field_dependency_cycle` |
| `LeadField.delete`/`deactivate` | Bloqueado (`400`) si otros campos activos dependen de él (`depends_on_field_id` apuntando a este campo) | `lead_field_service.py::_assert_no_active_dependents` |
| `Lead.create`/`update` | El/los ítem(s) elegido(s) en el campo hijo deben ser hijos (M2M) del/los ítem(s) elegido(s) en el campo padre — semántica OR si el padre es de selección múltiple | `lead_service.py::_validate_processed_data` |

### 8.3 Reemplazo completo de la lista de padres en `PUT`

`parent_nomenclator_ids`/`parent_item_ids`/`depends_on_field_id` en un `PUT` **reemplazan** la relación completa, no hacen merge (ej. mandar `parent_nomenclator_ids: [5]` deja al catálogo con el padre 5 únicamente, aunque antes tuviera además el padre 3). Es la opción "reemplazar limpio" que Franco confirmó como preferida frente a alternativas de merge incremental.

### 8.4 Validación de leads: valor del padre no incluido en un `PUT` parcial

Si un `PUT /leads/{id}` no incluye el campo padre (ej. solo se está editando el campo hijo), la validación usa el valor del padre **ya persistido** en la base — no lo ignora. Esto no requirió código nuevo: `lead_service.py::update()` ya arma `full_context = {**db_values, **incoming_data}` para otras validaciones (mezcla el estado persistido con lo que vino en el request), y la nueva validación de dependencia reutiliza `full_context.get(depends_on_field_id)` tal cual. En `Lead.create` no hay estado persistido previo, así que si el campo padre no viene en el payload, la validación falla (`400`, "todavía no tiene un valor asignado").

### 8.5 Semántica OR para padres de selección múltiple

Si el campo padre es `SELECTOR_MULTIPLE`/`CHECKBOX` (varios ítems seleccionados a la vez), el hijo es válido si es descendiente de **cualquiera** de los ítems padre elegidos (no de todos). Opción confirmada explícitamente por Franco frente a la alternativa AND.

### 8.6 Cómo se testea

`tests/functional/test_nomenclator_dependencies.py`, 6 clases:

- `TestNomenclatorMultipleParents` / `TestNomenclatorItemMultipleParents`: creación y reemplazo de múltiples padres, existencia, auto-referencia, ciclos, consistencia catálogo↔ítem.
- `TestLeadFieldDependsOnField`: alta/edición de `depends_on_field_id` con las 6 validaciones de la tabla §8.2 (tipo, campaña, consistencia de catálogo, auto-referencia, ciclo, bloqueo de borrado/desactivación con dependientes).
- `TestLeadDependentFieldValidation`: alta/edición de leads — coincidencia padre/hijo exitosa, hijo no descendiente del padre (`400`), padre sin valor (`400`), `PUT` parcial usa el valor persistido del padre (§8.4), semántica OR con padre multi-selección (§8.5).
- `TestNomenclatorItemParentFilter`: confirma que `GET /nomenclator_items/?parent_item_id=` sigue devolviendo solo los hijos directos tras la migración a M2M (§3).

**Nota:** igual que el resto de la suite, no pudo ejecutarse en este entorno por falta de PostgreSQL (ver §7) — verificado en su lugar con `ast.parse()` (sintaxis), `configure_mappers()` de SQLAlchemy (relaciones M2M bien declaradas) e imports completos de todos los módulos tocados. Correr `pytest tests/functional/test_nomenclator_dependencies.py -v` localmente antes de dar la feature por definitiva.
