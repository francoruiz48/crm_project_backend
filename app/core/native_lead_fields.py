"""
Registro de "campos nativos" del modelo Lead, utilizables como field_id/target_field_id en las
condiciones y acciones de Automatizaciones de Campos (`app/services/automation_engine.py`).

Los IDs (negativos) son LOS MISMOS que ya usa el frontend en
`frontend/src/features/lead/nativeLeadFields.ts` para los filtros/columnas de la lista de leads.
Se mantienen sincronizados a mano (no hay generación automática todavía) para que un
field_id/target_field_id negativo signifique exactamente lo mismo en toda la app. Si se agrega un
campo nativo nuevo de un lado, hay que replicarlo del otro con el mismo ID.

`writable` marca si una automatización puede sobreescribir ese campo directamente (Etapa, Estado,
Equipo, Usuario asignado) vs. si es de solo lectura -- utilizable en condiciones y como origen de
"Copiar de otro campo", pero no como destino de una acción (Fecha de creación/actualización,
Usuario Creador/Modificación son hechos de auditoría, no tiene sentido "setearlos" a mano).

Importante (pedido explícito del usuario 2026-07-25): cuando una automatización escribe un campo
nativo *writable*, se aplica como un UPDATE directo en la base de datos -- sin pasar por las
validaciones de negocio que sí exigen los endpoints dedicados (`change_state` valida transiciones
permitidas del flujo; `bulk-assign` valida que el usuario pertenezca al equipo). Sí queda
registrado en el historial/auditoría del lead, igual que cualquier otro cambio.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NativeLeadField:
    id: int
    attr: str   # nombre del atributo/columna real en el modelo Lead (app/models/lead.py)
    name: str   # display, mismo texto que en nativeLeadFields.ts
    writable: bool


_FIELDS = [
    NativeLeadField(id=-1, attr="contact_state_id",    name="Estado",                  writable=True),
    NativeLeadField(id=-2, attr="current_state_id",    name="Etapa",                   writable=True),
    NativeLeadField(id=-3, attr="team_id",             name="Equipo",                  writable=True),
    NativeLeadField(id=-4, attr="assigned_to_user_id", name="Asignado a",              writable=True),
    NativeLeadField(id=-5, attr="created_at",          name="Fecha de creación",       writable=False),
    NativeLeadField(id=-6, attr="updated_at",          name="Fecha de actualización",  writable=False),
    NativeLeadField(id=-7, attr="created_by",          name="Usuario Creador",         writable=False),
    NativeLeadField(id=-8, attr="updated_by",          name="Usuario Modificación",    writable=False),
]

# id -> NativeLeadField
NATIVE_LEAD_FIELDS: dict[int, NativeLeadField] = {f.id: f for f in _FIELDS}

# attr -> NativeLeadField (para construir el contexto a partir de un Lead/dict de valores)
NATIVE_LEAD_FIELDS_BY_ATTR: dict[str, NativeLeadField] = {f.attr: f for f in _FIELDS}

# ids que una automatización puede usar como target_field_id de una acción
WRITABLE_NATIVE_FIELD_IDS: set[int] = {f.id for f in _FIELDS if f.writable}

# Todos los ids nativos válidos (para condiciones / origen de "Copiar de otro campo")
ALL_NATIVE_FIELD_IDS: set[int] = set(NATIVE_LEAD_FIELDS.keys())


def is_native_field_id(field_id) -> bool:
    return isinstance(field_id, int) and field_id in NATIVE_LEAD_FIELDS


def build_native_context_from_lead(lead) -> dict:
    """
    Arma el dict {field_id_negativo: valor} a partir de un Lead ya persistido (usado en `update`,
    donde el lead ya existe antes de correr el motor de automatizaciones). Las fechas se formatean
    igual que en el resto del motor (`DATE_TIME_FORMAT`) para que operadores como IS_PAST/IS_FUTURE
    y las comparaciones funcionen igual que con un campo DATE_TIME normal.
    """
    from app.core.constans import DATE_TIME_FORMAT

    ctx = {}
    for f in _FIELDS:
        val = getattr(lead, f.attr, None)
        if f.attr in ("created_at", "updated_at") and val is not None:
            val = val.strftime(DATE_TIME_FORMAT)
        ctx[f.id] = val
    return ctx
