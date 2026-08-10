"""
Archivo de diagnóstico temporal (2026-07-30), usado para aislar el bug real de
current_state_id en el motor de ruteo (ver hallazgo reportado a Franco sobre
lead_service.py::create/change_state/simulate_create). Ya cumplió su propósito
-- no se pudo borrar por la misma limitación de la herramienta de borrado que
test_zzz_debug_probe.py. Franco: se puede borrar a mano sin problema, no forma
parte de la suite real (no queda ningún test acá abajo).
"""
