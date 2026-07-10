# Índice General de Documentación

Punto de entrada a la documentación técnica del backend del CRM. Si no sabés en qué archivo buscar algo, empezá acá. Última revisión: 2026-07-10.

## Cómo está organizada esta documentación

Cada archivo documenta uno o más módulos estrechamente relacionados (mismo criterio que ya existía en `autenticacion.md` y `equipos_y_enrutamiento.md`: entidades muy acopladas se documentan juntas en vez de fragmentarse). Todos comparten el mismo patrón de secciones (Visión general → Modelo de datos → Endpoints → Reglas de negocio → Puntos pendientes → Cómo se testea) y todos asumen conocido **`convenciones_generales.md`**, que explica una sola vez el patrón común (`BaseController`/`BaseService`/`BaseRepository`, estrategias de borrado, auditoría automática, multi-tenancy, paginación) para no repetirlo en cada documento.

Recomendación de lectura si es tu primera vez: `convenciones_generales.md` → `autenticacion.md` → el módulo específico que te interesa.

## Índice de documentos

| Documento | Qué cubre |
|---|---|
| [`convenciones_generales.md`](./convenciones_generales.md) | El patrón común a casi todo el backend: CRUD genérico, `delete_strategy`, auditoría automática, multi-tenancy, permisos automáticos, paginación. Leer primero. |
| [`autenticacion.md`](./autenticacion.md) | Login, tokens (access/refresh/invite), registro, invitaciones, modelo `User`/`Role`/`Permission`, RBAC, multi-tenancy (`X-Organization-Id`), superadmin. |
| [`usuarios_y_permisos.md`](./usuarios_y_permisos.md) | Endpoints de **gestión** de usuarios/roles/permisos (`/users`, `/roles`, `/permissions`) que no son parte del flujo de `/auth/*`: listado, edición, promoción a superadmin/owner. |
| [`organizaciones.md`](./organizaciones.md) | `Organization`: qué se crea automáticamente al dar de alta una organización (flujo, estados, sección, roles clonados). |
| [`equipos_y_enrutamiento.md`](./equipos_y_enrutamiento.md) | `Team` (equipos, miembros, accesos a workspace/campaña) y `LeadRoutingPolicy` (motor de enrutamiento automático a equipos). |
| [`lead.md`](./lead.md) | El módulo central: `Lead`, su pipeline de creación/actualización, validaciones, archivos, cambio de estado, reasignación masiva, visibilidad. |
| [`comentarios_de_leads.md`](./comentarios_de_leads.md) | `LeadComment`: notas sobre un lead. |
| [`campos_personalizados.md`](./campos_personalizados.md) | `LeadField` y su familia (tipo, subtipo, sección, valor): el sistema de campos dinámicos por campaña. |
| [`campanas_y_workspaces.md`](./campanas_y_workspaces.md) | `Workspace` y `Campaign`: contenedor de campañas, `is_public`, resolución de flujo, campos por defecto. |
| [`automatizacion_de_campos.md`](./automatizacion_de_campos.md) | `FieldAutomation`: motor de reglas "si se cumple X, mutá el campo Y" sobre leads. |
| [`estados_de_contacto.md`](./estados_de_contacto.md) | `LeadContactState`: estado del último contacto con el lead (distinto del estado de `LeadFlow`). |
| [`flujo_de_leads.md`](./flujo_de_leads.md) | `LeadFlow`, `LeadState`, `LeadStateTransition`: el embudo comercial y su editor visual de grafo. |
| [`importacion_y_exportacion.md`](./importacion_y_exportacion.md) | Carga masiva de leads desde Excel y exportación. |
| [`vistas_de_leads.md`](./vistas_de_leads.md) | `LeadView`: filtros y configuración visual guardada (privada/equipo/pública). |
| [`nomencladores.md`](./nomencladores.md) | `Nomenclator`/`NomenclatorItem`: catálogos de opciones para campos selector/checkbox. |
| [`etiquetas.md`](./etiquetas.md) | `Tag`: etiquetas libres sobre leads. |
| [`reglas_de_validacion.md`](./reglas_de_validacion.md) | `ValidationRule`: reglas de validación por campo (plantilla o fórmula manual). |
| [`formularios_web.md`](./formularios_web.md) | `WebForm`: formularios embebibles que crean leads públicamente, sin login. |
| [`auditoria.md`](./auditoria.md) | `SystemAuditLog`, `LeadActivityHistory`, `LeadStateHistory`: los tres mecanismos de historial/auditoría. |
| [`dashboard.md`](./dashboard.md) | Endpoints de métricas agregadas (`/dashboard/org`, `/dashboard/admin`). |
| [`busqueda.md`](./busqueda.md) | Búsqueda global (`/search`) sobre campañas, workspaces, nomencladores y leads. |
| [`almacenamiento.md`](./almacenamiento.md) | `StorageService`: subida de archivos (Supabase Storage), validación de tipo/tamaño. |
| [`plantillas.md`](./plantillas.md) | `/templates`: catálogo estático de plantillas de campo, reglas, fórmulas Excel y máscaras. |
| [`metadata.md`](./metadata.md) | `/metadata`: diccionarios/enums estáticos del sistema para poblar selects del frontend. |

## Busco información sobre... ¿en qué documento la encuentro?

- **Cómo funciona el CRUD genérico, qué es `delete_strategy`, cómo se audita automáticamente** → `convenciones_generales.md`
- **Login, contraseñas, tokens, invitar a alguien a mi organización** → `autenticacion.md`
- **Quién puede ver/editar qué (permisos, roles)** → `autenticacion.md` §7 (modelo) + `usuarios_y_permisos.md` (gestión)
- **Por qué un usuario ve o no ve un lead/vista/formulario/política determinada** → `lead.md` §9 (leads), `vistas_de_leads.md` §4 (vistas), `equipos_y_enrutamiento.md` §5 (campañas/equipos)
- **Cómo se crea un lead paso a paso, qué validaciones corre** → `lead.md` §4-§5
- **Por qué un campo de un lead cambió solo, sin que nadie lo tocara** → `automatizacion_de_campos.md`, o si el cambio vino de una fórmula, `campos_personalizados.md` §7 (recálculo de `CALCULATED`)
- **Cómo se define qué campos tiene una campaña** → `campos_personalizados.md`
- **Por qué un lead no puede pasar de un estado a otro** → `flujo_de_leads.md` §5 y §8
- **Diferencia entre "estado" y "estado de contacto" de un lead** → `estados_de_contacto.md` (intro) y `flujo_de_leads.md` (intro)
- **Cómo se decide a qué equipo se asigna un lead nuevo automáticamente** → `equipos_y_enrutamiento.md` §6-§8
- **Importar/exportar leads desde Excel** → `importacion_y_exportacion.md`
- **Formularios públicos embebidos en una landing page** → `formularios_web.md`
- **Quién hizo qué cambio y cuándo (auditoría)** → `auditoria.md`
- **Catálogos de opciones (países, rubros, etc.)** → `nomencladores.md`
- **Reglas de validación de un campo (mínimo, máximo, formato, etc.)** → `reglas_de_validacion.md`
- **Subida de archivos/imágenes** → `almacenamiento.md`
- **Multi-tenancy: por qué un dato de otra empresa no debería aparecer nunca** → `autenticacion.md` §8 + `convenciones_generales.md` §6

## Hallazgos pendientes de esta ronda de documentación

Durante esta revisión (2026-07-10) se encontraron los siguientes puntos. Los que siguen listados abajo no fueron corregidos (trabajo solo de documentación/análisis), ordenados por impacto:

1. ~~**`nomencladores.md` §6** — la protección de "solo superadmin puede tocar ítems de un nomenclador global" nunca se activaba.~~ **RESUELTO (2026-07-10):** se corrigió `nomenclator_item_service.py` y se agregó `tests/functional/test_nomenclators.py`. Ver `nomencladores.md` §6 para el detalle. Los tests se escribieron pero no se pudieron correr en este entorno (sin PostgreSQL disponible) — confirmar corriendo la suite.
2. **`formularios_web.md` §7** — el módulo de formularios públicos (único endpoint de escritura sin autenticación del sistema, con lógica de seguridad propia: honeypot, rate limit, CAPTCHA, validación de dominio) no tiene ningún test.
3. ~~**`almacenamiento.md` §5** e **`importacion_y_exportacion.md` §7** — dos endpoints (`POST /storage/upload`, `POST /import/detect-headers`) son alcanzables sin autenticación.~~ **RESUELTO (2026-07-10):** se agregó `Depends(get_current_user_roles)` a ambos, `PermissionChecker("lead:create")` a `/import/process` y `PermissionChecker("lead:view")` a `/export/{campaign_id}`. Tests en `tests/functional/test_storage_and_import_permissions.py`. Ver `almacenamiento.md` §5 e `importacion_y_exportacion.md` §7 para el detalle.
4. ~~**`estados_de_contacto.md` §5** — un `PUT` que marca `is_initial=True` sin cambiar el `name` en el mismo request produce un `500` (variable no definida) en vez del `400` esperado.~~ **RESUELTO (2026-07-10):** se movió el cálculo de `org_id` antes de la Regla 1 en `lead_contact_state_service.py` y se agregó `test_lead_contact_state_set_initial_without_changing_name_returns_400` en `tests/functional/test_lead_contact_states.py`. Ver `estados_de_contacto.md` §5. Test no ejecutado en este entorno (sin PostgreSQL) — confirmar corriendo la suite.
5. **`organizaciones.md` §2** — el campo `Organization.require_lead_state_notes` no está conectado a ninguna lógica; existe pero no hace nada todavía.

Cada uno tiene su recomendación puntual de solución en la sección correspondiente del documento indicado.
