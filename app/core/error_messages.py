# app/core/error_messages.py

# Mensajes genéricos
ERROR_NOT_FOUND = "{model}({id}) no encontrado."
ERROR_CREATE = "Error al crear {model}."
ERROR_UPDATE = "Error al actualizar {model}({id})."
ERROR_DELETE = "Error al eliminar {model}({id})."
ERROR_DATABASE = "Error en la base de datos: {error}"
ERROR_VALIDATION = "Error de validación: {error}"
ERROR_UNKNOWN = "Error desconocido."

# Mensajes de éxito opcionales (si querés estandarizar logs)
SUCCESS_CREATE = "{model} creado correctamente (ID={id})."
SUCCESS_UPDATE = "{model}({id}) actualizado correctamente."
SUCCESS_DELETE = "{model}({id}) eliminado correctamente."
