# Hallazgo #7 — Organizaciones (para el agente)

> Ver `hallazgos_agente/_README_PARA_EL_AGENTE.md` para las reglas de esta carpeta.

**Doc de usuario:** `docs/organizaciones.md` §2
**Estado:** PENDIENTE — bajo impacto, es un flag muerto.

## Qué se encontró

`Organization.require_lead_state_notes` existe como columna en el modelo (`app/models/organization.py`) pero no está conectado a ninguna lógica en todo `app/` — no se lee ni se valida en ningún service ni controller. Es un flag que se puede setear vía API pero que hoy no tiene ningún efecto funcional.

## Próximos pasos al retomar

1. Confirmar con grep que efectivamente no se usa en ningún lado (`grep -r require_lead_state_notes app/`).
2. Decidir con el usuario: ¿se implementa la lógica que falta (obligar `notes` al cambiar de estado si el flag está activo), o se elimina el campo por no usarse?
3. Bajo impacto — no es urgente, se puede dejar para el final.
