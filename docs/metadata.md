# Metadata (`/metadata`)

Documentación técnica del endpoint de diccionarios estáticos del sistema (enums, categorías, catálogos de opciones para dropdowns). Módulo agregado a esta ronda a pedido explícito. Sin modelo propio — expone `SYSTEM_DICTIONARIES`, definido en `app/core/dictionaries.py`, más una clave dinámica agregada el 2026-08-10 (`entity_delete_strategies`, ver §3-bis). Última revisión: 2026-08-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Endpoint](#2-endpoint)
3. [Qué contiene `SYSTEM_DICTIONARIES`](#3-qué-contiene-system_dictionaries)
3-bis. [`entity_delete_strategies`: método de borrado por entidad](#3-bis-entity_delete_strategies-método-de-borrado-por-entidad)
4. [`SYSTEM_ENTITIES_REGISTRY`: la fuente de los permisos automáticos](#4-system_entities_registry-la-fuente-de-los-permisos-automáticos)
5. [Cómo se testea](#5-cómo-se-testea)

---

## 1. Visión general

Es la contraparte de `plantillas.md` pero para enums/catálogos de sistema en vez de plantillas de configuración: valores fijos que el frontend necesita para poblar selects (roles de equipo, categorías de estado, operadores de búsqueda, etc.) sin tener que hardcodearlos también del lado del cliente ni consultar la base de datos.

Archivo: `app/controllers/meta_data_controller.py`. Fuente: `app/core/dictionaries.py::SYSTEM_DICTIONARIES`.

---

## 2. Endpoint

`GET /metadata/dictionaries` — requiere sesión válida (`get_current_user_roles`), sin permiso adicional. Acepta `?keys=clave1,clave2` para traer solo un subconjunto (las claves que no existan en el diccionario se ignoran en silencio, no dan error); sin el parámetro, devuelve el diccionario completo.

---

## 3. Qué contiene `SYSTEM_DICTIONARIES`

| Clave | Contenido |
|---|---|
| `lead_search_operators` | Operadores disponibles para `POST /leads/search` (ver `lead.md` §3). |
| `routing_condition_types` | `NATIVE`/`DYNAMIC` — distinción de campo nativo vs. dinámico en condiciones de enrutamiento (ver `equipos_y_enrutamiento.md` §6). |
| `team_roles` | `MANAGER`/`AGENT` (ver `equipos_y_enrutamiento.md` §4). |
| `lead_states_categories` | `OPEN`/`WON`/`LOST` (ver `flujo_de_leads.md` §2). |
| `lead_view_visibilities` | `PRIVATE`/`TEAM`/`PUBLIC` (ver `vistas_de_leads.md` §2). |
| `system_audit_log_actions` | Acciones posibles de `SystemAuditLog` (`CREATED`/`UPDATED`/`DELETED`/`DISABLED`/`ACTIVATED`/`PROMOTE_SUPERUSER`/`PROMOTE_OWNER`, ver `auditoria.md` §2). |

También expone (en otra sección del mismo archivo, no bajo `SYSTEM_DICTIONARIES` sino usada por `Field_Automation`, ver `automatizacion_de_campos.md`) el mapa de operadores/acciones válidos **por tipo de campo dinámico** — qué `ConditionOperatorEnum`/`ActionTypeEnum` tiene sentido ofrecer en el editor visual de automatizaciones según si el campo es `STRING`, `INT`, `NUMBER`, `BOOL`, etc. No se confirmó en esta pasada si esta parte específica se sirve también por `/metadata/dictionaries` bajo alguna clave, o si es exclusivamente de uso interno del backend.

---

## 3-bis. `entity_delete_strategies`: método de borrado por entidad

**[NUEVO 2026-08-10]** Clave agregada a pedido explícito para que el frontend pueda automatizar la UI de borrado (mostrar confirmación simple, ofrecer el toggle `?force=true`, deshabilitar el botón de borrar si la entidad es `PROTECTED`, etc.) sin tener que hardcodear a mano qué estrategia usa cada entidad.

A diferencia del resto de `SYSTEM_DICTIONARIES`, **no es un dict estático**: `app/core/dictionaries.py::get_entity_delete_strategies()` recorre en runtime todas las subclases de `BaseRepository` (recursivo) y arma `{NombreModelo: delete_strategy}` leyendo el atributo `delete_strategy` real de cada repositorio. `meta_data_controller.py` la llama en cada request y la mergea al resto de `SYSTEM_DICTIONARIES` antes de responder — por eso, a diferencia de las demás claves, nunca queda desincronizada si se agrega un repositorio nuevo o cambia la estrategia de uno existente.

Ejemplo de respuesta (`GET /metadata/dictionaries?keys=entity_delete_strategies`):

```json
{
  "entity_delete_strategies": {
    "Lead": "HARD_DELETE_ALWAYS",
    "Role": "SOFT_DELETE_ALWAYS",
    "Campaign": "SOFT_DELETE_HARD_OPT",
    "Organization": "PROTECTED",
    "LeadField": "SMART_DELETE",
    "LeadRoutingPolicy": "HARD_DELETE_WITH_TOGGLE"
  }
}
```

La clave de cada entrada es el nombre de la clase del modelo (`Lead`, `Role`, `TeamCampaignAccess`, etc.), **no** el código de entidad de `SYSTEM_ENTITIES_REGISTRY` (`lead`, `role`) ni el nombre de la tabla — hay que armar la traducción del lado del frontend si se necesita cruzar contra esos otros catálogos. El significado de cada valor posible (`HARD_DELETE_ALWAYS`, `SOFT_DELETE_ALWAYS`, `SOFT_DELETE_HARD_OPT`, `PROTECTED`, `SMART_DELETE`, `HARD_DELETE_WITH_TOGGLE`) está documentado en `convenciones_generales.md` §5; la tabla de referencia completa (ahora también obsoleta apenas se agregue un repo sin actualizarla a mano) vive en `convenciones_generales.md` §9, que enlaza de vuelta acá como fuente de verdad en runtime.

---

## 4. `SYSTEM_ENTITIES_REGISTRY`: la fuente de los permisos automáticos

En el mismo archivo `dictionaries.py` (pero **no** expuesto por `/metadata/dictionaries`) vive `SYSTEM_ENTITIES_REGISTRY` — el registro de todas las entidades del sistema (`Lead`, `LeadField`, `Campaign`, `Nomenclator`, `User`, `Team`, `LeadRoutingPolicy`, `WebForm`, `FieldAutomation`, etc., cada una con su `crud_type`: `FULL` o `READ_ONLY`) que usa `app/db/init_data.py::seed_rbac` para generar automáticamente los permisos `entidad:acción` de cada organización (ver `autenticacion.md` §7 y `convenciones_generales.md` §7). Es decir: agregar una entidad nueva a este registro es lo que hace que aparezcan sus permisos (`nueva_entidad:create`, `:view`, etc.) disponibles para asignar a roles — sin tocar nada en `security_models.py` ni en el seed de permisos directamente.

---

## 5. Cómo se testea

No se encontró ningún test para `GET /metadata/dictionaries` (ni el caso sin `keys`, ni el filtrado por `keys`, ni claves inexistentes ignoradas). Dado que es contenido estático de solo lectura, el riesgo es bajo, pero al ser la fuente de verdad que el frontend usa para poblar selects críticos (roles de equipo, categorías de estado), una desincronización silenciosa entre el diccionario y lo que el backend realmente acepta en otros endpoints no quedaría detectada por ningún test automatizado hoy. Tampoco hay test para `entity_delete_strategies` (§3-bis) — sería el más fácil de cubrir de toda la lista, ya que alcanza con recorrer `SYSTEM_ENTITIES_REGISTRY` (o directamente las subclases de `BaseRepository`) y comparar contra la respuesta del endpoint, sin necesidad de fixtures de negocio.
