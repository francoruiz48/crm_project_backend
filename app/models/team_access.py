from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base_model import BaseModelDB

class TeamWorkspaceAccess(BaseModelDB):
    __tablename__ = "team_workspace_access"

    team_id = Column(Integer, ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    team = relationship("Team", back_populates="workspace_access")
    workspace = relationship("Workspace", back_populates="team_access")

class TeamCampaignAccess(BaseModelDB):
    __tablename__ = "team_campaign_access"

    team_id = Column(Integer, ForeignKey("team.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False)

    team = relationship("Team", back_populates="campaign_access")
    campaign = relationship("Campaign", back_populates="team_access")