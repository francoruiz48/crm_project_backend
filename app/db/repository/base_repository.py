import re
from typing import Dict, Any, Iterable
from sqlalchemy.orm import selectinload
from app.core.exceptions import AppException, NotFoundException
from app.core.error_messages import ERROR_DATABASE, ERROR_NOT_FOUND
from sqlalchemy.exc import IntegrityError

class BaseRepository:
    model = None
    schema_out = None
    schema_out_detail = None
    relationships: list = []

    # ----------------- Helpers internos -----------------
    @classmethod
    def _execute_read_query(cls, query, detailed: bool = False):
        """
        Ejecuta una query de lectura aplicando:
        1. Relaciones (si detailed=True)
        2. Manejo de Errores (Try/Except genérico)
        3. Conversión a Esquema Pydantic
        """
        try:
            # A. Aplicar relaciones si es detailed
            if detailed and cls.relationships:
                query = cls._apply_relationships(query)

            # B. Ejecutar
            result = query.all()

            # C. Seleccionar esquema
            selected_schema = (
                cls.schema_out_detail 
                if detailed and cls.schema_out_detail 
                else cls.schema_out
            )

            # D. Convertir
            return [selected_schema.model_validate(obj) for obj in result] if selected_schema else result

        except Exception as e:
            # Aquí mantenemos la consistencia del manejo de errores
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))
        
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
    
    @staticmethod
    def _handle_integrity_error(e: IntegrityError):
        """
        Parsea el error de base de datos para dar un mensaje legible.
        Ej original: Key (campaign_id)=(99) is not present in table "campaign".
        """
        error_msg = str(e.orig) # Obtenemos el error original del driver (psycopg2)
        
        # Buscamos el patrón: Key (nombre_campo)=(valor)
        # Esto funciona estándar en Postgres
        match = re.search(r'Key \((.*?)\)=\((.*?)\)', error_msg)
        
        if match and "is not present in table" in error_msg:
            field_name = match.group(1)
            value = match.group(2)
            detail = f"El valor '{value}' para el campo '{field_name}' no existe en la base de datos relacionada."
        elif match and "already exists" in error_msg:
            field_name = match.group(1)
            detail = f"Ya existe un registro con el campo '{field_name}' igual a los datos proporcionados."
        else:
            detail = "Error de integridad de datos (posible ID inválido o duplicado)."

        raise AppException(detail=detail)

    # ----------------- CRUD Genérico -----------------
    @classmethod
    def get_all(cls, session, only_active: bool = True, detailed: bool = False):
        """Trae todos los objetos (Implementación Base)"""
        # 1. Construcción básica
        query = session.query(cls.model)
        
        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        # 2. Delegar ejecución al helper protegido
        return cls._execute_read_query(query, detailed)

    @classmethod
    def get_by_id(cls, session, obj_id: int, only_active: bool = True, detailed: bool = False):
        """
        Trae un objeto por id. 
        Si detailed=True, carga relaciones y usa schema_out_detail.
        """
        try:
            query = session.query(cls.model)

            if detailed and cls.relationships:
                query = cls._apply_relationships(query)
            
            if only_active and hasattr(cls.model, "active"):
                query = query.filter(cls.model.active.is_(True))

            obj = query.filter(cls.model.id == obj_id).first()

            if not obj:
                return None
            
            selected_schema = (
                cls.schema_out_detail 
                if detailed and cls.schema_out_detail 
                else cls.schema_out
            )

            return selected_schema.model_validate(obj) if selected_schema else obj

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

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
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

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
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
        try:
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
        
        except IntegrityError as e:
            session.rollback()
            # Esto usará tu nueva lógica para decir: 
            # "El valor '1' para el campo 'field_id' no existe..."
            cls._handle_integrity_error(e)

        except Exception as e:
            session.rollback()
            # Si ya es una AppException (ej: NotFoundException), la dejamos pasar
            if isinstance(e, AppException):
                raise e
            # Si es otro error desconocido, lanzamos el genérico
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))