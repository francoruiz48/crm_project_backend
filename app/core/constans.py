# Constantes para controladores
READ_ONLY = {"GET_ALL", "GET_ONE"}
READ_WRITE = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE", "PATCH"}

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
