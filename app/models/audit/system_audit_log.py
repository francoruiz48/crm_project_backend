import uuid
from app.db.base_sql import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr

class SystemAuditLog(Base):
    __tablename__ = "system_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    # Bug real encontrado 2026-08-01 (ver backend/AGENTS.md): este modelo nunca extendió
    # BaseModelDB (no tiene updated_at/active/updated_by, tiene sentido para un log append-
    # only), pero tampoco tenía esta columna -- y SystemAuditLogResponse.id sí declaraba
    # `validation_alias="public_uuid"` (mismo patrón que el resto de la API, Fase 1-3). Sin
    # esta columna, CUALQUIER llamada real a GET /audit-logs/ rompía con ResponseValidationError
    # (Pydantic no encontraba `public_uuid` en la fila y caía al `id` interno, int, donde el
    # schema esperaba str). Agregado ahora, mismo criterio que BaseModelDB.public_uuid.
    # OJO PARA EL PRÓXIMO AGENTE / DEPLOY: este proyecto no usa Alembic, solo
    # `Base.metadata.create_all()` al arrancar -- eso crea tablas nuevas pero NO agrega
    # columnas a tablas ya existentes. Antes de deployar este cambio a producción hace falta
    # correr manualmente:
    #   ALTER TABLE system_audit_log ADD COLUMN public_uuid VARCHAR(36);
    #   UPDATE system_audit_log SET public_uuid = gen_random_uuid()::text WHERE public_uuid IS NULL;
    #   ALTER TABLE system_audit_log ALTER COLUMN public_uuid SET NOT NULL;
    #   CREATE UNIQUE INDEX ix_system_audit_log_public_uuid ON system_audit_log (public_uuid);
    # Hasta que eso corra en la DB de producción, el endpoint sigue roto ahí aunque el código
    # ya esté arreglado.
    public_uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=True, index=True)
    
    # Qué tabla se modificó (ej: 'Campaign', 'Workspace')
    entity_type = Column(String, nullable=False, index=True)
    # El ID interno del registro modificado (uso interno del backend, nunca se expone al
    # front -- ver entity_uuid abajo, mismo criterio que BaseModelDB.id/public_uuid).
    entity_id = Column(Integer, nullable=False, index=True)
    # public_uuid de la entidad auditada, para poder exponerla al front sin filtrar el id
    # interno. Nullable porque es polimórfico (entity_type define la tabla real) y no hay
    # una FK real que la DB pueda validar. Agregado al encontrar que `_log_audit` insertaba
    # el uuid directo en `entity_id` (columna Integer) para CREATE/UPDATE -- ver
    # backend/AGENTS.md §18-ter.
    entity_uuid = Column(String(36), nullable=True, index=True)
    
    # 'CREATE', 'UPDATE', 'DELETE'
    action = Column(String, nullable=False)
    
    # Aquí guardamos la magia: {"name": {"old": "Camp A", "new": "Camp B"}}
    changes = Column(JSONB, nullable=True) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    @declared_attr
    def creator(cls):
        return relationship("User", primaryjoin="User.id == %s.created_by" % cls.__name__, foreign_keys=[cls.created_by], viewonly=True)