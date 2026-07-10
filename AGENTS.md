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

**`docs/` es para el usuario; `hallazgos_agente/` (carpeta separada, en la raíz del repo) es para el agente** — memoria de trabajo detallada de cada hallazgo de la auditoría, para no inflar este archivo. Ver §3 más abajo y `hallazgos_agente/_README_PARA_EL_AGENTE.md`.

### 2. Datos técnicos del backend que ya investigué (para no re-derivarlos)

- **Multi-tenancy, lectura vs. escritura (importante, ya causó un bug en un test):** `BaseRepository._apply_tenant_filter(query, is_read_operation)`. En **lectura** trae filas de la organización activa (`TENANT_ORG_ID`) **O** de `ADMIN_ORG_ID` (catálogos/roles compartidos). En **escritura** trae **solo** las de la organización activa — nunca toca filas de `ADMIN_ORG_ID`, ni siquiera para un superadmin. Para editar/borrar algo que vive en `ADMIN_ORG_ID` (ej. un nomenclador global) hay que mandar el request con `X-Organization-Id: <ADMIN_ORG_ID>` explícitamente, no alcanza con ser superadmin operando desde cualquier otra organización.
- `ADMIN_ORG_ID` (constante en `app/core/constans.py`) = la organización especial "Panel Global" (id=1). Es donde viven los roles plantilla (`admin`/`agent`/`viewer`) y los catálogos/nomencladores "globales" compartidos entre organizaciones. No existe el concepto de `organization_id = NULL` en ningún modelo real del sistema (las columnas son `nullable=False`) — "global" siempre significa `organization_id == ADMIN_ORG_ID`, nunca `None`.
- `delete_strategy` tiene 6 variantes (`HARD_DELETE_ALWAYS`, `SOFT_DELETE_ALWAYS`, `SOFT_DELETE_HARD_OPT`, `PROTECTED`, `SMART_DELETE`, `HARD_DELETE_WITH_TOGGLE`) — tabla completa de qué entidad usa cuál en `convenciones_generales.md` §9.
- Permisos: `BaseController._get_deps` arma automáticamente `f"{tabla}:{accion}"` (ej. `nomenclator_item:create`) salvo que el controller declare `required_permissions` a mano. El registro de entidades que generan permisos vive en `app/core/dictionaries.py::SYSTEM_ENTITIES_REGISTRY` (no expuesto por `/metadata/dictionaries`, que sirve `SYSTEM_DICTIONARIES`, algo distinto).
- Tests: fixtures clave en `tests/fixtures/` — `client` (actúa como superadmin `francoruiz.admin@crm.com` por default), `db_session`, `initial_structure` (org/workspace/campaign/flow de prueba, devuelve dict con `org_id`), `_make_user`/`_link_user_to_org`/`_apply_user_overrides`/`_remove_user_overrides` (`tests/fixtures/user_fixtures.py`, para simular otro usuario sin pasar por login real).

### 3. Hallazgos de la auditoría (2026-07-10) — índice

El detalle completo de cada hallazgo (qué se encontró, fix aplicado, tests, regresiones) **ya no vive acá** — se movió a `hallazgos_agente/` (una carpeta de uso interno del agente, separada de `docs/` que es para el usuario) porque esta tabla se estaba volviendo demasiado larga. Acá solo queda el índice de una línea por hallazgo.

**Regla:** antes de investigar o tocar un hallazgo, leer su archivo en `hallazgos_agente/`. Al resolver o investigar algo, actualizar **ese archivo** (no este). Acá en `AGENTS.md` solo se actualiza el estado de la fila correspondiente.

| # | Módulo | Detalle | Doc de usuario | Estado |
|---|---|---|---|---|
| 1 | Nomencladores | `hallazgos_agente/nomencladores.md` | `nomencladores.md` §6 | RESUELTO |
| 2 | Estados de contacto | `hallazgos_agente/estados_de_contacto.md` | `estados_de_contacto.md` §5 | RESUELTO |
| 3 | Almacenamiento / Import-Export | `hallazgos_agente/almacenamiento_y_importacion.md` | `almacenamiento.md` §5, `importacion_y_exportacion.md` §7 | RESUELTO |
| 4 | Formularios web | `hallazgos_agente/formularios_web.md` | `formularios_web.md` §7 | RESUELTO |
| 5 (+5b) | Auditoría (`SystemAuditLog`) | `hallazgos_agente/auditoria.md` | `auditoria.md` §7 | RESUELTO (incluye una regresión de FK detectada y corregida en producción — leer el archivo antes de tocar `_log_audit`) |
| 6 | Usuarios y permisos | `hallazgos_agente/usuarios_y_permisos.md` | `usuarios_y_permisos.md` §4 | PENDIENTE de investigar |
| 7 | Organizaciones | `hallazgos_agente/organizaciones.md` | `organizaciones.md` §2 | PENDIENTE (bajo impacto) |
| 8 | Búsqueda | `hallazgos_agente/busqueda.md` | `busqueda.md` §4 | PENDIENTE (cosmético, baja prioridad) |

Cuando se resuelva un hallazgo: aplicar el fix, actualizar/agregar el test de regresión correspondiente, actualizar el archivo de `hallazgos_agente/` con el detalle completo, actualizar el estado en la tabla de arriba, actualizar el doc de módulo en `docs/` (marcar `[RESUELTO]`, como se hizo en `nomencladores.md` §6) y la tabla de "Hallazgos pendientes" de `docs/indice_general.md`.

### 4. Limitaciones del entorno de esta sesión

- El sandbox de bash (`mcp__workspace__bash`) **no tiene PostgreSQL ni las dependencias del proyecto instaladas** (`pip list` vacío, sin `docker`, sin `psql`) — no se pudo ni se puede correr `pytest` desde acá. Cualquier test nuevo/modificado queda sin ejecutar hasta que el usuario lo corra localmente o en CI; siempre aclarárselo y pedirle el resultado en vez de asumir que pasa.
- Paths: las herramientas de archivo (Read/Write/Edit/Grep/Glob) usan rutas Windows (`C:\crm_project\backend\...`); el bash del sandbox monta lo mismo en `/sessions/<session>/mnt/backend/...`. Son la misma carpeta real del usuario — no una copia — así que escribir con Write/Edit ya persiste directo ahí, no hace falta copiar.
- Edit exige haber hecho Read del archivo en la misma sesión antes de editarlo.
- **Vista desincronizada del mount de bash (detectado 2026-07-10):** el sandbox de bash monta la carpeta real del usuario, pero para archivos editados varias veces seguidas en una misma sesión (vía Edit, no Write), esa vista puede quedar desincronizada — se vio `AGENTS.md` con 3 líneas por `cat`/`git diff` en bash cuando en realidad (confirmado con `Read`, que sí es confiable) tenía todo el contenido esperado; también se vieron archivos cortados a mitad de una línea (ej. `storage_controller.py` sin el `return` final). Esto **no es pérdida real de datos** — el archivo verdadero (accesible con `Read`) está bien — pero hace que cualquier comando de `git` corrido desde bash (status, diff, add, commit) sea **no confiable** para archivos tocados recientemente en la sesión. Por eso el agente no comitea desde acá (ver regla de workflow en §5). Si hace falta comparar contra git, usar `git show HEAD:<archivo>` (lee del historial, no del working tree) en vez de `git diff`/`cat` sobre el archivo en el mount.

**Cómo leer los resultados de una corrida de tests que el usuario ejecutó localmente:** aunque acá no se puede correr pytest, el proyecto tiene un plugin propio (`tests/plugins/log_reporter`, registrado en `conftest.py` como `pytest_plugins`) que después de cada corrida deja todo escrito en `tests/logs/` — esos archivos sí son legibles con `Read`/`Grep` una vez que el usuario corrió la suite en su máquina. El flujo para diagnosticar un fallo es siempre el mismo, en este orden:

1. **Empezar por `tests/logs/summary.log`.** Es el índice: una línea por archivo de test con `✓ OK` o `✗ FALLO` y cuántos casos pasaron (ej. `[ 16/17 ]`), más el path relativo a su log detallado (`→ logs/functional/test_X.log`). Debajo de cada `✗ FALLO` lista el/los `nombre_de_clase::nombre_de_test` puntuales que fallaron — no hace falta abrir nada más para saber *qué* test falló y *en qué archivo* está.
2. **De ahí, ir al log específico** en `tests/logs/functional/<archivo>.log` (el path ya lo da el summary). Ese archivo tiene, por cada test que falló, el traceback completo de pytest: la línea exacta del assert, los valores recibidos vs. esperados, y el fixture/estado con el que corrió (ej. IDs generados en `initial_structure`).
3. Con eso ya alcanza para diagnosticar sin pedirle al usuario que pegue el traceback a mano — el error puntual está siempre en el log específico, el summary solo sirve para ubicarlo rápido en una corrida grande (acá, 471 tests en 31 archivos).

Ejemplo real de este flujo (2026-07-10): `summary.log` marcó `✗ FALLO test_web_forms.py [16/17]` señalando `TestWebFormPrivateCRUD::test_create_web_form_rejects_field_from_other_campaign`; el traceback completo (con el `AssertionError` exacto: "El flujo de leads especificado no existe") estaba en `tests/logs/functional/test_web_forms.log`, y de ahí salió el diagnóstico correcto sin necesidad de que el usuario pegara nada más.

### 5. Cómo prefiere trabajar este usuario (Franco)

- Respuestas concisas y directas, sin verborragia.
- Instrucción de proyecto explícita: **avisar qué cambios se van a hacer y resolver dudas antes de tocar código** — no asumir y ejecutar. Ya se validó este patrón funcionando bien (se usó `AskUserQuestion` antes de aplicar el fix del hallazgo #1).
- Cuando se pide "analizar" algo, siempre indicar la solución recomendada si se encuentra un problema — no solo describir el problema.
- Va resolviendo los hallazgos de la auditoría **de a uno, en orden de impacto**. Hallazgos #1 (nomencladores), #2 (estados de contacto), #3 (storage/import sin autenticación/permiso), #4 (`WebForm` sin tests) y #5 (`SystemAuditLog.organization_id` nullable) ya están RESUELTOS (código/tests + docs). El siguiente en la lista, si pide continuar, es el #6 (`promote_to_org_owner` — `require_superuser` vs. owner-path, requiere leer `core/security.py::require_superuser` a fondo).
- Pidió explícitamente: "si hay test que se pueda hacer armalo siempre, agregalo al AGENTS.md" — para cada hallazgo que se resuelva, siempre escribir test de regresión si es posible, y dejar registrado en la tabla de arriba qué archivo de test lo cubre.
- **Workflow de git (acordado 2026-07-10, reemplaza cualquier intento de comitear desde el agente):** el agente NO hace `git commit` — el mount del sandbox de bash puede tener una vista desincronizada/truncada de archivos editados varias veces en la misma sesión (ver §4, "Vista desincronizada del mount de bash"), así que comitear desde ahí es riesgoso. En cambio, cuando el agente termina un cambio: (1) el usuario corre los tests localmente y confirma si pasaron, (2) recién ahí el agente sugiere el mensaje de commit (título + detalle, formato `[FIX]`/`[ADD]` como ya usa el usuario en su historial) listo para copiar, (3) el usuario hace el commit él mismo en su terminal. El agente nunca comitea "por las dudas" ni antes de la confirmación de tests.
