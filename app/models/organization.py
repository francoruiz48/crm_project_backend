
from app.models.base_model import BaseModelDB
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class Organization(BaseModelDB):
    __tablename__ = "organization"
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    require_lead_state_notes = Column(Boolean, default=False)

    users_access = relationship(
        "UserOrganization", 
        foreign_keys="[UserOrganization.organization_id]", 
        back_populates="organization", 
        cascade="all, delete-orphan"
    )
