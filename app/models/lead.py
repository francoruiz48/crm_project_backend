
from app.models.base_model import BaseModelDB
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.models.tag import lead_tag_association

class Lead(BaseModelDB):
    __tablename__ = "lead"

    campaign_id = Column(Integer, ForeignKey("campaign.id"), nullable=False)
    campaign = relationship("Campaign", back_populates="leads")
    field_values = relationship("LeadFieldValue", back_populates="lead", cascade="all, delete-orphan")
    comments = relationship("LeadComment", back_populates="lead", cascade="all, delete-orphan")

    picture_url = Column(String, nullable=True)

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])

    current_state_id = Column(Integer, ForeignKey("lead_state.id"), nullable=True)
    current_state = relationship("LeadState", foreign_keys=[current_state_id])

    contact_state_id = Column(Integer, ForeignKey("lead_contact_state.id"), nullable=True)
    contact_state = relationship("LeadContactState", back_populates="leads", foreign_keys=[contact_state_id])

    state_history = relationship(
        "LeadStateHistory", 
        back_populates="lead", 
        cascade="all, delete-orphan"
    )

    team_id = Column(Integer, ForeignKey("team.id", ondelete="SET NULL"), nullable=True)
    team = relationship("Team", foreign_keys=[team_id])

    assigned_to_user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    assigned_to_user = relationship("User", foreign_keys=[assigned_to_user_id])

    tags = relationship("Tag", secondary=lead_tag_association, back_populates="leads")

    

    
