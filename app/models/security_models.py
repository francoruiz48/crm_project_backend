from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

# Tabla intermedia: Muchos Roles tienen Muchos Permisos
role_permissions = Table(
    'role_permissions',
    BaseModelDB.metadata,
    Column('role_id', Integer, ForeignKey('role.id'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permission.id'), primary_key=True)
)

class Permission(BaseModelDB):
    __tablename__ = "permission"
    # Ej: name="Crear Lead", codename="lead:create"
    name = Column(String, nullable=False)
    codename = Column(String, unique=True, nullable=False)

class Role(BaseModelDB):
    __tablename__ = "role"
    # Ej: name="Vendedor", code="sales_agent"
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)
    
    # Relación M2M con Permisos
    permissions = relationship("Permission", secondary=role_permissions, backref="roles")

class User(BaseModelDB):
    __tablename__ = "user"
    
    email = Column(String, unique=True, index=True, nullable=False)
    # ... otros campos (password, etc) ...
    
    role_id = Column(Integer, ForeignKey("role.id"), nullable=True)
    role = relationship("Role", backref="users", foreign_keys=[role_id])

    @property
    def permission_codenames(self):
        if not self.role:
            return []
        return [p.codename for p in self.role.permissions]