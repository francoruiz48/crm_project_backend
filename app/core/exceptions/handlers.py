from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.exceptions.exceptions import ValidationError

async def pydantic_exception_handler(request: Request, exc: RequestValidationError):
    """
    Convierte errores de Pydantic a español y formato estándar.
    """
    errors = exc.errors()
    
    if errors:
        first_error = errors[0]
        
        # 1. Obtener nombre del campo
        # loc suele ser ('body', 'nombre') -> tomamos el último
        field_name = str(first_error["loc"][-1]) if first_error["loc"] else None
        
        # 2. Datos del error
        error_type = first_error["type"]
        ctx = first_error.get("ctx", {}) # Contexto (ej: límite de caracteres)
        
        # 3. Traducción
        message = first_error["msg"] # Fallback: mensaje original en inglés
        
        # --- DICCIONARIO DE TRADUCCIÓN ---
        if error_type == "missing":
            message = "Este campo es obligatorio."
            
        elif error_type == "string_type":
            message = "Se espera un valor de texto."
            
        elif error_type == "int_type":
            message = "Se espera un número entero."
            
        elif error_type == "bool_type":
            message = "Se espera un valor booleano (true/false)."
            
        # Validaciones de longitud (String)
        elif error_type == "string_too_short":
            limit = ctx.get("min_length")
            message = f"El texto debe tener al menos {limit} caracteres."
            
        elif error_type == "string_too_long":
            limit = ctx.get("max_length")
            message = f"El texto no puede superar los {limit} caracteres."

        # Validaciones numéricas (gt, ge, lt, le)
        elif error_type == "greater_than":
            limit = ctx.get("gt")
            message = f"El valor debe ser mayor a {limit}."
            
        elif error_type == "greater_than_equal":
            limit = ctx.get("ge")
            message = f"El valor debe ser mayor o igual a {limit}."

        elif error_type == "value_error":
             message = message.replace("Value error, ", "")

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "detail": {
                    "message": message,
                    "field": field_name
                }
            },
        )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": {"message": "Error de validación.", "field": None}},
    )

async def custom_validation_exception_handler(request: Request, exc: ValidationError):
    """
    Captura nuestra excepción ValidationError (lógica de negocio) 
    y devuelve el mismo formato JSON.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": {
                "message": exc.message,
                "field": exc.field
            }
        },
    )