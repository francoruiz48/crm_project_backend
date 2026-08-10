"""
Archivo de diagnóstico temporal (2026-07-30), usado para aislar un bug real reportado
a Franco: el backfill de lead_field_value al crear un campo nuevo en una campaña con
leads existentes (lead_field_value_repository.py::initialize_values_for_new_field) usa
un INSERT crudo que no incluye public_uuid, y esa columna es NOT NULL -- rompe con 500
cualquier alta de campo en una campaña que ya tenga leads. Ya cumplió su propósito --
no se pudo borrar por la misma limitación de la herramienta de borrado que los otros
test_zzz_debug*.py de esta sesión. Franco: se puede borrar a mano sin problema, no
forma parte de la suite real (no queda ningún test acá abajo).
"""
