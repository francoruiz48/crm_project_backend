# Hallazgo #25 — Patrón sistémico: queries crudas sin filtro de tenant en `update`/`delete` custom (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Estado:** [RESUELTO] 2026-07-11. Es un hallazgo **transversal**, no de un módulo puntual — se centraliza acá para no duplicar el mismo texto en cada doc de módulo.

## El patrón

Varios `update`/`delete` escritos a mano (no genéricos) resuelven el objeto a modificar con una consulta SQLAlchemy cruda:

```python
current_obj = uow.session.query(Modelo).filter_by(id=obj_id).first()
```

en vez de usar el repositorio (`cls.repository.get_by_id(session, obj_id, user_context=user_context)`), que sí aplica `_apply_tenant_filter`/`apply_security_filter`. Se detectó corriendo `grep -rn "session.query(...).filter_by(id="` sobre `app/services/*.py` (ver comando y resultado completo abajo) y revisando cuáles de esas queries efectivamente carecen de un filtro de organización explícito.

**Consecuencia típica:** como la escritura final (`cls.repository.update`/`delete`) sí filtra por `organization_id` (para los modelos que tienen esa columna), pasar el `id` de otra organización no logra un write cross-tenant real — pero las reglas de negocio que corren *antes* de esa escritura (unicidad de nombre, chequeos de "¿es global?", etc.) se ejecutan usando datos del objeto ajeno, y cuando finalmente se llama a `cls.repository.update`/`delete` y este devuelve `None` (no encontró la fila bajo el filtro de tenant correcto), el código que sigue generalmente no maneja ese `None` — lo más probable es un `500` no controlado en vez de un `404` limpio (no se pudo confirmar el traceback exacto sin correr el código, pero es el patrón esperado dada la estructura).

## Instancias confirmadas (además de las ya documentadas en su propio módulo)

| Archivo | Método | Modelo | Documentado en |
|---|---|---|---|
| `lead_contact_state_service.py:62` | `update` | `LeadContactState` | Hallazgo #22, `hallazgos_agente/estados_de_contacto.md` |
| `nomenclator_item_service.py:73,114` | `update`, `delete` | `NomenclatorItem` | Hallazgo #24, `hallazgos_agente/nomencladores.md` |
| `nomenclator_service.py:48,83` | `update`, `delete` | `Nomenclator` | **Nuevo, este archivo** |
| `lead_flow_service.py:44` | `update` | `LeadFlow` | **Nuevo, este archivo** |
| `tag_service.py:43` | `update` | `Tag` | **Nuevo, este archivo** |

Todos estos modelos (`Nomenclator`, `LeadFlow`, `Tag`) **sí tienen** columna `organization_id` — confirmado por lectura de cada modelo — así que la escritura final queda protegida (no es un write cross-tenant completo como los hallazgos #18/#20/#21). El riesgo real es: (a) un `500` no manejado en vez de `404` para un `obj_id` de otra organización, y (b) las validaciones de negocio (ej. unicidad de nombre) evalúan datos de un objeto ajeno antes de descubrir que no se puede escribir — no se confirmó que esto permita inferir información sensible de otra organización más allá de "existe un objeto con este ID en algún lado", pero es una imprecisión que vale la pena cerrar.

## Instancias revisadas y descartadas (ya protegidas, no requieren fix)

- `lead_routing_policy_service.py:161`, `lead_service.py:363,593,712,889`, `team_member_service.py:35`: la misma línea ya incluye `organization_id=org_id` en el `filter_by`, o el código inmediatamente después valida `objeto.organization_id != org_id` explícitamente — correctos tal cual están.
- `lead_service.py:665,977,1121`, `lead_field_service.py:458`: son un *segundo* fetch del mismo objeto (por el mismo `id`) que ya fue validado como accesible unas líneas antes vía `cls.repository.get_by_id(..., user_context=user_context)` — el re-fetch crudo es solo para obtener la instancia ORM mutable, no una nueva superficie de ataque.
- `routing_rule_evaluator_service.py:206,338`: código interno del motor de evaluación, no recibe IDs directo de un request HTTP sin haber pasado antes por una validación de pertenencia — no se investigó más a fondo por ser de menor prioridad, marcar para revisar si en el futuro se toca ese archivo.

## Solución recomendada

Para cada instancia de la tabla de arriba: reemplazar la query cruda por `cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)`, y si devuelve `None`, cortar inmediatamente con `cls._not_found(obj_id)` (patrón ya usado correctamente en la mayoría de los `create`/`update` del resto del sistema, ej. `LeadFieldService.update`, `CampaignService.update`). Es un fix mecánico, igual en los 5 casos — se puede hacer en una sola tanda una vez que el usuario confirme que quiere priorizarlo.

Test genérico (repetir por cada modelo de la tabla): usuario de la Org A intenta `PUT`/`DELETE` sobre un `id` de un objeto de la Org B → debe devolver `404`, no `500`.

## Fix aplicado (2026-07-11)

Se aplicó exactamente la solución recomendada, sin variaciones, en los 5 puntos:

- `app/services/lead_contact_state_service.py:62` (`update`) — hallazgo #22.
- `app/services/nomenclator_item_service.py:73` (`update`) y `:114`ish (`delete`) — hallazgo #24.
- `app/services/nomenclator_service.py:48` (`update`) y `:83`ish (`delete`) — hallazgo #25.
- `app/services/lead_flow_service.py:44` (`update`) — hallazgo #25.
- `app/services/tag_service.py:43` (`update`) — hallazgo #25.

En todos los casos: `current_obj/current_item = cls.repository.get_by_id(uow.session, obj_id, user_context=user_context)`, con `cls._not_found(obj_id)` si devuelve `None`. Para `NomenclatorItem`/`Nomenclator` (que tienen items/registros "globales" en `ADMIN_ORG_ID`), esto preserva el comportamiento correcto: `get_by_id` en lectura (`is_read_operation=True`, el default) sigue dejando pasar los globales — necesario porque las reglas de negocio de esos services (`REGLA 1: Protección Anti-Escritura de Globales`, etc.) necesitan poder leer un item global para decidir si el usuario tiene permiso de tocarlo, no solo los de su propia organización. Solo bloquea el acceso a objetos de **otra organización no-global**, que es el caso que estaba roto.

**Verificado que `get_by_id` devuelve algo con atributos accesibles** (no la instancia ORM cruda, sino un objeto Pydantic vía `schema_out_detail.model_validate(obj)`) — se confirmó contra el precedente ya existente en `CampaignService.update` (`campaign = cls.repository.get_by_id(...)`, después usado como `campaign.organization_id`), que usa el mismo patrón para el mismo propósito (comparaciones de solo lectura antes de mutar). Los 5 usos nuevos son igual de solo-lectura (comparar nombres/valores existentes, chequear flags), así que no hace falta la instancia ORM mutable — eso lo sigue manejando `cls.repository.update`/`delete` internamente con su propia query.

**Test de regresión:** `tests/functional/test_tenant_isolation.py` — se extendieron `TestLeadFlowIsolation` (`test_update_blocked_for_foreign_lead_flow`), `TestTagIsolation` (`test_update_blocked_for_foreign_tag`) y `TestNomenclatorIsolation` (`test_update_blocked_for_foreign_nomenclator`, `test_delete_blocked_for_foreign_nomenclator`); se agregaron las clases nuevas `TestNomenclatorItemIsolation` (`test_update_blocked_for_foreign_nomenclator_item`, `test_delete_blocked_for_foreign_nomenclator_item`) y `TestLeadContactStateIsolation` (`test_update_blocked_for_foreign_lead_contact_state`). Todos siguen el patrón "Beta intenta `PUT`/`DELETE` con un `obj_id` de Alpha → `404`" y **no encadenan ninguna verificación posterior** al 404 (ver `AGENTS.md` §5.1 — evita la limitación conocida de `db_session`).

## Comando usado para el barrido

```bash
grep -rn "session\.query([A-Za-z_]*)\.filter_by(id=obj_id)\|session\.query([A-Za-z_]*)\.filter_by(id=.*_id)" app/services/*.py
```
