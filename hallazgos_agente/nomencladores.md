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

---

# Hallazgo #24 — `NomenclatorItemService.update`/`delete` leen el objeto sin filtro de tenant (ronda de bug-hunting, 2026-07-10)

**Estado:** PENDIENTE — prioridad baja/media, mismo patrón que el hallazgo #22 (`LeadContactState`), no un write cross-tenant completo.

`update` y `delete` resuelven `current_item` con `uow.session.query(NomenclatorItem).filter_by(id=obj_id).first()` — consulta cruda, sin pasar por el repositorio (tenant-aware). Si `obj_id` pertenece a un ítem de otra organización (no global), la REGLA 1 ("¿es global? exigir superadmin") no se activa (porque `current_item.organization_id` no es `ADMIN_ORG_ID`, es la otra organización), y el código sigue de largo hasta `cls.repository.update`/`delete`, que sí filtran por tenant y devolverían `None`/fallarían al no encontrar la fila bajo el organization_id correcto — probablemente terminando en un error no manejado (`500`) en vez de un `404` limpio, en vez de un write real cross-tenant.

**Solución recomendada:** igual que el hallazgo #22 — resolver `current_item` con `cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)` en vez de la query cruda, y devolver `404` inmediato si no se encuentra. Aplica también a `create`'s validación del `parent_nom` (`uow.session.query(Nomenclator).filter_by(id=obj_in.nomenclator_id).first()`, línea 18) — mismo patrón, aunque ahí el impacto es menor porque solo se usa para decidir si exigir superadmin, no determina qué fila se escribe.

Este es el mismo patrón detectado en `hallazgos_agente/estados_de_contacto.md` (#22) y `hallazgos_agente/flujo_de_leads.md` (#21, ahí sí con impacto de write real) — vale la pena, cuando se prioricen los fixes, revisar sistemáticamente todos los `update`/`delete` custom del código en busca de `session.query(Modelo).filter_by(id=obj_id)` sin pasar por el repositorio.
