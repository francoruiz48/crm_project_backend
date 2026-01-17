from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.exceptions.exceptions import ValidationError

async def pydantic_exception_handler(request: Request, exc: RequestValidationError):
    """
    Captura errores de validación de esquema (Pydantic) y los formatea 
    al estándar { detail: { message: "...", field: "..." } }
    """
    errors = exc.errors()
    
    if errors:
        first_error = errors[0]
        
        # 1. Obtener nombre del campo
        # loc suele ser ('body', 'nombre_campo') -> tomamos el último
        field_name = str(first_error["loc"][-1]) if first_error["loc"] else None
        
        # 2. Personalizar mensaje según el tipo de error
        error_type = first_error["type"]
        original_msg = first_error["msg"]
        message = original_msg
        
        if error_type == "missing":
            message = "Este campo es obligatorio."
        elif error_type == "int_type":
            message = "Se esperaba un número entero."
        elif error_type == "string_type":
            message = "Se esperaba un texto."
        elif error_type == "value_error":
             message = original_msg.replace("Value error, ", "")

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