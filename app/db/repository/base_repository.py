from typing import Dict, Any, Iterable
from sqlalchemy.orm import selectinload
from app.core.exceptions import AppException, NotFoundException
from app.core.error_messages import ERROR_DATABASE, ERROR_NOT_FOUND


class BaseRepository:
    model = None
    schema_out = None
    relationships: list = []

    # ----------------- Helpers internos -----------------
    @classmethod
    def _apply_relationships(cls, query):
        """Aplica relaciones definidas en cls.relationships al query"""
        for chain in cls.relationships:
            option = selectinload(chain[0])
            for rel in chain[1:]:
                option = option.selectinload(rel)
            query = query.options(option)
        return query

    @staticmethod
    def _normalize_data(obj_data) -> Dict[str, Any]:
        """Convierte obj_data a dict (compatible con Pydantic u dict normal)"""
        if obj_data is None:
            return {}
        if hasattr(obj_data, "dict"):
            return obj_data.dict(exclude_unset=True)
        return dict(obj_data)

    # ----------------- CRUD Genérico -----------------
    @classmethod
    def get_all(cls, session, only_active: bool = True):
        """Trae todos los objetos, opcionalmente solo activos"""
        try:
            query = session.query(cls.model)
            query = cls._apply_relationships(query)

            if only_active and hasattr(cls.model, "active"):
                query = query.filter(cls.model.active.is_(True))

            result = query.all()
            return [cls.schema_out.model_validate(obj) for obj in result] if cls.schema_out else result

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def get_by_id(cls, session, obj_id: int, only_active: bool = True):
        """Trae un objeto por id"""
        try:
            query = session.query(cls.model)
            query = cls._apply_relationships(query)

            if only_active and hasattr(cls.model, "active"):
                query = query.filter(cls.model.active.is_(True))

            obj = query.filter(cls.model.id == obj_id).first()
            return cls.schema_out.model_validate(obj) if obj and cls.schema_out else obj

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def create(cls, session, obj_data=None):
        """Crea un objeto"""
        try:
            data = cls._normalize_data(obj_data)
            obj = cls.model(**data)
            session.add(obj)
            session.flush()  # flush para obtener ID antes de commit
            session.refresh(obj)
            return cls.schema_out.model_validate(obj) if cls.schema_out else obj

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def update(cls, session, obj_id: int, obj_data):
        """Actualiza un objeto por id"""
        try:
            data = cls._normalize_data(obj_data)
            obj = session.get(cls.model, obj_id)
            if not obj:
                return None

            for key, value in data.items():
                setattr(obj, key, value)

            session.flush()
            session.refresh(obj)
            return cls.schema_out.model_validate(obj) if cls.schema_out else obj

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def delete(cls, session, obj_id: int) -> bool:
        """Elimina un objeto por id"""
        try:
            obj = session.get(cls.model, obj_id)
            if not obj:
                return False
            session.delete(obj)
            session.flush()
            return True

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    # ----------------- Upsert relaciones One-to-Many -----------------
    @classmethod
    def upsert_children(
        cls,
        session,
        parent_model,
        parent_id: int,
        relation_name: str,
        items,
        key_attr: str,
        create_fn,
    ):
        """
        Upsert genérico sobre relaciones one-to-many.
        create_fn: lambda item -> instancia ORM
        """
        parent = session.get(parent_model, parent_id)
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
                child = create_fn(item)
                children.append(child)
                session.flush()
                session.refresh(child)

        session.refresh(parent)