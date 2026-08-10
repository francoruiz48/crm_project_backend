# Hallazgo #8 — Búsqueda (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/busqueda.md` §4
**Estado:** RESUELTO (2026-07-10)

## Qué se confirmó

`SearchService.global_search` (`app/services/search_service.py`) pasaba `search_fields=["code", "value"]` al buscar `NomenclatorItem`. El modelo (`app/models/nomenclator_item.py`) no tiene columna `code`, solo `value` — confirmado leyendo el modelo directamente.

`BaseRepository.get_all` arma el filtro de búsqueda con `if hasattr(cls.model, field): ...` (línea ~300 de `app/db/repository/base_repository.py`) — los campos que no existen se descartan en silencio, no hay excepción ni error. Confirmado: no era un bug funcional, la búsqueda de `NomenclatorItem` ya funcionaba, solo que efectivamente por `value` únicamente (no por los dos campos que el código sugería).

## Fix aplicado

Se quitó `"code"` de `search_fields` en `SearchService.global_search`, dejando `["value"]`. Cambio de una línea, sin impacto funcional (el comportamiento real no cambia, solo se limpia código engañoso).

## Tests agregados

No existía **ningún** test para `GET /search` antes de esto. Se aprovechó el fix para agregar cobertura básica: `tests/functional/test_global_search.py` (5 casos):

1. `test_search_requires_minimum_query_length` — `422` con query de menos de 3 caracteres.
2. `test_search_finds_campaign_by_name`.
3. `test_search_finds_workspace_by_name`.
4. `test_search_finds_nomenclator_by_name_and_item_by_value` — confirma que el fix de `NomenclatorItem` sigue encontrando resultados por `value`.
5. `test_search_respects_tenant_isolation` — un nomenclador/item de otra organización no aparece en los resultados.

Pendiente confirmación del usuario corriendo `pytest tests/functional/test_global_search.py -v`.

## Con esto se cierran los 8 hallazgos de la auditoría 2026-07-10

Resueltos con código+tests: #1, #2, #3, #4, #5 (+5b), #6, #8. Documentado sin implementar por decisión del usuario: #7. Ver la tabla-índice en `AGENTS.md` §3.
