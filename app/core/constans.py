# Constantes para controladores
READ_ONLY = {"GET_ALL", "GET_ONE"}
READ_WRITE = {"GET_ALL", "GET_ONE", "POST", "PUT", "DELETE", "ACTIVE"}

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



