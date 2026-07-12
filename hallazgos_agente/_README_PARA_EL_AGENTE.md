# Hallazgos de auditoría — carpeta de uso interno del AGENTE DE IA

Esta carpeta **no es documentación de usuario** (para eso está `docs/`). Es memoria de trabajo del agente de IA que asiste en este proyecto: acá vive el detalle completo de cada hallazgo de la auditoría técnica que se hizo el 2026-07-10, uno por módulo.

`AGENTS.md` (en la raíz del repo) tiene solo un índice corto de una línea por hallazgo. El detalle — qué se encontró, cómo se confirmó, qué se probó, qué se descartó, regresiones detectadas al arreglarlo, etc. — vive acá, para que `AGENTS.md` no crezca sin límite.

**Regla para el agente:** antes de investigar o tocar un hallazgo, leer el archivo de este directorio correspondiente al módulo. Al resolver o investigar algo nuevo sobre un hallazgo, actualizar **ese archivo** (no `AGENTS.md`). En `AGENTS.md` solo se actualiza el estado de una línea en la tabla-índice.

Archivos:

| Archivo | Módulo | Hallazgo(s) |
|---|---|---|
| `nomencladores.md` | Nomencladores | #1 |
| `estados_de_contacto.md` | Estados de contacto | #2 |
| `almacenamiento_y_importacion.md` | Almacenamiento / Importación-Exportación | #3 |
| `formularios_web.md` | Formularios web | #4 |
| `auditoria.md` | Auditoría (`SystemAuditLog`) | #5, #5b |
| `usuarios_y_permisos.md` | Usuarios y permisos | #6 |
| `organizaciones.md` | Organizaciones | #7 |
| `busqueda.md` | Búsqueda | #8 |
