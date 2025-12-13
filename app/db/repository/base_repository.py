from typing  import Dict
from typing import Any, Iterable
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload, Load
from app.core.exceptions import AppException, NotFoundException
from app.core.error_messages import ERROR_DATABASE, ERROR_NOT_FOUND
from app.db.session import SessionLocal
from app.db.utils.with_all_relationships import with_all_relationships


class BaseRepository:
    model = None
    schema_out = None
    relationships: list = []

    @classmethod
    def _apply_relationships(cls, query):
        for chain in cls.relationships:
            option = selectinload(chain[0])
            for rel in chain[1:]:
                option = option.selectinload(rel)
            query = query.options(option)
        return query
    
    @staticmethod
    def _normalize_data(obj_data) -> Dict[str, Any]:
        if obj_data is None:
            return {}
        if hasattr(obj_data, "dict"):
            return obj_data.dict(exclude_unset=True)
        return dict(obj_data)

    @classmethod
    def get_all(cls, only_active: bool = True):
        try:
            with SessionLocal() as db:
                query = db.query(cls.model)
                query = cls._apply_relationships(query)


                if only_active and hasattr(cls.model, "active"):
                    query = query.filter(cls.model.active.is_(True))

                result = query.all()

                if cls.schema_out:
                    return [cls.schema_out.model_validate(obj) for obj in result]

                return result
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))


    @classmethod
    def get_by_id(cls, obj_id: int, only_active: bool = True):
        try:
            with SessionLocal() as db:
                query = db.query(cls.model)
                query = cls._apply_relationships(query)

                if only_active and hasattr(cls.model, "active"):
                    query = query.filter(cls.model.active.is_(True))

                result = query.filter(cls.model.id == obj_id).first()

                return cls.schema_out.model_validate(result) if result and cls.schema_out else result
        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def upsert_children(
        cls,
        parent_model,
        parent_id: int,
        relation_name: str,
        items: Iterable,
        key_attr: str,
        create_fn,
    ):
        """
        Upsert genérico sobre relaciones one-to-many.
        create_fn: lambda item -> instancia ORM
        """
        with SessionLocal() as db:
            parent = db.get(parent_model, parent_id)
            if not parent:
                raise NotFoundException(
                    detail=ERROR_NOT_FOUND.format(
                        model=parent_model.__name__, id=parent_id
                    )
                )

            children = getattr(parent, relation_name)
            existing = {getattr(c, key_attr): c for c in children}

            for item in items:
                key = getattr(item, key_attr)
                if key in existing:
                    for attr, value in item.dict().items():
                        setattr(existing[key], attr, value)
                else:
                    children.append(create_fn(item))

            db.commit()

    @classmethod
    def create(cls, obj_data=None):
        try:
            data = cls._normalize_data(obj_data)

            with SessionLocal() as db:
                obj = cls.model(**data)
                db.add(obj)
                db.commit()
                db.refresh(obj)

                query = db.query(cls.model)
                query = cls._apply_relationships(query)
                obj = query.filter(cls.model.id == obj.id).first()

                return cls.schema_out.model_validate(obj) if cls.schema_out else obj

        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))


    @classmethod
    def update(cls, obj_id: int, obj_data):
        try:
            data = cls._normalize_data(obj_data)

            with SessionLocal() as db:
                obj = db.get(cls.model, obj_id)
                if not obj:
                    return None

                for key, value in data.items():
                    setattr(obj, key, value)

                db.commit()
                db.refresh(obj)

                query = db.query(cls.model)
                query = cls._apply_relationships(query)
                obj = query.filter(cls.model.id == obj_id).first()

                return cls.schema_out.model_validate(obj) if cls.schema_out else obj

        except SQLAlchemyError as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))


    @classmethod
    def delete(cls, obj_id: int) -> bool:
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
