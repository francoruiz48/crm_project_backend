# Hallazgo #17 — Lead (core) (ronda de bug-hunting, 2026-07-10)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/lead.md` §5
**Estado:** PENDIENTE — investigado, baja/media prioridad.

Se releyeron enteros `lead_controller.py` y `lead_service.py` (~1200 líneas). Es, con diferencia, el módulo más defensivo del backend: valida pertenencia a la organización de `team_id`/`assigned_to_user_id`/`contact_state_id`/tags/leads relacionados en cada punto de entrada, usa `SELECT ... FOR UPDATE` en `change_state` para evitar carreras, limita `bulk_assign` a 200 IDs, valida que el usuario destino de una reasignación pertenezca al equipo destino, etc. No se encontraron bugs de autorización ni de tenant-isolation — el patrón está aplicado de forma consistente en `create`, `update`, `bulk_assign`, `change_state`, `simulate_create`.

## Hallazgo #17 — Carrera (TOCTOU) en el chequeo de leads duplicados

`_check_duplicates` (usado en `create` y `update`) hace un `SELECT` (`repository.find_duplicate`) y, si no encuentra nada, el caller sigue adelante y hace el `INSERT` más adelante en la misma transacción — sin `with_for_update()` ni un constraint de unicidad a nivel de DB que respalde la regla. `change_state`, en cambio, sí usa `SELECT ... FOR UPDATE` para el mismo tipo de problema (evitar que dos requests concurrentes pisen el estado). Dos creaciones de lead simultáneas con los mismos valores en los campos `is_primary` de la misma campaña podrían ambas pasar el chequeo de duplicados antes de que la primera se confirme, resultando en dos leads que la regla de negocio considera "duplicados".

**Impacto:** bajo/medio. La ventana de carrera es chica (dos requests casi simultáneos con datos idénticos) y no es un problema de seguridad (no hay bypass de tenant/permisos), es un problema de integridad de datos en un caso de baja probabilidad.

**Por qué no es trivial de arreglar con un constraint de DB:** qué campos son "primary" es configuración dinámica por campaña (`LeadField.is_primary`), no columnas fijas — no se puede expresar directamente como un `UNIQUE` de Postgres sin un índice parcial/expresión generado dinámicamente por campaña, que sería mucho más invasivo.

**Solución recomendada:** si se decide priorizar, usar un advisory lock de Postgres (`pg_advisory_xact_lock(hash(campaign_id, valores_primarios))`) alrededor de la fase de chequeo + inserción en `create` (y el equivalente en `update` si aplica), liberado automáticamente al final de la transacción — mismo espíritu que el `with_for_update()` que ya usa `change_state`, pero sin depender de que exista una fila previa que lockear. Alternativa más simple pero menos elegante: aceptar el riesgo (ventana muy chica, bajo impacto) y solo documentarlo, sin cambiar código.
