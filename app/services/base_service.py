from app.core.logger import logger
from app.core.exceptions import AppException, NotFoundException
from app.core.error_messages import (
    ERROR_NOT_FOUND, ERROR_DATABASE,
    SUCCESS_CREATE, SUCCESS_UPDATE, SUCCESS_DELETE
)
from app.db.unit_of_work import UnitOfWork
from sqlalchemy.exc import SQLAlchemyError

class BaseService:
    repository = None  # Subclases deben definirlo

    # ---------- helpers internos ----------
    @classmethod
    def _model_name(cls):
        return cls.repository.model.__name__

    @classmethod
    def _not_found(cls, obj_id):
        raise NotFoundException(
            detail=ERROR_NOT_FOUND.format(model=cls._model_name(), id=obj_id)
        )

    @classmethod
    def _execute(
        cls,
        *,
        action: str,
        func,
        obj_id: int | None = None,
        success_msg: str | None = None
    ):
        model_name = cls._model_name()
        prefix = f"{model_name}({obj_id})" if obj_id else model_name

        logger.info(f"{action} {prefix}...")

        try:
            with UnitOfWork() as uow:
                result = func(uow)

                if result is None or result is False:
                    if obj_id:
                        cls._not_found(obj_id)

                if success_msg:
                    logger.info(success_msg.format(model=model_name, id=obj_id))

                return result

        except SQLAlchemyError as e:
            logger.error(f"{action} {model_name} falló. Detalle: {str(e)}")
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def get_all(cls, only_active: bool = True):
        return cls._execute(
            action="Obteniendo",
            func=lambda uow: cls.repository.get_all(uow.session, only_active)
        )

    @classmethod
    def get_by_id(cls, obj_id: int):
        return cls._execute(
            action="Obteniendo",
            obj_id=obj_id,
            func=lambda uow: cls.repository.get_by_id(uow.session, obj_id)
        )

    @classmethod
    def create(cls, obj_data):
        return cls._execute(
            action="Creando",
            func=lambda uow: cls.repository.create(uow.session, obj_data),
            success_msg=SUCCESS_CREATE
        )

    @classmethod
    def update(cls, obj_id: int, obj_data):
        return cls._execute(
            action="Actualizando",
            obj_id=obj_id,
            func=lambda uow: cls.repository.update(uow.session, obj_id, obj_data),
            success_msg=SUCCESS_UPDATE
        )

    @classmethod
    def delete(cls, obj_id: int):
        return cls._execute(
            action="Eliminando",
            obj_id=obj_id,
            func=lambda uow: cls.repository.delete(uow.session, obj_id),
            success_msg=SUCCESS_DELETE
        )

    @classmethod
    def set_disable(cls, obj_id: int):
        return cls._execute(
            action="Desactivando",
            obj_id=obj_id,
            func=lambda uow: cls.repository.update(uow.session, obj_id, {"active": False}),
            success_msg=SUCCESS_UPDATE
        )

    @classmethod
    def set_active(cls, obj_id: int):
        return cls._execute(
            action="Activando",
            obj_id=obj_id,
            func=lambda uow: cls.repository.update(uow.session, obj_id, {"active": True}),
            success_msg=SUCCESS_UPDATE
        )
