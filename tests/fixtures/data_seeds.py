import pytest
from app.models.lead_field_type import LeadFieldType
from app.models.lead_field import LeadField
from app.models.campaign import Campaign
from app.models.workspace import Workspace
from app.models.organization import Organization

@pytest.fixture(scope="function")
def initial_structure(db_session):
    org = Organization(name="Test org", description="Testing")
    db_session.add(org)
    db_session.flush()

    ws = Workspace(name="Test WS", description="Testing", organization_id=org.id)
    db_session.add(ws)
    db_session.flush()

    camp = Campaign(name="Test Campaign", workspace_id=ws.id, organization_id=org.id)
    db_session.add(camp)
    db_session.flush()
    
    db_session.commit()
    return {"campaign": camp, "workspace": ws, "organization": org}


@pytest.fixture(scope="function")
def initial_fields(db_session, initial_structure):
    camp_id = initial_structure["campaign"].id
    org_id = initial_structure["organization"].id
    
    # Asegúrate de usar valores correctos para required y types que ya existen en DB (por run_seeds)
    f_nombre = LeadField(
        name="Nombre", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        required=True, 
        order=1, 
        lead_field_section_id=1,
        organization_id=org_id
    )
    f_edad = LeadField(
        name="Edad", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        required=False, 
        order=2, 
        lead_field_section_id=1,
        organization_id=org_id
    )
    
    db_session.add_all([f_nombre, f_edad])
    db_session.commit()
    
    return {"nombre": f_nombre, "edad": f_edad, "campaign_id": camp_id}