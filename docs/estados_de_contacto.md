# Estados de Contacto (`LeadContactState`)

Documentación técnica de los estados de contacto de un lead (ej. "Sin contactar", "Contactado", "No responde"). Es un concepto **distinto** del estado dentro del `LeadFlow` (ver `flujo_de_leads.md`): el estado de `LeadFlow` describe en qué etapa del embudo comercial está el lead (Nuevo, Calificado, Ganado...), mientras que `LeadContactState` describe el resultado del último intento de contacto, y es transversal a toda la organización (no depende de la campaña). Asume conocido `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Reglas de negocio](#4-reglas-de-negocio)
5. [Punto pendiente: bug de `org_id` no definido en `update`](#5-punto-pendiente-bug-de-org_id-no-definido-en-update)
6. [Cómo se testea](#6-cómo-se-testea)

---

## 1. Visión general

`LeadContactState` pertenece directamente a una `Organization` (no a una campaña ni a un `LeadFlow`) — todas las campañas de una organización comparten el mismo catálogo de estados de contacto. Un lead recién creado recibe automáticamente el estado de contacto marcado como `is_initial=True` de su organización, si existe uno (ver `lead.md` §4, paso 4). `OrganizationService.create` siembra estados de contacto por defecto al crear una organización nueva (ver `autenticacion.md` §10).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead_contact_state.py` | Modelo |
| `app/controllers/lead_contact_state_controller.py` | Endpoints `/lead_contact_states/*` |
| `app/services/lead_contact_state_service.py` | Reglas de unicidad de nombre y de estado inicial |

---

## 2. Modelo de datos

```
Organization ──< LeadContactState ──< Lead (contact_state_id)
```

Campos propios: `name` (máx. 100 caracteres), `color` (opcional), `is_initial` (booleano, default `False`), `order` (entero, se auto-asigna al crear), `organization_id` (`ondelete="CASCADE"` — si se borra la organización, sus estados de contacto se van con ella a nivel de base).

`delete_strategy = SOFT_DELETE_ALWAYS` (ver `convenciones_generales.md` §9): nunca se puede hard-delete un estado de contacto, solo desactivarlo — tiene sentido porque leads históricos pueden seguir referenciando el estado por `contact_state_id`.

---

## 3. Endpoints

`LeadContactStateController` es genérico (`BaseController`, `enabled_methods = READ_WRITE`, ver `convenciones_generales.md` §3), sin `ACTIVE`/`DEACTIVATE` explícitos en la lista pero heredados igual por el default de `BaseController.enabled_methods` si no se restringe — en la práctica, como es `READ_WRITE` puro (sin agregar `DEACTIVATE`), el soft delete se maneja únicamente vía `DELETE /{id}` (que ya es soft por `delete_strategy`), no hay ruta separada de desactivación explícita para este módulo. `allowed_filter_fields = {"name", "is_initial", "order"}`.

---

## 4. Reglas de negocio

`LeadContactStateService` agrega, sobre el CRUD genérico:

- **Nombre único por organización** (case-insensitive, `ilike`) — tanto en creación como en actualización.
- **Un único estado inicial por organización**: al crear o actualizar con `is_initial=True`, rechaza si ya existe otro estado marcado como inicial (pide desmarcarlo primero explícitamente, no lo reemplaza automáticamente).
- **No se puede desmarcar el único estado inicial**: si se intenta actualizar el estado que actualmente es `is_initial=True` a `is_initial=False`, se rechaza — siempre tiene que haber exactamente un estado inicial en la organización (o cero, si nunca se configuró ninguno).
- **`order` autoincremental**: se calcula solo en creación (`MAX(order) + 1` dentro de la organización), no es editable a través del payload de creación.

---

## 5. Punto pendiente: bug de `org_id` no definido en `update`

Al leer `LeadContactStateService.update` (`app/services/lead_contact_state_service.py`, líneas 60–108) se encontró lo siguiente: la variable `org_id` se calcula **solo dentro** del bloque `if obj_in.name and obj_in.name.lower() != current_obj.name.lower():` (Regla 1, línea 68), pero se **vuelve a usar** más abajo, fuera de ese bloque, dentro de la Regla 2 (línea 84: `LeadContactState.organization_id == org_id`).

Si un `PUT /lead_contact_states/{id}` cambia `is_initial` a `True` **sin** cambiar el `name` (el caso más común: "marcar este estado como inicial" desde la UI), la Regla 1 nunca se ejecuta, `org_id` nunca se define, y la línea 84 lanza `NameError: name 'org_id' is not defined` — un `500` en vez del `400` de validación esperado.

No se encontró ningún test que cubra este caso exacto (todos los tests de `is_initial` en `update` parecen ir acompañados de cambio de nombre, o no llegan a disparar la Regla 2 en ese orden — ver §6), por eso no quedó detectado.

**Solución recomendada:** mover el cálculo de `org_id` al principio de `do_update`, antes de la Regla 1, para que esté disponible sin importar qué combinación de campos venga en el `PUT` — es el mismo patrón de una línea que ya usa `create` (línea 17). No se aplicó el cambio porque este documento es solo de análisis; avisá si querés que lo corrija.

---

## 6. Cómo se testea

`tests/functional/test_lead_contact_states.py`: inyección de estados por defecto al crear una organización, creación exitosa, nombre duplicado (create y update), segundo estado inicial rechazado, y `test_lead_contact_state_prevent_uncheck_initial` (no se puede desmarcar el único inicial). No hay un test que combine "actualizar `is_initial=True` sin tocar `name`" — el escenario exacto del bug de §5 queda sin cobertura.
