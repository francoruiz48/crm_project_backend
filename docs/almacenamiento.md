# Almacenamiento (`StorageService`)

Documentación técnica del servicio de subida de archivos (avatares de lead, campos tipo `FILE`, adjuntos). Módulo agregado a esta ronda a pedido explícito. No tiene modelo propio — es un wrapper sobre Supabase Storage usado por otros módulos (`lead.md` §6, `campos_personalizados.md`). Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Validación de archivos](#2-validación-de-archivos)
3. [Subida y URL pública](#3-subida-y-url-pública)
4. [Endpoint directo `POST /storage/upload`](#4-endpoint-directo-post-storageupload)
5. [Punto pendiente: endpoint sin autenticación](#5-punto-pendiente-endpoint-sin-autenticación)
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

## 5. Punto pendiente: endpoint sin autenticación

`POST /storage/upload` no tiene **ninguna** dependencia de autenticación en su firma (`def upload_file(file: UploadFile = File(...))`, sin `Depends(get_current_user_roles)`) — es alcanzable sin estar logueado, y al no llamar a `validate_file`, tampoco restringe tipos de archivo permitidos (solo bloquea si el nombre tiene una extensión inconsistente con un MIME **conocido**; un archivo con un MIME fuera del mapa `_MIME_TO_EXTENSIONS` pasa sin ninguna validación de tipo). En conjunto: cualquiera en internet puede subir archivos arbitrarios al bucket de Supabase de la organización, sin límite de tipo, consumiendo espacio y cuota. Es el mismo patrón de riesgo que `POST /import/detect-headers` (ver `importacion_y_exportacion.md` §7).

**Recomendación:** agregar `Depends(get_current_user_roles)` (como mínimo) al endpoint, y considerar pasar una lista de tipos permitidos explícita (llamando a `validate_file` antes de `upload_file`, como ya hace el pipeline de `Lead`) en vez de subir cualquier archivo sin restricción de tipo. No se aplicó el cambio porque este documento es solo de análisis; avisá si querés que lo corrija.

---

## 6. Cómo se testea

`tests/functional/test_lead_fixes.py` (Grupo 12) cubre la validación de coherencia extensión/MIME de `StorageService.upload_file` directamente (extensión no coincide con el MIME declarado → `400`; coincide → pasa; MIME desconocido → se saltea el chequeo sin bloquear) — son tests unitarios sobre el service con mocks, no contra Supabase real. No se encontró ningún test para el endpoint `POST /storage/upload` en sí (ni su falta de autenticación, ni `validate_file`/tamaño máximo a través de la API).
