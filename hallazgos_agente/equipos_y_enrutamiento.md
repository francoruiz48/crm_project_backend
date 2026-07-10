# Hallazgo #16 — Equipos y enrutamiento (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/equipos_y_enrutamiento.md` §7 y §11
**Estado:** PENDIENTE — investigado y confirmado por lectura de código, sin aplicar fix.

Se releyeron: `team_controller.py`, `team_member_controller.py`, `team_campaign_access_controller.py`, `team_workspace_access_controller.py`, `lead_routing_policy_controller.py`, `team_service.py`, `team_member_service.py`, `team_access_service.py`, `lead_routing_policy_service.py`.

## Hallazgo #16 — `DELETE`/reactivar/desactivar de `LeadRoutingPolicy` no exigen ser `MANAGER` del equipo (create/update sí)

`LeadRoutingPolicyController` es un router manual (no usa `BaseController`, según el propio doc §7: "necesita dos rutas extra que no encajaban en el patrón genérico"). Sus rutas `create`/`update` llaman a `LeadRoutingPolicyService.create`/`.update`, que internamente corren `_assert_manager(session, user_context, team_id)` — exige ser `MANAGER` del `target_team_id` (o superadmin/owner) antes de crear o modificar una política.

Pero `DELETE /lead_routing_policies/{id}`, `PUT /lead_routing_policies/active/{id}` (reactivar) y `DELETE /lead_routing_policies/active/{id}` (desactivar) llaman directo a `LeadRoutingPolicyService.delete`/`.set_active`/`.deactivate` — **`LeadRoutingPolicyService` no sobreescribe ninguno de esos tres métodos**, así que corren el `BaseService.delete`/`set_active`/`deactivate` genérico, que solo verifica que la política pertenezca a la organización activa (vía `_apply_tenant_filter`/`get_by_id`) — **sin ningún chequeo de rol `MANAGER`**. El router tampoco agrega `PermissionChecker` en ninguna ruta (a diferencia de los controllers genéricos, que sí lo hacen automáticamente vía `_get_deps`) — es un router 100% manual sin ese mecanismo.

Consecuencia: cualquier usuario autenticado que pertenezca a la organización (aunque sea un simple `AGENT` sin relación con el equipo destino de la política, o incluso de otro equipo) puede:
- Borrar **permanentemente** cualquier política de enrutamiento de su organización (`delete_strategy = HARD_DELETE_WITH_TOGGLE` — es un borrado físico e irreversible, no hay soft-delete de por medio).
- Desactivar/reactivar cualquier política, alterando a qué equipo se enrutan los leads nuevos de la organización.

Esto contradice la regla que el propio código documenta para create/update ("solo un MANAGER del equipo destino puede crear/gestionar sus políticas") y que `docs/equipos_y_enrutamiento.md` §7 ya describe como la regla vigente — el doc no aclaraba (hasta ahora) que esa regla no cubre delete/activar/desactivar.

## Solución recomendada

Agregar el mismo chequeo `_assert_manager(session, user_context, policy.target_team_id)` en `LeadRoutingPolicyService`, sobreescribiendo `delete`, `set_active` y `deactivate` (mismo patrón que ya usa `create`/`update`: buscar la policy primero para conocer su `target_team_id`, después validar, después delegar en `super()` o en el repositorio). Test: un `AGENT` (o un `MANAGER` de otro equipo) intenta `DELETE`/`PUT active`/`DELETE active` sobre una política de un equipo ajeno → `403`, igual que ya pasa hoy con `create`/`update`.

## Nota menor (no es un hallazgo aparte, ya documentada por el propio código)

`docs/equipos_y_enrutamiento.md` §5 y §11 ya dejan registrado que la validación de organización en `TeamWorkspaceAccessRepository.create`/`TeamCampaignAccessRepository.create` está condicionada a `if org_id:` (se saltea en silencio si `TENANT_ORG_ID` viene vacío) — no se encontró un caso reproducible nuevo de que eso ocurra en la práctica, se deja como estaba documentado.
