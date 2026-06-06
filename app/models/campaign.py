
from app.models.base_model import BaseModelDB
from sqlalchemy import Boolean, Column, ForeignKey, String,Integer, UniqueConstraint
from sqlalchemy.orm import relationship


class Campaign(BaseModelDB):
    __tablename__ = "campaign"
    __table_args__ = (
        UniqueConstraint('name', 'workspace_id', name='uq_campaign_name_workspace'),
    )
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_public = Column(Boolean, default=True, nullable=False)

    leads = relationship("Lead", back_populates="campaign")

    workspace_id = Column(Integer, ForeignKey("workspace.id"), nullable=False)
    workspace = relationship("Workspace", back_populates="campaigns")

    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False)
    organization = relationship("Organization", foreign_keys=[organization_id])

    lead_flow_id = Column(Integer, ForeignKey("lead_flow.id"), nullable=False) 
    lead_flow = relationship("LeadFlow", back_populates="campaigns")

    team_access = relationship("TeamCampaignAccess", back_populates="campaign", cascade="all, delete-orphan")