# Campos Personalizados (`LeadField`)

Documentación técnica del sistema de campos dinámicos de una campaña: definición del campo (`LeadField`), su tipo/subtipo (`LeadFieldType`/`LeadFieldSubtype`), su agrupación visual (`LeadFieldSection`) y el valor que toma en cada lead (`LeadFieldValue`). Se documentan juntos porque son 5 tablas que solo tienen sentido como una unidad — es el sistema de "campos personalizados" del CRM. Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Catálogo de tipos y subtipos](#3-catálogo-de-tipos-y-subtipos)
4. [Endpoints](#4-endpoints)
5. [Creación de un campo (`create_within_session`)](#5-creación-de-un-campo-create_within_session)
6. [Restricciones históricas (campañas con leads existentes)](#6-restricciones-históricas-campañas-con-leads-existentes)
7. [Actualización y recálculo masivo de fórmulas](#7-actualización-y-recálculo-masivo-de-fórmulas)
8. [Reordenamiento (`/reorder/bulk`)](#8-reordenamiento-reorderbulk)
9. [`LeadFieldValue`: cómo se guarda el valor](#9-leadfieldvalue-cómo-se-guarda-el-valor)
10. [Cómo se testea](#10-cómo-se-testea)

---

## 1. Visión general

Cada `Campaign` define su propio conjunto de campos (`LeadField`) — no hay un esquema fijo de "lead": todo dato de negocio (nombre, teléfono, presupuesto, etc.) es un `LeadField` configurado por campaña. Un campo tiene un tipo (`STRING`, `INT`, `DATE`, `SELECTOR`, `FILE`, `CALCULATED`, `LEAD`...) y opcionalmente un subtipo (ej. `SELECTOR` → `SELECTOR_SIMPLE`/`SELECTOR_MULTIPLE`/`CHECKBOX_SIMPLE`/`CHECKBOX_MULTIPLE`) que determina reglas de validación por defecto y máscaras de input sugeridas.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead_field.py` | Modelo `LeadField` (la definición del campo) |
| `app/models/lead_field_type.py` / `lead_field_subtype.py` | Catálogos de tipo/subtipo (semilla fija, ver §3) |
| `app/models/lead_field_section.py` | Agrupación visual de campos ("Información básica", etc.) |
| `app/models/lead_field_value.py` | El valor concreto de un campo en un lead puntual |
| `app/controllers/lead_field_controller.py` | Endpoints `/lead_fields/*` |
| `app/services/lead_field_service.py` | Toda la lógica de creación/actualización/reorder (~650 líneas, el service más grande después de `Lead`) |
| `app/core/templates/field_templates.py` | Plantillas estándar (`STANDARD_FIELD_TEMPLATES`) que prearman tipo + reglas de validación |
| `app/core/templates/field_rules_map.py` | Reglas y máscaras implícitas por tipo/subtipo (`DEFAULT_TYPE_RULES`, `DEFAULT_SUBTYPE_RULES`, `STANDARD_INPUT_MASKS`) |

---

## 2. Modelo de datos

```
Campaign ──< LeadField >── LeadFieldType (field_type_code)
   │              │
   │              ├──> LeadFieldSubtype (field_subtype_code, opcional)
   │              ├──> LeadFieldSection (lead_field_section_id)
   │              ├──> Nomenclator (nomenclator_id, opcional — para SELECTOR/CHECKBOX)
   │              ├──> Campaign (related_campaign_id, opcional — para tipo LEAD)
   │              └──< ValidationRule (cascade delete-orphan)
   │
   └──< Lead >── LeadFieldValue >── LeadField
                       │
                       ├──M2M── NomenclatorItem (lead_field_value_nomenclator)
                       └──M2M── Lead (lead_field_value_leads, related_leads — campos tipo LEAD)
```

Campos propios de `LeadField` (además de `BaseModelDB`): `name`, `required`, `default_value`, `is_primary` (identificador de duplicados, ver `lead.md` §5), `input_mask`, `order`, `is_visible`, `calculation_expression` (solo `CALCULATED`), `configuration` (JSON libre), `title_order` (define qué campos arman el "título" visible de un lead relacionado, ver `lead.md` §8), `field_template_code`/`field_template_name` (si se creó desde una plantilla).

`LeadFieldSection` solo tiene `name` y `color`, agrupa campos visualmente dentro de una organización (no de una campaña). `LeadFieldValue.value` **siempre se guarda como texto** — la interpretación al tipo real (`int`, `float`, `date`, etc.) ocurre en la capa de servicio (`lead_service.py::_convert_value_by_type`), nunca en la base.

`delete_strategy` por entidad (ver también `convenciones_generales.md` §9):

| Entidad | Estrategia |
|---|---|
| `LeadField` | `SMART_DELETE` — hard delete si no tiene `LeadFieldValue`/`ValidationRule` asociados, soft delete si ya se usó |
| `LeadFieldSection` | `SOFT_DELETE_ALWAYS` |
| `LeadFieldSubtype` / `LeadFieldType` | `PROTECTED` — catálogo fijo del sistema, no editable en runtime |
| `LeadFieldValue` | `HARD_DELETE_ALWAYS` |

---

## 3. Catálogo de tipos y subtipos

Sembrados en `app/db/init_data.py` (no hay endpoint de escritura para `LeadFieldType`/`LeadFieldSubtype`, son `PROTECTED` y de solo lectura vía API):

| `LeadFieldType.code` | Subtipos (`LeadFieldSubtype.code`) |
|---|---|
| `STRING` | `EMAIL`, `URL`, `WEBSITE`, `SOCIAL_MEDIA`, `WHATSAPP`, `MOBILE`, `PHONE`, `LANDLINE`, `SIMPLE_ADDRESS`, `MAPS_URL`, `COORDINATES`, `HTML`, `MARKDOWN`, `PASSWORD` |
| `INT` | — |
| `NUMBER` | `MONEY`, `PERCENTAGE`, `STAR_RATING`, `NPS`, `SCORE` |
| `DATE` | `DATE_ONLY` (default si no se especifica), `BIRTH_DATE` |
| `DATE_TIME` | `TIME_ONLY`, `DATE_EVENT` |
| `BOOL` | — |
| `SELECTOR` | `SELECTOR_SIMPLE`, `SELECTOR_MULTIPLE`, `CHECKBOX_SIMPLE`, `CHECKBOX_MULTIPLE` — **subtipo obligatorio** |
| `FILE` | `FILE_IMAGE`, `FILE_DOCUMENT` — **subtipo obligatorio** |
| `CALCULATED` | — (requiere `calculation_expression`, nunca `required`/`is_primary`) |
| `LEAD` | — (requiere `related_campaign_id`, relación a otro lead) |

---

## 4. Endpoints

`LeadFieldController` (`/lead_fields`, `enabled_methods = READ_WRITE | {"DEACTIVATE"}`, ver `convenciones_generales.md` §3) es genérico salvo por una ruta extra:

| Método y ruta | Qué hace |
|---|---|
| CRUD estándar | `GET /`, `GET /{id}`, `POST /`, `PUT /{id}`, `DELETE /{id}`, `PUT /active/{id}`, `DELETE /active/{id}` |
| `PATCH /lead_fields/reorder/bulk` | Reordena varios campos de una campaña en una sola llamada (ver §8) |

`allowed_filter_fields` habilita filtrar `GET /` por `name`, `required`, `is_primary`, `order`, `is_visible`, `campaign_id`, `nomenclator_id`, `related_campaign_id`, `field_type_code`, `lead_field_section_id`, `field_subtype_code`.

`LeadFieldSection`, `LeadFieldSubtype` y `LeadFieldType` tienen sus propios controllers (`lead_field_section_controller.py`, `lead_field_subtype_controller.py`, `lead_field_type_controller.py`) — genéricos, sin lógica propia; los dos últimos son de solo catálogo (`PROTECTED`, no tiene sentido exponer `POST`/`PUT`/`DELETE` reales aunque el router los registre, cualquier intento de borrado los rechaza).

---

## 5. Creación de un campo (`create_within_session`)

Es el flujo más elaborado del módulo. Puntos clave:

- **Plantillas** (`field_template_code`): si se manda, trae tipo, nombre por defecto, máscara y **reglas de validación predefinidas** (`STANDARD_FIELD_TEMPLATES`) — ej. crear un campo "Email" ya trae la regla de formato de email sin configurarla a mano.
- **Sección por defecto**: si no se manda `lead_field_section_id`, usa la sección más antigua (`id` más bajo) de la organización — asume que siempre existe al menos una (la crea `OrganizationService.create`, ver `autenticacion.md` §10). Si no existe ninguna, es un error de integridad de datos, no de request.
- **Máscara inteligente**: si no viene `input_mask` explícito, se resuelve en cascada: `mask_template_code` (catálogo `STANDARD_INPUT_MASKS`) → máscara por defecto del subtipo (`DEFAULT_SUBTYPE_MASKS`) → máscara por defecto del tipo (`DEFAULT_TYPE_MASKS`).
- **Validaciones cruzadas de tipo**: `SELECTOR`/`FILE` exigen subtipo explícito; `DATE` sin subtipo cae a `DATE_ONLY` automáticamente; `nomenclator_id` solo es válido si el tipo está en `NOMENCLATOR_FIELD_TYPES`; `related_campaign_id` es obligatorio si y solo si el tipo es `LEAD`; `default_value` no tiene sentido en campos de nomenclador/`LEAD` (se descarta silenciosamente, no rompe el request); `CALCULATED` fuerza `required=False` e `is_primary=False` y exige `calculation_expression`.
- **Un campo oculto no puede ser obligatorio ni primario** (`is_visible=False` + `required`/`is_primary=True` → error).
- **Reglas implícitas**: si no vino de una plantilla, se agregan automáticamente las reglas por defecto del tipo/subtipo (`DEFAULT_TYPE_RULES`/`DEFAULT_SUBTYPE_RULES`) como `ValidationRule` nombradas `Auto-Rule (<origen>)` — ver `reglas_de_validacion.md`.
- **Retro-inicialización**: si la campaña ya tiene leads, al crear el campo se generan sus `LeadFieldValue` para todos los leads existentes (`initialize_values_for_new_field`), con el `default_value` si aplica.

---

## 6. Restricciones históricas (campañas con leads existentes)

`_check_historic_constraints` protege la integridad de datos ya cargados:

- No se puede marcar un campo como `required=True` si ya existen leads activos con ese campo vacío (dejaría datos "obligatorios" incompletos retroactivamente).
- No se puede marcar `is_primary=True` si la campaña ya tiene leads — el chequeo de duplicados de `lead.md` §5 depende de que los campos primarios estén definidos *antes* de que existan datos, para no generar falsos duplicados sobre datos históricos.
- Al **crear** un campo (no solo actualizar), si la campaña ya tiene leads, tampoco se permite crearlo directamente como `required`/`is_primary` — mismo motivo.

---

## 7. Actualización y recálculo masivo de fórmulas

Además de las mismas validaciones de creación (unicidad de nombre/orden, restricciones históricas, sección válida), `update` tiene un caso especial: si cambia `calculation_expression` de un campo `CALCULATED`, dispara `_recalculate_leads_formula`, que recorre **todos** los leads de la campaña, reconstruye el contexto de variables con los valores actuales de cada lead, y recalcula/persiste el nuevo valor de ese campo para cada uno. Es una operación potencialmente pesada (todos los leads de la campaña, uno por uno, sin batching) — a tener en cuenta en campañas con volumen alto.

`set_active` (reactivar un campo soft-deleted) revalida nombre único, y si el `order` que tenía quedó ocupado por otro campo mientras estaba inactivo, lo reasigna automáticamente al siguiente disponible (`max_order + 1`) en vez de fallar.

---

## 8. Reordenamiento (`/reorder/bulk`)

Recibe una lista `{field_id, order}` y una `campaign_id`. Antes de aplicar nada, valida el **universo completo** de campos activos de la campaña (los que cambian y los que no) para detectar colisiones de `order` — no alcanza con validar solo los que vienen en el request, porque uno nuevo podría chocar con uno que se queda quieto. Si hay colisión, rechaza todo el batch con `400` señalando los dos campos en conflicto. Cada cambio real de orden queda auditado individualmente en `SystemAuditLog`.

---

## 9. `LeadFieldValue`: cómo se guarda el valor

- **Tipos simples** (`STRING`, `INT`, `NUMBER`, `BOOL`, `DATE`, `DATE_TIME`, `CALCULATED`): en la columna `value` (texto).
- **Nomencladores** (`SELECTOR`/`CHECKBOX`): en la tabla puente `lead_field_value_nomenclator` (M2M contra `NomenclatorItem`), `value` queda `NULL`. Se carga siempre (`lazy="selectin"`).
- **Tipo `LEAD`** (relación entre leads): en la tabla puente `lead_field_value_leads` (M2M contra `Lead`, con `ondelete="CASCADE"` en ambos extremos — si se borra el lead origen o el relacionado, la fila puente se limpia sola). Se carga siempre (`lazy="joined"`).

---

## 10. Cómo se testea

`tests/functional/test_lead_fields.py` (CRUD, validaciones de tipo/subtipo, unicidad de nombre/orden, restricciones históricas), `test_lead_field_templates.py` (creación desde plantilla, con y sin validación exitosa). La interacción con la carga real de valores en un lead se cubre desde `test_leads.py` (ver `lead.md` §12).
