"""
Archivo de diagnóstico temporal (2026-07-30), usado para confirmar en vivo el bug de
FieldAutomation (RuleCondition.field_id/AutomationAction.target_field_id tipados como
int puro, rotos contra uuids reales de LeadField) reportado a Franco y ya arreglado
(ver field_automation_schema.py/field_automation_service.py). Ya cumplió su propósito
-- no se pudo borrar por la misma limitación de la herramienta de borrado que los
otros test_zzz_debug*.py de esta sesión. Franco: se puede borrar a mano sin problema,
no forma parte de la suite real (no queda ningún test acá abajo).
"""
