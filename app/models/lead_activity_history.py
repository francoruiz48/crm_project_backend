from app.db.base_sql import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB

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