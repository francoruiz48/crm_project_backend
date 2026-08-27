# Automatización de Campos (`FieldAutomation`)

Documentación técnica del motor de reglas "si se cumple esta condición, modificá este otro campo" que corre sobre los campos dinámicos de un lead. Asume conocido `convenciones_generales.md` y el pipeline de creación/actualización de `lead.md` (`AutomationEngine.run` se invoca ahí, en los eventos `ON_CREATE`/`ON_UPDATE`). Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [El motor (`AutomationEngine.run`)](#4-el-motor-automationenginerun)
5. [Condiciones: operadores y valores dinámicos](#5-condiciones-operadores-y-valores-dinámicos)
6. [Acciones disponibles](#6-acciones-disponibles)
7. [Protecciones contra bucles y JSON malicioso](#7-protecciones-contra-bucles-y-json-malicioso)
8. [Auditoría de cambios automáticos](#8-auditoría-de-cambios-automáticos)
9. [Cómo se testea](#9-cómo-se-testea)

---

## 1. Visión general

Una `FieldAutomation` (regla) pertenece a una `Campaign`, escucha uno o más eventos (`trigger_events`: `ON_CREATE`, `ON_UPDATE`), evalúa un árbol de condiciones (`conditions`, JSON anidado con grupos `AND`/`OR`) sobre los valores del lead que se está creando/actualizando, y si matchea, ejecuta una lista de `actions` que mutan otros campos del mismo lead (ej. "si `Prioridad` = Alta, entonces `Fecha límite` = hoy + 3 días").

El motor corre **dentro** del pipeline de `LeadService.create`/`update` (ver `lead.md` §4 y §8), antes de persistir — nunca es un job asíncrono ni corre fuera del request.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/field_automation.py` | Modelo `FieldAutomation` |
| `app/controllers/field_automation_controller.py` | Endpoints `/field_automations/*` (genérico) |
| `app/services/field_automation_service.py` | No valida el árbol de condiciones al crear/editar una regla más allá de lo que valida Pydantic. **[RESUELTO, hallazgo #20, 2026-07-10]** Sobreescribe `create` para validar que `campaign_id` pertenezca a la organización activa (antes no lo hacía — `FieldAutomation` no tiene columna `organization_id` propia, así que el aislamiento de tenant automático no aplicaba por sí solo; cualquier usuario autenticado podía crear/editar/borrar reglas en campañas de otra organización). Detalle en `hallazgos_agente/automatizacion_de_campos.md`. |
| `app/services/automation_engine.py` | El motor: evaluación de condiciones + aplicación de acciones |
| `app/schemas/field_automation_schema.py` | `RuleGroup`, `RuleCondition`, `AutomationAction`, enums de operadores/acciones |

---

## 2. Modelo de datos

```
Campaign ──< FieldAutomation
```

Campos propios: `campaign_id` (`ondelete="CASCADE"` — si se borra la campaña, las reglas se van con ella a nivel de base), `name`, `description`, `trigger_events` (`ARRAY(String)`, ej. `["ON_CREATE", "ON_UPDATE"]`), `conditions` (`JSONB`, árbol recursivo `RuleGroup`), `actions` (`JSONB`, lista de `AutomationAction`), `priority` (entero, determina orden de evaluación — **menor = se evalúa antes**), `active`.

`delete_strategy = HARD_DELETE_WITH_TOGGLE` (ver `convenciones_generales.md` §5 y §9): `DELETE /field_automations/{id}` es físico e irreversible; `DELETE /active/{id}` es la forma de "pausar sin borrar" una regla.

**Nota:** `conditions` y `actions` no tienen validación de esquema a nivel de servicio al crear/editar la regla — solo lo que Pydantic valida en `schema_in` (`RuleGroup`/`AutomationAction`). La validación semántica real (¿el `field_id` referenciado existe en la campaña? ¿el operador es válido para ese tipo de campo?) ocurre recién en tiempo de ejecución, dentro de `AutomationEngine.run`, envuelta en un `try/except` que **descarta silenciosamente** la regla si falla (ver §4) — una regla mal configurada no rompe la creación del lead, pero tampoco avisa al usuario que se creó una regla que nunca va a disparar.

---

## 3. Endpoints

`FieldAutomationController` es 100% genérico (`BaseController`, `enabled_methods = READ_WRITE | {"DEACTIVATE"}`, ver `convenciones_generales.md` §3), sin rutas propias. `allowed_filter_fields = {"description", "name", "campaign_id"}`. No existe un endpoint de "probar regla" equivalente al `/leads/simulate` de `Lead` — para ver si una regla dispara hay que crear/actualizar un lead real (o usar `/leads/simulate`, que sí corre el motor).

---

## 4. El motor (`AutomationEngine.run`)

`run(session, campaign_id, context_data, event)` — `context_data` es el mismo dict `{field_id: valor}` que arma `LeadService` durante creación/actualización:

1. Trae las reglas **activas** de la campaña cuyo `trigger_events` contenga el `event` actual, ordenadas por `priority` ascendente.
2. Si no hay reglas, devuelve el contexto sin tocar.
3. Corre en un **bucle de cascada** (ver §7): evalúa todas las reglas en orden; si alguna acción cambió un valor, vuelve a evaluar todas las reglas desde el principio (una regla puede depender del resultado de otra) — hasta `MAX_CASCADES=5` iteraciones.
4. Por cada regla: parsea `conditions` a `RuleGroup` y `actions` a lista de `AutomationAction` (validación Pydantic tardía, recién acá); si el parseo o la evaluación tira excepción, la regla se **salta** (`continue`), sin abortar el resto del pipeline — solo imprime un warning por consola, no queda registro visible para el usuario.
5. Devuelve `(context_data mutado, audit_log)` — el `audit_log` es lo que después usa `LeadService` para mostrar `source_rule` en el historial legible del lead (ver `lead.md` §8).

---

## 5. Condiciones: operadores y valores dinámicos

`RuleCondition` = `{field_id, operator, value}`. Operadores soportados (`ConditionOperatorEnum`): `IS_EMPTY`, `IS_NOT_EMPTY`, `EQUALS`, `NOT_EQUALS`, `CONTAINS`, `NOT_CONTAINS`, `GREATER_THAN`, `LESS_THAN`, `STARTS_WITH`, `ENDS_WITH`, `IS_PAST`, `IS_FUTURE`.

Notas de comportamiento:

- `EQUALS`/`NOT_EQUALS`/`CONTAINS`/`NOT_CONTAINS` normalizan a `set` de strings — comparan por contenido, no por orden, y toleran listas vs. valores sueltos indistintamente.
- `GREATER_THAN`/`LESS_THAN` intentan comparación numérica primero (`float()`); si falla, caen a comparación de strings (orden alfabético) en vez de tirar error.
- `IS_PAST`/`IS_FUTURE` parsean el valor como fecha (`DATE_TIME_FORMAT` primero, `DATE_FORMAT` después); si no matchea ningún formato, la condición es `False`.
- `value` soporta placeholders dinámicos resueltos en el momento de evaluar: `{{CURRENT_DATE}}`, `{{CURRENT_DATETIME}}`, `{{YESTERDAY}}`, `{{TOMORROW}}`.
- Los grupos (`RuleGroup`) son recursivos: cada nodo puede ser otro `RuleGroup` (con su propio operador `AND`/`OR`) o una `RuleCondition` — permite armar condiciones anidadas arbitrariamente complejas, dentro del límite de profundidad (§7).

---

## 6. Acciones disponibles

Cada `AutomationAction` tiene `type` (`ActionTypeEnum`) y `target_field_id` (el campo que muta):

| Tipo | Efecto |
|---|---|
| `SET_VALUE` | Asigna `action.value` literal. |
| `CLEAR_VALUE` | Vacía el campo (`None`). |
| `SET_CURRENT_DATE` / `SET_CURRENT_DATETIME` | Fecha/hora actual (UTC). |
| `COPY_FROM_FIELD` | Copia el valor de `source_field_id`, solo si ese campo tiene valor no vacío (si no, no toca el destino). |
| `INCREMENT` / `DECREMENT` | Suma/resta `action.value` (o 1 por default) al valor numérico actual (`0` si estaba vacío). |
| `APPEND_TO_LIST` | Agrega elementos a una lista, sin duplicar. |
| `REMOVE_FROM_LIST` | Quita elementos de una lista. |
| `SET_DATE_OFFSET` | Fecha actual + `action.value` días (puede ser negativo). |
| `SET_VALUE_IF_EMPTY` | Solo asigna si el destino está vacío — no pisa un valor ya cargado. |
| `NORMALIZE_TEXT` | `UPPERCASE` / `LOWERCASE` / trim (default) sobre el texto actual. |
| `CONCAT_FIELDS` | Concatena varios `source_field_ids` con un separador, ignorando los que estén vacíos. |

Una acción solo se considera "cambio real" (y por lo tanto dispara auditoría y re-evaluación en cascada) si el valor nuevo, comparado como string, difiere del anterior — evita ruido de auditoría por "cambios" que en realidad no modifican nada.

---

## 7. Protecciones contra bucles y JSON malicioso

Dos límites duros, pensados porque `conditions`/`actions` son JSON libre configurado por el usuario (potencial vector de abuso):

- **`MAX_CASCADES = 5`**: tope de iteraciones del bucle de re-evaluación. Si dos reglas se retroalimentan infinitamente (regla A cambia el campo que dispara la regla B, que cambia el campo que dispara A...), el motor corta a la quinta vuelta y sigue con el valor que quedó en ese momento — no se cuelga, pero el resultado final puede no ser el "estado estable" esperado si el ciclo nunca converge.
- **`MAX_JSON_DEPTH = 10`**: tope de anidamiento de grupos de condiciones. Un árbol con más de 10 niveles de profundidad corta la evaluación de esa rama (la trata como no cumplida) en vez de arriesgar un stack overflow por recursión.

Ambos casos están cubiertos explícitamente por tests (`test_vulnerability_infinite_loop_prevention`, `test_vulnerability_max_json_depth_prevention`, ver §9) — son protecciones deliberadas, no efectos secundarios accidentales.

---

## 8. Auditoría de cambios automáticos

Cada campo mutado por una regla queda en `audit_log[field_id] = {old_value, new_value, source_rule}`. Si **varias** reglas tocan el mismo campo en la misma corrida (incluso a través de distintas iteraciones de cascada), `source_rule` se va concatenando (`"Regla A -> Regla B"`) para que quede rastro de la cadena completa, no solo la última que escribió. Este `audit_log` es lo que `LeadService` usa para marcar `source_rule` en `LeadActivityHistory` (ver `lead.md` §8) — el usuario final ve en el timeline del lead qué campos cambiaron solos y por qué regla.

---

## 9. Cómo se testea

`tests/functional/test_automation_engine.py` (~40 tests) es una de las suites más exhaustivas del backend: disparo en `ON_CREATE`/`ON_UPDATE`, rastro de auditoría, condición no cumplida (no hay cambio), operador `OR`, grupos anidados, cada acción por separado (`CLEAR_VALUE`, `COPY_FROM_FIELD`, `SET_CURRENT_DATETIME`, `INCREMENT`/`DECREMENT`, `SET_DATE_OFFSET`, `SET_VALUE_IF_EMPTY`, `NORMALIZE_TEXT` en sus 3 modos, `CONCAT_FIELDS`, `APPEND_TO_LIST`/`REMOVE_FROM_LIST`), múltiples reglas sobre el mismo campo ("gana la última"), efecto cascada y su límite, cada operador de condición por separado (incluidos los placeholders dinámicos como `{{YESTERDAY}}`), los dos tests de "vulnerabilidad" del §7, y casos negativos (regla desactivada no dispara, regla con el evento equivocado no dispara).
