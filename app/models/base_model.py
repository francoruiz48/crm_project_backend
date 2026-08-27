
import uuid
from app.db.base_sql import Base
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr

class BaseModelDB(Base):
    __abstract__ = True  # No se crea tabla

    id = Column(Integer, primary_key=True, index=True)  # Uso interno del backend, nunca se expone al front
    # Id público de la entidad: es lo único que el front conoce (ver base_schema.py, Fase 3).
    public_uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    @declared_attr
    def creator(cls):
        return relationship("User", primaryjoin="User.id == %s.created_by" % cls.__name__, foreign_keys=[cls.created_by], uselist=False, viewonly=True)

    @declared_attr
    def updater(cls):
        return relationship("User", primaryjoin="User.id == %s.updated_by" % cls.__name__, foreign_keys=[cls.updated_by], uselist=False, viewonly=True)

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.id})>"
