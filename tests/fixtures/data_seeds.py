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
    
    # Hacemos commit para asegurar todo en la DB
    db_session.commit()
    
    # Retornamos un diccionario con IDs puros
    return {"campaign_id": camp.id, "workspace_id": ws.id, "org_id": org.id}

@pytest.fixture(scope="function")
def initial_fields(db_session, initial_structure):
    camp_id = initial_structure["campaign_id"]
    org_id = initial_structure["org_id"]
    
    f_nombre = LeadField(
        name="Nombre", 
        field_type_code="STRING", 
        campaign_id=camp_id, 
        required=True, 
        order=1, 
        lead_field_section_id=1, 
        organization_id=org_id,
        active=True
    )
    f_edad = LeadField(
        name="Edad", 
        field_type_code="INT", 
        campaign_id=camp_id, 
        required=False, 
        order=2, 
        lead_field_section_id=1, 
        organization_id=org_id,
        active=True
    )
    
    db_session.add_all([f_nombre, f_edad])
    db_session.commit()
    
    # Retornamos un diccionario con IDs puros
    return {"nombre_id": f_nombre.id, "edad_id": f_edad.id, "campaign_id": camp_id, "org_id": org_id}