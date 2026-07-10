# Hallazgo #1 — Nomencladores (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/nomencladores.md` §6
**Estado:** RESUELTO (2026-07-10)

## Qué se encontró

`NomenclatorItemService` (`create`, `update`, `delete`) tiene una regla explícita: "si el nomenclador padre es global, solo un superadmin puede tocar sus ítems". Estaba implementada como `if parent_nom.organization_id is None: ... requiere is_superuser`. No existe ningún `Nomenclator` con `organization_id = None` — la columna es `nullable=False` y los catálogos "globales" reales viven en `organization_id = ADMIN_ORG_ID` (un entero válido, no `None`). La condición nunca era verdadera, así que la protección nunca se activaba: cualquier usuario con permiso `nomenclator_item:create`/`update`/`delete` en su propia organización podía agregar, editar o borrar ítems de un catálogo global (ej. "Países"), afectando a todas las organizaciones que lo comparten.

Además, la "REGLA A" (herencia de globalidad al crear un item nuevo) forzaba `organization_id = None` en el item, lo cual habría violado la constraint `NOT NULL` de la columna si esa rama alguna vez hubiese llegado a ejecutarse.

## Fix aplicado

En `app/services/nomenclator_item_service.py`, las tres comparaciones `organization_id is None` pasaron a `organization_id == ADMIN_ORG_ID` (constante importada desde `app.core.constans`), y la asignación de herencia pasó de `db_item.organization_id = None` a `db_item.organization_id = ADMIN_ORG_ID`.

## Tests

`tests/functional/test_nomenclators.py` (6 casos): un admin de organización recibe `403` al intentar crear/editar/borrar ítems de un nomenclador global, un superadmin sí puede hacerlo (y el ítem nuevo hereda `organization_id=ADMIN_ORG_ID` correctamente), y un admin de organización sí puede operar sin restricción sobre un nomenclador de su propia organización (control negativo).

**Nota de la primera corrida:** la primera versión de `test_superadmin_can_update_and_delete_item_in_global_nomenclator` fallaba porque mandaba el header `X-Organization-Id` de una organización de prueba cualquiera en vez de `ADMIN_ORG_ID`. No era un bug del fix: la escritura (a diferencia de la lectura) solo toca filas de la organización activa en el request (`_apply_tenant_filter(is_read_operation=False)`), nunca las de `ADMIN_ORG_ID`, ni siquiera para un superadmin — para editar/borrar un ítem de un nomenclador global hay que operar "parado en" `ADMIN_ORG_ID`. Se corrigió el test, no el código de producción. Este comportamiento quedó documentado en `docs/nomencladores.md` §4.

Confirmado por el usuario: suite completa OK.
