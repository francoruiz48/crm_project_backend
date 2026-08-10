"""
Archivo de diagnóstico temporal (2026-07-30), usado para confirmar en vivo un bug real
reportado a Franco: LeadFieldValueBase.value sigue tipado como List[int] para campos
SELECTOR, pero NomenclatorItem.id que devuelve la API ahora es public_uuid (Fase 4) --
cualquier alta/edición real de un valor SELECTOR rompe con 422. Ya cumplió su
propósito -- no se pudo borrar por la misma limitación de la herramienta de borrado
que los otros test_zzz_debug*.py de esta sesión. Franco: se puede borrar a mano sin
problema, no forma parte de la suite real (no queda ningún test acá abajo).
"""
