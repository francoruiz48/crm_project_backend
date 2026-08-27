# Plantillas (`/templates`)

Documentación técnica de los endpoints de catálogo estático que exponen las plantillas usadas por otros módulos (campos, reglas de validación, fórmulas Excel, máscaras de input). Módulo agregado a esta ronda a pedido explícito. No tiene modelo ni base de datos — todo el contenido vive hardcodeado en `app/core/templates/*.py`. Última revisión: 2026-07-10.

## Índice

1. [Visión general](#1-visión-general)
2. [Endpoints](#2-endpoints)
3. [Relación con otros módulos](#3-relación-con-otros-módulos)
4. [Cómo se testea](#4-cómo-se-testea)

---

## 1. Visión general

`TemplateController` es un `APIRouter` manual (no hereda `BaseController` — no tiene sentido, no hay entidad de base de datos detrás) que simplemente serializa diccionarios Python definidos en código a JSON. Pensado para que el frontend arme selectores/wizards ("elegí un tipo de campo predefinido", "elegí una regla de validación") sin tener que hardcodear esas listas también del lado del cliente.

Archivo: `app/controllers/template_controller.py`. Fuentes de datos: `app/core/templates/field_templates.py` (`STANDARD_FIELD_TEMPLATES`), `rule_templates.py` (`STANDARD_RULES`), `excel_formulas.py` (`EXCEL_FORMULAS`), `field_rules_map.py` (`STANDARD_INPUT_MASKS`).

---

## 2. Endpoints

Ninguno requiere autenticación (sin `Depends(get_current_user_roles)` en ninguna ruta) — es información estática de catálogo, no datos de ninguna organización, así que no representa un riesgo de exposición de datos (a diferencia de `almacenamiento.md` §5 e `importacion_y_exportacion.md` §7, donde la falta de auth sí es relevante porque esos endpoints escriben o procesan datos del usuario).

| Ruta | Devuelve |
|---|---|
| `GET /templates/lead_fields` | Plantillas de campo predefinidas (ver `campos_personalizados.md` §5) — código, nombre, tipo, reglas que trae incluidas, máscara. |
| `GET /templates/lead_fields/input_masks` | Catálogo de máscaras de input reutilizables (ver `campos_personalizados.md` §5). |
| `GET /templates/validation_rules` | Plantillas de `ValidationRule` (ver `reglas_de_validacion.md` §5) — código, nombre, descripción, parámetros requeridos, mensaje de error. |
| `GET /templates/excel_formulas` | Catálogo de funciones soportadas por `ExcelFormulaEvaluatorService` (usado por campos `CALCULATED`, reglas de validación y `Field_Automation`) — nombre en español/inglés, sintaxis, ejemplo, categoría, nota. |

---

## 3. Relación con otros módulos

Este controller no ejecuta lógica de negocio — es puramente informativo, un espejo de constantes que ya se usan del lado del servidor:

- `STANDARD_FIELD_TEMPLATES` es la misma fuente que consume `LeadFieldService.create_within_session` al crear un campo desde plantilla (`campos_personalizados.md` §5).
- `STANDARD_RULES` es la misma fuente que `ValidationRuleService._build_expression_from_template` (`reglas_de_validacion.md` §5).
- `EXCEL_FORMULAS` documenta las funciones que entiende `ExcelFormulaEvaluatorService`, motor compartido por campos `CALCULATED` (`campos_personalizados.md`), reglas de validación (`reglas_de_validacion.md`) y `Field_Automation` (no se leyó el archivo `excel_formulas.py` en esta pasada; el detalle de qué funciones soporta el evaluador queda fuera del alcance de este documento).

Si se agrega una plantilla nueva a cualquiera de estos catálogos en código, aparece automáticamente en el endpoint correspondiente sin tocar `template_controller.py` — el controller solo itera lo que encuentre en el diccionario.

---

## 4. Cómo se testea

No se encontró ningún test para los 4 endpoints de `/templates`. Dado que es contenido estático sin lógica de negocio ni acceso a datos, el riesgo de regresión silenciosa es bajo, pero tampoco hay ninguna verificación automática de que, por ejemplo, `GET /templates/validation_rules` siga sincronizado con `STANDARD_RULES` si alguien cambia la estructura del diccionario.
