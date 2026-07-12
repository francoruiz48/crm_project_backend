# Almacenamiento (`StorageService`)

Documentación técnica del servicio de subida de archivos (avatares de lead, campos tipo `FILE`, adjuntos). Módulo agregado a esta ronda a pedido explícito. No tiene modelo propio — es un wrapper sobre Supabase Storage usado por otros módulos (`lead.md` §6, `campos_personalizados.md`). Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Validación de archivos](#2-validación-de-archivos)
3. [Subida y URL pública](#3-subida-y-url-pública)
4. [Endpoint directo `POST /storage/upload`](#4-endpoint-directo-post-storageupload)
5. [RESUELTO: endpoint sin autenticación](#5-resuelto-endpoint-sin-autenticación)
6. [Cómo se testea](#6-cómo-se-testea)

---

## 1. Visión general

`StorageService` es un cliente de Supabase Storage (`supabase-py`) usado internamente por `Lead` (avatares y campos `FILE`, ver `lead.md` §6) y expuesto también como endpoint directo (`POST /storage/upload`, ver §4). El cliente se inicializa perezosamente (`_client` singleton a nivel de clase, se crea en el primer uso).

Archivos: `app/controllers/storage_controller.py`, `app/services/storage_service.py`.

---

## 2. Validación de archivos

`validate_file(file, allowed_types)` — usado antes de cualquier subida real (fase 1 del patrón de dos fases descripto en `lead.md` §6):

- Valida `content_type` contra una lista blanca (`ALLOWED_IMAGE_TYPES`/`ALLOWED_DOCUMENT_TYPES`, definidas en `app/core/constans.py`, no leídas en esta pasada).
- Valida tamaño máximo (`MAX_FILE_SIZE_MB`), leyendo el archivo con `seek(0, 2)`/`tell()` para obtener el tamaño sin cargarlo entero en memoria de más.

Adicionalmente, `upload_file` valida algo que `validate_file` no cubre: que la **extensión del nombre de archivo** sea consistente con el `content_type` declarado (`_MIME_TO_EXTENSIONS`, ej. `image/jpeg` solo acepta `.jpg`/`.jpeg`) — previene el caso de un archivo `malware.exe` renombrado con `Content-Type: image/jpeg` para pasar el primer filtro. Si el MIME no está en el mapa, este chequeo se saltea sin bloquear (fallback permisivo para tipos no mapeados explícitamente, ej. `text/csv` en `import_export`).

---

## 3. Subida y URL pública

`upload_file(file, folder)`: genera un nombre único (`uuid4().<ext>`) para evitar colisiones y no depender del nombre original del archivo, sube el contenido a Supabase bajo `{folder}/{nombre_unico}`, y devuelve el **path relativo** (no la URL completa) — es lo que se guarda en `Lead.picture_url`/`LeadFieldValue.value` (ver `lead.md` §6).

`get_public_url(path)` resuelve ese path a una URL pública real, recién al momento de **leer** el dato (no se guarda la URL completa en la base, para no acoplarse a un dominio/bucket específico). Soporta el caso de datos migrados donde el campo ya tenía una URL completa guardada (`if path.startswith("http"): return path`, sin volver a resolver).

---

## 4. Endpoint directo `POST /storage/upload`

Además de usarse internamente desde `Lead`, existe un endpoint standalone: sube un archivo (sin restricción de tipo — no llama a `validate_file`, solo a `upload_file`, que únicamente valida la coherencia extensión/MIME, no una lista blanca de tipos permitidos) y devuelve `{path, url}`. No se encontró desde dónde lo consume el frontend en el código de este repositorio (podría ser para casos de uso genéricos fuera del flujo de leads).

---

## 5. [RESUELTO] Endpoint sin autenticación

**Bug (hasta 2026-07-10):** `POST /storage/upload` no tenía **ninguna** dependencia de autenticación en su firma (`def upload_file(file: UploadFile = File(...))`, sin `Depends(get_current_user_roles)`) — era alcanzable sin estar logueado. Además, al no llamar a `validate_file`, tampoco restringe tipos de archivo permitidos (solo bloquea si el nombre tiene una extensión inconsistente con un MIME **conocido**; esto último sigue así, ver nota abajo). En conjunto, antes del fix: cualquiera en internet podía subir archivos arbitrarios al bucket de Supabase de la organización, sin límite de tipo, consumiendo espacio y cuota. Es el mismo patrón de riesgo que tenía `POST /import/detect-headers` (ver `importacion_y_exportacion.md` §7).

**Fix aplicado:** se agregó `Depends(get_current_user_roles)` al endpoint — ahora exige estar logueado (login, sin requerir un permiso puntual, ya que no está atado a ninguna entidad del sistema).

**Decisión explícita, no aplicada:** no se agregó restricción de tipos de archivo (`validate_file`) — se evaluó y se decidió no hacerlo, porque es un endpoint genérico sin dueño claro (no se encontró desde dónde lo consume el frontend en este repo) y restringir mal el tipo podría romper un uso legítimo que no se ve en este código. Sigue pendiente si en el futuro se identifica su consumidor real.

---

## 6. Cómo se testea

`tests/functional/test_lead_fixes.py` (Grupo 12) cubre la validación de coherencia extensión/MIME de `StorageService.upload_file` directamente (extensión no coincide con el MIME declarado → `400`; coincide → pasa; MIME desconocido → se saltea el chequeo sin bloquear) — son tests unitarios sobre el service con mocks, no contra Supabase real. Desde 2026-07-10, `tests/functional/test_storage_and_import_permissions.py::TestUnauthenticatedAccessBlocked::test_storage_upload_requires_authentication` cubre el endpoint en sí: una request sin token a `POST /storage/upload` debe devolver `401` (antes del fix de §5, pasaba). No hay cobertura end-to-end de `validate_file`/tamaño máximo a través de la API (serían tests contra Supabase real o con mock del cliente).
