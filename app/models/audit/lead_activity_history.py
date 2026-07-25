from app.db.base_sql import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

class LeadActivityHistory(Base):
    __tablename__ = "lead_activity_history"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("lead.id", ondelete="CASCADE"), nullable=False, index=True)

    # 'FIELD_UPDATED', 'NOTE_ADDED', 'EMAIL_SENT', 'FILE_UPLOADED'
    activity_type = Column(String, nullable=False, index=True)

    # Detalles específicos de la acción
    # Ej: {"field_id": 85, "field_name": "Sueldo", "old_value": "1000", "new_value": "2000"}
    details = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    # Este modelo no hereda de BaseModelDB (no tiene updated_at/updated_by, es solo-inserción),
    # así que no recibe la relación "creator" que BaseModelDB provee automáticamente a los
    # demás modelos. Se agrega acá a mano para que el frontend pueda mostrar el nombre de quien
    # generó el evento, en vez de solo el id crudo (created_by).
    creator = relationship("User", primaryjoin="User.id == LeadActivityHistory.created_by",
                            foreign_keys=[created_by], uselist=False, viewonly=True)