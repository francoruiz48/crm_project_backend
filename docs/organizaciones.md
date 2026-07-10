# Organizaciones (`Organization`)

Documentación técnica del endpoint de gestión de organizaciones (el "tenant" del sistema multi-empresa). El concepto de multi-tenancy, el header `X-Organization-Id` y las reglas generales ya están documentados en `autenticacion.md` §8 y §10 — este doc profundiza en el detalle de qué hace exactamente `OrganizationService.create` al dar de alta una organización nueva, que en `autenticacion.md` solo se resume en 4 puntos. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Modelo de datos](#2-modelo-de-datos)
3. [Endpoints](#3-endpoints)
4. [Todo lo que se crea automáticamente al crear una organización](#4-todo-lo-que-se-crea-automáticamente-al-crear-una-organización)
5. [Cómo se testea](#5-cómo-se-testea)

---

## 1. Visión general

`Organization` es el tenant del sistema (ver `autenticacion.md` §1). Crear una organización es una operación con efectos secundarios importantes: no solo inserta una fila, sino que arma toda la estructura mínima para que esa organización sea usable de inmediato (flujo de ventas, estados de contacto, sección de campos, roles).

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/models/organization.py` | Modelo |
| `app/controllers/organization_controller.py` | Endpoints `/organizations/*` |
| `app/services/organization_service.py` | Todo el efecto secundario de creación |

---

## 2. Modelo de datos

```
Organization ──< UserOrganization >── User
```

Campos propios: `name`, `description`, `require_lead_state_notes` (booleano). El nombre sugiere "exigir notas al cambiar de estado un lead", pero **no se encontró ninguna referencia a este campo en todo el código de `app/`** fuera de su propia declaración en el modelo — `LeadService.change_state` (ver `lead.md` §7) acepta `notes` como parámetro siempre opcional, sin consultar este flag. Es un campo de configuración que existe en el modelo y probablemente en el schema, pero no está conectado a ninguna lógica de negocio todavía.

`delete_strategy = PROTECTED` (ver `convenciones_generales.md` §9) — una organización nunca se borra vía API, ni soft ni hard.

---

## 3. Endpoints

`OrganizationController` es genérico (`BaseController`, `enabled_methods = READ_WRITE`), con un detalle propio: sobreescribe `_get_deps` para que **`create` y `read` no requieran ningún permiso** (`return []`), a diferencia del resto del sistema donde `BaseController._get_deps` arma automáticamente `organization:create`/`organization:view` (ver `convenciones_generales.md` §7). Solo `update`/`delete` piden permiso. Tiene sentido: crear una organización es el primer paso de un usuario recién registrado (ver `autenticacion.md` §10, "el registro no crea una organización, son dos pasos separados") — en ese momento el usuario todavía no tiene ningún rol/permiso en ninguna organización, así que exigir un permiso para `POST /organizations/` dejaría a todo usuario nuevo sin forma de crear su primera organización.

`allowed_filter_fields = {"name", "description"}`.

---

## 4. Todo lo que se crea automáticamente al crear una organización

`OrganizationService.create`, en una sola transacción:

1. **Límite de propiedad**: si quien crea no es superadmin, valida que no sea ya `owner` de ninguna otra organización (`UserOrganization.is_owner=True` en cualquier organización) — un usuario común solo puede ser dueño de una organización (ver `autenticacion.md` §10).
2. Crea la fila `Organization`.
3. **`LeadFlow` por defecto** ("Flujo de Ventas Predeterminado"): con sus `LeadState` (`INITIAL_STATES`, constante en `app/core/constans.py`) y `LeadStateTransition` (`INITIAL_ROUTES_STATES`) — el embudo de ventas genérico con el que arranca toda organización nueva (ver `flujo_de_leads.md`).
4. **Estados de contacto por defecto** (`_create_default_contact_states`, ver `estados_de_contacto.md`): "No Contactado" (inicial), "Esperando Respuesta", "En Conversación", "Rechazado".
5. **Sección de campos por defecto** (`_create_default_sections`, ver `campos_personalizados.md`): una única sección "Información básica" — es la sección a la que caen los `LeadField` creados sin especificar `lead_field_section_id` explícito (ver `campos_personalizados.md` §5).
6. **Clonado de roles plantilla** (`_clone_default_roles_for_org`, ver `usuarios_y_permisos.md` §5 y `autenticacion.md` §7): copia `admin`/`agent`/`viewer` desde `ADMIN_ORG_ID` a la organización nueva, con los mismos permisos que tenía la plantilla en ese momento (cambios futuros a la plantilla global no se retro-propagan a organizaciones ya creadas).
7. **Corona al creador**: lo agrega como `UserOrganization` con `is_owner=True` y le asigna el rol `admin` recién clonado.

Todo esto corre dentro de la misma transacción que la creación de la organización — si algo falla a mitad de camino, no queda una organización "a medias" en la base.

---

## 5. Cómo se testea

`test_organization_creation_injects_states_and_initial` (`test_lead_contact_states.py`) confirma la inyección de estados de contacto. `test_org_creation_via_api_clones_roles` y `test_org_creator_gets_admin_role` (`test_permissions_and_roles.py`) confirman el clonado de roles y la asignación de `admin` al creador. No se encontró un test que verifique específicamente la creación del `LeadFlow`/sección por defecto de forma aislada (se ejercitan indirectamente porque casi todos los demás tests dependen de que existan, vía el fixture `initial_structure`), ni el límite de "una organización propia por usuario" (§4, paso 1) para el caso no-superadmin.
