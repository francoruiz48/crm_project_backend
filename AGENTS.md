## Imported Claude Cowork project instructions

Antes de hacer cualquier cambio indicame que cambios vas a hacer. Preguntame todas las dudas que tengas antes de cambiar algo. Cuando te pida que analices algo, siempre mencione tu solución recomendada si es que encontras algo para solucionar.
Cada cambio o dato que sea relevante que hagas necesito que quede registrado aqui mismo para que lo lea el siguente agente de IA. 

---

## Contexto para el agente (actualizado 2026-07-10)

Esta sección es un resumen de lo avanzado en la sesión donde se documentó todo el backend módulo por módulo y se empezó a corregir los bugs encontrados. Léela antes de asumir que hay que re-investigar algo — mucho de esto ya está resuelto o mapeado.

Cada cambio o dato que sea relevante que hagas necesito que quede registrado aqui mismo para que lo lea el siguente agente de IA.

### 1. Documentación técnica completa en `docs/`

Se generó documentación de los 21 módulos de negocio + 1 doc transversal + 1 índice, siguiendo el mismo formato que ya tenían `autenticacion.md` y `equipos_y_enrutamiento.md` (los dos únicos docs que existían antes de esta ronda). **Empezar siempre por `docs/indice_general.md`** — tiene la tabla completa de qué doc cubre qué módulo y una sección "busco información sobre X → ver Y".

Léer **`docs/convenciones_generales.md`** antes de tocar cualquier módulo nuevo: documenta una sola vez el patrón común a casi todo el backend (`BaseController`/`BaseService`/`BaseRepository`/`BaseModelDB`, las 6 variantes de `delete_strategy`, auditoría automática vía `_log_audit`, permisos automáticos `entidad:acción`, paginación/filtros). Todos los demás docs de módulo asumen esto conocido y no lo repiten — si vas a explicarle algo al usuario sobre CRUD genérico, la fuente es ese archivo, no reinventar la explicación.

Mapa completo: `lead.md`, `comentarios_de_leads.md`, `campos_personalizados.md`, `campanas_y_workspaces.md`, `automatizacion_de_campos.md`, `estados_de_contacto.md`, `flujo_de_leads.md`, `importacion_y_exportacion.md`, `vistas_de_leads.md`, `nomencladores.md`, `etiquetas.md`, `reglas_de_validacion.md`, `formularios_web.md`, `usuarios_y_permisos.md`, `auditoria.md`, `organizaciones.md`, `dashboard.md`, `busqueda.md`, `almacenamiento.md`, `plantillas.md`, `metadata.md` (más `autenticacion.md` y `equipos_y_enrutamiento.md`, preexistentes).

**Convención a mantener si se agregan más docs:** índice al principio, secciones "Visión general → Modelo de datos → Endpoints → Reglas de negocio → Puntos pendientes/hallazgos → Cómo se testea", y **verificar con grep en `tests/` antes de afirmar "no hay tests para X"** — varias veces asumí ausencia de cobertura y estaba mal (ver ejemplos reales de corrección en `campanas_y_workspaces.md` y `etiquetas.md`). No fabricar contenido de changelog: solo documentar cambios/bugs que efectivamente se verificaron leyendo código.

### 2. Datos técnicos del backend que ya investigué (para no re-derivarlos)

- **Multi-tenancy, lectura vs. escritura (importante, ya causó un bug en un test):** `BaseRepository._apply_tenant_filter(query, is_read_operation)`. En **lectura** trae filas de la organización activa (`TENANT_ORG_ID`) **O** de `ADMIN_ORG_ID` (catálogos/roles compartidos). En **escritura** trae **solo** las de la organización activa — nunca toca filas de `ADMIN_ORG_ID`, ni siquiera para un superadmin. Para editar/borrar algo que vive en `ADMIN_ORG_ID` (ej. un nomenclador global) hay que mandar el request con `X-Organization-Id: <ADMIN_ORG_ID>` explícitamente, no alcanza con ser superadmin operando desde cualquier otra organización.
- `ADMIN_ORG_ID` (constante en `app/core/constans.py`) = la organización especial "Panel Global" (id=1). Es donde viven los roles plantilla (`admin`/`agent`/`viewer`) y los catálogos/nomencladores "globales" compartidos entre organizaciones. No existe el concepto de `organization_id = NULL` en ningún modelo real del sistema (las columnas son `nullable=False`) — "global" siempre significa `organization_id == ADMIN_ORG_ID`, nunca `None`.
- `delete_strategy` tiene 6 variantes (`HARD_DELETE_ALWAYS`, `SOFT_DELETE_ALWAYS`, `SOFT_DELETE_HARD_OPT`, `PROTECTED`, `SMART_DELETE`, `HARD_DELETE_WITH_TOGGLE`) — tabla completa de qué entidad usa cuál en `convenciones_generales.md` §9.
- Permisos: `BaseController._get_deps` arma automáticamente `f"{tabla}:{accion}"` (ej. `nomenclator_item:create`) salvo que el controller declare `required_permissions` a mano. El registro de entidades que generan permisos vive en `app/core/dictionaries.py::SYSTEM_ENTITIES_REGISTRY` (no expuesto por `/metadata/dictionaries`, que sirve `SYSTEM_DICTIONARIES`, algo distinto).
- Tests: fixtures clave en `tests/fixtures/` — `client` (actúa como superadmin `francoruiz.admin@crm.com` por default), `db_session`, `initial_structure` (org/workspace/campaign/flow de prueba, devuelve dict con `org_id`), `_make_user`/`_link_user_to_org`/`_apply_user_overrides`/`_remove_user_overrides` (`tests/fixtures/user_fixtures.py`, para simular otro usuario sin pasar por login real).

### 3. Hallazgos de la auditoría (2026-07-10) — estado

| # | Hallazgo | Doc | Estado |
|---|---|---|---|
| 1 | Protección de nomencladores globales nunca se activaba (`organization_id is None` en vez de `== ADMIN_ORG_ID`) en `nomenclator_item_service.py` | `nomencladores.md` §6 | **RESUELTO.** Fix aplicado + `tests/functional/test_nomenclators.py` agregado (6 casos). No se pudo correr la suite en este sandbox (sin Postgres, ver §4) — pendiente que el usuario confirme corriendo `pytest tests/functional/test_nomenclators.py -v`. |
| 2 | `LeadContactStateService.update` (`app/services/lead_contact_state_service.py`): `org_id` solo se definía dentro del `if` de "Regla 1" (cambio de nombre), pero se reusaba en "Regla 2" (chequeo de `is_initial`) fuera de ese bloque → `NameError` → `500` en vez de `400` si se mandaba `is_initial=True` sin cambiar `name` en el mismo `PUT`. | `estados_de_contacto.md` §5 | **RESUELTO.** Se movió el cálculo de `org_id` al principio de `do_update`, antes de la Regla 1 (mismo patrón que ya usa `create`). Test de regresión agregado: `test_lead_contact_state_set_initial_without_changing_name_returns_400` en `tests/functional/test_lead_contact_states.py`. No se pudo correr la suite en este sandbox (sin Postgres, ver §4) — pendiente que el usuario confirme corriendo `pytest tests/functional/test_lead_contact_states.py -v`. |
| 3 | `POST /storage/upload` y `POST /import/detect-headers` alcanzables sin autenticación; `/import/process` y `/export/{campaign_id}` no validan permiso específico (solo login). | `almacenamiento.md` §5, `importacion_y_exportacion.md` §7 | Pendiente. |
| 4 | `WebForm`/`WebFormField`/`/public/forms/*` sin ningún test (único endpoint de escritura público del sistema). | `formularios_web.md` §7 | Pendiente (no es un bug, es un hueco de cobertura de riesgo alto). |
| 5 | `SystemAuditLog.organization_id` nullable — si queda `NULL`, el filtro de tenant de lectura lo vuelve invisible por API para cualquiera. | `auditoria.md` §7 | Pendiente, no confirmado si ocurre en la práctica. |
| 6 | `promote_to_org_owner`: la ruta exige `require_superuser` pero el service contempla también que un owner no-superadmin la ejecute — no se confirmó cuál de los dos comportamientos es el real. | `usuarios_y_permisos.md` §4 | Pendiente de investigar (requiere leer `core/security.py::require_superuser` a fondo). |
| 7 | `Organization.require_lead_state_notes` existe en el modelo pero no está conectado a ninguna lógica en todo `app/`. | `organizaciones.md` §2 | Pendiente (bajo impacto, es un flag muerto). |
| 8 | Búsqueda global incluye `"code"` como campo de `NomenclatorItem`, columna que no existe (se ignora en silencio, no rompe nada). | `busqueda.md` §4 | Cosmético, baja prioridad. |

Cuando se resuelva un hallazgo: aplicar el fix, actualizar/agregar el test de regresión correspondiente, y actualizar tanto el doc de módulo (marcar `[RESUELTO]` con el detalle, como se hizo en `nomencladores.md` §6) como la tabla de "Hallazgos pendientes" de `indice_general.md`.

### 4. Limitaciones del entorno de esta sesión

- El sandbox de bash (`mcp__workspace__bash`) **no tiene PostgreSQL ni las dependencias del proyecto instaladas** (`pip list` vacío, sin `docker`, sin `psql`) — no se pudo ni se puede correr `pytest` desde acá. Cualquier test nuevo/modificado queda sin ejecutar hasta que el usuario lo corra localmente o en CI; siempre aclarárselo y pedirle el resultado en vez de asumir que pasa.
- Paths: las herramientas de archivo (Read/Write/Edit/Grep/Glob) usan rutas Windows (`C:\crm_project\backend\...`); el bash del sandbox monta lo mismo en `/sessions/<session>/mnt/backend/...`. Son la misma carpeta real del usuario — no una copia — así que escribir con Write/Edit ya persiste directo ahí, no hace falta copiar.
- Edit exige haber hecho Read del archivo en la misma sesión antes de editarlo.

### 5. Cómo prefiere trabajar este usuario (Franco)

- Respuestas concisas y directas, sin verborragia.
- Instrucción de proyecto explícita: **avisar qué cambios se van a hacer y resolver dudas antes de tocar código** — no asumir y ejecutar. Ya se validó este patrón funcionando bien (se usó `AskUserQuestion` antes de aplicar el fix del hallazgo #1).
- Cuando se pide "analizar" algo, siempre indicar la solución recomendada si se encuentra un problema — no solo describir el problema.
- Va resolviendo los hallazgos de la auditoría **de a uno, en orden de impacto**. Hallazgos #1 (nomencladores) y #2 (estados de contacto) ya están RESUELTOS (código + test + docs). El siguiente en la lista, si pide continuar, es el #3 (endpoints de storage/import sin autenticación).
