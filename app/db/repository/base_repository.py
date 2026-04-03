import re
from typing import Dict, Any, Optional
from math import ceil
from sqlalchemy.orm import selectinload
from app.core.exceptions.exceptions import AppException, NotFoundException
from app.core.error_messages import ERROR_DATABASE, ERROR_NOT_FOUND
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, inspect, or_
from app.core.context import TENANT_ORG_ID
from app.core.security import UserContext

class BaseRepository:
    model = None
    schema_out = None
    schema_out_detail = None
    relationships: list = []

    # ===============================================================
    # Inyección automática de Tenant (Multi-empresa)
    # ===============================================================
    @classmethod
    def _apply_tenant_filter(cls, query, is_read_operation: bool = True):
        """
        is_read_operation:
          - True (Lectura): Trae registros del tenant actual O globales (NULL).
          - False (Escritura): Trae SOLO registros del tenant actual (protege los globales).
        """
        if hasattr(cls.model, "organization_id"):
            org_id = TENANT_ORG_ID.get()
            
            # Si hay un tenant activo en el contexto
            if org_id is not None:
                if is_read_operation:
                    # LECTURA: Ve los suyos O los del sistema (NULL)
                    query = query.filter(
                        or_(
                            cls.model.organization_id == org_id,
                            cls.model.organization_id.is_(None)
                        )
                    )
                else:
                    # ESCRITURA: Solo puede tocar los suyos. (Excluye los NULL)
                    query = query.filter(cls.model.organization_id == org_id)
                    
        return query

    # ----------------- Helpers internos -----------------
    @classmethod
    def apply_security_filter(cls, session, query, user_context: UserContext):
        """
        MÉTODO HOOK (Template Method).
        Los repositorios hijos deben sobrescribir este método para inyectar 
        su lógica de seguridad específica (La Bóveda).
        Por defecto, devuelve la query intacta.
        """
        return query
    
    @classmethod
    def _paginate(cls, query, page: int = 0, page_size: int = 0):
        """
        Aplica paginación y devuelve (total, query_paginada).
        Si page o page_size son 0/None, devuelve (total, query_original).
        """
        total = query.count()

        if page_size > 0:
            total_pages = ceil(total / page_size)
        else:
            total_pages = 0

        if page> total_pages and total_pages > 0:
            page = total_pages

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
    def get_all(cls, session, user_context: Optional[UserContext] = None, only_active: bool = True, detailed: bool = False, base_query=None, **kwargs):
        """
        Trae todos los objetos con filtros dinámicos.
        Cualquier argumento extra (ej: campaign_id=1) se aplica como filtro "=" 
        si el modelo tiene ese atributo.
        """

        query = base_query if base_query is not None else session.query(cls.model)

        query = cls.apply_security_filter(session, query, user_context)

        query = cls._apply_tenant_filter(query)
            
        # 1. Filtro 'active' (Soft Delete)
        if only_active and hasattr(cls.model, "active"):
            query = query.filter(cls.model.active.is_(True))

        # 2. Filtros Dinámicos (kwargs)
        # Extraemos page/page_size primero para no confundirlos con columnas
        page = kwargs.pop('page', 0)
        page_size = kwargs.pop('page_size', 0)

        #Parametros de ordenamiento
        order_by = kwargs.pop('order_by', None)
        ascending = kwargs.pop('ascending', True)

        # Extraemos parámetros especiales de búsqueda
        search_query = kwargs.pop('search', None)
        search_fields = kwargs.pop('search_fields', [])

        for key, value in kwargs.items():
            if value is None:
                continue

            # Verificamos si la clave tiene el sufijo magico "__ilike"
            if "__ilike" in key:
                field_name = key.replace("__ilike", "") # Obtenemos el nombre real del campo
                print("ENTRE")
                if hasattr(cls.model, field_name):
                    column = getattr(cls.model, field_name)
                    # Aplicamos ilike con % automático para que sea "contiene"
                    query = query.filter(column.ilike(f"%{value}%"))
            
            # Comportamiento normal (Igualdad exacta)
            elif hasattr(cls.model, key):
                query = query.filter(getattr(cls.model, key) == value)

        # Lógica para Búsqueda Global (OR)
        if search_query and search_fields:
            search_conditions = []
            for field in search_fields:
                if hasattr(cls.model, field):
                    column = getattr(cls.model, field)
                    # Preparamos la condición ILIKE
                    search_conditions.append(column.ilike(f"%{search_query}%"))
            
            # Si encontramos campos válidos, aplicamos un OR (uno u otro)
            if search_conditions:
                query = query.filter(or_(*search_conditions))

        if order_by and hasattr(cls.model, order_by):
            column = getattr(cls.model, order_by)
            # Aplicamos asc() o desc() según el flag
            query = query.order_by(column.asc() if ascending else column.desc())
        elif hasattr(cls.model, 'id'):
                query = query.order_by(cls.model.id.desc())

        # 3. Paginación y Ejecución
        total, query = cls._paginate(query, page, page_size)
        items = cls._execute_read_query(query, detailed)
        
        if page:
            return total, items
        return items

    @classmethod
    def get_by_id(cls, session, obj_id: int, user_context: Optional[UserContext] = None, only_active: bool = False, detailed: bool = False):
        """
        Trae un objeto por id. 
        Si detailed=True, carga relaciones y usa schema_out_detail.
        """
        try:

            query = session.query(cls.model)

            query = cls.apply_security_filter(session, query, user_context)

            query = cls._apply_tenant_filter(query)

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
    def create(cls, session, obj_data=None, user_context: Optional[UserContext] = None,):
        """Crea un objeto"""
        try:
            created_by = None
            is_super_admin = False
            is_owner = False
            
            if user_context is not None:
                created_by = user_context.user.id
                is_super_admin = user_context.is_superuser
                is_owner = user_context.is_owner

            data = cls._normalize_data(obj_data)
            
            if hasattr(cls.model, "organization_id"):
                org_id = TENANT_ORG_ID.get()
                if org_id is not None:
                    data["organization_id"] = org_id
            
            if created_by is not None and hasattr(cls.model, "created_by"):
                data["created_by"] = created_by

            obj = cls.model(**data)
            session.add(obj)
            session.flush()  # flush para obtener ID antes de commit
            session.refresh(obj)
            return cls.schema_out_detail.model_validate(obj)

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def update(cls, session, obj_id: int, obj_data, user_context: Optional[UserContext] = None,):
        """Actualiza un objeto por id"""
        try:
            updated_by = None
            is_super_admin = False
            is_owner = False
            
            if user_context is not None:
                updated_by = user_context.user.id
                is_super_admin = user_context.is_superuser
                is_owner = user_context.is_owner

            data = cls._normalize_data(obj_data)
            query = session.query(cls.model).filter(cls.model.id == obj_id)
            # PASAMOS FALSE: Para asegurar que no pueda editar un registro global (NULL)
            query = cls._apply_tenant_filter(query, is_read_operation=False)
            obj = query.first()
            if not obj:
                return None
            
            if updated_by is not None and hasattr(cls.model, "updated_by"):
                data["updated_by"] = updated_by

            # IMPORTANTE: Prevenir que el usuario transfiera objetos a otra organización
            if "organization_id" in data:
                del data["organization_id"]

            for key, value in data.items():
                setattr(obj, key, value)

            session.flush()
            session.refresh(obj)
            return cls.schema_out_detail.model_validate(obj)

        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)
            
        except Exception as e:
            session.rollback()
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))

    @classmethod
    def delete(cls, session, obj_id: int, user_context: Optional[UserContext] = None,) -> Dict[str, str]:
        """
        Intenta eliminar un objeto físicamente.
        
        Comportamiento:
        Si hay dependencias (Error de Integridad o Validación):
           - Si el modelo tiene campo 'active', realiza un Soft Delete (Deshabilitar).
           - Si no tiene campo 'active', lanza el error original.
           
        Returns:
            Dict con claves 'action' ('deleted' | 'disabled') y 'message'.
        """

        updated_by = None
        is_super_admin = False
        is_owner = False
        
        if user_context is not None:
            updated_by = user_context.user.id
            is_super_admin = user_context.is_superuser
            is_owner = user_context.is_owner

        query = session.query(cls.model).filter(cls.model.id == obj_id)
        # PASAMOS FALSE: Para asegurar que no pueda editar un registro global (NULL)
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        obj = query.first()

        if not obj:
            raise NotFoundException(detail=f"{cls.model.__name__} no encontrado.")
        

        try:
            with session.begin_nested():
                session.delete(obj)
                session.flush()
            
            return {
                "action": "deleted"
            }

        except (IntegrityError, AppException) as e:            
            obj_fresh = session.get(cls.model, obj_id)
            # Verificamos si el modelo soporta 'active' (Soft Delete)
            if obj_fresh and hasattr(obj_fresh, 'active'):
                obj_fresh.active = False
                if updated_by is not None and hasattr(cls.model, "updated_by"):
                    obj_fresh.updated_by = updated_by

                session.add(obj_fresh)
                session.flush()
                session.refresh(obj_fresh)
                
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
        try:
            # 1. Buscar al padre aplicando Tenant Filter
            parent_query = session.query(parent_model).filter(parent_model.id == parent_id)
            if hasattr(parent_model, "organization_id"):
                org_id = TENANT_ORG_ID.get()
                if org_id is not None:
                    parent_query = parent_query.filter(parent_model.organization_id == org_id)
            
            parent = parent_query.first()
            
            if not parent:
                raise NotFoundException(
                    detail=ERROR_NOT_FOUND.format(
                        model=parent_model.__name__, id=parent_id
                    )
                )

            children = getattr(parent, relation_name)
            
            existing = {str(getattr(c, key_attr)): c for c in children}

            for item in items:
                raw_key = getattr(item, key_attr)
                key = str(raw_key)
                
                # OJO: Aquí NO inyectamos el tenant al crear el hijo de forma automática, 
                # porque create_fn (lambda) o la relación de SQLAlchemy se encargará 
                # de propagar el organization_id / parent_id según cómo esté mapeado.
                
                if key in existing:
                    child_obj = existing[key]
                    
                    item_dict = item.dict()
                    if "organization_id" in item_dict:
                        del item_dict["organization_id"]

                    for attr, value in item_dict.items():
                        setattr(child_obj, attr, value)
                    
                    session.add(child_obj)
                else:
                    child = create_fn(item)
                    children.append(child)
                    session.add(child) 
            
            session.flush()
            session.refresh(parent)
        
        except IntegrityError as e:
            session.rollback()
            cls._handle_integrity_error(e)

        except Exception as e:
            session.rollback()
            if isinstance(e, AppException):
                raise e
            raise AppException(detail=ERROR_DATABASE.format(error=str(e)))
        
    @classmethod
    def bulk_delete(cls, session, obj_ids: list[int], user_context: Optional[UserContext] = None) -> Dict[str, list]:
        """
        Elimina masivamente un listado de IDs.
        Aplica la misma lógica de Soft Delete que la eliminación individual en caso de fallo.
        """
        updated_by = None
        if user_context is not None and user_context.user is not None:
            updated_by = user_context.user.id

        # 1. Buscamos los objetos que realmente existen y le pertenecen a la empresa
        query = session.query(cls.model).filter(cls.model.id.in_(obj_ids))
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        objs = query.all()

        results = {"deleted": [], "disabled": [], "failed": []}

        # 2. Separar los que no se encontraron (o no tienen permisos)
        valid_ids = [obj.id for obj in objs]
        for requested_id in obj_ids:
            if requested_id not in valid_ids:
                results["failed"].append(requested_id)

        if not objs:
            return results

        # 3. Iteramos aplicando transacciones anidadas (Savepoints)
        for obj in objs:
            obj_id = obj.id
            try:
                # begin_nested() crea un SAVEPOINT. Si falla, hace rollback SOLO de este objeto.
                with session.begin_nested():
                    session.delete(obj)
                    session.flush()
                results["deleted"].append(obj_id)

            except (IntegrityError, AppException) as e:
                # Ocurrió un error (ej: FK restrict). Intentamos Soft Delete.
                obj_fresh = session.get(cls.model, obj_id)
                if obj_fresh and hasattr(obj_fresh, 'active'):
                    obj_fresh.active = False
                    if updated_by is not None and hasattr(cls.model, "updated_by"):
                        obj_fresh.updated_by = updated_by

                    session.add(obj_fresh)
                    session.flush()
                    session.refresh(obj_fresh)
                    results["disabled"].append(obj_id)
                else:
                    results["failed"].append(obj_id)

        return results
    

    @classmethod
    def bulk_set_active(cls, session, obj_ids: list[int], user_context: Optional[UserContext] = None) -> Dict[str, list]:
        """
        Activa masivamente un listado de IDs.
        """
        updated_by = None
        if user_context is not None and user_context.user is not None:
            updated_by = user_context.user.id

        results = {"activated": [], "already_active": [], "failed": []}

        # Verificamos tempranamente si el modelo soporta la columna 'active'
        if not hasattr(cls.model, 'active'):
            results["failed"] = obj_ids
            return results

        # Buscamos los objetos aplicando el filtro de la empresa
        query = session.query(cls.model).filter(cls.model.id.in_(obj_ids))
        query = cls._apply_tenant_filter(query, is_read_operation=False)
        objs = query.all()

        # Separar los que no se encontraron
        valid_ids = [obj.id for obj in objs]
        for requested_id in obj_ids:
            if requested_id not in valid_ids:
                results["failed"].append(requested_id)

        if not objs:
            return results

        # Iteramos con transacciones anidadas
        for obj in objs:
            obj_id = obj.id
            try:
                with session.begin_nested():
                    # Si ya está activo, no hacemos nada y lo informamos
                    if getattr(obj, 'active') is True:
                        results["already_active"].append(obj_id)
                    else:
                        obj.active = True
                        if updated_by is not None and hasattr(cls.model, "updated_by"):
                            obj.updated_by = updated_by
                        
                        session.add(obj)
                        session.flush()
                        results["activated"].append(obj_id)

            except Exception as e:
                # Si por algún motivo de base de datos falla la actualización
                results["failed"].append(obj_id)

        return results