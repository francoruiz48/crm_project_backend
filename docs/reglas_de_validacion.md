# Reglas de Validación (`ValidationRule`)

Documentación técnica de las reglas de validación configurables por campo, que se evalúan durante la creación/actualización de un lead (ver `lead.md` §5). Asume conocido `convenciones_generales.md` y `campos_personalizados.md` (una `ValidationRule` siempre pertenece a un `LeadField`). Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Dos formas de definir una regla: plantilla vs. expresión manual](#4-dos-formas-de-definir-una-regla-plantilla-vs-expresión-manual)
5. [Catálogo de plantillas (`STANDARD_RULES`)](#5-catálogo-de-plantillas-standard_rules)
6. [Validación de sintaxis en tiempo de configuración](#6-validación-de-sintaxis-en-tiempo-de-configuración)
7. [Ejecución en tiempo real (`LeadValidationLogic`)](#7-ejecución-en-tiempo-real-leadvalidationlogic)
8. [Reglas implícitas por tipo/subtipo de campo](#8-reglas-implícitas-por-tiposubtipo-de-campo)
9. [Cómo se testea](#9-cómo-se-testea)

---

## 1. Visión general

Una `ValidationRule` es una fórmula tipo Excel (evaluada por el mismo `ExcelFormulaEvaluatorService` que usan los campos `CALCULATED`, ver `campos_personalizados.md`) que debe devolver verdadero para que el valor de un campo se considere válido. Se puede armar de dos formas: escribiendo la fórmula a mano, o eligiendo una **plantilla** predefinida (ej. "Valor Mínimo") y completando sus parámetros — la plantilla genera la fórmula automáticamente.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/validation_rule.py` | Modelo `ValidationRule` |
| `app/controllers/validation_rule_controller.py` | Endpoints `/validation_rules/*` (genérico) |
| `app/services/validation_rule_service.py` | Lógica de plantillas, validación de sintaxis |
| `app/services/lead_validation_logic.py` | Ejecución real de las reglas al crear/actualizar un lead |
| `app/core/templates/rule_templates.py` | Catálogo `STANDARD_RULES` |
| `app/core/templates/field_rules_map.py` | Reglas implícitas por tipo/subtipo (`DEFAULT_TYPE_RULES`/`DEFAULT_SUBTYPE_RULES`), ver `campos_personalizados.md` §5 |

---

## 2. Modelo de datos

```
LeadField ──< ValidationRule
```

Campos propios: `name` (opcional), `expression` (la fórmula, opcional si viene de plantilla), `error_message` (opcional, mensaje mostrado al usuario si falla), `template_code`/`template_params` (opcionales, si la regla es "de plantilla"), `field_id` (obligatorio), `organization_id`.

`delete_strategy = HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9). `LeadField.validation_rules` tiene `cascade="all, delete-orphan"` (ver `campos_personalizados.md` §2) — las reglas se borran junto con su campo.

---

## 3. Endpoints

`ValidationRuleController` es genérico (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3), sin rutas propias. `allowed_filter_fields = {"name", "field_id", "template_code"}`. Toda la lógica de plantillas/validación vive en el service.

---

## 4. Dos formas de definir una regla: plantilla vs. expresión manual

Un `ValidationRule` es **una de las dos cosas, no ambas**, y el service lo hace cumplir:

- **De plantilla** (`template_code` + `template_params`): la `expression` se genera automáticamente (`_build_expression_from_template`, interpola los parámetros en `template.expression_fmt`). Una vez creada así, en `update` **no** se puede editar `expression` directamente — hay que mandar nuevos `template_params` y la fórmula se regenera sola. Intentar mandar `expression` a mano en una regla de plantilla es rechazado.
- **Manual** (`expression` directa, sin `template_code`): una vez creada así, **no** acepta `template_params` en ningún update posterior — es rechazado explícitamente.

Al crear con plantilla, si no se manda `name`/`error_message`, se autocompletan desde la plantilla (el `error_message` se formatea interpolando los mismos `template_params`, ej. `"El valor debe ser mayor a {min}"` → `"El valor debe ser mayor a 18"`).

---

## 5. Catálogo de plantillas (`STANDARD_RULES`)

Sembrado en código (`app/core/templates/rule_templates.py`), agrupadas por categoría: numéricas (`MIN_VALUE`, `MAX_VALUE`, `RANGE`, `EXACT_VALUE`, `NOT_ZERO`, `MULTIPLE_OF`, `IS_EVEN`, `IS_NUMBER`), texto (`MAX_LENGTH`, `MIN_LENGTH`, `EXACT_LENGTH`, `STARTS_WITH`, `ENDS_WITH`, `CONTAINS_TEXT`, `NOT_CONTAINS_TEXT`, `IS_UPPERCASE`, `IS_LOWERCASE`, `NO_SPACES`), formato (`EMAIL_FORMAT`, `ONLY_DIGITS`, `ALPHANUMERIC`, `IS_URL`, `REGEX_MATCH`), listas (`IN_LIST`, `NOT_IN_LIST`), y fechas (`DATE_FUTURE`, `DATE_PAST`, `DATE_PAST_OR_TODAY`, `MIN_AGE`, `IS_WEEKDAY`). Cada plantilla declara sus `params` obligatorios — al crear/actualizar una regla de plantilla, el service valida que todos estén presentes y no vacíos antes de generar la expresión.

---

## 6. Validación de sintaxis en tiempo de configuración

Antes de guardar cualquier regla (manual o de plantilla), `_check_expression_syntax` corre la fórmula contra un **contexto dummy** (`value`/`VALUE` con un valor de ejemplo según el tipo de campo, más variables de prueba fijas como `Edad`, `Nombre`, `Monto`, `Fecha`) usando el mismo `ExcelFormulaEvaluatorService` — así se detectan errores de sintaxis o de tipos al momento de **configurar** la regla, no recién cuando un usuario final intenta cargar un lead y la fórmula explota. Si el evaluador devuelve un string `#ERROR...` o tira excepción, se rechaza la creación/actualización de la regla.

---

## 7. Ejecución en tiempo real (`LeadValidationLogic`)

Cuando un lead se crea/actualiza (ver `lead.md` §5), por cada campo con reglas activas (`_check_field_definition` ya pasó, valor no vacío):

1. Arma un contexto con **todos** los campos del lead por nombre (`{NombreCampo: valor_tipado}`) — permite reglas cruzadas entre campos (ej. "si `Ciudad` = 'Madrid', entonces `Precio` > 100").
2. Inyecta el valor del campo actual bajo tres claves: `value`, `VALUE`, y el propio nombre del campo — para que la fórmula pueda referirse a "sí misma" de cualquiera de esas formas.
3. Evalúa cada regla activa del campo. Si el valor actual es `None`, se saltan las reglas extra (se asume que `required` ya cubrió el caso de vacío).
4. Si el evaluador devuelve un `#ERROR`, se lanza excepción señalando que la regla está **rota** (no que el dato del usuario sea inválido) — distingue explícitamente error técnico de la regla vs. dato que no la cumple.
5. Si la fórmula evalúa a falsy (`False`/`0`), se lanza con `error_message` (o un mensaje genérico si no se configuró uno).

---

## 8. Reglas implícitas por tipo/subtipo de campo

Documentado en detalle en `campos_personalizados.md` §5: al crear un `LeadField` sin plantilla de campo, se agregan automáticamente `ValidationRule`s por defecto según su tipo/subtipo (`DEFAULT_TYPE_RULES`/`DEFAULT_SUBTYPE_RULES`), nombradas `Auto-Rule (<tipo_o_subtipo>)`. Son reglas normales, editables/borrables como cualquier otra desde `/validation_rules`.

---

## 9. Cómo se testea

`tests/functional/test_validation_rules.py` y `test_validation_templates.py` (suites grandes, con tests parametrizados por plantilla): "probar regla" antes de guardar (éxito/fallo), borrado (y `404` tras borrar), creación manual (éxito/fallo de sintaxis), matemáticas (min/max), lógica de fechas, longitud de texto, parámetros vacíos rechazados, cada categoría de plantilla parametrizada (numéricas, texto, formato, listas, fechas), plantillas relacionales y condicionales (cruce entre campos). La ejecución real sobre un lead se cubre también desde `test_leads.py`/`test_simulate_lead.py` (ver `lead.md` §12).
