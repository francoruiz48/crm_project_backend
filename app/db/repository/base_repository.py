from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from app.core.exceptions import AppException
from app.core.error_messages import ERROR_DATABASE
from app.db.session import SessionLocal
from app.db.utils.with_all_relationships import with_all_relationships


class BaseRepository:
    model = None
    schema_out = None
    relations = None

    @classmethod
    def _apply_relationship_loading(cls, query):
        if cls.relations:
            for rel in cls.relations:
                query = query.options(selectinload(rel))
            return query

        # Comportamiento viejo: cargar TODAS las relaciones automáticamente
        return with_all_relationships(query, cls.model)

    @classmethod
    def get_all(cls):
        try:
            with SessionLocal() as db:
                query = db.query(cls.model)
                query = cls._apply_relationship_loading(query)
                return query.all()
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def get_by_id(cls, obj_id: int):
        try:
            with SessionLocal() as db:
                query = db.query(cls.model)
                query = cls._apply_relationship_loading(query)
                return query.filter(cls.model.id == obj_id).first()
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def create(cls, obj_data):
        try:
            with SessionLocal() as db:
                obj = cls.model(**obj_data.dict())
                db.add(obj)
                db.commit()
                db.refresh(obj)

                # Volvemos a pedir el objeto con relaciones (según configuración)
                query = db.query(cls.model)
                query = cls._apply_relationship_loading(query)
                result = query.filter(cls.model.id == obj.id).first()

                return cls.schema_out.model_validate(result) if cls.schema_out else result
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def update(cls, obj_id, obj_data):
        try:
            with SessionLocal() as db:
                obj = db.get(cls.model, obj_id)
                if not obj:
                    return None

                for key, value in obj_data.dict().items():
                    setattr(obj, key, value)

                db.commit()
                db.refresh(obj)

                # Volvemos a obtenerlo con las relaciones que correspondan
                query = db.query(cls.model)
                query = cls._apply_relationship_loading(query)
                result = query.filter(cls.model.id == obj.id).first()

                return cls.schema_out.model_validate(result) if cls.schema_out else result
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def delete(cls, obj_id):
        try:
            with SessionLocal() as db:
                obj = db.get(cls.model, obj_id)
                if not obj:
                    return False

                db.delete(obj)
                db.commit()
                return True
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))
