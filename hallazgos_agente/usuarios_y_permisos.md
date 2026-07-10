# Hallazgo #6 — Usuarios y permisos (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/usuarios_y_permisos.md` §4
**Estado:** RESUELTO (2026-07-10)

## Qué se encontró (confirmado, no solo teórico)

`promote_to_org_owner` (`app/controllers/security_controllers/user_controller.py`) tenía en la ruta `dependencies=[Depends(require_superuser)]`. `require_superuser` (`app/core/security.py`) es una dependencia de FastAPI que corre en la misma fase que las demás (antes del cuerpo del endpoint) y lanza `403` si `current_user.is_superuser` es `False` — corta la request ahí mismo, **nunca llega a ejecutarse el service**.

`UserService.promote_to_org_owner` (`app/services/security_services/user_service.py`) tiene, desde siempre, una lógica de autorización con dos ramas, documentada en su propio docstring: "SOLO un Super Admin o un Owner actual de ESA organización puede hacerlo":

```python
has_permission = False
if user_context and user_context.is_superuser:
    has_permission = True
elif user_context and user_context.is_owner:
    if TENANT_ORG_ID.get() == organization_id:
        has_permission = True
```

La rama `elif user_context.is_owner` era **código muerto inalcanzable**: el guard de la ruta ya había bloqueado a cualquier no-superadmin antes de que el service pudiera correr. El endpoint era, en la práctica, "solo superadmin", contradiciendo la intención explícita del código.

`user_context.is_owner` se calcula en `get_current_user_roles` consultando `UserOrganization` para el `x_organization_id` del header — ya viene correctamente scopeado a "soy owner de ESA organización puntual", y el service además valida que el header (`TENANT_ORG_ID.get()`) coincida con el `organization_id` de la URL. La lógica de autorización en el service ya era correcta y suficiente; el problema era solo el guard extra en la ruta.

## Fix aplicado

En `app/controllers/security_controllers/user_controller.py`, se sacó `dependencies=[Depends(require_superuser)]` de la ruta `PATCH /users/organization/{organization_id}/promote-owner/{user_id}`. Queda solo `user_context=Depends(get_current_user_roles)` como parámetro (autenticación); la autorización fina la maneja el service.

`require_superuser` sigue importado y usado en `promote_to_superuser` (el otro endpoint de promoción, que sí es exclusivamente de superadmin — no se tocó).

**Ajuste adicional tras la primera corrida de tests (2026-07-10):** 2 de los 5 tests fallaban (`test_owner_can_promote_member_in_own_org`, `test_owner_can_promote_user_not_yet_member_of_org`) — ambos son los que ejercitan la rama de owner con éxito (200 esperado). El service comparaba `TENANT_ORG_ID.get() == organization_id` — `TENANT_ORG_ID` es una `contextvars.ContextVar` global que `get_current_user_roles` setea desde el header. Se hizo una prueba aislada con `contextvars` puro (fuera de este repo, en el sandbox) que mostró que un valor seteado dentro de una dependencia ejecutada vía threadpool no está garantizado a propagarse de vuelta al contexto que seguirá ejecutando el resto del request — esto afecta específicamente al **mecanismo de override de tests** (`_apply_user_overrides`/`fake_get_current_user_roles`), no necesariamente al comportamiento en producción (que viene funcionando así desde siempre). En vez de perseguir esa ambigüedad, se cambió el service para comparar contra `user_context.organization_id` en lugar de `TENANT_ORG_ID.get()` — es el mismo valor en la práctica (`get_current_user_roles` llena ambos desde el mismo header), pero viaja explícito en el objeto `UserContext` en vez de depender de una contextvar global, lo cual es más robusto y más fácil de testear. Ningún otro comportamiento cambió.

## Tests

`tests/functional/test_promote_to_org_owner.py` (5 casos):

1. `test_owner_can_promote_member_in_own_org` — la rama antes inalcanzable: un owner (no superadmin) promueve a otro miembro de su propia organización.
2. `test_owner_can_promote_user_not_yet_member_of_org` — un owner promueve a alguien que todavía no era miembro; se crea el `UserOrganization` con `is_owner=True`.
3. `test_owner_cannot_promote_in_a_different_org` — un owner de la org A no puede usar ese poder en la org B.
4. `test_regular_member_cannot_promote_anyone` — ni owner ni superadmin → `403` con el mensaje del service.
5. `test_superadmin_can_still_promote` — control: el superadmin sigue funcionando igual que antes del fix.

Pendiente confirmación del usuario corriendo `pytest tests/functional/test_promote_to_org_owner.py -v`.
