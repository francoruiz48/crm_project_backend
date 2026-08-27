from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_sql import Base


class RefreshToken(Base):
    """
    Tokens de refresco almacenados en DB.
    Se guarda el token hasheado para mayor seguridad.
    """
    __tablename__ = "refresh_token"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)

    user = relationship("User", foreign_keys=[user_id])
