from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

role_permissions = Table(
    'role_permissions',
    BaseModelDB.metadata,
    Column('role_id', Integer, ForeignKey('role.id'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permission.id'), primary_key=True)
)

user_roles = Table(
    'user_roles',
    BaseModelDB.metadata,
    Column('users_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('role.id'), primary_key=True)
)

class Permission(BaseModelDB):
    __tablename__ = "permission"
    name = Column(String, nullable=False)
    codename = Column(String, unique=True, nullable=False)

class Role(BaseModelDB):
    __tablename__ = "role"
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)
    
    permissions = relationship("Permission", secondary=role_permissions, backref="roles")

class User(BaseModelDB):
    __tablename__ = "users"
    
    email = Column(String, unique=True, index=True, nullable=False)
    
    roles = relationship("Role", secondary=user_roles, backref="users")

    @property
    def permissions(self):
        if not self.roles:
            return []
        
        # Usamos un set para evitar duplicados si dos roles tienen el mismo permiso
        perms = set()
        for role in self.roles:
            for perm in role.permissions:
                perms.add(perm.codename)
                
        return list(perms)
    
    @property
    def permission_objects(self):
        """
        Devuelve la lista de OBJETOS Permission.
        """
        print(f"DEBUG: Accediendo a permission_objects para User {self.id}")
        
        if not self.roles:
            print("DEBUG: No hay roles cargados en self.roles")
            return []
        
        print(f"DEBUG: Roles encontrados: {[r.code for r in self.roles]}")
        
        unique_perms = {}
        for role in self.roles:
            # Imprimimos cuántos permisos tiene cada rol en memoria
            print(f"DEBUG: Rol {role.code} tiene {len(role.permissions)} permisos")
            for perm in role.permissions:
                unique_perms[perm.codename] = perm
                
        results = list(unique_perms.values())
        print(f"DEBUG: Total permisos únicos encontrados: {len(results)}")
        return results