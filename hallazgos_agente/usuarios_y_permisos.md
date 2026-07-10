# Hallazgo #6 — Usuarios y permisos (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/usuarios_y_permisos.md` §4
**Estado:** PENDIENTE de investigar — todavía no se tocó código.

## Qué se encontró (nivel documentación, sin investigar a fondo)

`promote_to_org_owner`: la ruta exige `require_superuser` (dependencia de FastAPI que solo deja pasar a un superadmin), pero el service (`app/services/...` — confirmar archivo exacto al retomar) contempla también la posibilidad de que un owner no-superadmin la ejecute. No se confirmó cuál de los dos comportamientos es el real (¿el chequeo de la ruta es más estricto que lo que el service espera? ¿o el código del service que contempla el caso "owner no-superadmin" es una rama muerta que nunca se alcanza por el guard de la ruta?).

## Próximos pasos al retomar

1. Leer `core/security.py::require_superuser` a fondo (ver qué hace exactamente y cómo se usa como dependencia).
2. Leer el service completo de `promote_to_org_owner` para entender la rama "owner no-superadmin".
3. Confirmar con un test o lectura de código cuál es el comportamiento real en runtime.
4. Aplicar el fix (recomendación pendiente hasta investigar) + test de regresión + actualizar este archivo y `docs/usuarios_y_permisos.md` §4.
