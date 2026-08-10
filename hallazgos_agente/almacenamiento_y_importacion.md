# Hallazgo #3 — Almacenamiento / Importación-Exportación (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/almacenamiento.md` §5, `docs/importacion_y_exportacion.md` §7
**Estado:** RESUELTO (2026-07-10)

## Qué se encontró

- `POST /storage/upload` no tenía **ninguna** dependencia de autenticación (`Depends(get_current_user_roles)` ausente) — alcanzable sin login. Tampoco llamaba a `validate_file`, así que no restringía tipos de archivo (solo bloqueaba si el nombre tenía una extensión inconsistente con un MIME **conocido**).
- `POST /import/detect-headers` tampoco tenía dependencia de autenticación.
- `POST /import/process` y `GET /export/{campaign_id}` sí exigían login (`get_current_user_roles`), pero no validaban ningún permiso específico — cualquier usuario autenticado de la organización podía importar/exportar leads de cualquier campaña a la que tuviera acceso de lectura por tenant, sin importar su rol.

## Fix aplicado

- `app/controllers/storage_controller.py`: se agregó `Depends(get_current_user_roles)` a `/storage/upload` — solo login, **sin** restricción de tipos (decisión explícita: el endpoint no tiene dueño claro identificado en el repo, no se encontró desde dónde lo consume el frontend; restringir mal el tipo podría romper un uso legítimo que no se ve en este código).
- `app/controllers/import_export_controller.py`:
  - `POST /import/detect-headers`: se agregó `Depends(get_current_user_roles)`.
  - `POST /import/process`: se agregó `dependencies=[Depends(PermissionChecker("lead:create"))]`.
  - `GET /export/{campaign_id}`: se agregó `dependencies=[Depends(PermissionChecker("lead:view"))]`.

**Corrección sobre la recomendación original del doc:** el doc original recomendaba `lead:view_all` para `/export/{campaign_id}`. Se cambió a `lead:view` al implementar, después de verificar en `app/db/init_data.py` que el rol `agent` (uso diario) solo tiene `lead:view`, no `lead:view_all` (ese es de `viewer`/`admin`) — exigir `view_all` le hubiera impedido a un agente exportar hasta sus propios leads asignados. `lead:view` + el filtro de visibilidad que ya aplica `LeadRepository.get_all` internamente es el mismo patrón que usa `GET /leads/`.

## Tests

`tests/functional/test_storage_and_import_permissions.py` (5 casos): `401` sin token en `/storage/upload` y `/import/detect-headers`; `403` para un usuario `viewer` (sin `lead:create`) en `/import/process`; `403` para un usuario sin roles (sin `lead:view`) en `/export/{campaign_id}`; control de que el superadmin sigue pudiendo usar ambos endpoints con normalidad.

Confirmado por el usuario: suite completa OK.
