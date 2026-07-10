# Importación y Exportación de Leads

Documentación técnica de la carga masiva de leads desde Excel y su exportación. Asume conocido `lead.md` (cada fila importada termina pasando por `LeadService.create`, con todo su pipeline de validación) y `convenciones_generales.md`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Endpoints](#2-endpoints)
3. [Importación: mapeo de columnas](#3-importación-mapeo-de-columnas)
4. [Resolución de nomencladores y leads relacionados](#4-resolución-de-nomencladores-y-leads-relacionados)
5. [Manejo de errores fila por fila](#5-manejo-de-errores-fila-por-fila)
6. [Exportación](#6-exportación)
7. [RESUELTO: permisos de este módulo](#7-resuelto-permisos-de-este-módulo)
8. [Cómo se testea](#8-cómo-se-testea)

---

## 1. Visión general

Este módulo no tiene modelo propio: opera sobre `Lead`/`LeadField` existentes, leyendo/escribiendo archivos Excel (`pandas` + `openpyxl`). Es, junto con `Búsqueda`/`Dashboard`/`Metadata`, uno de los pocos controllers del sistema que **no** hereda de `BaseController` — es un `APIRouter` de FastAPI armado a mano, sin `schema_in`/`schema_out` ni el patrón CRUD genérico.

Archivos principales:

| Archivo | Responsabilidad |
|---|---|
| `app/controllers/import_export_controller.py` | Endpoints `/import/*`, `/export/{campaign_id}` |
| `app/services/lead_import_export_service.py` | Lectura/escritura de Excel, mapeo de columnas, resolución de valores |
| `app/schemas/import_export_schema.py` | `ImportHeadersResponse`, `ImportResultResponse` |

---

## 2. Endpoints

| Método y ruta | Qué hace |
|---|---|
| `POST /import/detect-headers` | Sube un Excel, devuelve la lista de encabezados de columna detectados (sin procesar filas). |
| `POST /import/process` | Importa: recibe `campaign_id`, un `mapping` (JSON string `{"ColumnaExcel": "NombreCampoDB"}`) y el archivo. Crea un `Lead` por fila válida. |
| `GET /export/{campaign_id}` | Descarga un `.xlsx` con todos los leads activos de la campaña, una columna por `LeadField` (ordenadas por `order`). |

---

## 3. Importación: mapeo de columnas

El `mapping` que arma el frontend (después de llamar a `/import/detect-headers`) asocia cada columna del Excel a un campo de la campaña. Dos formatos de clave:

- **Simple**: `"ColumnaExcel": "NombreDelCampo"` — mapea directo al valor del campo.
- **Compuesta**: `"ColumnaExcel": "NombreDelCampo.atributo"` — usada para campos tipo `LEAD` (relación entre leads), donde `atributo` es el nombre de un campo primario del lead relacionado (ej. `"Email Referido": "Padre.Email"` para resolver el lead padre por su email). Varias columnas Excel pueden apuntar al mismo `NombreDelCampo` con distintos `atributo`, se agrupan para buscar el lead relacionado por combinación de criterios.

Los valores se leen como texto (`df.astype(str)`), con limpieza básica: `NaN`/`"nan"`/`"none"`/`"null"` se tratan como vacío, y un sufijo `.0` se recorta (para el caso típico de Excel convirtiendo enteros a float, ej. `"5.0"` → `"5"`). Campos `CALCULATED` y `FILE` se **ignoran** siempre en la importación (no tiene sentido importarlos: uno se calcula solo, el otro requeriría subir archivos por fuera del Excel).

Cada fila válida termina armando un `LeadCreate` y llamando a `LeadService.create` — es decir, corre el pipeline completo de validación, automatización, cálculo y duplicados descripto en `lead.md` §4, fila por fila, secuencialmente (no hay batching ni bulk-insert).

---

## 4. Resolución de nomencladores y leads relacionados

- **Nomencladores** (`_build_nomenclator_cache`): antes de procesar filas, arma un cache `{(nomenclator_id, texto_lower): item_id}` con todos los ítems de los nomencladores usados en la campaña, para no hacer una query por celda. El Excel debe traer el **texto** de la opción (no el ID) — si el texto no matchea ningún ítem del nomenclador, esa fila falla con el mensaje señalando el valor no encontrado. Soporta multi-selección separando por coma.
- **Leads relacionados** (`_resolve_related_leads`, campos tipo `LEAD`): busca en la campaña destino (`related_campaign_id`) un lead cuyos campos primarios coincidan exactamente con los valores de las columnas mapeadas. Si hay varias columnas de criterio, deben tener la misma cantidad de valores separados por coma (soporta relacionar con varios leads a la vez); si no encuentra ningún lead que matchee todos los criterios, la fila falla.

---

## 5. Manejo de errores fila por fila

La importación **no es transaccional en conjunto**: cada fila se procesa dentro de su propio `try/except`, y un error en una fila no aborta las demás (siguen procesándose las filas restantes). El resultado (`ImportResultResponse`) devuelve `total_rows`, `imported`, `failed`, y hasta **20** mensajes de error (`errors[:20]`) — si hay más de 20 filas fallidas, las siguientes no se reportan individualmente, solo cuentan en `failed`.

Nota: como cada fila llama a `LeadService.create` de forma independiente (cada una abre su propia `UnitOfWork` internamente), un archivo grande con muchas filas implica muchas transacciones cortas en secuencia, no una sola transacción con rollback total — si se corta la importación a mitad de camino (ej. error de conexión), las filas ya procesadas quedan creadas en la base.

---

## 6. Exportación

`GET /export/{campaign_id}` arma un `DataFrame` con una columna por cada `LeadField` activo de la campaña (en su `order`), y una fila por lead activo. Los campos de nomenclador se exportan como el/los texto(s) de la opción, separados por coma si es multi-selección (nunca el ID crudo). El nombre del archivo descargado se arma a partir del nombre de la campaña, normalizado (sin tildes, `ñ`→`n`, espacios→guión bajo, cualquier otro símbolo se elimina) para evitar problemas con el header `Content-Disposition`.

---

## 7. [RESUELTO] Permisos de este módulo

Al revisar `import_export_controller.py` se encontró que, a diferencia de casi todo el resto del sistema (donde `BaseController._get_deps` arma automáticamente un permiso `entidad:acción` por endpoint, ver `convenciones_generales.md` §7), este controller es un `APIRouter` manual que **no tenía ningún `PermissionChecker`**:

- `POST /import/detect-headers` no tenía **ninguna** dependencia de autenticación (`Depends(get_current_user_roles)` ausente en la firma) — era alcanzable sin estar logueado.
- `POST /import/process` y `GET /export/{campaign_id}` sí exigían estar autenticado (`get_current_user_roles`), pero no validaban ningún permiso específico — cualquier usuario autenticado de la organización podía importar o exportar leads de cualquier campaña a la que tuviera acceso de lectura por tenant, sin importar su rol.

**Fix aplicado** (`app/controllers/import_export_controller.py`):

- `POST /import/detect-headers`: se agregó `Depends(get_current_user_roles)` — ahora exige login.
- `POST /import/process`: se agregó `dependencies=[Depends(PermissionChecker("lead:create"))]` — mismo permiso que exige crear un lead por la vía normal (ver `autenticacion.md` §7).
- `GET /export/{campaign_id}`: se agregó `dependencies=[Depends(PermissionChecker("lead:view"))]` — **no** `lead:view_all` (la recomendación original de este documento decía `lead:view_all`, se corrigió al implementar). Motivo: `init_data.py` muestra que el rol `agent` (uso diario) solo tiene `lead:view`, no `lead:view_all` (ese es de `viewer`/`admin`); exigir `lead:view_all` le hubiera impedido a un agente exportar incluso sus propios leads asignados. `lead:view` + el filtro de visibilidad que ya aplica `LeadRepository.get_all` internamente (scope propio vs. todos, según si el usuario tiene `lead:view_all`) es el mismo patrón que usa `GET /leads/`, y sigue evitando que alguien sin ningún permiso sobre leads pueda exportar.

---

## 8. Cómo se testea

`tests/functional/test_excel_features.py`: exportación de datos de campaña, detección de encabezados, e importación de un archivo completo (caso feliz). Desde 2026-07-10, `tests/functional/test_storage_and_import_permissions.py` cubre el fix de §7: `detect-headers` sin token → `401`; usuario `viewer` (sin `lead:create`) intentando `/import/process` → `403`; usuario sin roles (sin `lead:view`) intentando `/export/{campaign_id}` → `403`; y un control de que el superadmin sigue pudiendo usar ambos endpoints con normalidad. **Sigue sin haber tests** para: filas con errores individuales (nomenclador inexistente, lead relacionado no encontrado, cantidad desigual de valores) ni el límite de 20 errores reportados — quedan fuera del alcance de este fix.
