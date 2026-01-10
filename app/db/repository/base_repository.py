import re
from typing import Dict, Any
from sqlalchemy.orm import selectinload
from app.core.exceptions import AppException, NotFoundException
from app.core.error_messages import ERROR_DATABASE, ERROR_NOT_FOUND
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect
from sqlalchemy.orm.interfaces import ONETOMANY

class BaseRepository:
    model = None
    schema_out = None
    schema_out_detail = None
    relationships: list = []

    # ----------------- Helpers internos -----------------
    @classmethod
    def _paginate(cls, query, page: int = 0, page_size: int = 0):
        """
        Aplica paginación y devuelve (total, query_paginada).
        Si page o page_size son 0/None, devuelve (total, query_original).
        """
        # Siempre contamos primero (requerido para el frontend)
        total = query.count()

        # Ordenamiento por defecto (si no tiene order_by previo)
        # Esto evita resultados aleatorios en Postgres
        if hasattr(cls.model, "id") and not query._order_by_clauses:
            query = query.order_by(cls.model.id.desc())

        if page and page > 0 and page_size and page_size > 0:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
        
        return total, query
    
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
        """
        Aplica relaciones al query. Soporta dos formatos en cls.relationships:
        1. Listas/Tuplas: [User.roles, Role.permissions] -> Genera selectinload en cadena.
        2. SQLAlchemy Options: selectinload(User.roles).selectinload(Role.permissions) -> Se aplica directo.
        """
        for item in cls.relationships:
            # CASO 1: Es una lista o tupla (Tu lógica original "automática")
            if isinstance(item, (list, tuple)):
                if not item:
                    continue
                # Iniciamos la cadena con el primer elemento
                option = selectinload(item[0])
                # Encadenamos el resto
                for rel in item[1:]:
                    option = option.selectinload(rel)
                query = query.options(option)
            
            # CASO 2: Es una opción directa de SQLAlchemy (Estrategia Avanzada)
            # Esto permite pasar 'selectinload(User.roles).selectinload(Role.permissions)'
            # o incluso 'joinedload(User.profile)'
            else:
                query = query.options(item)
                
        return query

    @staticmethod
    def _normalize_data(obj_data) -> Dict[str, Any]:
        """Convierte obj_data a dict (compatible con Pydantic u dict normal)"""
        if obj_data is None:
            return {}
        # Soporte para Pydantic V2
        if hasattr(obj_data, "model_dump"):
            return obj_data.model_dump(exclude_unset=True)
            
        # Soporte Legacy / Pydantic V1
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
            raise AppException(detail=detail)
        if match and "already exists" in error_msg:
            field_name = match.group(1)
            detail = f"Ya existe un registro con el campo '{field_name}' igual a los datos proporcionados."
            raise AppException(detail=detail)
        if "update or delete on table" in error_msg and "violates foreign key constraint" in error_msg:
            match_table = re.search(r'on table "(.*?)"', error_msg)
            table_name = match_table.group(1) if match_table else "otra entidad"            
            detail = f"No se puede eliminar el registro porque está siendo utilizado en '{table_name}'."
            raise AppException(detail=detail)

        match_fk = re.search(r'Key \((.*?)\)=\((.*?)\) is not present in table', error_msg)
        if match_fk:
            field_name = match_fk.group(1)
            value = match_fk.group(2)
            raise AppException(detail=f"El valor '{value}' para '{field_name}' no existe.")

        match_dup = re.search(r'Key \((.*?)\)=\((.*?)\) already exists', error_msg)
        if match_dup:
            field_name = match_dup.group(1)
            value = match_dup.group(2)
            raise AppException(detail=f"Ya existe un registro con {field_name}='{value}'.")
        raise AppException(detail="Error de integridad de datos en la base de datos.")

    # ----------------- CRUD Genérico -----------------
    @classmethod
    def get_all(cls, session, only_active: bool = True, detailed: bool = False, **kwargs):
        """Trae todos los objetos (Implementación Base)"""
        query = session.query(cls.model)
            
        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        
        page = kwargs.get('page', 0)
        page_size = kwargs.get('page_size', 0)
        
        total, query = cls._paginate(query, page, page_size)
        
        items = cls._execute_read_query(query, detailed)
        
        if page:
            return total, items
        return items

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

            return cls.schema_out_detail.model_validate(obj)

        except Exception as e:
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def create(cls, session, obj_data=None, created_by=None):
        """Crea un objeto"""
        try:
            data = cls._normalize_data(obj_data)
            
            if created_by is not None and hasattr(cls.model, "created_by"):
                data["created_by"] = created_by

            obj = cls.model(**data)
            session.add(obj)
            session.flush()  # flush para obtener ID antes de commit
            session.refresh(obj)
            schema_to_use = cls.schema_out_detail or cls.schema_out
            return schema_to_use.model_validate(obj) if schema_to_use else obj

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
            schema_to_use = cls.schema_out_detail or cls.schema_out
            return schema_to_use.model_validate(obj) if schema_to_use else obj

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def delete(cls, session, obj_id: int, force: bool = False) -> Dict[str, str]:
        """
        Intenta eliminar un objeto físicamente.
        
        Comportamiento:
        1. Intenta borrar el registro (validando dependencias si force=False).
        2. Si hay dependencias (Error de Integridad o Validación):
           - Si el modelo tiene campo 'active', realiza un Soft Delete (Deshabilitar).
           - Si no tiene campo 'active', lanza el error original.
           
        Returns:
            Dict con claves 'action' ('deleted' | 'disabled') y 'message'.
        """
        obj = session.get(cls.model, obj_id)
        if not obj:
            raise NotFoundException(detail=f"{cls.model.__name__} no encontrado.")

        try:
            if not force:
                mapper = inspect(cls.model)
                for rel in mapper.relationships:
                    if rel.direction == ONETOMANY:
                        # Verificamos si hay hijos en memoria o cargados
                        related_items = getattr(obj, rel.key)
                        if related_items:
                            rel_name = rel.key.replace('_', ' ').capitalize()
                            # Lanzamos excepción para caer en el bloque except y deshabilitar
                            raise AppException(detail=f"Dependencias detectadas en {rel_name}")

            # 2. Borrado y Flush (Aquí salta la Defensa Reactiva de la DB si hay FK ocultas)
            session.delete(obj)
            session.flush()
            
            return {
                "action": "deleted"
            }

        except (IntegrityError, AppException) as e:
            # --- FALLBACK: SOFT DELETE (DESHABILITAR) ---
            session.rollback() # Importante: Limpiar el intento fallido de delete
            
            # Verificamos si el modelo soporta 'active' (Soft Delete)
            if hasattr(obj, 'active'):
                obj.active = False
                session.add(obj)
                session.flush()
                session.refresh(obj)
                
                return {
                    "action": "disabled"
                }
            
            # Si no soporta 'active', no nos queda otra que fallar con el error original
            if isinstance(e, IntegrityError):
                cls._handle_integrity_error(e) # Esto lanza AppException
            raise e # Relanzamos AppException original

        except Exception as e:
            session.rollback()
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
            
            # Mapa de existentes: { 2: ObjetoORM, 5: ObjetoORM }
            # Convertimos la clave a string para evitar problemas de tipos (2 vs "2")
            existing = {str(getattr(c, key_attr)): c for c in children}

            for item in items:
                # Obtenemos la clave del item entrante y la convertimos a string
                raw_key = getattr(item, key_attr)
                key = str(raw_key)
                
                if key in existing:
                    # UPDATE: El hijo ya existe
                    child_obj = existing[key]
                    for attr, value in item.dict().items():
                        setattr(child_obj, attr, value)
                    
                    # [FIX CRITICO]: Forzamos a la sesión a ver el cambio
                    session.add(child_obj)
                else:
                    # CREATE: Es nuevo
                    child = create_fn(item)
                    children.append(child)
                    session.add(child) # Aseguramos agregar
            
            # Flush para enviar cambios a la DB
            session.flush()
            
            # Refrescamos el padre para ver los cambios reflejados
            session.refresh(parent)
        
        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)

        except Exception as e:
            session.rollback()
            if isinstance(e, AppException):
                raise e
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))