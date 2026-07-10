# Hallazgo #7 — Organizaciones (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/organizaciones.md` §2
**Estado:** DOCUMENTADO, sin implementar — decisión explícita del usuario (2026-07-10).

## Qué se confirmó (investigación completa, no solo teórica)

`Organization.require_lead_state_notes` (`app/models/organization.py`) no está conectado a ninguna lógica en todo `app/` — confirmado con `grep -r require_lead_state_notes app/`, único resultado es la declaración de la columna en el modelo. Ni siquiera está expuesto en `app/schemas/organization_schema.py` (`OrganizationCreate`/`OrganizationUpdate`), así que **no se puede setear a `True` ni vía API** — es más muerto de lo que sugería la doc original (no es solo "no se lee", es "no se puede ni escribir"). `LeadService.change_state` (`app/services/lead_service.py:788`) acepta `notes: str = None` siempre opcional, sin consultar este flag en ningún punto.

## Decisión del usuario (2026-07-10)

Se le preguntó explícitamente qué hacer (implementar / eliminar / solo documentar). Eligió **"Dejar documentado que falta implementar en el futuro"**, aclarando: "no estoy seguro de si lo vamos a hacer así" — es decir, no hay certeza de que la feature tal como está pensada (un flag por organización que exige notas al cambiar de estado) sea la dirección de producto correcta. **No se tocó código.**

## Si se retoma en el futuro

Dos caminos, a decidir con el usuario en su momento (no asumir cuál sin preguntar):

1. **Implementar:** exponer `require_lead_state_notes` en `OrganizationCreate`/`OrganizationUpdate`, y en `LeadService.change_state` validar `notes` no vacío si `campaign.organization.require_lead_state_notes` (o el objeto organization correspondiente) es `True` — devolver `400` si falta.
2. **Eliminar:** sacar la columna del modelo y agregar un script de migración en `scripts/` (mismo patrón que `scripts/migrate_add_user_profile_fields.py`, `ALTER TABLE organization DROP COLUMN require_lead_state_notes;`) para limpiar la DB existente.

Bajo impacto — no es urgente.
