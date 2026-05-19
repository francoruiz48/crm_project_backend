from app.db.base_sql import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr

class SystemAuditLog(Base):
    __tablename__ = "system_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=True, index=True)
    
    # Qué tabla se modificó (ej: 'Campaign', 'Workspace')
    entity_type = Column(String, nullable=False, index=True) 
    # El ID del registro modificado
    entity_id = Column(Integer, nullable=False, index=True)
    
    # 'CREATE', 'UPDATE', 'DELETE'
    action = Column(String, nullable=False)
    
    # Aquí guardamos la magia: {"name": {"old": "Camp A", "new": "Camp B"}}
    changes = Column(JSONB, nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    @declared_attr
    def creator(cls):
        return relationship("User", primaryjoin="User.id == %s.created_by" % cls.__name__, foreign_keys=[cls.created_by], viewonly=True)