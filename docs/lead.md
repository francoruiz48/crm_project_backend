# Lead

Documentación técnica del módulo central del CRM: el `Lead` (registro comercial que avanza por un `LeadFlow`). Este doc asume conocidos los patrones descriptos en `convenciones_generales.md` (CRUD genérico, `delete_strategy`, auditoría automática) y se enfoca en lo específico de `Lead`, que **no** usa el patrón genérico de forma directa por la complejidad de sus campos dinámicos. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints de `/leads`](#3-endpoints-de-leads)
4. [Creación de un Lead: pipeline de `_prepare_creation_data`](#4-creación-de-un-lead-pipeline-de-_prepare_creation_data)
5. [Duplicados, validaciones y campos calculados](#5-duplicados-validaciones-y-campos-calculados)
6. [Archivos adjuntos (dos fases)](#6-archivos-adjuntos-dos-fases)
7. [Cambio de estado (`change_state`)](#7-cambio-de-estado-change_state)
8. [Actualización: historial legible vs. auditoría técnica](#8-actualización-historial-legible-vs-auditoría-técnica)
9. [Visibilidad de leads (`apply_security_filter`)](#9-visibilidad-de-leads-apply_security_filter)
10. [Reasignación masiva (`bulk_assign`)](#10-reasignación-masiva-bulk_assign)
11. [Borrado](#11-borrado)
12. [Cómo se testea](#12-cómo-se-testea)

---

## 1. Visión general

Un `Lead` pertenece a una `Campaign` (y por lo tanto a una `Organization`), tiene un conjunto de valores dinámicos (`field_values`, definidos por `LeadField` — ver `campos_personalizados.md`), un estado dentro del `LeadFlow` de su campaña (`current_state_id`, ver `flujo_de_leads.md`), opcionalmente un estado de contacto (`contact_state_id`, ver `estados_de_contacto.md`), tags, comentarios (ver `comentarios_de_leads.md`) y puede estar asignado a un `Team`/`User`.

La creación y actualización de un lead **no** son un simple insert: pasan por un pipeline que valida tipos, aplica automatizaciones (`Field_Automation`), evalúa campos calculados, chequea duplicados, sube archivos, corre el motor de enrutamiento de equipos (`equipos_y_enrutamiento.md`) y registra dos historiales distintos (uno técnico para auditoría, uno legible para el timeline visible del lead).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/lead.py` | Modelo `Lead` |
| `app/controllers/lead_controller.py` | Endpoints `/leads/*` (controller manual, no usa `BaseController.get_router()` directo) |
| `app/services/lead_service.py` | Toda la lógica de negocio: creación, update, cambio de estado, reasignación, búsqueda |
| `app/schemas/lead_schema.py` | Schemas de request/response |
| `app/db/repository/lead_repository.py` | Queries, `apply_security_filter`, `find_duplicate` |
| `app/services/automation_engine.py` | Motor de `Field_Automation`, se invoca en `ON_CREATE`/`ON_UPDATE` |
| `app/services/lead_validation_logic.py` | Reglas de `Validation_Rule` sobre cada campo |
| `app/services/excel_formula_evaluator_service.py` | Evalúa `CALCULATED` fields |
| `app/services/routing_rule_evaluator_service.py` | Motor de enrutamiento a equipos (ver `equipos_y_enrutamiento.md`) |

---

## 2. Modelo de datos

```
Campaign ──< Lead >── LeadFieldValue >── LeadField
   │            │
   │            ├──< LeadStateHistory
   │            ├──< LeadActivityHistory
   │            ├──< LeadComment
   │            └──< Tag (M2M, lead_tag_association)
   │
Organization ──< Lead
LeadState ──< Lead (current_state_id)
LeadContactState ──< Lead (contact_state_id)
Team ──< Lead (team_id, ON DELETE SET NULL)
User ──< Lead (assigned_to_user_id, ON DELETE SET NULL)
```

Campos nativos de `Lead` (además de los heredados de `BaseModelDB`, ver `convenciones_generales.md` §2): `campaign_id` (obligatorio), `organization_id` (obligatorio, se copia de la campaña), `picture_url`, `current_state_id`, `contact_state_id`, `team_id`, `assigned_to_user_id`. Si se borra el `Team` o el `User` asignado, el lead **no** se borra en cascada — el FK tiene `ondelete="SET NULL"`, el lead queda sin asignar.

`delete_strategy = HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9) — un `DELETE /leads/{id}` es físico y definitivo, sin soft delete. `field_values`, `comments` y `state_history` tienen `cascade="all, delete-orphan"`: se borran junto con el lead.

---

## 3. Endpoints de `/leads`

`LeadController` no hereda `BaseController.get_router()` directo: llama a `super().get_router()` (que solo trae `GET_ONE` y `DELETE`, por `enabled_methods = {"GET_ONE", "DELETE"}`) y agrega a mano el resto, porque `create`/`update` necesitan soportar **tanto JSON como `multipart/form-data`** (para subir archivos junto con los datos del lead).

| Método y ruta | Qué hace |
|---|---|
| `GET /leads/{id}` | Detalle (genérico, heredado). |
| `DELETE /leads/{id}` | Borrado físico (genérico, heredado). |
| `GET /leads/` | Listado paginado con filtro por `campaign_id`, búsqueda de texto (`query`), orden. |
| `POST /leads/search` | Búsqueda avanzada con body `LeadSearchRequest` (filtros complejos por campo dinámico). |
| `POST /leads/` | Crea un lead. Acepta JSON o multipart (archivos con key `file_<field_id>`, avatar con `avatar_file`). |
| `PUT /leads/{id}` | Actualiza. Igual que `POST`, soporta JSON/multipart, y permite mandar **solo archivos** sin JSON. |
| `POST /leads/simulate` | Corre el mismo pipeline de validación/automatización/cálculo que `POST /`, pero **no persiste nada** — para que el frontend arme formularios con feedback en vivo. |
| `POST /leads/{id}/change_state` | Cambia `current_state_id` validando que la transición exista en el `LeadFlow` de la campaña. |
| `PATCH /leads/bulk-assign` | Reasignación masiva a un equipo y/o usuario (ver §10). |

### Parseo híbrido (`_parse_hybrid_request`)

Un helper interno del controller detecta `Content-Type` y devuelve `(lead_dict, files_map, avatar_file)` sea el request JSON puro o multipart. En multipart, el JSON de datos va en un campo `data` (string), y cada archivo de un campo dinámico se manda como `file_<field_id>`.

---

## 4. Creación de un Lead: pipeline de `_prepare_creation_data`

`LeadService.create` (y `simulate_create`, que comparte el mismo pipeline) sigue esta secuencia:

1. Valida que la `campaign_id` exista.
2. Valida que `team_id`/`assigned_to_user_id` (si vienen) pertenezcan a la misma organización que la campaña.
3. `_prepare_creation_data`:
   1. Trae las definiciones de campo activas de la campaña (`LeadFieldRepository.get_all_active_with_rules`).
   2. Valida que cada `field_id` recibido exista y pertenezca a esa campaña (si no, error `400` estructural, corta antes de seguir).
   3. Convierte la lista `values` del request a un dict `{field_id: valor}` (`_prepare_context_dict`) — rechaza si el mismo campo viene repetido en el mismo request.
   4. **Fase 1 de archivos**: valida tipo/tamaño sin subir todavía (`_validate_file_uploads`), deja un placeholder `"__pending_upload__"` en el campo para que las validaciones de "requerido" no fallen en falso.
   5. Completa campos faltantes con `None` y aplica `default_value` a los que estén vacíos y no sean obligatorios (`_fill_missing_fields`, `_apply_defaults`).
   6. **Motor de automatización** (`AutomationEngine.run`, evento `ON_CREATE`) — puede sobreescribir valores según las reglas de `Field_Automation` (ver `automatizacion_de_campos.md`).
   7. Evalúa campos `CALCULATED` (`_evaluate_calculated_fields`) — si la fórmula falla, el campo queda en `None` en vez de romper la creación.
   8. Chequea duplicados por campos `is_primary` (`_check_duplicates`, ver §5).
   9. Valida tipos y reglas de negocio de cada campo (`_validate_processed_data`, ver §5).
   10. Si hubo errores en 8 o 9, `400` con la lista completa (no corta en el primer error).
   11. **Fase 2 de archivos**: recién ahora sube los archivos pre-validados (`_execute_file_uploads`) — evita subir archivos "huérfanos" si después la validación de negocio falla.
4. Resuelve el estado inicial del `LeadFlow` de la campaña (falla si no hay uno configurado) y el estado de contacto inicial de la organización (opcional, si existe uno con `is_initial=True`).
5. Corre el **motor de enrutamiento** (`RoutingRuleEvaluatorService.evaluate`) para decidir `team_id` automáticamente — gana sobre lo que mandó el frontend si alguna política matchea (ver `equipos_y_enrutamiento.md` §8).
6. Sube el avatar (`avatar_file`) si vino, separado de los archivos de campos dinámicos.
7. Inserta el lead, sus `field_values`, sus `tags` (si vinieron), un registro inicial en `LeadStateHistory` (`from_state_id=None`), una entrada `LEAD_CREATED` en `LeadActivityHistory`, y un `SystemAuditLog` de tipo `CREATED`.

`simulate_create` corre exactamente el mismo pipeline salvo por: los archivos no se suben de verdad (path simulado `simulated_path/<filename>`), y el resultado se arma a mano con `id=-1` sin tocar la base — pensado para que el frontend valide un formulario "en vivo" sin generar leads fantasma.

---

## 5. Duplicados, validaciones y campos calculados

- **Duplicados** (`_check_duplicates`): solo compara campos marcados `is_primary=True` que no sean de tipo nomenclador. Si **todos** esos campos coinciden con un lead existente de la misma campaña, es duplicado — `400` señalando el primer campo primario.
- **Validación por tipo** (`_check_field_definition`): tipo básico (`INT`/`NUMBER`/`BOOL`/`DATE`/`DATE_TIME`), máscara de input si el campo la tiene (`_validate_mask`, gramática simple: `#`=dígito, `A`=letra, `*`=alfanumérico, cualquier otro carácter es literal).
- **Reglas de negocio** (`LeadValidationLogic.validate_rules`): entran en juego las `Validation_Rule` configuradas por campo (ver `reglas_de_validacion.md`), solo si el campo pasó la validación de tipo básico y no está vacío.
- **Nomencladores**: valida que los IDs enviados existan, estén activos y pertenezcan al `nomenclator_id` configurado en el campo. Si el subtipo es `_SINGLE`, rechaza listas con más de un elemento.
- **Campo tipo `LEAD`** (relación entre leads): valida que los IDs sean enteros, que el lead relacionado exista **en la misma organización** (mensaje genérico si no existe, para no filtrar existencia cross-tenant), que no se relacione consigo mismo, y que pertenezca a la campaña configurada en `related_campaign_id`.
- **Campos calculados**: se evalúan con `ExcelFormulaEvaluatorService` sobre un contexto `{nombre_campo: valor_tipado}`. Si la fórmula tira excepción, el campo calculado queda `None` en vez de bloquear la creación/actualización.

**[PENDIENTE, ronda de bug-hunting 2026-07-10, hallazgo #17]** `_check_duplicates` es un chequeo a nivel de aplicación (`SELECT` seguido de `INSERT`, sin `with_for_update()` ni constraint de DB) — a diferencia de `change_state`, que sí usa `SELECT ... FOR UPDATE` para evitar condiciones de carrera. Dos requests de creación concurrentes con los mismos valores de campos `is_primary` podrían pasar ambas la verificación de duplicados antes de que la primera inserción se confirme, resultando en dos leads "duplicados" según la regla de negocio. Impacto bajo/medio (ventana de carrera muy chica, requiere que dos requests casi simultáneos manden exactamente los mismos datos primarios) y no es trivial de resolver con un constraint de DB real porque `is_primary` es una configuración dinámica por campaña, no una columna fija. Solución recomendada si se prioriza: usar un lock a nivel de aplicación (ej. advisory lock de Postgres por `(campaign_id, hash de valores primarios)`) alrededor de la fase de chequeo+inserción, similar al patrón que ya usa `change_state`. Ver `hallazgos_agente/lead.md`.

---

## 6. Archivos adjuntos (dos fases)

Tanto en creación como en actualización, la subida de archivos de campos tipo `FILE` sigue el mismo patrón de dos fases para evitar archivos huérfanos en el storage si después falla una validación de negocio:

1. **Fase 1** (`_validate_file_uploads`): valida que el `field_id` exista, sea de tipo `FILE`, y que el archivo respete el tipo permitido según el subtipo (`FILE_IMAGE` → `ALLOWED_IMAGE_TYPES`, `FILE_DOCUMENT` → `ALLOWED_DOCUMENT_TYPES`, sin subtipo → ambos). No sube nada todavía, solo dispara un placeholder en el contexto.
2. **Fase 2** (`_execute_file_uploads`): recién se ejecuta si **todas** las validaciones (tipo, duplicados, reglas) pasaron. Sube cada archivo con `StorageService.upload_file` (ver `almacenamiento.md`) y reemplaza el placeholder con el path real.

El avatar del lead (`picture_url`) es un caso aparte, fuera de este pipeline de campos dinámicos: se valida y sube directo con `StorageService` en el mismo método de `create`/`update`.

Las URLs de archivos (avatar y campos `FILE`) se enriquecen a `URL` pública recién al leer el lead (`_enrich_lead_with_urls`), no se guardan como URL completa en la base — se guarda el path relativo.

---

## 7. Cambio de estado (`change_state`)

`POST /leads/{id}/change_state`:

- Usa `SELECT ... FOR UPDATE` (`with_for_update()`) sobre el lead para evitar condiciones de carrera si dos requests cambian el estado al mismo tiempo.
- Rechaza si `new_state_id` es igual al estado actual.
- Si el lead **no tiene estado** (`current_state_id is None`), solo permite ir al estado inicial del flujo.
- Si tiene estado, exige que exista una `LeadStateTransition` explícita de `current_state_id` → `new_state_id` en el `LeadFlow` de la campaña (ver `flujo_de_leads.md`) — no hay "saltos libres".
- Registra el cambio en `LeadStateHistory` (historial técnico) y en `LeadActivityHistory` (timeline visible, evento `STATE_CHANGED`), además del `SystemAuditLog`.

---

## 8. Actualización: historial legible vs. auditoría técnica

`LeadService.update` reconstruye el estado actual de los `field_values` en memoria (`db_values`), lo mezcla con lo que llega en el request (`incoming_data`), corre el mismo pipeline de automatización + cálculo + duplicados + validación que en creación (evento `ON_UPDATE` en vez de `ON_CREATE`), y solo si todo pasa persiste.

Lo particular de `update` es que arma **dos** registros de cambio distintos por cada campo que efectivamente cambió (comparación normalizada: listas se ordenan, floats se redondean a 4 decimales, `None` se trata como string vacío):

- `changes` (técnico, con IDs crudos) → va a `SystemAuditLog` vía `_log_audit`.
- `history_changes` (legible, con nombres) → va a `LeadActivityHistory` como evento `FIELDS_UPDATED`. Los valores se traducen con `_translate_value_for_history`: IDs de nomenclador se resuelven a su `value` (texto), IDs de lead relacionado se resuelven concatenando los campos con `title_order` de ese lead (o `"Lead vinculado"` si no tiene ninguno con `title_order`).

Si el cambio vino de una regla de `Field_Automation`, `history_changes` incluye `source_rule` para que el frontend pueda mostrar "este campo se actualizó automáticamente por la regla X".

Nota de implementación: si hubo cambios en `field_values`, el servicio fuerza `lead.updated_at = func.now()` a mano — `upsert_values` solo toca las filas de `lead_field_value` (que tienen su propio `updated_at`), así que sin este paso el `updated_at` del lead quedaría desactualizado aunque haya cambiado contenido.

---

## 9. Visibilidad de leads (`apply_security_filter`)

`LeadRepository.apply_security_filter` es más fino que el default de `BaseRepository` (que no filtra nada). Sin filtro (ve todo) si: es superadmin, es `owner` de la organización, o tiene el permiso `lead:view_all`. Si no, un lead es visible si se cumple **alguna** de estas condiciones:

- La campaña del lead es pública (`Campaign.is_public = True`).
- El lead está asignado directamente al usuario (`assigned_to_user_id`).
- El usuario creó el lead (`created_by`).
- El usuario pertenece al `Team` del lead, **y** además: es `MANAGER` de ese equipo, **o** el equipo tiene `is_visibility_shared=True`, **o** el lead está sin asignar (`assigned_to_user_id IS NULL`, "libre" dentro del equipo).

Es la misma lógica de negocio descripta desde el ángulo de `Team` en `equipos_y_enrutamiento.md` §5, acá documentada desde el lado de la query real sobre `Lead`.

---

## 10. Reasignación masiva (`bulk_assign`)

`PATCH /leads/bulk-assign` — reasigna una lista de `lead_ids` a un `target_team_id` y/o `target_user_id` (al menos uno de los dos es obligatorio, validado en el controller). Reglas:

- Límite duro de **200 leads** por llamada (previene abuso/DoS).
- Valida que el equipo y el usuario destino pertenezcan a la organización activa.
- Si se mandan ambos, valida que el usuario destino sea efectivamente miembro del equipo destino.
- Filtra los leads por tenant **y** por `apply_security_filter` antes de tocarlos — un usuario no puede reasignar leads que no podría ver (protección IDOR).
- No corre el motor de enrutamiento (es reasignación manual y directa, a diferencia de la asignación automática en `create`).
- Loguea cada reasignación tanto en `LeadActivityHistory` (`LEAD_REASSIGNED`) como en `SystemAuditLog`.

---

## 11. Borrado

`delete_strategy = HARD_DELETE_ALWAYS` (ver `convenciones_generales.md` §9): `DELETE /leads/{id}` es físico y no reversible. Se llevan en cascada `field_values`, `comments` y `state_history` (definido a nivel de relación SQLAlchemy, `cascade="all, delete-orphan"`), pero **no** `LeadActivityHistory` ni `SystemAuditLog` — esos quedan como rastro histórico aunque el lead ya no exista (ver `auditoria.md`).

---

## 12. Cómo se testea

Suite principal: `tests/functional/test_leads.py` (creación simple, campos de distintos tipos, validación de máscaras, duplicados, ciclo de vida, búsqueda avanzada, nomencladores múltiples, filtrado, validación de enteros/decimales). Complementan: `test_lead_fixes.py`, `test_lead_flows_and_states.py` (transiciones de estado), `test_lead_relationships.py` (campos tipo `LEAD`), `test_lead_field_templates.py`, `test_lead_contact_states.py`, `test_lead_views.py`, `test_simulate_lead.py` (endpoint `/simulate`). La visibilidad por equipo/campaña pública se cubre en `test_teams_and_routing.py` (ver `equipos_y_enrutamiento.md` §12).
