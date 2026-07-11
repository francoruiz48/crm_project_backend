# Hallazgo #19 — Campañas y workspaces (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/campanas_y_workspaces.md` §6, §8
**Estado:** [RESUELTO 2026-07-11]

Se releyeron `campaign_controller.py`, `campaign_service.py`, `workspace_controller.py`, `workspace_service.py`.

## Hallazgo #19 — `DELETE /campaigns/{id}` no tiene la misma restricción de creador/owner que `PUT`

`CampaignService.update` (documentado en `docs/campanas_y_workspaces.md` §6, es una regla **deliberada**, con test dedicado `test_campaign_update_by_non_creator_fails_with_403`) exige que quien edita una campaña sea su `created_by`, el `owner` de la organización, o superadmin — **aunque tenga el permiso genérico `campaign:update`** vía su rol. Es una capa de autorización extra encima del RBAC estándar, específica de este servicio.

`CampaignService` **no sobreescribe `delete` ni `deactivate`** — usan el `BaseService` genérico, que solo exige el permiso RBAC estándar (`campaign:delete`), sin ningún chequeo de creador/owner. No se encontró ningún test que ejercite "un no-creador con permiso `campaign:delete` intenta borrar una campaña ajena" (sí existe el equivalente para `update`).

**Resultado:** un usuario con el rol `admin` de su organización (que tiene todos los permisos, incluido `campaign:delete`) **no puede renombrar** una campaña creada por un colega, pero **sí puede borrarla** (`DELETE /campaigns/{id}`, que con `delete_strategy = SOFT_DELETE_HARD_OPT` puede incluso ser un hard delete con `?force=true`, arrastrando leads y campos en cascada). Es una asimetría rara: la operación más destructiva (borrar, potencialmente con cascada irreversible) tiene *menos* restricción que la menos destructiva (renombrar/editar).

## Por qué probablemente es un descuido y no una decisión

La regla de `update` está documentada como intencional y tiene test dedicado — sugiere que hubo una decisión consciente de "solo el dueño/creador debería poder tocar esta campaña". Es poco probable que la intención haya sido "pero cualquier admin sí puede borrarla del todo" — más bien parece que al agregar el chequeo extra en `update` no se replicó en `delete`/`deactivate`.

## Solución recomendada

Extraer el chequeo de `CampaignService.update` a un helper (`_assert_can_modify_campaign` o similar) y aplicarlo también en `delete`/`deactivate` (sobreescribiendo esos métodos en `CampaignService`, mismo patrón que ya usa `UserService._assert_can_modify`). Antes de aplicar el fix, confirmar con el usuario si la intención real es "solo creador/owner/superadmin puede modificar O borrar" (lo más consistente) — no asumirlo sin preguntar, según la instrucción del proyecto. Test: un admin no-creador con permiso `campaign:delete` intenta `DELETE /campaigns/{id}` de una campaña ajena → debería dar `403`, igual que ya pasa hoy con `PUT`.

## Fix aplicado (2026-07-11)

Se confirmó con el usuario: "El delete/disable debe ir acorde al update, creador, owner, y admin puede ejecutar la acción" — y que "admin" se refiere al superadmin global (`is_superuser`), no al rol admin de organización. No se agregó ninguna condición nueva, solo se replicó la regla existente de `update`.

En `app/services/campaign_service.py`:
- Se extrajo el chequeo de `update()` a `CampaignService._assert_can_modify_campaign(campaign, user_context, action_label)` (creador `campaign.created_by == user_context.user.id`, o `is_owner`, o `is_superuser`; si no, `403`).
- `update()` ahora llama a este helper en vez de tener el chequeo inline.
- Se agregaron overrides de `delete()` y `deactivate()` en `CampaignService`: abren un `with UnitOfWork() as uow:` solo para buscar la campaña (`cls.repository.get_by_id`, que aplica `apply_security_filter`) y correr el guard; si pasa, delegan en `super().delete(...)`/`super().deactivate(...)` para no duplicar la lógica de auditoría/estrategia de borrado (mismo patrón usado en el hallazgo #16 sobre `LeadRoutingPolicyService` y el #15 sobre `OrganizationService`).
- `set_active` (reactivación) quedó fuera de alcance a propósito — no estaba pedido.

**Tests** (`tests/functional/test_campaign.py`, sección "BORRAR / DESACTIVAR CAMPAÑA — CONTROL DE ACCESO"): 6 tests nuevos, mirroring los 3 existentes de `update` — creador puede borrar/desactivar, no-creador recibe `403` en ambos, superuser puede borrar/desactivar cualquier campaña.
