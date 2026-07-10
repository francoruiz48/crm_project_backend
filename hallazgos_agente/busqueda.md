# Hallazgo #8 — Búsqueda (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/busqueda.md` §4
**Estado:** PENDIENTE — cosmético, baja prioridad.

## Qué se encontró

La búsqueda global incluye `"code"` como campo de `NomenclatorItem` en su configuración de campos buscables, pero esa columna no existe en el modelo `NomenclatorItem`. Se ignora en silencio (no rompe nada), pero es código muerto/incorrecto.

## Próximos pasos al retomar

1. Confirmar en `app/services/search_service.py` (o donde esté la config de campos por entidad) dónde se declara `"code"` para `NomenclatorItem`.
2. Sacar esa referencia (o corregirla si en realidad se quiso decir otro campo, ej. `value`).
3. Baja prioridad — dejar para el final de la lista.
