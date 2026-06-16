from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

# Rol <-> Permisos
role_permissions = Table(
    'role_permissions',
    BaseModelDB.metadata,
    Column('role_id', Integer, ForeignKey('role.id', ondelete="CASCADE"), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permission.id', ondelete="CASCADE"), primary_key=True)
)

# Membresía (User+Org) <-> Múltiples Roles
user_organization_roles = Table(
    'user_organization_roles',
    BaseModelDB.metadata,
    Column('user_organization_id', Integer, ForeignKey('user_organization.id', ondelete="CASCADE"), primary_key=True),
    Column('role_id', Integer, ForeignKey('role.id', ondelete="CASCADE"), primary_key=True)
)

class Permission(BaseModelDB):
    __tablename__ = "permission"
    name = Column(String, nullable=False)
    codename = Column(String, unique=True, nullable=False)


class Role(BaseModelDB):
    __tablename__ = "role"
    name = Column(String, nullable=False)
    code = Column(String, nullable=False) 
    
    permissions = relationship("Permission", secondary=role_permissions, backref="roles")
    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=True)
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint('code', 'organization_id', name='uq_role_code_per_org'),
    )

class UserOrganization(BaseModelDB):
    """Representa la Membresía de un usuario en una organización."""
    __tablename__ = "user_organization"
    
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False)
    is_owner = Column(Boolean, default=False, nullable=False)

    user = relationship("User", foreign_keys=[user_id], back_populates="organizations_access")
    organization = relationship("Organization", foreign_keys=[organization_id], back_populates="users_access")
    
    roles = relationship("Role", secondary=user_organization_roles)

    __table_args__ = (
        UniqueConstraint('user_id', 'organization_id', name='uq_user_per_org'),
    )

    @property
    def permission_objects(self):
        """Agrupa los permisos de todos los roles que tiene en esta organización"""
        if not self.roles or not self.active:
            return []
            
        unique_perms = {}
        for role in self.roles:
            for perm in role.permissions:
                unique_perms[perm.codename] = perm
                
        return list(unique_perms.values())

class User(BaseModelDB):
    __tablename__ = "user"

    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # nullable para no romper seeds/tests existentes
    is_superuser = Column(Boolean, default=False)
    
    organizations_access = relationship("UserOrganization", foreign_keys="[UserOrganization.user_id]", back_populates="user", cascade="all, delete-orphan")

    def get_roles_for_org(self, org_id: int):
        """Obtiene la LISTA de roles del usuario para una org específica."""
        for access in self.organizations_access:
            if access.organization_id == org_id and access.active:
                return access.roles # Retorna la lista de roles
        return []

    def get_permissions(self, org_id: int) -> list[str]:
        """Devuelve lista de strings (codenames) válidos en esta org uniendo todos sus roles."""
        if self.is_superuser: return ["*"] 
        
        roles = self.get_roles_for_org(org_id)
        if not roles: return []
        
        perms = set()
        for role in roles:
            for perm in role.permissions:
                perms.add(perm.codename)
                
        return list(perms)