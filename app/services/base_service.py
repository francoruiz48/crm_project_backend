from app.core.logger import logger
from app.core.exceptions import AppException, NotFoundException
from app.core.error_messages import (
    ERROR_NOT_FOUND, ERROR_CREATE, ERROR_UPDATE, ERROR_DELETE, ERROR_DATABASE,
    SUCCESS_CREATE, SUCCESS_UPDATE, SUCCESS_DELETE
)
from sqlalchemy.exc import SQLAlchemyError

class BaseService:
    repository = None  # Subclases deben definirlo

    @classmethod
    def get_all(cls):
        model_name = cls.repository.model.__name__
        try:
            return cls.repository.get_all()
        except SQLAlchemyError as e:
            logger.error(ERROR_DATABASE.format(error=str(e)))
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def get_by_id(cls, obj_id: int):
        model_name = cls.repository.model.__name__
        result = cls.repository.get_by_id(obj_id)
        if not result:
            message = ERROR_NOT_FOUND.format(model=model_name, id=obj_id)
            logger.warning(message)
            raise NotFoundException(detail=message)
        return result

    @classmethod
    def create(cls, obj_data):
        model_name = cls.repository.model.__name__
        try:
            logger.info(f"Creando {model_name}...")
            obj = cls.repository.create(obj_data)
            logger.info(SUCCESS_CREATE.format(model=model_name, id=getattr(obj, 'id', '?')))
            return obj
        except SQLAlchemyError as e:
            message = ERROR_CREATE.format(model=model_name)
            logger.error(f"{message} Detalle: {str(e)}")
            raise AppException(detail=message)

    @classmethod
    def update(cls, obj_id, obj_data):
        model_name = cls.repository.model.__name__
        try:
            logger.info(f"Actualizando {model_name}({obj_id})...")
            updated = cls.repository.update(obj_id, obj_data)
            if not updated:
                raise NotFoundException(detail=ERROR_NOT_FOUND.format(model=model_name, id=obj_id))
            logger.info(SUCCESS_UPDATE.format(model=model_name, id=obj_id))
            return updated
        except SQLAlchemyError as e:
            message = ERROR_UPDATE.format(model=model_name, id=obj_id)
            logger.error(f"{message} Detalle: {str(e)}")
            raise AppException(detail=message)

    @classmethod
    def delete(cls, obj_id):
        model_name = cls.repository.model.__name__
        try:
            logger.info(f"Eliminando {model_name}({obj_id})...")
            deleted = cls.repository.delete(obj_id)
            if not deleted:
                raise NotFoundException(detail=ERROR_NOT_FOUND.format(model=model_name, id=obj_id))
            logger.info(SUCCESS_DELETE.format(model=model_name, id=obj_id))
            return {"deleted": True}
        except SQLAlchemyError as e:
            message = ERROR_DELETE.format(model=model_name, id=obj_id)
            logger.error(f"{message} Detalle: {str(e)}")
            raise AppException(detail=message)
