# Búsqueda Global (`/search`)

Documentación técnica del endpoint de búsqueda global (barra de búsqueda tipo "buscar en todo el sistema"). Módulo agregado a esta ronda a pedido explícito (no estaba en la lista original). Asume conocido `convenciones_generales.md` §8 (mecanismo `search`/`search_fields` del CRUD genérico, que este módulo reutiliza). Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Endpoint](#2-endpoint)
3. [Qué entidades busca y por qué campos](#3-qué-entidades-busca-y-por-qué-campos)
4. [RESUELTO: `code` no existe en `NomenclatorItem`](#4-resuelto-code-no-existe-en-nomenclatoritem)
5. [Cómo se testea](#5-cómo-se-testea)

---

## 1. Visión general

`GET /search?query=...` corre en paralelo (secuencialmente, no con `asyncio.gather`) una búsqueda de texto parcial sobre 5 entidades distintas, devolviendo hasta 5 resultados de cada una. Reutiliza el mismo mecanismo `search`/`search_fields` (`ILIKE` sobre columnas de texto) que ya usa `GET /` en cualquier controller genérico (ver `convenciones_generales.md` §8), pero llamado directamente a nivel de repositorio en vez de vía un endpoint CRUD.

Archivos: `app/controllers/search_controller.py`, `app/services/search_service.py`, `app/schemas/search_schema.py`.

---

## 2. Endpoint

`GET /search?query=<texto>` — requiere sesión válida (`get_current_user_roles`), sin permiso adicional específico. `query` tiene mínimo 3 caracteres (validación de schema, `Query(..., min_length=3)`) — búsquedas más cortas devuelven `422` en vez de ejecutar la query.

---

## 3. Qué entidades busca y por qué campos

Cada búsqueda respeta `apply_security_filter`/tenant filter de su propio repositorio (ver `convenciones_generales.md` §6) — un usuario no ve en la búsqueda global nada que no pudiera ver listando esa entidad normalmente:

| Entidad | Campos buscados | Resultados |
|---|---|---|
| `Campaign` | `name`, `description` | Hasta 5 |
| `Workspace` | `name` | Hasta 5 |
| `NomenclatorItem` | `code`, `value` (ver §4) | Hasta 5 |
| `Nomenclator` | `name` | Hasta 5 |
| `Lead` | (default del repositorio — sin `search_fields` explícito, ver nota) | Hasta 5 |

**Nota sobre `Lead`:** a diferencia de las otras 4 búsquedas, la de `Lead` no pasa `search_fields` — usa el default del propio `LeadRepository.get_all`, que arma sus propios `JOIN`s para buscar en campos dinámicos tipo texto (ver `lead.md`, aunque el detalle exacto de qué campos cubre esa búsqueda vive en `lead_repository.py`, no en este módulo).

No se busca en `Tag`, `User`, `LeadField`, `WebForm` ni ninguna otra entidad — el alcance está fijo en código (`SearchService.global_search`), agregar una entidad nueva a la búsqueda global requiere tocar este archivo.

---

## 4. [RESUELTO] `code` no existe en `NomenclatorItem`

**Antes (hasta 2026-07-10):** `search_fields=["code", "value"]` para `NomenclatorItem` incluía `"code"`, pero el modelo `NomenclatorItem` (ver `nomencladores.md` §2) no tiene ninguna columna `code` — solo `value`. El motor de búsqueda genérico (`BaseRepository.get_all`) ignora en silencio los campos que no existen en el modelo (`hasattr(cls.model, field)`), así que no rompía nada — la búsqueda de nomencladores funcionaba solo por `value`, no por los dos campos que el código sugería. No era un bug funcional, era código que aparentaba más de lo que hacía.

**Fix aplicado:** se quitó `"code"` de `search_fields` en `SearchService.global_search` (`app/services/search_service.py`), dejando solo `["value"]` — sin cambio de comportamiento real, solo limpieza.

---

## 5. Cómo se testea

Desde 2026-07-10, `tests/functional/test_global_search.py` cubre: validación de `min_length=3` (`422` con query de 2 caracteres), caso feliz para `Campaign`/`Workspace`/`Nomenclator`/`NomenclatorItem` (búsqueda por `value`, confirmando que el fix de §4 sigue encontrando resultados), y aislamiento de tenant (un nomenclador/item de otra organización no aparece en los resultados). **Sigue sin haber cobertura específica** para la búsqueda de `Lead` (que usa un mecanismo distinto, sin `search_fields` explícito) ni para el caso de que una búsqueda devuelva resultados combinados de las 5 categorías a la vez.
