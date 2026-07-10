# Hallazgo #2 — Estados de contacto (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/estados_de_contacto.md` §5
**Estado:** RESUELTO (2026-07-10)

## Qué se encontró

En `LeadContactStateService.update` (`app/services/lead_contact_state_service.py`), la variable `org_id` se calculaba **solo dentro** del bloque `if obj_in.name and obj_in.name.lower() != current_obj.name.lower():` (Regla 1, unicidad de nombre), pero se reusaba más abajo, fuera de ese bloque, dentro de la Regla 2 (`LeadContactState.organization_id == org_id`, chequeo de estado inicial único).

Si un `PUT /lead_contact_states/{id}` cambiaba `is_initial` a `True` **sin** cambiar el `name` (el caso más común: "marcar este estado como inicial" desde la UI), la Regla 1 nunca se ejecutaba, `org_id` nunca quedaba definido, y la Regla 2 lanzaba `NameError: name 'org_id' is not defined` — un `500` en vez del `400` de validación esperado.

## Fix aplicado

Se movió el cálculo de `org_id` al principio de `do_update`, antes de la Regla 1, para que esté disponible sin importar qué combinación de campos venga en el `PUT` — mismo patrón de una línea que ya usa `create`.

## Tests

`tests/functional/test_lead_contact_states.py::test_lead_contact_state_set_initial_without_changing_name_returns_400`: hace un `PUT` con `is_initial=True` sin tocar `name` y verifica que devuelva `400` (antes rompía con `500`).

Confirmado por el usuario: suite completa OK.
