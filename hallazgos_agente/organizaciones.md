# Hallazgo #7 — Organizaciones (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/organizaciones.md` §2
**Estado:** DOCUMENTADO, sin implementar — decisión explícita del usuario (2026-07-10).

## Qué se confirmó (investigación completa, no solo teórica)

`Organization.require_lead_state_notes` (`app/models/organization.py`) no está conectado a ninguna lógica en todo `app/` — confirmado con `grep -r require_lead_state_notes app/`, único resultado es la declaración de la columna en el modelo. Ni siquiera está expuesto en `app/schemas/organization_schema.py` (`OrganizationCreate`/`OrganizationUpdate`), así que **no se puede setear a `True` ni vía API** — es más muerto de lo que sugería la doc original (no es solo "no se lee", es "no se puede ni escribir"). `LeadService.change_state` (`app/services/lead_service.py:788`) acepta `notes: str = None` siempre opcional, sin consultar este flag en ningún punto.

## Decisión del usuario (2026-07-10)

Se le preguntó explícitamente qué hacer (implementar / eliminar / solo documentar). Eligió **"Dejar documentado que falta implementar en el futuro"**, aclarando: "no estoy seguro de si lo vamos a hacer así" — es decir, no hay certeza de que la feature tal como está pensada (un flag por organización que exige notas al cambiar de estado) sea la dirección de producto correcta. **No se tocó código.**

## Si se retoma en el futuro

Dos caminos, a decidir con el usuario en su momento (no asumir cuál sin preguntar):

1. **Implementar:** exponer `require_lead_state_notes` en `OrganizationCreate`/`OrganizationUpdate`, y en `LeadService.change_state` validar `notes` no vacío si `campaign.organization.require_lead_state_notes` (o el objeto organization correspondiente) es `True` — devolver `400` si falta.
2. **Eliminar:** sacar la columna del modelo y agregar un script de migración en `scripts/` (mismo patrón que `scripts/migrate_add_user_profile_fields.py`, `ALTER TABLE organization DROP COLUMN require_lead_state_notes;`) para limpiar la DB existente.

Bajo impacto — no es urgente.

---

# Hallazgo #15 — `PUT /organizations/{id}`: el permiso se valida contra la org del header, el acceso al objeto contra "cualquier org donde soy miembro" (ronda de bug-hunting, 2026-07-10)

**Doc de usuario:** `docs/organizaciones.md` §3
**Estado:** PENDIENTE — investigado y confirmado por lectura de código, sin aplicar fix.

## Qué se encontró

`OrganizationController` no sobreescribe `update`, así que usa el `BaseService.update` genérico, que primero hace `cls.repository.get_by_id(...)` (gatekeeper) y recién si eso devuelve un objeto llama a `cls.repository.update(...)` (mutación sin filtro propio). Para la mayoría de las entidades esto es seguro porque ambos pasos terminan filtrando por el mismo criterio (`TENANT_ORG_ID` == la org del header `X-Organization-Id`, vía `_apply_tenant_filter`).

`Organization` es distinta: no tiene columna `organization_id` (es ella misma el tenant), así que `_apply_tenant_filter` no hace nada para este modelo, y `OrganizationRepository` en cambio sobreescribe `apply_security_filter` (el hook que sí usa `get_by_id`) con su propio criterio: "cualquier organización de la que el usuario sea miembro" (`UserOrganization.user_id == user_context.user.id`, sin filtrar por el header).

Mientras tanto, el chequeo de **permiso** (`PermissionChecker("organization:update")`, vía `_get_deps`) valida `user.get_permissions(org_id=x_organization_id)` — es decir, los permisos que el usuario tiene **en la organización del header**, no en la organización que se está editando (`obj_id` de la URL).

Como son dos criterios distintos (permiso: org del header: pertenencia al objeto: cualquier org del usuario), un usuario que pertenece a **dos o más organizaciones** puede editar `name`/`description` de una organización donde **no** tiene el permiso `organization:update`, mandando `X-Organization-Id` con el header de la organización donde sí lo tiene (ej. donde es admin) y `obj_id` en la URL apuntando a la otra organización (donde solo es, por ejemplo, `viewer`). El chequeo de permiso pasa (mira la org del header), y `apply_security_filter` deja pasar el objeto (es miembro de esa otra org, sin importar su rol ahí).

**Impacto acotado por ahora:** `OrganizationUpdate` solo expone `name` y `description` (`organization_schema.py`) — no permite tocar `require_lead_state_notes` ni nada más sensible, así que el daño concreto hoy es limitado (podría renombrar/cambiar la descripción de una organización ajena a la que pertenece con un rol menor). Pero es una inconsistencia real del modelo de permisos: en el resto del sistema, "tener permiso en la org del header" y "poder tocar el objeto" son la misma cosa; acá no.

## Solución recomendada

En `OrganizationRepository.apply_security_filter`, para operaciones de escritura (`update`/`delete`/`deactivate`/`set_active`), restringir adicionalmente a que `Organization.id == user_context.organization_id` (la org del header) además de la pertenencia — no alcanza con ser miembro, tiene que ser la organización "activa" del request. Alternativa más simple: agregar el mismo chequeo explícito que ya usa `WebFormService.update`/`delete` (comparación manual `== org_id` antes de mutar) directamente en un `OrganizationService.update` a medida, en vez de depender del genérico. Test: usuario miembro de Org A (admin, con `organization:update`) y Org B (viewer, sin ese permiso) — `PUT /organizations/{org_B_id}` con header `X-Organization-Id: org_A_id` debe devolver `403`/`404`, no `200`.
