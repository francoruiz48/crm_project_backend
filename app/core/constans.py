# Constantes para controladores
READ_ONLY = {"GET_ALL", "GET_ONE"}
READ_WRITE = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE", "PATCH"}

# Organización del sistema (superadmins). Siempre tiene id=1 (primer seed).
ADMIN_ORG_ID = 1

DEFAULT_PAGE_SIZE = 50
PAGE_SIZE_LIMIT = 999
DATE_FORMAT = "%Y-%m-%d"
DATE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

NOMENCLATOR_FIELD_TYPES = ["SELECTOR", "CHECKBOX"]

MAX_FILE_SIZE_MB = 5
ALLOWED_IMAGE_TYPES = [
    "image/jpeg", 
    "image/png", 
    "image/webp", 
    "image/gif",
    "image/avif"
]
ALLOWED_DOCUMENT_TYPES = [
    "application/pdf",
    "application/msword", # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
    "application/vnd.ms-excel", # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", # .xlsx
    "text/plain",
    "text/csv"
]

class SystemAuditLogAction:
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    DISABLED = "DISABLED"
    ACTIVATED = "ACTIVATED"
    PATCHED = "PATCHED"
    PROMOTE_SUPERUSER = "PROMOTE_SUPERUSER"
    PROMOTE_OWNER = "PROMOTE_OWNER"


INITIAL_STATES = [
    {"name": "Ingresado", "category": "OPEN", "is_initial": True, "order": 1, "color": "#3b82f6", "position_x": 159, "position_y": -114.5},
    {"name": "Contactado", "category": "OPEN", "is_initial": False, "order": 2, "color": "#3b82f6", "position_x": 122, "position_y": 56},
    {"name": "Reunión Agendada", "category": "OPEN", "is_initial": False, "order": 3, "color": "#3b82f6", "position_x": 113, "position_y": 207},
    {"name": "Propuesta enviada", "category": "OPEN", "is_initial": False, "order": 4, "color": "#3b82f6", "position_x": 131, "position_y": 353},
    {"name": "Venta concretada", "category": "WON", "is_initial": False, "order": None, "color": "#22c55e", "position_x": 177, "position_y": 512},
    {"name": "No interesado", "category": "LOST", "is_initial": False, "order": None, "color": "#ef4444", "position_x": 601, "position_y": 240},
]

INITIAL_ROUTES_STATES = [
    # Happy Path lineal
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Vías directas a "No interesado" desde cualquier punto activo
    (0, 5), (1, 5), (2, 5), (3, 5),
    # Y si nos equivocamos y lo dimos por perdido, que pueda volver a "Contactado"
    (5, 1)
]


class DeleteStrategy:
    """
    Estrategias de borrado para BaseRepository.
    Configurar en cada repositorio via: delete_strategy = DeleteStrategy.XXXX

    HARD_DELETE_ALWAYS      → Borra físicamente siempre. Si hay FK violation → 409 con detalle.
    SOFT_DELETE_ALWAYS      → Siempre desactiva (active=False). No hay hard delete disponible.
    SOFT_DELETE_HARD_OPT    → Desactiva por defecto. Hard delete disponible pasando ?force=true,
                               con cascade de hijos según las relaciones del modelo.
    PROTECTED               → Nunca borrable (audit trails). Lanza error en cualquier intento.
    SMART_DELETE            → Desactiva por defecto. Hard delete con ?force=true SOLO si no hay
                               registros en delete_blockers. Cascades del modelo se aplican igual.
    HARD_DELETE_WITH_TOGGLE → Hard delete directo. Desactivación disponible via DELETE /active/{id}.
    """
    HARD_DELETE_ALWAYS      = "HARD_DELETE_ALWAYS"
    SOFT_DELETE_ALWAYS      = "SOFT_DELETE_ALWAYS"
    SOFT_DELETE_HARD_OPT    = "SOFT_DELETE_HARD_OPT"
    PROTECTED               = "PROTECTED"
    SMART_DELETE            = "SMART_DELETE"
    HARD_DELETE_WITH_TOGGLE = "HARD_DELETE_WITH_TOGGLE"
