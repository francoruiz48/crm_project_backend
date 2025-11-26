from fastapi import HTTPException, status
from app.core import error_messages as errors

class AppException(HTTPException):
    """Excepción base para el sistema."""
    def __init__(self, status_code=status.HTTP_400_BAD_REQUEST, detail=None):
        super().__init__(status_code=status_code, detail=detail or "Error desconocido")


class NotFoundException(AppException):
    def __init__(self, detail=None):
        super().__init__(status.HTTP_404_NOT_FOUND, detail or errors.ERROR_NOT_FOUND)


class AlreadyExistsException(AppException):
    def __init__(self, detail=None):
        super().__init__(status.HTTP_409_CONFLICT, detail or errors.ERROR_ALREADY_EXISTS)


class InvalidDataException(AppException):
    def __init__(self, detail=None):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail or errors.ERROR_INVALID_DATA)
