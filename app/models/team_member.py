from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class TeamMember(BaseModelDB):
    __tablename__ = "team_member"

    team_id = Column(Integer, ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    
    # Roles: 'MANAGER' (Ve todo, reasigna, configura) o 'AGENT' (Vendedor normal)
    role = Column(String, nullable=False, default="AGENT")

    team = relationship("Team", back_populates="members", foreign_keys=[team_id])
    user = relationship("User", foreign_keys=[user_id])