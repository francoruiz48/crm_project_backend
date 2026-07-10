# Flujo de Leads (`LeadFlow`, `LeadState`, `LeadStateTransition`)

Documentación técnica del embudo comercial: `LeadFlow` (el flujo en sí), `LeadState` (sus etapas/columnas) y `LeadStateTransition` (las rutas permitidas entre etapas). Se documentan como un solo módulo — igual que hicieron con `Team`+`LeadRoutingPolicy` en `equipos_y_enrutamiento.md` — porque un flujo no tiene sentido sin sus estados y transiciones. Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [El editor visual: `POST /lead_flows/graph`](#4-el-editor-visual-post-lead_flowsgraph)
5. [Reglas de validación del grafo](#5-reglas-de-validación-del-grafo)
6. [CRUD granular de estados y transiciones](#6-crud-granular-de-estados-y-transiciones)
7. [`/lead_states/{id}/next-states`](#7-lead_statesidnext-states)
8. [Relación con `Lead.change_state`](#8-relación-con-leadchange_state)
9. [Cómo se testea](#9-cómo-se-testea)

---

## 1. Visión general

Cada `Campaign` apunta a un `LeadFlow` (ver `campanas_y_workspaces.md` §5). Un `LeadFlow` es un grafo dirigido: nodos = `LeadState` (con categoría `OPEN`/`WON`/`LOST` y posición `x`/`y` para el editor visual tipo Kanban/diagrama), aristas = `LeadStateTransition` (pares `from_state_id → to_state_id` permitidos). El estado de un lead solo puede avanzar siguiendo una arista existente — no hay "saltos libres" (ver `lead.md` §7).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead_flow.py`, `lead_state.py`, `lead_state_transition.py` | Modelos |
| `app/controllers/lead_flow_controller.py` | CRUD del `LeadFlow` (genérico) |
| `app/controllers/lead_flow_graph_controller.py` | `POST /lead_flows/graph` — guarda flujo + estados + transiciones en una sola llamada |
| `app/controllers/lead_state_controller.py`, `lead_state_transition_controller.py` | CRUD granular de estados/transiciones |
| `app/services/lead_flow_orchestrator_service.py` | Lógica del editor visual (`save_graph`) |
| `app/services/lead_state_service.py`, `lead_state_transition_service.py` | Reglas de negocio del CRUD granular |

---

## 2. Modelo de datos

```
Organization ──< LeadFlow >── LeadState >── LeadStateTransition (from_state_id)
                    │              │                    │
                    │              └──< LeadStateTransition (to_state_id)
                    │
                    └──< Campaign
```

- **`LeadFlow`**: `organization_id`, `name`, `description`. `states` y `transitions` tienen `cascade="all, delete-orphan"` — se borran junto con el flujo (a nivel ORM).
- **`LeadState`**: `lead_flow_id`, `organization_id` (denormalizado, coincide con el de su flujo), `name`, `color`, `position_x`/`position_y` (coordenadas del editor visual), `category` (`OPEN`=activo, `WON`=ganado, `LOST`=perdido — determina cómo se interpreta visual y lógicamente el estado), `is_initial` (booleano), `order` (solo tiene sentido para estados `OPEN`, ordena las columnas del Kanban).
- **`LeadStateTransition`**: `lead_flow_id`, `from_state_id`, `to_state_id`. Constraint de DB: `UniqueConstraint('lead_flow_id', 'from_state_id', 'to_state_id')` — no puede haber dos transiciones idénticas en el mismo flujo.

`delete_strategy`: `LeadFlow` y `LeadState` → `SOFT_DELETE_ALWAYS`; `LeadStateTransition` → `HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9) — tiene sentido: los flujos y estados quedan como referencia histórica de leads que ya pasaron por ahí, pero las transiciones (reglas de qué se puede hacer *hacia adelante*) no necesitan preservarse una vez que dejan de estar vigentes.

---

## 3. Endpoints

`LeadFlowController` (`/lead_flows`, genérico, `enabled_methods = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "DEACTIVATE"}`) cubre el CRUD del flujo en sí (nombre/descripción), pero **no** de sus estados/transiciones vía este controller.

`LeadStateController` (`/lead_states`, `enabled_methods = READ_WRITE | {"DEACTIVATE"}`) y `LeadStateTransitionController` (`/lead_state_transitions`, `enabled_methods = {"GET_ALL", "GET_ONE", "POST", "DELETE"}` — **sin `PUT` ni `ACTIVE`**, la única forma de "cambiar" una transición es borrarla y crear otra) exponen el CRUD granular, más:

| Ruta extra | Controller | Qué hace |
|---|---|---|
| `POST /lead_flows/graph` | `lead_flow_graph_controller` (router aparte, no hereda `BaseController`) | Guarda flujo completo (nodos + aristas) en una transacción, ver §4 |
| `GET /lead_states/{id}/next-states` | `LeadStateController` | Estados de destino permitidos desde un estado dado, ver §7 |
| `POST /lead_state_transitions/bulk` | `LeadStateTransitionController` | Crea varias transiciones en un solo request |
| `PUT /lead_state_transitions/bulk` | `LeadStateTransitionController` | Reemplaza el set de transiciones (usado internamente por el editor) |

---

## 4. El editor visual: `POST /lead_flows/graph`

`LeadFlowOrchestratorService.save_graph` es el endpoint que usa el editor visual tipo diagrama de flujo: recibe el flujo completo (`{id?, name, description, states: [...], transitions: [...]}`) y hace upsert de todo en una transacción:

1. **Resolver el padre**: si `payload.id` viene, actualiza ese `LeadFlow` (validando que el nombre no colisione con otro flujo activo de la organización); si no, crea uno nuevo.
2. **Estados**: exige **exactamente un** estado marcado `is_initial=True`, y que sea de categoría `OPEN`. Los nodos nuevos se identifican con `id` negativo o `None` en el payload (convención del frontend: "-1, -2..." para nodos que todavía no existen en la base) — se crean y se arma un `id_translation_map` para que las transiciones puedan referenciarlos por su ID temporal.
3. **Orden automático**: si un estado `OPEN` no trae `order` explícito (o es `≤0`), se le asigna un contador secuencial en el orden en que aparece en el payload.
4. **Transiciones**: se traducen los IDs temporales a IDs reales vía `id_translation_map`; si una transición apunta a un estado que no está en el payload (ni es nuevo ni existente), `400`.
5. **Validación de callejones sin salida** (ver §5) — corre *antes* de tocar la base, para poder dar un error limpio sin dejar cambios a medio aplicar.
6. **Borrado**: primero borra físicamente las transiciones que ya no están en el payload (orden estricto — hay que borrar la arista antes que el nodo por FK), después hace soft-delete de los estados que dejaron de estar en el payload, validando antes que no tengan leads activos apuntándolos (`current_state_id`) — si los tiene, rechaza con el conteo.
7. **Creación**: finalmente crea las transiciones nuevas que no existían.

Toda la operación queda auditada como un único evento `UPDATED` sobre el `LeadFlow` (no se audita cada estado/transición individualmente en este flujo).

---

## 5. Reglas de validación del grafo

- Debe haber **exactamente un** estado inicial, y debe ser categoría `OPEN`.
- Todo estado `OPEN` debe tener **al menos una** transición saliente (`exits == 0` → error "callejón sin salida") — evita diseñar un flujo donde un lead pueda quedar atascado sin poder avanzar ni cerrarse. Los estados `WON`/`LOST` no tienen esta exigencia (son terminales por diseño).
- No se puede eliminar (vía omitirlo del payload) un estado que tenga leads activos actualmente en él.
- No puede haber dos flujos con el mismo nombre (case-insensitive) activos en la misma organización.

---

## 6. CRUD granular de estados y transiciones

Fuera del editor de grafo completo, también se puede operar estado por estado:

- `LeadStateService` (create/update) replica varias de las mismas reglas del orquestador (único estado inicial por flujo, inicial debe ser `OPEN`, orden sin colisión) pero a nivel de una sola entidad — usado por integraciones o formularios más simples que no necesitan reenviar el grafo completo.
- Al borrar un estado individual, si tiene leads activos, se rechaza (mismo criterio que en `save_graph`); al borrarlo con éxito, los demás estados `OPEN` se reordenan para no dejar huecos.
- `LeadStateTransitionController` no permite `PUT` individual a propósito — para cambiar una transición hay que borrarla y crear la nueva (o usar `PUT /bulk`, que reemplaza el set completo).
- Las transiciones bulk validan lo mismo que el grafo: no duplicados dentro del mismo request, estados existentes, y que el update masivo no genere un callejón sin salida.

---

## 7. `/lead_states/{id}/next-states`

`GET /lead_states/{id}/next-states` — devuelve los `LeadState` activos alcanzables desde el estado dado, ordenados por `order`. Pensado para poblar el dropdown "Mover a..." en el detalle de un lead o en una vista Kanban, sin que el frontend tenga que traer todas las transiciones del flujo y filtrar del lado cliente.

---

## 8. Relación con `Lead.change_state`

La validación real de "¿puede este lead pasar de X a Y?" vive en `LeadService.change_state` (ver `lead.md` §7), consultando `LeadStateTransitionRepository` directamente — este endpoint (`next-states`) es solo una ayuda de UI, no es la fuente de verdad de la regla de negocio (la regla real se re-valida en el propio `change_state`, así que un frontend desactualizado no puede saltarse la restricción).

---

## 9. Cómo se testea

`tests/functional/test_lead_flows_and_states.py` es una suite grande (~35 tests) que cubre: unicidad de estado inicial (crear/actualizar), auto-orden y categoría `WON`, orden duplicado rechazado, transiciones cross-flow rechazadas, duplicados de transición rechazados, ciclo de vida completo de un lead a través del flujo (con historial), "movimiento fantasma" (un lead sin estado que intenta saltar directo), nombre de flujo único por organización (crear/actualizar, y reusable tras borrar), bloqueo de cambio de `lead_flow_id` en campaña con leads (ver `campanas_y_workspaces.md` §6), borrado de estado inicial prevenido, borrado de estado reordena los `OPEN` restantes, borrado con/sin leads activos, prevención de auto-loop en transiciones, y una batería completa sobre `POST /lead_flows/graph` (creación, actualización, cada regla de validación de §5 por separado, idempotencia al guardar el mismo grafo dos veces, y conflicto de nombre).
